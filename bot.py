import os
import random

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from moderation import is_exempt_role, should_delete_message

load_dotenv()


def _parse_id_set(value: str) -> set[int]:
    return {int(v) for v in value.split(",") if v.strip()}


TOKEN = os.environ["DISCORD_BOT_TOKEN"]
MONITORED_CHANNEL_ID = int(os.environ["MONITORED_CHANNEL_ID"])
GUILD_ID = int(os.environ["GUILD_ID"])

# Users with any of these roles are allowed to post freely (includes the bot's own role)
EXEMPT_ROLE_IDS = _parse_id_set(os.environ["EXEMPT_ROLE_IDS"])

# The bot's own user ID — prevents it from acting on itself
BOT_ID = int(os.environ["BOT_ID"])

# These users will be banned but their messages will NOT be deleted
EXEMPT_USER_IDS = _parse_id_set(os.environ.get("EXEMPT_USER_IDS", ""))

# User to DM whenever a ban is issued
OWNER_ID = int(os.environ["OWNER_ID"])

# --- Intents ---
# Server Members and Message Content intents must also be enabled
# in the Discord Developer Portal under your bot's settings.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    if not post_random_number.is_running():
        post_random_number.start()


@tasks.loop(minutes=1)
async def post_random_number():
    try:
        channel = bot.get_channel(MONITORED_CHANNEL_ID)
        if channel is not None:
            await channel.send(str(random.randint(1, 66000)))
    except discord.HTTPException as e:
        print(f"Failed to post random number: {e}")


@bot.event
async def on_message(message: discord.Message):
    # Skip the bot itself
    if message.author.id == BOT_ID:
        return

    # DMs have no guild — ignore them
    if message.guild is None:
        return

    # Single-tenant safety net — ignore any other guild the bot might be in
    if message.guild.id != GUILD_ID:
        return

    # Only enforce rules in the monitored channel
    if message.channel.id != MONITORED_CHANNEL_ID:
        await bot.process_commands(message)
        return

    member = message.guild.get_member(message.author.id)
    if member is None:
        await bot.process_commands(message)
        return

    # Allow users with an exempt role to post freely (matched by role ID, not name)
    user_roles = {role.id for role in member.roles}
    if is_exempt_role(user_roles, EXEMPT_ROLE_IDS):
        await bot.process_commands(message)
        return

    # Delete the message unless the user is in the exempt users list.
    # Independent of the ban below so a delete failure can't suppress it.
    if should_delete_message(message.author.id, EXEMPT_USER_IDS):
        try:
            await message.delete()
        except discord.HTTPException as e:
            print(f"Failed to delete message from {member}: {e}")

    try:
        await message.guild.ban(
            member, reason="Posted in restricted channel without required role"
        )
        print(f"Banned {member} for posting in restricted channel")
        await notify_owner(
            f"Banned {member} ({member.id}) for posting in #{message.channel} without the required role."
        )
    except discord.Forbidden:
        print(f"Missing permissions to ban {member}")
    except discord.HTTPException as e:
        print(f"Failed to ban {member}: {e}")


async def notify_owner(content: str):
    owner = bot.get_user(OWNER_ID) or await bot.fetch_user(OWNER_ID)
    try:
        await owner.send(content)
    except discord.Forbidden:
        print(f"Could not DM owner {OWNER_ID} (DMs may be closed)")


if __name__ == "__main__":
    bot.run(TOKEN)
