"""Tests for _lib.config."""
from __future__ import annotations

import pytest

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
    monkeypatch: pytest.MonkeyPatch, cfg, script_root
) -> None:
    monkeypatch.delenv("SR_REPO_PATH", raising=False)
    monkeypatch.delenv("SR_RESEARCH_REPO", raising=False)
    env_var = (
        "SR_RESEARCH_REPO"
        if script_root.parent.name == "stock-recap"
        else "SR_REPO_PATH"
    )

    with pytest.raises(cfg.ConfigError, match=env_var):
        cfg.research_repo_path()


def test_research_repo_path_uses_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path, cfg, script_root
) -> None:
    env_var = (
        "SR_RESEARCH_REPO"
        if script_root.parent.name == "stock-recap"
        else "SR_REPO_PATH"
    )
    monkeypatch.setenv(env_var, str(tmp_path))
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
