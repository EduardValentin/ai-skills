"""Environment-driven config for bundled stock research scripts.

All settings come from env vars. Required: SR_SEC_USER_AGENT (SEC blocks empty
or default user agents) and SR_RESEARCH_REPO. Optional: SR_DISCOUNT_RATE,
SR_TERMINAL_GROWTH, and SR_YEARS_OF_HISTORY.
"""
from __future__ import annotations

import os
from pathlib import Path


class ConfigError(RuntimeError):
    pass


def sec_user_agent() -> str:
    value = os.environ.get("SR_SEC_USER_AGENT")
    if not value:
        raise ConfigError(
            "SR_SEC_USER_AGENT is required. Set it to 'Name email@domain.tld' "
            "so SEC EDGAR accepts the request."
        )
    return value


def research_repo_path() -> Path:
    raw = os.environ.get("SR_RESEARCH_REPO")
    if not raw:
        raise ConfigError(
            "SR_RESEARCH_REPO is required. Set it to the investing research repo root."
        )
    return Path(raw).expanduser()


def discount_rate() -> float:
    return float(os.environ.get("SR_DISCOUNT_RATE", "0.10"))


def terminal_growth_rate() -> float:
    return float(os.environ.get("SR_TERMINAL_GROWTH", "0.025"))


def years_of_history() -> int:
    return int(os.environ.get("SR_YEARS_OF_HISTORY", "10"))
