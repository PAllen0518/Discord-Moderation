import argparse
import asyncio
import functools
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import discord
from dotenv import load_dotenv

from moderation import is_exempt_role
from nickname_rules import (
    MATCH,
    MAX_TIMEOUT_DAYS,
    MAYBE,
    NOT_MATCH,
    allowlist_hits,
    classify_member,
    clean_shown,
    closeness,
    format_line,
    parse_allowlist,
    parse_list_entries,
    skip_reason,
    timeout_duration,
)

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "namecheck_output"
ALLOWLIST_FILE = BASE_DIR / "namecheck_allowlist.txt"

SKIPPED = "skipped"
TIMEOUT_REASON = "Server nickname doesn't include a human name (namecheck)"

PERMISSION_HELP = (
    'The bot is missing the "Timeout Members" permission.\n'
    'In Discord: Server Settings -> Roles -> the bot\'s role -> enable "Timeout Members",\n'
    "and make sure the bot's role is above the members it needs to time out."
)

LIST_HEADERS = {
    MATCH: "Members with a known first name in their nickname. Nothing happens to anyone here.",
    MAYBE: "Review these. To time someone out, cut their line and paste it into not_match.txt.",
    NOT_MATCH: (
        "'namecheck.py timeout --apply' times out everyone listed here.\n"
        "# Delete a line to spare someone; paste lines from maybe.txt to add people."
    ),
    SKIPPED: "Never timed out: bots, the owner, administrators, exempt roles, roles at or above the bot's.",
}


def load_config() -> tuple[str, int, set[int]]:
    load_dotenv(BASE_DIR / ".env")
    try:
        token = os.environ["DISCORD_BOT_TOKEN"]
        guild_id = int(os.environ["GUILD_ID"])
    except KeyError as missing:
        sys.exit(f"Missing {missing.args[0]} in .env")
    exempt_roles = {
        int(v) for v in os.environ.get("EXEMPT_ROLE_IDS", "").split(",") if v.strip()
    }
    return token, guild_id, exempt_roles


def timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def read_allowlist() -> list[str]:
    return parse_allowlist(read_text(ALLOWLIST_FILE)) if ALLOWLIST_FILE.exists() else []


def can_timeout(me: discord.Member) -> bool:
    perms = me.guild_permissions
    return perms.moderate_members or perms.administrator


def skip_for(member, guild, me, exempt_roles) -> str | None:
    return skip_reason(
        is_bot=member.bot,
        is_owner=member.id == guild.owner_id,
        is_admin=member.guild_permissions.administrator,
        has_exempt_role=is_exempt_role({r.id for r in member.roles}, exempt_roles),
        top_role_position=member.top_role.position,
        bot_top_role_position=me.top_role.position,
    )


@functools.cache
def first_names() -> set[str]:
    try:
        from gender_guesser.detector import Detector
    except ImportError:
        sys.exit("The first-name list is missing - run: pip install -r requirements.txt")
    return {name.lower() for name in Detector().names if name.isascii() and name.isalpha()}


def classify(member, allow_entries) -> tuple[str, str, list[str]]:
    hits = allowlist_hits(
        allow_entries, member.id, (member.name, member.global_name, member.nick)
    )
    if hits:
        return MATCH, f"allowlisted ({hits[0]})", hits
    bucket, reason = classify_member(member.nick, member.display_name, first_names())
    return bucket, reason, []


def shown_name(member) -> str:
    return member.nick or f"(no nickname) {member.display_name}"


def describe(member, reason: str) -> str:
    return format_line(member.id, member.name, shown_name(member), reason)


def write_list(path: Path, name: str, lines: list[str]) -> None:
    header = f"# {name}.txt - {len(lines)} members\n# {LIST_HEADERS[name]}\n"
    path.write_text(
        header + "".join(f"{line}\n" for line in lines), encoding="utf-8-sig"
    )


def latest_not_match() -> Path:
    scans = sorted(OUTPUT_DIR.glob("scan_*/not_match.txt"))
    if not scans:
        sys.exit("No scan found - run 'python namecheck.py scan' first.")
    return scans[-1]


