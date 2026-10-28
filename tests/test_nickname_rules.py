from datetime import timedelta

import pytest

from nickname_rules import (
    MATCH,
    MAYBE,
    NOT_MATCH,
    allowlist_hits,
    classify_member,
    classify_nickname,
    clean_shown,
    closeness,
    format_line,
    parse_allowlist,
    parse_id_list,
    parse_list_entries,
    skip_reason,
    timeout_duration,
)

# A stand-in for the real first-name list, including the word-names "the" and
# "king" that the real list also contains
NAMES = {
    "tobias", "matt", "koda", "mary", "jane", "john", "smith", "colin", "kay", "mike",
    "steve", "tyson", "dillan", "ty", "nick", "king", "the", "buzz", "jos",
}


def classify(nickname):
    return classify_nickname(nickname, NAMES)[0]


@pytest.mark.parametrize(
    "nickname",
    [
        "Tobias",
        "BossSauce585 Tobias",
        "Matt (Koda)",
        "[CPT] Matt",
        "Mary-Jane",
        "john smith",
        "JohnSmith",
        "Ty",
        "Canoptek (Dillan)",
        "Qwerty (Colin Kay)",
        "Washing Machine Servitor Nick",
        "\U0001f451 Tobias \U0001f451",
    ],
)
def test_nicknames_with_a_first_name_match(nickname):
    assert classify(nickname) == MATCH


@pytest.mark.parametrize(
    "nickname",
    [
        "AbsoluteIdiots",
        "Asgorath",
        "ArjacRockfist",
        "Buzzlitebeer",
        "I eat paint",
        "TheButcher20",
        "DarkLord",
        "BossSauce585",
        "J",
        "x1",
        "12345",
        "\U0001f451\U0001f451",
        "",
        "   ",
    ],
)
def test_nicknames_without_a_first_name_do_not_match(nickname):
    assert classify(nickname) == NOT_MATCH


@pytest.mark.parametrize(
    "nickname",
    [
        "GodlikeMike_001",
        "tyson0796",
        "Steve_the_man",
        "John_Smith",
        "TombKing20",
        "King",
        "José",
        "Алексей",
    ],
)
def test_names_in_handles_word_names_and_non_ascii_are_maybe(nickname):
    assert classify(nickname) == MAYBE


def test_reason_names_the_first_name_found():
    assert classify_nickname("BossSauce585 Tobias", NAMES)[1] == "first name: Tobias"


def test_reason_shows_the_handle_a_name_was_found_in():
    reason = classify_nickname("GodlikeMike_001", NAMES)[1]
    assert "Mike" in reason and "GodlikeMike_001" in reason


def test_a_clear_name_beats_a_word_name():
    assert classify("King Tobias") == MATCH


def test_member_with_nickname_is_judged_on_the_nickname():
    assert classify_member("Tobias", "xX_Slayer_Xx", NAMES)[0] == MATCH


def test_member_without_nickname_is_judged_on_the_display_name():
    bucket, reason = classify_member(None, "Qwerty (Colin Kay)", NAMES)
    assert bucket == MATCH
    assert "display name (no server nickname)" in reason


def test_member_without_nickname_and_no_name_is_not_a_match():
    assert classify_member(None, "AbsoluteIdiots", NAMES)[0] == NOT_MATCH


def test_empty_nickname_counts_as_no_nickname():
    assert classify_member("", "Tobias", NAMES)[0] == MATCH


def test_closeness_orders_name_like_text_first():
    assert closeness("John") == 1.0
    assert closeness("1234") == 0.0
    assert closeness("") == 0.0
    assert 0 < closeness("John99") < closeness("John_Smith") < 1


def skip(**overrides):
    args = {
        "is_bot": False,
        "is_owner": False,
        "is_admin": False,
        "has_exempt_role": False,
        "top_role_position": 1,
        "bot_top_role_position": 5,
    }
    args.update(overrides)
    return skip_reason(**args)


