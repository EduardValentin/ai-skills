"""Generic skill text names no concrete tool or language; only the adapter templates may."""

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


def _files_under(directory) -> list:
    return sorted(path for path in directory.rglob("*") if path.is_file() and "__pycache__" not in path.parts)


GENERIC_SCRIPTS = _files_under(SKILL_DIR / "scripts")
SKILL_TEXT = [SKILL_DIR / "SKILL.md", *_files_under(SKILL_DIR / "references")]
AGENT_FILES = sorted((REPO_ROOT / "agents").glob("architecture-*.md"))


def _violations(paths) -> list[str]:
    violations = []
    for path in paths:
        for index, line in enumerate(path.read_text().splitlines(), start=1):
            if WORD_PATTERN.search(line):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{index}: {line.strip()}")
    return violations


def test_generic_text_names_no_tool_or_language():
    violations = _violations([*SKILL_TEXT, *AGENT_FILES])
    assert not violations, "tool or language name in generic skill text:\n" + "\n".join(violations)


def test_generic_scripts_name_no_tool_or_language():
    violations = _violations(GENERIC_SCRIPTS)
    assert not violations, "tool or language name in a generic script:\n" + "\n".join(violations)
