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
    "lodash",
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


FENCE_TAG = re.compile(r"^\s*```([A-Za-z0-9_+.-]+)")
NEUTRAL_FENCE_TAGS = {"json", "markdown", "text"}
LANGUAGE_EXTENSION = re.compile(
    r"\.(ts|tsx|js|jsx|mjs|cjs|py|java|kt|go|rb|cs|rs|php|swift|scala|cpp|hpp|c|h)\b"
)
STRING_LITERAL = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`")
IMPORT_LINE = re.compile(r"^\s*(import\b|export\b.*\bfrom\b|\}\s*from\b)|\bimport\(")
LIB_SCRIPTS = sorted((SKILL_DIR / "scripts").rglob("*.mjs"))


def test_no_fenced_block_is_tagged_with_a_language():
    violations = []
    for path in [*SKILL_TEXT, *AGENT_FILES]:
        for index, line in enumerate(path.read_text().splitlines(), start=1):
            match = FENCE_TAG.match(line)
            if match and match.group(1).lower() not in NEUTRAL_FENCE_TAGS:
                violations.append(f"{path.relative_to(REPO_ROOT)}:{index}: {line.strip()}")
    assert not violations, "fenced block tagged with a language:\n" + "\n".join(violations)


def test_command_messages_name_no_file_extension_of_a_language():
    violations = []
    for path in LIB_SCRIPTS:
        for index, line in enumerate(path.read_text().splitlines(), start=1):
            if IMPORT_LINE.search(line):
                continue
            for literal in STRING_LITERAL.findall(line):
                if LANGUAGE_EXTENSION.search(literal):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{index}: {literal}")
    assert not violations, "language file extension in a command message:\n" + "\n".join(violations)


OWN_ENTRY_POINT = "scripts/arch.mjs"
NEUTRAL_PAGES = [*sorted((SKILL_DIR / "references" / "flows").glob("*.md")), SKILL_DIR / "references" / "adapter-contract.md"]


def test_flows_and_the_adapter_contract_name_no_file_extension_of_a_language():
    violations = [
        f"{path.relative_to(REPO_ROOT)}:{index}: {line.strip()}"
        for path in NEUTRAL_PAGES
        for index, line in enumerate(path.read_text().splitlines(), start=1)
        if LANGUAGE_EXTENSION.search(line.replace(OWN_ENTRY_POINT, ""))
    ]
    assert not violations, "language file extension in a flow or the adapter contract:\n" + "\n".join(violations)
