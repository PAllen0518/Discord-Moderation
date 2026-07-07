# BattleBorn Auto Ban Bot

Monitors a specific Discord channel and automatically bans any user who posts without an exempt role. Optionally skips message deletion for specified users while still banning them. Also posts a random integer to the monitored channel roughly once a minute.

## Requirements

- Python 3.8 or higher
- A Discord bot token

## Installation

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your values:
   ```
   DISCORD_BOT_TOKEN=your-bot-token
   MONITORED_CHANNEL_ID=your_channel_id
   GUILD_ID=your_server_id
   EXEMPT_ROLE_IDS=role_id_1,role_id_2  # include the bot's own role so it can't ban itself
   BOT_ID=your_bot_user_id
   EXEMPT_USER_IDS=user_id  # banned but messages not deleted; leave blank for none
   OWNER_ID=your_user_id    # DM'd whenever a ban is issued
   ```

3. Enable the following in the [Discord Developer Portal](https://discord.com/developers/applications) under your bot's **Bot** settings:
   - Server Members Intent
   - Message Content Intent

4. Invite the bot to your server with these permissions:
   - View Channels
   - Ban Members
   - Manage Messages (for message deletion)
   - Read Message History

   Use **OAuth2 → URL Generator** in the Developer Portal to generate an invite link.

5. In your server's role settings, make sure the bot's role is ranked **above** the roles of users it needs to ban.

## Running

```
python bot.py
```

The console logs startup, ban outcomes, and any delete/DM failures. It does not log every message the bot sees.

## Configuration Reference

| Variable | Description |
|---|---|
| `DISCORD_BOT_TOKEN` | Your bot's token from the Developer Portal |
| `MONITORED_CHANNEL_ID` | ID of the channel to enforce bans in |
| `GUILD_ID` | ID of your Discord server — messages from any other guild are ignored |
| `EXEMPT_ROLE_IDS` | Comma-separated role IDs allowed to post freely (matched against each member's role IDs, not role names) — include the bot's own role here |
| `BOT_ID` | Your bot's user ID |
| `EXEMPT_USER_IDS` | Comma-separated user IDs who get banned but keep their messages; leave blank for none |
| `OWNER_ID` | User DM'd with a notification whenever a ban occurs |

## Ban Notifications

When a ban occurs, the bot sends a DM to `OWNER_ID` with the banned user's name, ID, and channel. The owner must share at least one server with the bot for the DM to succeed — if DMs are closed, the bot logs a warning to the console instead.

## Random Number Posting

Once connected, the bot starts a background loop that posts a random integer between 1 and 66,000 to `MONITORED_CHANNEL_ID` roughly once a minute for as long as the bot is running.

## Getting IDs

Enable **Developer Mode** in Discord (Settings → Advanced → Developer Mode), then right-click any user, role, channel, or server to copy its ID.

## Development

Install dev dependencies and run tests/lint locally before pushing changes:

```
pip install -r requirements-dev.txt
pytest
ruff check .
```

CI runs the same two checks on every push and pull request to `main` (see `.github/workflows/ci.yml`).

## Suggested Member Disclosure

The bot reads every message posted in the monitored channel to check the poster's roles — it doesn't store or review message content. Consider pinning a note like this in the channel or your server rules:

> This channel is auto-moderated: anyone posting here without the required role will have their message removed and be banned automatically. Only role membership is checked.
