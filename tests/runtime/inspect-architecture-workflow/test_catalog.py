"""The rule catalog agrees with the registry, the defaults, and its own readability rules."""

import json
import re
import shlex
from functools import cache

import pytest

from support import SKILL_DIR, copy_fixture, init_repo, run_arch, run_node

REFERENCES = SKILL_DIR / "references"
RULES_DIR = REFERENCES / "rules"
VOCABULARY = RULES_DIR / "vocabulary.md"
METRICS = REFERENCES / "metrics.md"
CLASSIFICATION = REFERENCES / "classification.md"

GROUP_RULES = {
    "cross-cutting": range(1, 4),
    "dependency-direction": range(4, 10),
    "reasons-to-change": range(10, 17),
    "business-rule-placement": range(17, 20),
    "humble-objects": range(20, 23),
    "deferral-and-boundaries": range(23, 27),
    "components-and-stability": range(27, 34),
    "tests": range(34, 38),
    "enforcement-and-organization": range(38, 42),
}
CONDITIONS_HEADER = "| Id | Condition | Rule | Decided by | Severity | Defect |"
RULE_HEADING = re.compile(r"^### (R\d+)\. (.+)$")
NOT_A_FINDING = "Not a finding when:"
GUIDANCE = "Guidance: advisory by default."
LEGACY_ADVISORY = "Advisory by default in a legacy baseline."
HANDED_OFF = "Reported to the reviewers who own it."
DESIGN_SCOPE_ONLY = "Evaluated only when the session's scope includes a design or topology decision."
HANDED_OFF_RULES = {"R15", "R37"}
DESIGN_SCOPE_RULES = {"R24", "R29", "R33"}
KNOB = re.compile(r"\{([a-z][A-Za-z]*)\}")
BANNED_PHRASES = ["fewer than half", "a quarter of", "three or more", "two or more recent"]
RETIRED_WORDS = re.compile(r"\b(evaluator|ledger|slice|packet)", re.IGNORECASE)
NUMBERED_STEP = re.compile(r"^\s*\d+\.\s")
RULE_NUMBER = re.compile(r"\bR\d+\b")
NUMBER_WORDS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
                "twice", "half", "quarter", "several", "dozen"]
NUMBER_IN_TEXT = re.compile(rf"\d|\b({'|'.join(NUMBER_WORDS)})\b", re.IGNORECASE)
PLURAL_NOT_A_THRESHOLD = re.compile(r"\bmore than one\b", re.IGNORECASE)
NO_EXEMPTION = "no exemption."
CLAUSE_START = re.compile(r"^`[a-z]+(?:-[a-z]+)+`: ")
REQUIRED_TERMS = ["Port", "Storage port", "Adapter", "Gateway", "Plugin", "Device boundary", "Collected evidence",
                  "Metrics", "Presenter"]

REGISTRY_SCRIPT = """
import { CHECKS, JUDGMENTS, RULE_TITLES } from "./scripts/lib/checks/registry.mjs";
import {
  DEFAULT_KINDS, DEFAULT_STATUSES, DEFAULT_THRESHOLDS, THRESHOLD_DESCRIPTIONS,
} from "./scripts/lib/model/defaults.mjs";
const entry = (kind) => (item) => ({
  kind, id: item.id, group: item.group, rules: item.rules, severity: item.severity, defect: item.defect,
  facts: item.facts ?? [], condition: item.condition ?? null,
});
console.log(JSON.stringify({
  entries: [...CHECKS.map(entry("check")), ...JUDGMENTS.map(entry("judgment"))],
  titles: RULE_TITLES,
  kinds: DEFAULT_KINDS,
  statuses: DEFAULT_STATUSES,
  thresholds: DEFAULT_THRESHOLDS,
  descriptions: THRESHOLD_DESCRIPTIONS,
}));
"""


@cache
def registry() -> dict:
    result = run_node(REGISTRY_SCRIPT, SKILL_DIR)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def group_file(group: str):
    return RULES_DIR / f"{group}.md"


