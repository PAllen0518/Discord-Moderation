import random

import discord
from discord.ext import commands, tasks

# --- Configuration ---
# Replace these values with your own before running the bot.
TOKEN = "YOUR_BOT_TOKEN_HERE"
MONITORED_CHANNEL_ID = 123456789012345678  # ID of the channel to enforce bans in
GUILD_ID = 123456789012345678              # ID of your Discord server

# Users with any of these roles are allowed to post freely (includes the bot's own role)
EXEMPT_ROLE_IDS = {123456789012345678, 123456789012345678, 123456789012345678}

# The bot's own user ID — prevents it from acting on itself
BOT_ID = 123456789012345678

# These users will be banned but their messages will NOT be deleted
EXEMPT_USER_IDS = set()

# User to DM whenever a ban is issued
OWNER_ID = 123456789012345678

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
    channel = bot.get_channel(MONITORED_CHANNEL_ID)
    if channel is not None:
        await channel.send(str(random.randint(1, 66000)))


@bot.event
async def on_message(message: discord.Message):
    print(f"Message from {message.author} in #{message.channel}")

    # Ignore messages from other bots
    if message.author.bot:
        return

    # DMs have no guild — ignore them
    if message.guild is None:
        return

    # Only enforce rules in the monitored channel
    if message.channel.id != MONITORED_CHANNEL_ID:
        print(f"Ignoring channel {message.channel.id}, watching {MONITORED_CHANNEL_ID}")
        await bot.process_commands(message)
        return

    member = message.guild.get_member(message.author.id)
    if member is None:
        await bot.process_commands(message)
        return

    # Skip the bot itself
    if message.author.id == BOT_ID:
        return

    # Allow users with an exempt role to post freely (matched by role ID, not name)
    user_roles = {role.id for role in member.roles}
    if user_roles & EXEMPT_ROLE_IDS:
        await bot.process_commands(message)
        return

    try:
        # Delete the message unless the user is in the exempt users list
        if message.author.id not in EXEMPT_USER_IDS:
            await message.delete()
        await message.guild.ban(
            member, reason="Posted in restricted channel without required role"
        )
        print(f"Banned {member} for posting in restricted channel")
        await notify_owner(f"Banned {member} ({member.id}) for posting in #{message.channel} without the required role.")
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


bot.run(TOKEN)
