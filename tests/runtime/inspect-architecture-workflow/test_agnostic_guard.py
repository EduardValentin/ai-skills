"""Generic skill text names no concrete tool or language."""

import re

from support import REPO_ROOT, SKILL_DIR

BANNED_WORDS = [
    "dependency-cruiser",
    "depcruise",
    "typescript",
    "tsconfig",
    "jdeps",
    "grimp",
    "madge",
    "knip",
    "eslint",
    "javascript",
    "python",
    "java",
    "golang",
]

WORD_PATTERN = re.compile(
    "|".join(rf"\b{re.escape(word)}\b" for word in BANNED_WORDS),
    re.IGNORECASE,
)

COMMAND_MD = SKILL_DIR / "references" / "command.md"
START_MARKER = "<!-- adapters -->"
END_MARKER = "<!-- /adapters -->"

GENERIC_SCRIPTS = [
    SKILL_DIR / "scripts" / "lib" / name for name in ("graph.mjs", "queries.mjs", "assess.mjs", "ledger.mjs")
]

AGENT_FILES = [
    REPO_ROOT / "agents" / "architecture-coordinator.md",
    REPO_ROOT / "agents" / "architecture-evaluator.md",
    REPO_ROOT / "agents" / "architecture-code-auditor.md",
]


def _allowed_line_numbers(path) -> set[int]:
    """Lines inside the adapter markers of command.md; empty for every other file."""
    if path != COMMAND_MD:
        return set()
    lines = path.read_text().splitlines()
    allowed: set[int] = set()
    inside = False
    for index, line in enumerate(lines, start=1):
        if line.strip() == START_MARKER:
            inside = True
            allowed.add(index)
            continue
        if line.strip() == END_MARKER:
            inside = False
            allowed.add(index)
            continue
        if inside:
            allowed.add(index)
    return allowed


def _md_files() -> list:
    files = sorted(SKILL_DIR.rglob("*.md"))
    return files + AGENT_FILES


def _violations(paths) -> list[str]:
    violations = []
    for path in paths:
        allowed = _allowed_line_numbers(path)
        for index, line in enumerate(path.read_text().splitlines(), start=1):
            if index in allowed:
                continue
            if WORD_PATTERN.search(line):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{index}: {line.strip()}")
    return violations


def test_generic_text_names_no_tool_or_language():
    violations = _violations(_md_files())
    assert not violations, "tool or language name outside the adapter markers:\n" + "\n".join(violations)


def test_generic_scripts_name_no_tool_or_language():
    violations = _violations(GENERIC_SCRIPTS)
    assert not violations, "tool or language name in a generic script:\n" + "\n".join(violations)
