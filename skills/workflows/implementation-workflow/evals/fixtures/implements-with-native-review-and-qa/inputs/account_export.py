"""Account export policy used by the fake offline fixture."""


def _denied_export_message(requester_id, owner_id):
    return f"requester {requester_id} cannot export account {owner_id}"


def export_account(requester_id, owner_id, records):
    """Return an account export for the requested owner."""
    return [dict(record) for record in records]