def test_ordinary_member_is_not_skipped():
    assert skip() is None


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"is_bot": True}, "bot"),
        ({"is_owner": True}, "server owner"),
        ({"is_admin": True}, "administrator"),
        ({"has_exempt_role": True}, "exempt role"),
        ({"top_role_position": 5}, "role at or above the bot's"),
        ({"top_role_position": 9}, "role at or above the bot's"),
    ],
)
def test_members_who_cannot_be_timed_out_are_skipped(overrides, reason):
    assert skip(**overrides) == reason


def test_parse_allowlist_ignores_comments_blanks_and_at_signs():
    text = "# note\n\n  ChalupaDelux3  \n@someone\n123456789012345678\n"
    assert parse_allowlist(text) == ["ChalupaDelux3", "someone", "123456789012345678"]


def test_allowlist_matches_names_case_insensitively():
    hits = allowlist_hits(["ChalupaDelux3"], 1, ["chalupadelux3", None, "Chalupa"])
    assert hits == ["ChalupaDelux3"]


def test_allowlist_matches_server_nickname():
    assert allowlist_hits(["ChalupaDelux3"], 1, ["someone", None, "CHALUPADELUX3"])


def test_allowlist_ignores_emoji_and_punctuation_around_a_name():
    names = [".cliodhna", "\U0001f32eChalupaDelux3\U0001f32e", None]
    assert allowlist_hits(["ChalupaDelux3"], 1, names) == ["ChalupaDelux3"]


def test_allowlist_needs_the_whole_name():
    assert allowlist_hits(["Matt"], 1, ["Matt (Koda)"]) == []


def test_allowlist_entry_without_letters_matches_nobody():
    assert allowlist_hits(["\U0001f32e"], 1, ["\U0001f32e", "x"]) == []


def test_allowlist_matches_user_id():
    assert allowlist_hits(["123456789012345678"], 123456789012345678, ["x"])


def test_allowlist_ignores_other_members():
    assert allowlist_hits(["ChalupaDelux3", "999999999999999999"], 1, ["Tobias"]) == []


def test_format_line_keeps_one_member_per_line():
    line = format_line(123456789012345678, "tobias", "To\nbias", "name word: To")
    assert "\n" not in line
    assert line.startswith("123456789012345678 | @tobias | ")


def test_parse_id_list_reads_the_leading_id_of_each_line():
    text = (
        "# not_match.txt - 3 members\n"
        "123456789012345678 | @a | 12345 | no word of 2+ letters\n"
        "\n"
        "223456789012345678\n"
        "   323456789012345678 | @c | x1 | no word of 2+ letters\n"
    )
    assert parse_id_list(text) == [
        123456789012345678,
        223456789012345678,
        323456789012345678,
    ]


def test_parse_id_list_dedupes_and_ignores_non_ids():
    text = "123456789012345678\n123456789012345678\n12345\n123456789012345678901234\nhello\n"
    assert parse_id_list(text) == [123456789012345678]


def test_timeout_duration_is_exact_below_the_maximum():
    assert timeout_duration(7) == timedelta(days=7)


def test_timeout_duration_stays_just_under_28_days():
    assert timedelta(days=28) - timedelta(minutes=10) < timeout_duration(28) < timedelta(days=28)


@pytest.mark.parametrize("days", [0, -1, 29])
def test_timeout_duration_rejects_out_of_range_days(days):
    with pytest.raises(ValueError):
        timeout_duration(days)


def test_parse_list_entries_records_the_shown_name():
    text = (
        "# header\n"
        "123456789012345678 | @a | Red Leader | first name: Red\n"
        "223456789012345678 | @b | invyrse | ari! | first name: ari\n"
        "323456789012345678\n"
    )
    assert parse_list_entries(text) == {
        123456789012345678: "Red Leader",
        223456789012345678: "invyrse | ari!",
        323456789012345678: None,
    }


def test_clean_shown_matches_what_format_line_writes():
    line = format_line(123456789012345678, "a", "To\nbias ", "x")
    assert parse_list_entries(line)[123456789012345678] == clean_shown("To\nbias ")
