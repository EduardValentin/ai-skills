"""Feature-flag visibility for the fake offline fixture."""


def visible_flag_names(role, flags):
    if role == "admin":
        return sorted(flag["name"] for flag in flags)
    return sorted(
        flag["name"]
        for flag in flags
        if flag["audience"] == "public" and flag["enabled"]
    )
