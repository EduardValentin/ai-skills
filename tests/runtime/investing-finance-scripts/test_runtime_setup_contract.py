"""Finance runtime setup and dependency parity contracts."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
STOCK_RESEARCH_ROOT = (
    REPO_ROOT / "skills" / "investing-finance" / "stock-research"
)
SKILL_ROOTS = (STOCK_RESEARCH_ROOT,)
SKILL_IDS = ("stock-research",)
STOCK_RESEARCH_EVALS = STOCK_RESEARCH_ROOT / "evals" / "evals.json"
FINANCE_RUNTIME_REQUIREMENTS = (
    "requests==2.34.2",
    "yfinance==0.2.40",
    "beautifulsoup4==4.12.0",
    "lxml==5.0.0",
    "PyYAML==6.0",
)
DOCUMENTED_BUNDLED_PYTHON_INVOCATION = re.compile(
    r"<skill-python>(?:`)?\s+(?!-B(?:\s|`))"
    r"(?=(?:--|-|<scripts_dir>|<skill-scripts-dir>|<skill_scripts_dir>))"
)
DOCUMENTED_PYTHON_INTERPRETER_INVOCATION = re.compile(
    r'(?:\bpython3|"[^"\n]*/bin/python")\s+(?!-B(?:\s|`))'
)


def _tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | str]]:
    snapshot: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = ("symlink", os.readlink(path))
        elif path.is_dir():
            snapshot[relative] = ("directory", b"")
        else:
            snapshot[relative] = ("file", path.read_bytes())
    return snapshot


@pytest.mark.parametrize("skill_root", SKILL_ROOTS, ids=SKILL_IDS)
def test_finance_setup_never_references_a_skill_local_virtualenv(
    skill_root: Path,
) -> None:
    forbidden = (".venv/bin", "venv .venv", "scripts/.venv")
    violations = []
    for path in skill_root.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in forbidden):
            violations.append(path.relative_to(skill_root).as_posix())

    assert violations == []


@pytest.mark.parametrize("skill_root", SKILL_ROOTS, ids=SKILL_IDS)
def test_skill_setup_documents_external_runtime_fallbacks(skill_root: Path) -> None:
    skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")

    assert "AI_SKILLS_RUNTIME_HOME" in skill_text
    assert "${XDG_CACHE_HOME}/ai-skills" in skill_text
    assert "${HOME}/.cache/ai-skills" in skill_text
    assert "<skill-python>" in skill_text
    assert "the skill's own caches" not in skill_text


@pytest.mark.parametrize("skill_root", SKILL_ROOTS, ids=SKILL_IDS)
def test_documented_bundled_python_invocations_disable_bytecode(
    skill_root: Path,
) -> None:
    violations = []
    for path in skill_root.rglob("*.md"):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if (
                DOCUMENTED_BUNDLED_PYTHON_INVOCATION.search(line)
                or DOCUMENTED_PYTHON_INTERPRETER_INVOCATION.search(line)
            ):
                violations.append(
                    f"{path.relative_to(skill_root).as_posix()}:{line_number}"
                )

    assert violations == []


@pytest.mark.parametrize("skill_root", SKILL_ROOTS, ids=SKILL_IDS)
def test_python_usage_blocks_disable_bytecode(skill_root: Path) -> None:
    violations = []
    for path in (skill_root / "scripts").glob("*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        for usage_index, line in enumerate(lines):
            if line.strip() != "Usage:":
                continue
            invocation = next(
                (
                    candidate.strip()
                    for candidate in lines[usage_index + 1 :]
                    if candidate.strip()
                ),
                "",
            )
            if not invocation.startswith(
                "<skill-python> -B <scripts-dir>/"
            ):
                violations.append(path.relative_to(skill_root).as_posix())

    assert violations == []


@pytest.mark.parametrize("skill_root", SKILL_ROOTS, ids=SKILL_IDS)
def test_normal_subprocess_invocations_leave_copied_install_unchanged(
    skill_root: Path,
    fixtures_dir: Path,
    tmp_path: Path,
) -> None:
    installed_root = tmp_path / "installed" / skill_root.name
    shutil.copytree(skill_root, installed_root)
    before = _tree_snapshot(installed_root)

    runtime_home = (tmp_path / "runtime-home").resolve()
    env = os.environ.copy()
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env.pop("PYTHONPYCACHEPREFIX", None)
    env["AI_SKILLS_RUNTIME_HOME"] = str(runtime_home)
    env["PYTHONPATH"] = str(installed_root / "scripts")

    helper = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "from _lib.config import ai_skills_runtime_home; "
            "print(ai_skills_runtime_home())",
        ],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert helper.stdout.strip() == str(runtime_home)

    subprocess.run(
        [
            sys.executable,
            "-B",
            str(installed_root / "scripts" / "extract_10k_sections.py"),
            "TEST",
            "--html",
            str(fixtures_dir / "tenk_sample.html"),
            "--year",
            "2025",
            "--out",
            str(tmp_path / "script-output"),
        ],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert _tree_snapshot(installed_root) == before
    assert list(installed_root.rglob("__pycache__")) == []


def test_stock_research_evals_use_external_finance_runtime_contract() -> None:
    evals_text = STOCK_RESEARCH_EVALS.read_text(encoding="utf-8")

    assert "AI_SKILLS_RUNTIME_HOME" in evals_text
    assert "${XDG_CACHE_HOME}/ai-skills" in evals_text
    assert "${HOME}/.cache/ai-skills" in evals_text
    assert "skill-local" not in evals_text
    assert "scripts/.venv" not in evals_text


def test_finance_test_harness_does_not_globally_disable_bytecode() -> None:
    conftest_text = Path(__file__).with_name("conftest.py").read_text(
        encoding="utf-8"
    )

    assert "dont_write_bytecode" not in conftest_text


def test_bundled_finance_requirements_are_synchronized_and_exact() -> None:
    bundled = [
        tuple(
            (skill_root / "scripts" / "requirements.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        for skill_root in SKILL_ROOTS
    ]

    assert bundled == [FINANCE_RUNTIME_REQUIREMENTS]


def test_test_requirements_include_every_finance_runtime_dependency() -> None:
    test_requirements = set(
        (REPO_ROOT / "requirements-test.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )

    assert set(FINANCE_RUNTIME_REQUIREMENTS) <= test_requirements
