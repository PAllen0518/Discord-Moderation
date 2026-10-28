import re
from collections.abc import Iterable
from datetime import timedelta

MATCH = "match"
MAYBE = "maybe"
NOT_MATCH = "not_match"

MAX_TIMEOUT_DAYS = 28
# Discord rejects timeouts over 28 days, so stay a few minutes under it in case
# this PC's clock runs fast.
CLOCK_MARGIN = timedelta(minutes=5)

_LETTER_RUN = re.compile(r"[A-Za-z]+")
# Splits camelCase: "ArjacRockfist" -> Arjac, Rockfist; "GodlikeMike" -> Godlike, Mike
_CAMEL_PART = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])")
_ID_AT_START = re.compile(r"^\s*(\d{15,20})\b")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")

# Short words that happen to be in the name list but never mean a name here
_STOPWORDS = {
    "a", "an", "and", "as", "at", "be", "by", "do", "dr", "go", "if", "in", "is", "it",
    "me", "mr", "mrs", "ms", "my", "no", "of", "on", "or", "sir", "so", "the", "to",
    "up", "we",
}

# Real first names that are also everyday words, so they only earn a "maybe"
_WORD_NAMES = {
    "ace", "amber", "angel", "april", "archer", "art", "ash", "august", "autumn",
    "baron", "bear", "bill", "bishop", "blaze", "buck", "candy", "cash", "chance",
    "chase", "cherry", "chip", "cliff", "colt", "crystal", "dale", "dawn", "destiny",
    "drew", "duke", "dusty", "earl", "eve", "faith", "forest", "fox", "frank", "ginger",
    "glen", "grace", "guy", "gunner", "happy", "harmony", "hawk", "heath", "honey",
    "hope", "hunter", "iris", "ivy", "jack", "jade", "jay", "joy", "june", "justice",
    "king", "knight", "lane", "legend", "lily", "lucky", "major", "mark", "max", "may",
    "melody", "mercy", "miles", "pat", "pearl", "penny", "precious", "prince",
    "ranger", "raven", "ray", "rex", "rich", "river", "rob", "rocky", "rose", "royal",
    "ruby", "rusty", "sage", "saint", "sandy", "skip", "sky", "sonny", "star",
    "sterling", "stone", "storm", "summer", "sunny", "victor", "wade", "west", "will",
    "winter", "wolf",
}


def _name_hits(text: str, names: set[str]) -> list[tuple[str, bool, str]]:
    """(name, standalone, whitespace-separated chunk it came from) for each first name found."""
    hits = []
    for chunk in text.split():
        for run in _LETTER_RUN.finditer(chunk):
            before = chunk[run.start() - 1] if run.start() else ""
            after = chunk[run.end()] if run.end() < len(chunk) else ""
            # Glued = touching a digit, underscore or non-ASCII letter, i.e. part of a handle
            standalone = not any(c and (c.isalnum() or c == "_") for c in (before, after))
            for part in _CAMEL_PART.findall(run.group()):
                word = part.lower()
                if len(word) >= 2 and word not in _STOPWORDS and word in names:
                    hits.append((part, standalone, chunk))
    return hits


def classify_nickname(text: str, names: set[str]) -> tuple[str, str]:
    """Bucket a nickname as match, maybe or not_match against a set of lowercase first names."""
    s = text.strip()
    hits = _name_hits(s, names)
    clear = [n for n, standalone, _ in hits if standalone and n.lower() not in _WORD_NAMES]
    if clear:
        return MATCH, f"first name: {', '.join(dict.fromkeys(clear[:3]))}"
    glued = [(n, chunk) for n, standalone, chunk in hits if not standalone]
    if glued:
        return MAYBE, f"first name inside a handle: {glued[0][0]} ({glued[0][1]})"
    if hits:
        return MAYBE, f"name that's also a common word: {hits[0][0]}"
    if any(ch.isalpha() and not ch.isascii() for ch in s):
        return MAYBE, "non-ASCII letters (can't be checked automatically)"
    return NOT_MATCH, "no known first name"


def classify_member(
    nick: str | None, display_name: str, names: set[str]
) -> tuple[str, str]:
    """Judge the server nickname, or the display name when there isn't one."""
    if nick:
        return classify_nickname(nick, names)
    bucket, reason = classify_nickname(display_name, names)
    return bucket, f"display name (no server nickname): {reason}"


def closeness(text: str) -> float:
    """Share of the text that is letters; sorts 'maybe' entries closest-first."""
    s = text.strip()
    return sum(ch.isalpha() for ch in s) / len(s) if s else 0.0


def skip_reason(
    *,
    is_bot: bool,
    is_owner: bool,
    is_admin: bool,
    has_exempt_role: bool,
    top_role_position: int,
    bot_top_role_position: int,
) -> str | None:
    """Why this member must never be timed out, or None if they can be."""
    if is_bot:
        return "bot"
    if is_owner:
        return "server owner"
    if is_admin:
        return "administrator"
    if has_exempt_role:
        return "exempt role"
    if top_role_position >= bot_top_role_position:
        return "role at or above the bot's"
    return None


def parse_allowlist(text: str) -> list[str]:
    """Entries from the allowlist file; blank lines and # comments are ignored."""
    entries = []
    for line in text.splitlines():
        line = line.strip().lstrip("@").strip()
        if line and not line.startswith("#"):
            entries.append(line)
    return entries


def _squash(name: str) -> str:
    """Casefolded letters and digits only, so emoji and punctuation around a name are ignored."""
    return "".join(ch for ch in name.casefold() if ch.isalnum())


def allowlist_hits(
    entries: list[str], member_id: int, names: Iterable[str | None]
) -> list[str]:
    """Allowlist entries that identify this member by ID or by any of their names."""
    squashed = {_squash(name) for name in names if name} - {""}
    return [
        entry
        for entry in entries
        if (entry.isdigit() and int(entry) == member_id) or _squash(entry) in squashed
    ]


def clean_shown(shown_name: str) -> str:
    return _CONTROL_CHARS.sub(" ", shown_name).strip()


def format_line(member_id: int, username: str, shown_name: str, reason: str) -> str:
    return f"{member_id} | @{username} | {clean_shown(shown_name)} | {reason}"


def parse_list_entries(text: str) -> dict[int, str | None]:
    """Member ID -> the shown name recorded in a list line (None for a bare ID)."""
    entries = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        found = _ID_AT_START.match(line)
        if found:
            fields = line.split(" | ")
            # The shown name can itself contain " | ", so it's everything between
            # the @username field and the trailing reason field
            shown = " | ".join(fields[2:-1]).strip() if len(fields) >= 4 else None
            entries.setdefault(int(found.group(1)), shown)
    return entries


def parse_id_list(text: str) -> list[int]:
    """Member IDs from a list file: one per line, anything after the ID is ignored."""
    return list(parse_list_entries(text))


def timeout_duration(days: int) -> timedelta:
    """Length of a timeout, trimmed slightly at the 28-day maximum."""
    if not 1 <= days <= MAX_TIMEOUT_DAYS:
        raise ValueError(f"days must be between 1 and {MAX_TIMEOUT_DAYS}")
    duration = timedelta(days=days)
    return duration - CLOCK_MARGIN if days == MAX_TIMEOUT_DAYS else duration