def catalog_files() -> list:
    return [*sorted(RULES_DIR.glob("*.md")), METRICS, CLASSIFICATION]


def cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def table_rows(text: str, header: str) -> list[list[str]]:
    lines = text.splitlines()
    rows = []
    for index, line in enumerate(lines):
        if line.strip() != header:
            continue
        for row in lines[index + 2:]:
            if not row.startswith("|"):
                break
            rows.append(cells(row))
    return rows


def condition_rows(group: str) -> dict[str, list[list[str]]]:
    rows: dict[str, list[list[str]]] = {}
    for row in table_rows(group_file(group).read_text(), CONDITIONS_HEADER):
        rows.setdefault(row[0].strip("`"), []).append(row)
    return rows


def rule_sections() -> dict[str, dict]:
    sections = {}
    for group in GROUP_RULES:
        lines = group_file(group).read_text().splitlines()
        current = None
        for line in lines:
            heading = RULE_HEADING.match(line)
            if heading:
                current = heading.group(1)
                assert current not in sections, f"{current} has two headings"
                sections[current] = {"group": group, "title": heading.group(2), "lines": []}
            elif line.startswith("#"):
                current = None
            elif current:
                sections[current]["lines"].append(line)
    return sections


def first_paragraph(lines: list[str]) -> str:
    paragraph = []
    for line in lines:
        if not line.strip():
            if paragraph:
                break
            continue
        paragraph.append(line.strip())
    return " ".join(paragraph)


def decided_by(entry: dict) -> str:
    if entry["kind"] == "judgment":
        return "judgment"
    if entry["facts"]:
        return f"check (needs {', '.join(entry['facts'])})"
    return "check"


def rules_in(cell: str) -> list[str]:
    return re.findall(r"R\d+", cell)


def test_every_registry_entry_has_one_matching_catalog_row():
    problems = []
    for entry in registry()["entries"]:
        rows = condition_rows(entry["group"]).get(entry["id"], [])
        if len(rows) != 1:
            problems.append(f"{entry['id']}: {len(rows)} rows in {entry['group']}.md")
            continue
        _, condition, rule, decided, severity, defect = rows[0]
        if rules_in(rule) != entry["rules"]:
            problems.append(f"{entry['id']}: rules {rule!r}, registry {entry['rules']}")
        if decided != decided_by(entry):
            problems.append(f"{entry['id']}: decided by {decided!r}, expected {decided_by(entry)!r}")
        if severity != entry["severity"]:
            problems.append(f"{entry['id']}: severity {severity!r}, registry {entry['severity']!r}")
        if defect.strip("`") != entry["defect"]:
            problems.append(f"{entry['id']}: defect {defect!r}, registry {entry['defect']!r}")
        if entry["kind"] == "judgment" and condition != entry["condition"]:
            problems.append(f"{entry['id']}: condition differs from the registry sentence")
        if entry["kind"] == "check" and not condition.endswith("."):
            problems.append(f"{entry['id']}: condition is not one plain sentence")
    assert not problems, "\n".join(problems)


def test_no_catalog_row_without_a_registry_entry():
    known = {(entry["group"], entry["id"]) for entry in registry()["entries"]}
    strays = [
        f"{group}.md: {row_id}"
        for group in GROUP_RULES
        for row_id in condition_rows(group)
        if (group, row_id) not in known
    ]
    assert not strays, "rows with no registry entry:\n" + "\n".join(strays)


def test_every_registry_entry_cites_rules_of_its_own_group():
    misplaced = [
        f"{entry['id']} ({entry['group']}): {rule}"
        for entry in registry()["entries"]
        for rule in entry["rules"]
        if int(rule[1:]) not in GROUP_RULES[entry["group"]]
    ]
    assert not misplaced, "\n".join(misplaced)


