"""Shared environment ownership rules for isolated evaluation cases."""

from __future__ import annotations


CASE_OWNED_ENVIRONMENT_NAMES = frozenset(
    {
        "HOME",
        "CODEX_HOME",
        "TMPDIR",
        "USER",
        "LOGNAME",
        "SHELL",
        "BASH_ENV",
        "ENV",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_RUNTIME_DIR",
        "SSH_AUTH_SOCK",
        "GIT_CONFIG_GLOBAL",
        "GNUPGHOME",
        "DOCKER_HOST",
    }
)
