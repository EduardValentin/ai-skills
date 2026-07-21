"""Shared fixtures for deterministic investing-finance script tests."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
STOCK_RESEARCH_SCRIPTS = (
    REPO_ROOT / "skills" / "investing-finance" / "stock-research" / "scripts"
)
STOCK_RECAP_SCRIPTS = (
    REPO_ROOT / "skills" / "investing-finance" / "stock-recap" / "scripts"
)
SCRIPT_ROOTS = (
    pytest.param(STOCK_RESEARCH_SCRIPTS, id="stock-research"),
    pytest.param(STOCK_RECAP_SCRIPTS, id="stock-recap"),
)
TOP_LEVEL_SCRIPT_MODULES = frozenset(
    path.stem
    for scripts_root in (STOCK_RESEARCH_SCRIPTS, STOCK_RECAP_SCRIPTS)
    for path in scripts_root.glob("*.py")
    if path.name != "__init__.py"
)


def _clear_script_modules() -> None:
    for module_name in tuple(sys.modules):
        if (
            module_name in TOP_LEVEL_SCRIPT_MODULES
            or module_name == "_lib"
            or module_name.startswith("_lib.")
        ):
            sys.modules.pop(module_name, None)
    importlib.invalidate_caches()


def _activate_script_root(
    scripts_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_script_modules()
    monkeypatch.setattr(sys, "pycache_prefix", str(tmp_path / "python-pycache"))
    monkeypatch.syspath_prepend(str(scripts_root))
    ticker_resolver = importlib.import_module("_lib.ticker_resolver")
    monkeypatch.setattr(
        ticker_resolver,
        "DEFAULT_CACHE_DIR",
        tmp_path / "sr_cache",
    )


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def tmp_research_repo(tmp_path: Path) -> Path:
    """Build a minimal investing-research repository layout."""
    (tmp_path / "tickers").mkdir()
    (tmp_path / "archive").mkdir()
    (tmp_path / "notes").mkdir()
    (tmp_path / "tickers.json").write_text(
        '{"schema_version": 1, "tickers": {}}\n'
    )
    (tmp_path / "INDEX.md").write_text("# Index\n\n_No tickers yet._\n")
    return tmp_path


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SR_SEC_USER_AGENT", "Test Suite test@example.com")
    monkeypatch.delenv("SR_REPO_PATH", raising=False)
    monkeypatch.delenv("SR_RESEARCH_REPO", raising=False)


@pytest.fixture(params=SCRIPT_ROOTS)
def script_root(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[Path]:
    scripts_root = request.param
    _activate_script_root(scripts_root, monkeypatch, tmp_path)
    try:
        yield scripts_root
    finally:
        _clear_script_modules()


@pytest.fixture
def stock_research_script_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[Path]:
    _activate_script_root(STOCK_RESEARCH_SCRIPTS, monkeypatch, tmp_path)
    try:
        yield STOCK_RESEARCH_SCRIPTS
    finally:
        _clear_script_modules()


@pytest.fixture
def stock_recap_script_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[Path]:
    _activate_script_root(STOCK_RECAP_SCRIPTS, monkeypatch, tmp_path)
    try:
        yield STOCK_RECAP_SCRIPTS
    finally:
        _clear_script_modules()


@pytest.fixture
def compute_financials(script_root: Path) -> ModuleType:
    return importlib.import_module("compute_financials")


@pytest.fixture
def compute_pe_band(script_root: Path) -> ModuleType:
    return importlib.import_module("compute_pe_band")


@pytest.fixture
def compute_reverse_dcf(script_root: Path) -> ModuleType:
    return importlib.import_module("compute_reverse_dcf")


@pytest.fixture
def diff_risk_factors(script_root: Path) -> ModuleType:
    return importlib.import_module("diff_risk_factors")


@pytest.fixture
def extract_10k_sections(script_root: Path) -> ModuleType:
    return importlib.import_module("extract_10k_sections")


@pytest.fixture
def extract_10q_sections(script_root: Path) -> ModuleType:
    return importlib.import_module("extract_10q_sections")


@pytest.fixture
def fetch_analyst_estimates(script_root: Path) -> ModuleType:
    return importlib.import_module("fetch_analyst_estimates")


@pytest.fixture
def fetch_prices(script_root: Path) -> ModuleType:
    return importlib.import_module("fetch_prices")


@pytest.fixture
def fetch_sec(script_root: Path) -> ModuleType:
    return importlib.import_module("fetch_sec")


@pytest.fixture
def stock_recap_fetch_sec(stock_recap_script_root: Path) -> ModuleType:
    return importlib.import_module("fetch_sec")


@pytest.fixture
def fetch_transcript(script_root: Path) -> ModuleType:
    return importlib.import_module("fetch_transcript")


@pytest.fixture
def update_index(script_root: Path) -> ModuleType:
    return importlib.import_module("update_index")


@pytest.fixture
def upsert_ticker(script_root: Path) -> ModuleType:
    return importlib.import_module("upsert_ticker")


@pytest.fixture
def cfg(script_root: Path) -> ModuleType:
    return importlib.import_module("_lib.config")


@pytest.fixture
def fm(script_root: Path) -> ModuleType:
    return importlib.import_module("_lib.frontmatter")


@pytest.fixture
def sec(script_root: Path) -> ModuleType:
    return importlib.import_module("_lib.sec_client")


@pytest.fixture
def tr(script_root: Path) -> ModuleType:
    return importlib.import_module("_lib.ticker_resolver")


@pytest.fixture
def yfa(script_root: Path) -> ModuleType:
    return importlib.import_module("_lib.yf_adapter")


@pytest.fixture
def validate_financials(stock_research_script_root: Path) -> ModuleType:
    return importlib.import_module("validate_financials")