def test_rule_titles_match_the_registry():
    sections = rule_sections()
    titles = registry()["titles"]
    assert sorted(sections, key=lambda rule: int(rule[1:])) == [f"R{n}" for n in range(1, 42)]
    for rule, section in sections.items():
        assert section["title"] == titles[rule], rule
        assert int(rule[1:]) in GROUP_RULES[section["group"]], f"{rule} sits in {section['group']}.md"


def conditions_by_rule() -> dict[str, set[str]]:
    ids: dict[str, set[str]] = {}
    for entry in registry()["entries"]:
        for rule in entry["rules"]:
            ids.setdefault(rule, set()).add(entry["id"])
    return ids


def test_condition_cells_state_no_number_outside_a_knob():
    for group in GROUP_RULES:
        for row_id, rows in condition_rows(group).items():
            condition = PLURAL_NOT_A_THRESHOLD.sub("", RULE_NUMBER.sub("", KNOB.sub("", rows[0][1])))
            assert not NUMBER_IN_TEXT.search(condition), f"{row_id}: condition states a number: {rows[0][1]!r}"


def not_a_finding_clauses(line: str) -> list[str]:
    return line[len(NOT_A_FINDING):].strip().split("; ")


def test_not_a_finding_clauses_name_the_condition_they_exempt():
    by_rule = conditions_by_rule()
    for rule, section in rule_sections().items():
        own = by_rule.get(rule, set())
        line = next(line for line in section["lines"] if line.startswith(NOT_A_FINDING))
        named = set(re.findall(r"`([a-z]+(?:-[a-z]+)+)`: ", line))
        assert named <= own, f"{rule}: names conditions of another rule: {sorted(named - own)}"
        if len(own) < 2:
            continue
        for clause in not_a_finding_clauses(line):
            start = CLAUSE_START.match(clause)
            assert start, f"{rule}: clause names no condition id: {clause!r}"
            exemption = clause[start.end():].rstrip(".") + "."
            assert exemption == NO_EXEMPTION or len(exemption) > 30, f"{rule}: clause names no situation: {clause!r}"


def rule_references(path):
    for block in path.read_text().split("\n\n"):
        text = " ".join(line.strip() for line in block.splitlines() if not line.startswith(("#", "|")))
        for match in re.finditer(r"\bR(\d+)\b", text):
            yield int(match.group(1)), text[match.end():]


def test_references_to_other_groups_carry_the_rule_title():
    titles = registry()["titles"]
    for path in catalog_files():
        own = GROUP_RULES.get(path.stem, range(0))
        for number, rest in rule_references(path):
            if number in own:
                assert not rest.startswith(" ("), f"{path.name}: R{number} is in this group and needs no title"
                continue
            expected = f" ({titles[f'R{number}']})"
            assert rest.startswith(expected), f"{path.name}: R{number} must be followed by{expected}"


def test_every_rule_has_a_not_a_finding_when_line():
    lines = {}
    for rule, section in rule_sections().items():
        found = [line for line in section["lines"] if line.startswith(NOT_A_FINDING)]
        assert len(found) == 1, f"{rule} has {len(found)} '{NOT_A_FINDING}' lines"
        assert len(found[0]) > len(NOT_A_FINDING) + 20, f"{rule}: the line names no situation"
        lines[rule] = found[0]
    assert len(set(lines.values())) == len(lines), "two rules share the same 'Not a finding when' line"


def test_advisory_markers_agree_with_default_statuses():
    statuses = registry()["statuses"]
    for rule, section in rule_sections().items():
        greenfield = statuses["greenfield"][rule]
        legacy = statuses["legacy"][rule]
        markers = first_paragraph(section["lines"])
        text = "\n".join(section["lines"])
        expected = {
            GUIDANCE: greenfield == "advisory" and legacy == "advisory",
            LEGACY_ADVISORY: greenfield == "enforced" and legacy == "advisory",
            HANDED_OFF: rule in HANDED_OFF_RULES,
            DESIGN_SCOPE_ONLY: rule in DESIGN_SCOPE_RULES,
        }
        for marker, wanted in expected.items():
            assert (marker in markers) == wanted, f"{rule}: marker {marker!r} expected {wanted}"
            assert text.count(marker) == (1 if wanted else 0), f"{rule}: {marker!r} appears outside the markers"