async def cmd_scan(args, guild, me, members, exempt_roles) -> int:
    allow_entries = read_allowlist()
    resolved = {entry: [] for entry in allow_entries}
    rows = {MATCH: [], MAYBE: [], NOT_MATCH: [], SKIPPED: []}

    for member in members:
        bucket, reason, hits = classify(member, allow_entries)
        for entry in hits:
            resolved[entry].append(member)
        why_skipped = skip_for(member, guild, me, exempt_roles)
        if why_skipped:
            reason = f"skipped ({why_skipped}); would be {bucket}: {reason}"
            bucket = SKIPPED
        rows[bucket].append((member, reason))

    def sort_key(row):
        member = row[0]
        shown = (member.nick or member.display_name).casefold()
        return (-closeness(member.nick or member.display_name), shown)

    rows[MAYBE].sort(key=sort_key)
    for bucket in (MATCH, NOT_MATCH, SKIPPED):
        rows[bucket].sort(key=lambda row: (row[0].nick or row[0].display_name).casefold())

    folder = OUTPUT_DIR / f"scan_{timestamp()}"
    folder.mkdir(parents=True)
    for bucket, bucket_rows in rows.items():
        lines = [describe(member, reason) for member, reason in bucket_rows]
        write_list(folder / f"{bucket}.txt", bucket, lines)

    print(f"Scanned {len(members)} members -> {folder}")
    for bucket, bucket_rows in rows.items():
        print(f"  {bucket:<10}{len(bucket_rows)}")
    for entry, found in resolved.items():
        if not found:
            print(f"WARNING: allowlist entry '{entry}' matched nobody")
        else:
            who = ", ".join(f"@{m.name} (id {m.id})" for m in found)
            note = "  <- matches more than one member; use an ID" if len(found) > 1 else ""
            print(f"Allowlist: '{entry}' -> {who}{note}")
    if not can_timeout(me):
        print(f"\nNote: {PERMISSION_HELP}")
    return 0


async def cmd_timeout(args, guild, me, members, exempt_roles) -> int:
    if not can_timeout(me):
        print(PERMISSION_HELP)
        return 1

    list_path = Path(args.list) if args.list else latest_not_match()
    print(f"Using {list_path}")
    listed = parse_list_entries(read_text(list_path))
    by_id = {m.id: m for m in members}
    allow_entries = read_allowlist()

    targets, spared = [], []
    for member_id, listed_name in listed.items():
        member = by_id.get(member_id)
        if member is None:
            spared.append((member_id, "no longer in the server"))
            continue
        why = skip_for(member, guild, me, set() if args.include_exempt else exempt_roles)
        bucket, reason, hits = classify(member, allow_entries)
        if why:
            spared.append((member_id, f"skipped ({why})"))
        elif hits:
            spared.append((member_id, "allowlisted"))
        elif (
            bucket == MATCH
            and listed_name is not None
            and listed_name != clean_shown(shown_name(member))
        ):
            # They changed their name after the scan and it passes now. A match you
            # put on the list deliberately (same name as scanned) still gets timed out.
            spared.append((member_id, f"name changed since the scan and now matches ({reason})"))
        elif member.is_timed_out():
            spared.append((member_id, "already timed out"))
        else:
            targets.append((member, reason))

    for member_id, why in spared:
        print(f"SPARED   {member_id}: {why}")
    for member, reason in targets:
        print(f"TIMEOUT  {describe(member, reason)}")

    if not targets:
        print("\nNobody to time out.")
        return 0
    if not args.apply:
        print(
            f"\nDRY RUN: {len(targets)} members would be timed out for {args.days} days. "
            "Nothing was changed.\nRe-run with --apply to do it."
        )
        return 0

    try:
        answer = input(
            f"\nType {len(targets)} to time out {len(targets)} members for {args.days} days: "
        )
    except EOFError:
        answer = ""
    if answer.strip() != str(len(targets)):
        print("Cancelled - nothing was changed.")
        return 1

    duration = timeout_duration(args.days)
    OUTPUT_DIR.mkdir(exist_ok=True)
    log_path = OUTPUT_DIR / f"timeout_log_{timestamp()}.txt"
    log = [f"Timeouts of {args.days} days from {list_path}"]
    done = failed = 0
    try:
        for member, reason in targets:
            try:
                await member.timeout(duration, reason=TIMEOUT_REASON)
                outcome, done = "ok", done + 1
            except discord.Forbidden:
                outcome, failed = "FAILED: forbidden (bot permissions or role position)", failed + 1
            except discord.HTTPException as error:
                outcome, failed = f"FAILED: {error}", failed + 1
            line = f"{outcome}  {describe(member, reason)}"
            log.append(line)
            print(line)
            await asyncio.sleep(0.25)
    finally:
        log_path.write_text("\n".join(log) + "\n", encoding="utf-8-sig")

    print(f"\nTimed out {done}, failed {failed}. Log: {log_path}")
    return 0 if not failed else 1


