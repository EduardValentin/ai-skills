"""Environment-driven config for bundled stock research scripts.

All settings come from env vars. Required: SR_SEC_USER_AGENT (SEC blocks empty
or default user agents) and SR_RESEARCH_REPO. AI_SKILLS_RUNTIME_HOME optionally
selects external mutable runtime state. Optional financial settings are
SR_DISCOUNT_RATE, SR_TERMINAL_GROWTH, and SR_YEARS_OF_HISTORY.
"""
from __future__ import annotations

import os
from pathlib import Path


class ConfigError(RuntimeError):
    pass


def _validated_external_runtime_home(path: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise ConfigError("Finance runtime paths must be absolute.")

    resolved = expanded.resolve()
    installed_skill_root = Path(__file__).resolve().parents[2]
    if resolved == installed_skill_root or installed_skill_root in resolved.parents:
        raise ConfigError("Finance runtime state must stay outside the installed skill.")
    return resolved


def ai_skills_runtime_home() -> Path:
    explicit = os.environ.get("AI_SKILLS_RUNTIME_HOME")
    if explicit:
        return _validated_external_runtime_home(Path(explicit))

    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        return _validated_external_runtime_home(Path(xdg_cache) / "ai-skills")

    home = os.environ.get("HOME")
    if home:
        return _validated_external_runtime_home(
            Path(home) / ".cache" / "ai-skills"
        )

    raise ConfigError(
        "Set AI_SKILLS_RUNTIME_HOME, XDG_CACHE_HOME, or HOME so finance "
        "runtime state can live outside the installed skill."
    )


def finance_runtime_dir() -> Path:
    return ai_skills_runtime_home() / "investing-finance"


def finance_virtualenv_path() -> Path:
    return finance_runtime_dir() / "venv"


def finance_python_path() -> Path:
    executable_dir = "Scripts" if os.name == "nt" else "bin"
    executable_name = "python.exe" if os.name == "nt" else "python"
    return finance_virtualenv_path() / executable_dir / executable_name


def finance_cache_dir() -> Path:
    return finance_runtime_dir() / "cache"


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
