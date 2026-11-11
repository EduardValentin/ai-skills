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


CATALOG = sorted((SKILL_DIR / "references" / "rules").glob("*.md"))
INLINE_CODE = re.compile(r"`([^`]+)`")
LANGUAGE_SYNTAX_PATTERNS = [
    r"\b[A-Z]\w*<\w",
    r"=>",
    r"===",
    r"\bimport\s*\{",
    r"\bfrom\s+[\"']",
    r"\b(export|const|let|private|public|protected|async|await)\s",
    r"\bnew\s+\w+\s*\(",
    r"\binstanceof\b",
    r"\bclass\s+[A-Z]",
    r"\bif\s*\(",
    r"\[\]",
    r"\{\s*\}",
    r"\)\s*:\s*\w",
    r":\s*(string|number|boolean|void)\b",
    r"\bdef\s",
    r"\bself\b",
    r"\bfrom\s+[\w.]+\s+import\s",
    r"\bfunc\s",
    r":=",
    r"\bfn\s",
    r"@[A-Za-z_]\w*\(",
]
LANGUAGE_SYNTAX = re.compile("|".join(LANGUAGE_SYNTAX_PATTERNS))
DECLARATION_KEYWORD = r"\b(export|const|let|private|public|protected|async|await)\s"
DECLARATION = DECLARATION_KEYWORD + r"+(?:\w+\s+)?\w+\s*[=(:;]"
CODE_IN_COMMENT = re.compile(
    "|".join(pattern for pattern in LANGUAGE_SYNTAX_PATTERNS if pattern != DECLARATION_KEYWORD) + "|" + DECLARATION
)
PSEUDOCODE_COMMENT = "//"


def _code_examples(path) -> list[tuple[int, str]]:
    examples = []
    prose_lines = []
    in_fence = False
    for index, line in enumerate(path.read_text().splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            prose_lines.append("")
        elif in_fence:
            examples.append((index, line))
            prose_lines.append("")
        else:
            prose_lines.append(line)
    prose = "\n".join(prose_lines)
    for match in INLINE_CODE.finditer(prose):
        examples.append((prose.count("\n", 0, match.start()) + 1, match.group(1)))
    return examples


def _language_syntax_in(example: str) -> bool:
    code, _, comment = example.partition(PSEUDOCODE_COMMENT)
    code_in_comment = CODE_IN_COMMENT.search(comment)
    return bool(LANGUAGE_SYNTAX.search(code) or ";" in code or code_in_comment or LANGUAGE_EXTENSION.search(example))


def test_catalog_examples_are_written_in_pseudocode():
    violations = [
        f"{path.relative_to(REPO_ROOT)}:{index}: {example.strip()}"
        for path in CATALOG
        for index, example in _code_examples(path)
        if _language_syntax_in(example)
    ]
    assert not violations, "catalog example in a language's syntax:\n" + "\n".join(violations)


CODE_SAMPLES = [
    "def total(order):",
    "return self.items",
    "from billing import Invoice",
    "func Total(o Order) Money",
    "total := sum(lines)",
    "fn total(order: Order) -> Money",
    "public Money total()",
    "protected void apply()",
    '@Entity("loans")',
    "unit Cart: add(i: Item)     // self.items.append(i)",
    "unit Cart: add(i: Item)     // const items = []",
]
PSEUDOCODE_SAMPLES = [
    "unit Cart: add(i: Item), total() -> Money             // items stays private to Cart",
    "interface Users: query(sql: Text) -> List of Row",
    "expect r.interest is \"12.50\"",
    "done = false, repeat until done: ... if x then done = true",
    "unit Loan extends OrmModel, annotated Entity: toJson()",
    "// bad: the use case defines itself by the framework",
]


def test_the_pseudocode_guard_flags_code_in_examples_and_in_their_comments():
    flagged = [sample for sample in CODE_SAMPLES if not _language_syntax_in(sample)]
    assert not flagged, f"not flagged as a language's syntax: {flagged}"
    wrongly = [sample for sample in PSEUDOCODE_SAMPLES if _language_syntax_in(sample)]
    assert not wrongly, f"pseudocode flagged as a language's syntax: {wrongly}"


EXAMPLE_CONSTRUCTS = ["`List of X`", "then", "`repeat until`", "`annotated`", "`expect x is y`",
                      "`component X publishes:`", "`implements`", "`// bad`"]


def test_the_vocabulary_explains_every_example_construct_in_at_most_six_lines():
    vocabulary = (SKILL_DIR / "references" / "rules" / "vocabulary.md").read_text()
    section = vocabulary.split("## How examples are written", 1)[1].strip().splitlines()
    assert len(section) <= 6, section
    text = " ".join(section)
    assert [construct for construct in EXAMPLE_CONSTRUCTS if construct not in text] == []
    assert "how the catalog's examples are written" in " ".join(vocabulary.split("\n## ", 1)[0].split())


def test_publishes_names_only_a_component_surface_in_examples():
    lines = [line for path in CATALOG for _, line in _code_examples(path) if "publishes" in line]
    assert lines and all(line.lstrip().startswith("component ") for line in lines), lines
