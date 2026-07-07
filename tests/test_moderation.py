from moderation import is_exempt_role, should_delete_message


def test_is_exempt_role_true_when_overlap():
    assert is_exempt_role({1, 2, 3}, {3, 4}) is True


def test_is_exempt_role_false_when_no_overlap():
    assert is_exempt_role({1, 2}, {3, 4}) is False


def test_is_exempt_role_false_when_member_has_no_roles():
    assert is_exempt_role(set(), {3, 4}) is False


def test_should_delete_message_true_for_non_exempt_user():
    assert should_delete_message(111, {222}) is True


def test_should_delete_message_false_for_exempt_user():
    assert should_delete_message(222, {222}) is False


def test_should_delete_message_true_when_exempt_set_empty():
    assert should_delete_message(111, set()) is True
