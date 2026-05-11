"""Shared pytest fixtures and path setup for stock-research scripts tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def tmp_research_repo(tmp_path: Path) -> Path:
    """Build a minimal investing-research repo layout under tmp_path."""
    (tmp_path / "tickers").mkdir()
    (tmp_path / "archive").mkdir()
    (tmp_path / "notes").mkdir()
    (tmp_path / "tickers.json").write_text('{"schema_version": 1, "tickers": {}}\n')
    (tmp_path / "INDEX.md").write_text("# Index\n\n_No tickers yet._\n")
    return tmp_path


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force a known SEC User-Agent in every test so config never reads from the host."""
    monkeypatch.setenv("SR_SEC_USER_AGENT", "Test Suite test@example.com")
    monkeypatch.delenv("SR_REPO_PATH", raising=False)
