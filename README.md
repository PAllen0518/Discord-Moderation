# BattleBorn Auto Ban Bot

Monitors a specific Discord channel and automatically bans any user who posts without an exempt role. Optionally skips message deletion for specified users while still banning them. Also posts a random integer to the monitored channel roughly once every 10 minutes.

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

Once connected, the bot starts a background loop that posts a random integer between 1 and 66,000 to `MONITORED_CHANNEL_ID` roughly once every 10 minutes for as long as the bot is running.

## Nickname Audit

`namecheck.py` is a separate command-line tool. Run it on your own PC; it doesn't touch the bot running on the server. It reads every member, checks their server nickname for a human name, and lets you time out the ones you confirm.

Each word (camelCase is split, so `GodlikeMike` is `Godlike` + `Mike`) is checked against an offline list of about 60,000 first names from the `gender-guesser` package. A nickname **matches** if it contains a standalone first name, e.g. `Tobias`, `BossSauce585 Tobias`, `Matt (Koda)`. It's **maybe** if the only name is glued into a handle (`GodlikeMike_001`, `tyson0796`), is also an everyday word (`Mark`, `Jay`, `King`), or uses non-ASCII letters. Otherwise it's **not match** (`AbsoluteIdiots`, `Asgorath`, `I eat paint`). A member with no server nickname is judged the same way on their display name. Rare names, misspellings and names run together in lowercase (`jacobbowers`) aren't recognized, so check `not_match.txt` and add real names to the allowlist.

1. `python namecheck.py scan` writes `match.txt`, `maybe.txt`, `not_match.txt` and `skipped.txt` (bots, the owner, administrators, exempt roles, and anyone at or above the bot's role) into `namecheck_output/scan_<date>_<time>/`.
2. Open the lists in Notepad. In `not_match.txt`, delete a line to spare someone; to add someone from `maybe.txt`, paste their line (or just their ID) into `not_match.txt`.
3. `python namecheck.py timeout` is a dry run that shows who would be timed out.
4. `python namecheck.py timeout --apply` asks you to type the count, then times them out for 28 days (`--days N` for 1-28). Anyone whose nickname now matches, who is allowlisted, or who is already timed out is skipped.
5. `python namecheck.py untimeout ID [ID...]` removes timeouts.
6. `python namecheck.py status` lists everyone currently timed out and when each timeout expires.

To protect members in advance, list them in `namecheck_allowlist.txt` (one user ID, username, display name or nickname per line; capitalization, emoji and punctuation are ignored when comparing names). They always count as a match and are never timed out.

The bot needs the **Timeout Members** permission (Server Settings -> Roles), and its role must be above the members it times out. `namecheck_output/` and `namecheck_allowlist.txt` are gitignored because they contain member data.

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
