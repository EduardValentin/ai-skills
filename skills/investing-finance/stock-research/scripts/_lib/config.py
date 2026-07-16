"""Environment-driven config for stock-research scripts.

All settings come from env vars. Required: SR_SEC_USER_AGENT (SEC blocks empty
or default user agents). Optional: SR_REPO_PATH, SR_DISCOUNT_RATE,
SR_TERMINAL_GROWTH, SR_YEARS_OF_HISTORY.
"""
from __future__ import annotations

import os
from pathlib import Path


class ConfigError(RuntimeError):
    pass


DEFAULT_REPO_PATH = Path.home() / "Documents" / "Personal" / "investing-research"


def sec_user_agent() -> str:
    value = os.environ.get("SR_SEC_USER_AGENT")
    if not value:
        raise ConfigError(
            "SR_SEC_USER_AGENT is required. Set it to 'Name email@domain.tld' "
            "so SEC EDGAR accepts the request."
        )
    return value


def research_repo_path() -> Path:
    raw = os.environ.get("SR_REPO_PATH")
    return Path(raw) if raw else DEFAULT_REPO_PATH


def discount_rate() -> float:
    return float(os.environ.get("SR_DISCOUNT_RATE", "0.10"))


def terminal_growth_rate() -> float:
    return float(os.environ.get("SR_TERMINAL_GROWTH", "0.025"))


def years_of_history() -> int:
    return int(os.environ.get("SR_YEARS_OF_HISTORY", "10"))