async def cmd_status(args, guild, me, members, exempt_roles) -> int:
    timed_out = [m for m in members if m.is_timed_out()]
    timed_out.sort(key=lambda m: m.timed_out_until)
    if not timed_out:
        print("Nobody is currently timed out.")
        return 0
    now = datetime.now(timezone.utc)
    for member in timed_out:
        remaining = member.timed_out_until - now
        hours = int(remaining.total_seconds() // 3600)
        expires = member.timed_out_until.astimezone().strftime("%Y-%m-%d %H:%M %Z")
        print(describe(member, f"expires {expires} (~{hours}h left)"))
    print(f"\n{len(timed_out)} member(s) currently timed out.")
    return 0


async def cmd_untimeout(args, guild, me, members, exempt_roles) -> int:
    if not can_timeout(me):
        print(PERMISSION_HELP)
        return 1
    by_id = {m.id: m for m in members}
    for member_id in args.ids:
        member = by_id.get(member_id)
        if member is None:
            print(f"{member_id}: not in the server")
        elif not member.is_timed_out():
            print(f"{member_id}: not timed out")
        else:
            await member.timeout(None, reason="Timeout removed (namecheck)")
            print(f"{member_id}: timeout removed")
    return 0


async def run(args) -> int:
    token, guild_id, exempt_roles = load_config()
    intents = discord.Intents.default()
    intents.members = True
    # REST only: no gateway session, so this can't disturb the bot that's running
    async with discord.Client(intents=intents) as client:
        await client.login(token)
        guild = await client.fetch_guild(guild_id)
        me = await guild.fetch_member(client.user.id)
        members = [m async for m in guild.fetch_members(limit=None)]
        return await args.func(args, guild, me, members, exempt_roles)


def days_arg(value: str) -> int:
    days = int(value)
    if not 1 <= days <= MAX_TIMEOUT_DAYS:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_TIMEOUT_DAYS}")
    return days


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Check member nicknames for a human name and time out the ones you confirm."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="write the match / maybe / not_match / skipped lists")
    scan.set_defaults(func=cmd_scan)

    timeout = commands.add_parser(
        "timeout", help="time out everyone in not_match.txt (dry run unless --apply)"
    )
    timeout.add_argument("--list", help="list file to use (default: newest scan's not_match.txt)")
    timeout.add_argument(
        "--days", type=days_arg, default=MAX_TIMEOUT_DAYS,
        help=f"timeout length, 1-{MAX_TIMEOUT_DAYS} (default {MAX_TIMEOUT_DAYS})",
    )
    timeout.add_argument("--apply", action="store_true", help="actually time people out")
    timeout.add_argument(
        "--include-exempt", action="store_true",
        help="also time out listed members who hold an exempt role",
    )
    timeout.set_defaults(func=cmd_timeout)

    status = commands.add_parser("status", help="list members currently timed out")
    status.set_defaults(func=cmd_status)

    untimeout = commands.add_parser("untimeout", help="remove timeouts")
    untimeout.add_argument("ids", nargs="+", type=int, help="member IDs")
    untimeout.set_defaults(func=cmd_untimeout)

    args = parser.parse_args()
    try:
        return asyncio.run(run(args))
    except discord.LoginFailure:
        print("Discord rejected the bot token in .env.", file=sys.stderr)
    except aiohttp.ClientConnectorError as error:
        print(f"Couldn't reach Discord (network or DNS problem?): {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
