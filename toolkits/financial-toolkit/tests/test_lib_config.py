"""Tests for _lib.config."""
from __future__ import annotations

import pytest

from _lib import config as cfg


def test_sec_user_agent_returns_env_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SR_SEC_USER_AGENT", "Alice alice@example.com")
    assert cfg.sec_user_agent() == "Alice alice@example.com"


def test_sec_user_agent_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SR_SEC_USER_AGENT", raising=False)
    with pytest.raises(cfg.ConfigError, match="SR_SEC_USER_AGENT"):
        cfg.sec_user_agent()


def test_research_repo_path_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SR_REPO_PATH", raising=False)
    assert str(cfg.research_repo_path()).endswith("investing-research")


def test_research_repo_path_uses_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("SR_REPO_PATH", str(tmp_path))
    assert cfg.research_repo_path() == tmp_path


def test_numeric_defaults() -> None:
    assert cfg.discount_rate() == 0.10
    assert cfg.terminal_growth_rate() == 0.025
    assert cfg.years_of_history() == 10


def test_numeric_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SR_DISCOUNT_RATE", "0.12")
    monkeypatch.setenv("SR_TERMINAL_GROWTH", "0.03")
    monkeypatch.setenv("SR_YEARS_OF_HISTORY", "15")
    assert cfg.discount_rate() == 0.12
    assert cfg.terminal_growth_rate() == 0.03
    assert cfg.years_of_history() == 15