def test_catalog_uses_knob_names_not_numbers():
    knobs = set(registry()["thresholds"])
    for path in catalog_files():
        text = path.read_text()
        unknown = set(KNOB.findall(text)) - knobs
        assert not unknown, f"{path.name}: unknown knobs {sorted(unknown)}"
        for phrase in BANNED_PHRASES:
            assert phrase not in text.lower(), f"{path.name}: states a threshold as {phrase!r}"


def test_judgment_conditions_use_known_knobs():
    knobs = set(registry()["thresholds"])
    for entry in registry()["entries"]:
        if entry["kind"] == "judgment":
            assert set(KNOB.findall(entry["condition"])) <= knobs, entry["id"]


def vocabulary_terms() -> list[str]:
    return [row[0] for row in table_rows(VOCABULARY.read_text(), "| Term | Meaning |")]


def test_each_vocabulary_term_is_defined_once():
    terms = vocabulary_terms()
    assert len(terms) == len(set(term.lower() for term in terms)), "a term is defined twice in vocabulary.md"
    for term in REQUIRED_TERMS:
        assert term in terms, f"vocabulary.md does not define {term}"
    lowered = {term.lower() for term in terms}
    for path in sorted(REFERENCES.rglob("*.md")):
        if path == VOCABULARY:
            continue
        lines = path.read_text().splitlines()
        for index, line in enumerate(lines):
            is_header = index + 1 < len(lines) and lines[index + 1].startswith("|---")
            if line.startswith("|") and not is_header and cells(line)[0].lower() in lowered:
                pytest.fail(f"{path.name} redefines {cells(line)[0]!r} in a table")
            bold = re.match(r"^\*\*([^*]+?)\.?\*\*", line)
            if bold and bold.group(1).lower() in lowered:
                pytest.fail(f"{path.name} redefines {bold.group(1)!r}")


def test_every_reference_file_opens_with_a_paragraph():
    for path in sorted(REFERENCES.rglob("*.md")):
        blocks = [block.strip() for block in path.read_text().split("\n\n") if block.strip()]
        assert blocks[0].startswith("# ") and "\n" not in blocks[0], f"{path.name}: no title line"
        opening = blocks[1]
        assert not opening.startswith(("#", "|", "-", "*", "`", ">")), f"{path.name}: does not open with a paragraph"
        assert not NUMBERED_STEP.match(opening), f"{path.name}: opens with a numbered step"


def test_catalog_has_no_numbered_procedures():
    for path in catalog_files():
        in_code = False
        for line in path.read_text().splitlines():
            if line.startswith("```"):
                in_code = not in_code
            assert in_code or not NUMBERED_STEP.match(line), f"{path.name}: numbered step {line!r}"


def test_catalog_names_no_retired_mechanism():
    for path in catalog_files():
        match = RETIRED_WORDS.search(path.read_text())
        assert not match, f"{path.name} mentions {match.group(0)!r}"


def test_metrics_lists_every_knob_with_its_default():
    rows = table_rows(METRICS.read_text(), "| Knob | Default | Meaning |")
    listed = {row[0].strip("`{}"): (row[1], row[2]) for row in rows}
    defaults = registry()["thresholds"]
    descriptions = registry()["descriptions"]
    assert set(listed) == set(defaults)
    for knob, value in defaults.items():
        assert listed[knob] == (str(value), descriptions[knob]), knob


def test_classification_kinds_table_matches_the_defaults():
    rows = table_rows(CLASSIFICATION.read_text(), "| Kind | Role | Ring | Recognize by |")
    listed = {row[0].strip("`"): (row[1], row[2].strip("`")) for row in rows}
    kinds = registry()["kinds"]
    assert set(listed) == set(kinds)
    for kind, default in kinds.items():
        assert listed[kind] == (default["role"], default["ring"] or "none"), kind


