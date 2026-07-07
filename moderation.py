def is_exempt_role(member_role_ids: set[int], exempt_role_ids: set[int]) -> bool:
    """True if the member holds any role that exempts them from enforcement."""
    return bool(member_role_ids & exempt_role_ids)


def should_delete_message(author_id: int, exempt_user_ids: set[int]) -> bool:
    """True if this author's message should be deleted when they're banned."""
    return author_id not in exempt_user_ids
