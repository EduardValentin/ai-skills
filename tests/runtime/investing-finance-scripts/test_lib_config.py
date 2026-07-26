"""Tests for _lib.config."""
from __future__ import annotations

from pathlib import Path

import pytest


def _clear_runtime_location_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("AI_SKILLS_RUNTIME_HOME", "XDG_CACHE_HOME", "HOME"):
        monkeypatch.delenv(name, raising=False)


def test_ai_skills_runtime_home_prefers_explicit_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cfg
) -> None:
    explicit = tmp_path / "explicit-runtime"
    monkeypatch.setenv("AI_SKILLS_RUNTIME_HOME", str(explicit))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    assert cfg.ai_skills_runtime_home() == explicit


def test_ai_skills_runtime_home_uses_xdg_cache_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cfg
) -> None:
    _clear_runtime_location_env(monkeypatch)
    xdg_cache = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_cache))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    assert cfg.ai_skills_runtime_home() == xdg_cache / "ai-skills"


def test_ai_skills_runtime_home_uses_home_cache_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cfg
) -> None:
    _clear_runtime_location_env(monkeypatch)
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))

    assert cfg.ai_skills_runtime_home() == home / ".cache" / "ai-skills"


def test_ai_skills_runtime_home_requires_portable_base(
    monkeypatch: pytest.MonkeyPatch, cfg
) -> None:
    _clear_runtime_location_env(monkeypatch)

    with pytest.raises(cfg.ConfigError, match="AI_SKILLS_RUNTIME_HOME"):
        cfg.ai_skills_runtime_home()


def test_ai_skills_runtime_home_rejects_relative_override(
    monkeypatch: pytest.MonkeyPatch, cfg
) -> None:
    monkeypatch.setenv("AI_SKILLS_RUNTIME_HOME", "relative/runtime")

    with pytest.raises(cfg.ConfigError, match="absolute"):
        cfg.ai_skills_runtime_home()


def test_ai_skills_runtime_home_rejects_installed_skill_path(
    monkeypatch: pytest.MonkeyPatch, cfg, script_root: Path
) -> None:
    monkeypatch.setenv(
        "AI_SKILLS_RUNTIME_HOME", str(script_root / "mutable-runtime")
    )

    with pytest.raises(cfg.ConfigError, match="outside the installed skill"):
        cfg.ai_skills_runtime_home()


def test_finance_runtime_paths_are_outside_installed_skill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cfg, script_root: Path
) -> None:
    runtime_home = tmp_path / "runtime"
    monkeypatch.setenv("AI_SKILLS_RUNTIME_HOME", str(runtime_home))
    expected_runtime = runtime_home / "investing-finance"
    executable_dir = "Scripts" if cfg.os.name == "nt" else "bin"
    executable_name = "python.exe" if cfg.os.name == "nt" else "python"

    assert cfg.finance_runtime_dir() == expected_runtime
    assert cfg.finance_virtualenv_path() == expected_runtime / "venv"
    assert cfg.finance_python_path() == (
        expected_runtime / "venv" / executable_dir / executable_name
    )
    assert cfg.finance_cache_dir() == expected_runtime / "cache"
    assert not cfg.finance_runtime_dir().is_relative_to(script_root)


def test_sec_user_agent_returns_env_value(
    monkeypatch: pytest.MonkeyPatch, cfg
) -> None:
    monkeypatch.setenv("SR_SEC_USER_AGENT", "Alice alice@example.com")
    assert cfg.sec_user_agent() == "Alice alice@example.com"


def test_sec_user_agent_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch, cfg
) -> None:
    monkeypatch.delenv("SR_SEC_USER_AGENT", raising=False)
    with pytest.raises(cfg.ConfigError, match="SR_SEC_USER_AGENT"):
        cfg.sec_user_agent()


def test_research_repo_path_follows_unset_contract(
    monkeypatch: pytest.MonkeyPatch, cfg
) -> None:
    monkeypatch.delenv("SR_REPO_PATH", raising=False)

    with pytest.raises(cfg.ConfigError, match="SR_REPO_PATH"):
        cfg.research_repo_path()


def test_research_repo_path_uses_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path, cfg
) -> None:
    monkeypatch.setenv("SR_REPO_PATH", str(tmp_path))
    assert cfg.research_repo_path() == tmp_path


def test_numeric_defaults(cfg) -> None:
    assert cfg.discount_rate() == 0.10
    assert cfg.terminal_growth_rate() == 0.025
    assert cfg.years_of_history() == 10


def test_numeric_overrides(monkeypatch: pytest.MonkeyPatch, cfg) -> None:
    monkeypatch.setenv("SR_DISCOUNT_RATE", "0.12")
    monkeypatch.setenv("SR_TERMINAL_GROWTH", "0.03")
    monkeypatch.setenv("SR_YEARS_OF_HISTORY", "15")
    assert cfg.discount_rate() == 0.12
    assert cfg.terminal_growth_rate() == 0.03
    assert cfg.years_of_history() == 15