def test_classification_shows_the_model_commands():
    text = CLASSIFICATION.read_text()
    for command in ["arch model classify", "arch model add-component", "arch model add-port", "arch model explain"]:
        assert command in text, command


def test_old_catalog_files_are_gone():
    for name in ["preface.md", *[f"w{n}.md" for n in range(1, 9)]]:
        assert not (RULES_DIR / name).exists(), name
    assert not (REFERENCES / "workflows").exists()
    assert not (REFERENCES / "mapping.md").exists()


def not_a_finding_line(rule: str) -> str:
    return next(line for line in rule_sections()[rule]["lines"] if line.startswith(NOT_A_FINDING))


def clause_for(rule: str, condition: str) -> str:
    clauses = not_a_finding_clauses(not_a_finding_line(rule))
    return next(clause for clause in clauses if clause.startswith(f"`{condition}`"))


def test_the_port_r4_requires_is_never_an_abstraction_without_reason():
    exemption = not_a_finding_line("R8")
    assert "the port R4 requires between policy and a store, a vendor, or another external agency" in exemption
    assert "even with one implementer" in exemption
    assert "the port R4 (Dependencies point toward policy) requires" in clause_for("R25", "boundary-defers-nothing")


def test_r6_raises_the_direct_call_only_for_more_than_one_delivery_mechanism():
    text = " ".join("\n".join(rule_sections()["R6"]["lines"]).split())
    assert "only when controllers of more than one component call the same use case" in text
    row = condition_rows("dependency-direction")["controller-imports-use-case"][0]
    assert row[1].startswith("Controllers of more than one component import the same use-case unit")
    assert "returns its result to its caller" in clause_for("R6", "use-case-names-its-details")


def test_distance_is_a_screen_and_never_a_verdict():
    text = " ".join("\n".join(rule_sections()["R32"]["lines"]).split())
    assert "Distance is a screen" in text and "never on its own a finding" in text
    for rule in ["R28", "R32"]:
        assert first_paragraph(rule_sections()[rule]["lines"]).startswith(GUIDANCE), rule


UNRECORDED_STRUCTURE = "no change in scope was made harder by"


def test_judgments_about_unrecorded_structure_need_a_change_made_harder():
    for rule, condition in [
        ("R27", "thin-use-of-unpublished-component"),
        ("R28", "change-history-without-groups"),
        ("R38", "unconsumed-export-of-unpublished-component"),
    ]:
        assert UNRECORDED_STRUCTURE in clause_for(rule, condition), condition


CLASSIFY_ARGUMENTS = ["before=", "ring=", "actors=", "value-type=true", "reason="]
CODE_BLOCK = re.compile(r"^```(json)?\n(.*?)^```", re.MULTILINE | re.DOTALL)


def test_classification_gives_one_example_for_each_classify_argument():
    text = CLASSIFICATION.read_text()
    for argument in CLASSIFY_ARGUMENTS:
        items = re.findall(rf"^- `{re.escape(argument)}.*?(?=^- |^$)", text, re.MULTILINE | re.DOTALL)
        assert len(items) == 1, f"classification.md does not explain {argument} once"
        assert "`arch model classify" in items[0], f"{argument} has no example"


def test_classification_commands_build_the_component_it_shows(tmp_path):
    root = copy_fixture("known-defects", tmp_path / "project")
    init_repo(root)
    blocks = CODE_BLOCK.findall(CLASSIFICATION.read_text())
    shown = json.loads(next(body for kind, body in blocks if kind == "json"))
    commands = next(body for kind, body in blocks if not kind and "arch model add-component" in body)
    for line in commands.splitlines():
        result = run_arch(shlex.split(line)[1:], root)
        assert result.returncode == 0, f"{line}: {result.stderr}"
    model = json.loads((root / "docs/architecture/architecture.json").read_text())
    built = next(component for component in model["components"] if component["name"] == shown["name"])
    assert built == shown
