import json
import re
from pathlib import Path

import pytest

from support import FIXTURES, SKILL_DIR, copy_fixture, run_arch, run_node

CHECKS_DIR = SKILL_DIR / "scripts" / "lib" / "checks"
RUN_MODULE = (CHECKS_DIR / "run.mjs").as_uri()
DEFAULTS_MODULE = (SKILL_DIR / "scripts" / "lib" / "model" / "defaults.mjs").as_uri()
README = FIXTURES / "known-defects" / "README.md"
MODEL = "docs/architecture/architecture.json"
ADAPTER = "adapter.json"
SEVERITIES = ["minor", "major", "blocker"]
SEEDED_LINE = re.compile(r"^\| `([^`]+)` \| `([a-z-]+)` \| (R[0-9, R]+) \| `([a-z-]+)` \|$")

NEW_CONDITIONS = {
    "port-owner-below-consumer": ("R5", "blocker"),
    "port-signature-detail-type": ("R5", "blocker"),
    "policy-detail-edge-beside-port": ("R5", "blocker"),
    "controller-imports-use-case": ("R6", "blocker"),
    "entity-imports-non-entity": ("R17", "blocker"),
    "entity-imports-use-case": ("R18", "blocker"),
    "boundary-data-imports": ("R19", "blocker"),
    "presenter-imports-ui-framework": ("R21", "major"),
    "plugin-imports-plugin": ("R25", "major"),
    "production-imports-test": ("R34", "blocker"),
    "unenforced-component": ("R38", "major"),
    "deep-import": ("R38", "major"),
    "forbidden-edge-present": ("R39", "major"),
    "distance-over-threshold": ("R32", "minor"),
    "type-check-on-implementation": ("R13", "major"),
    "thin-component-use": ("R27", "minor"),
    "unconsumed-export": ("R38", "major"),
}
FACTS_OF = {
    "port-signature-detail-type": ["signatures"],
    "policy-detail-edge-beside-port": ["implements"],
    "plugin-imports-plugin": ["implements"],
    "distance-over-threshold": ["exports"],
    "type-check-on-implementation": ["typeChecks"],
    "thin-component-use": ["symbolImports"],
    "unconsumed-export": ["signatures", "symbolImports"],
}
FACT_CASES = [(check, fact) for check, facts in FACTS_OF.items() for fact in facts]
FRAMEWORK_ROW = "src/lending/member.ts -> external:orm"


def seeded() -> list[dict]:
    entries = []
    for line in README.read_text().splitlines():
        match = SEEDED_LINE.match(line)
        if match:
            target, check, rules, defect = match.groups()
            entries.append({"target": target, "check": check, "rules": rules.split(", "), "defect": defect})
    return entries


def edit_json(path: Path, change) -> None:
    document = json.loads(path.read_text())
    change(document)
    path.write_text(json.dumps(document))


def model_edit(root: Path, *args: str) -> None:
    result = run_arch(["model", *args], root)
    assert result.returncode == 0, result.stderr


def check_output(root: Path) -> dict:
    result = run_arch(["check", "--json"], root)
    assert result.returncode in (0, 1), result.stderr
    return json.loads(result.stdout)


def fixture_root(tmp_path: Path) -> Path:
    return copy_fixture("known-defects", tmp_path / "p")


def ids_of(row: dict) -> list[str]:
    return row["check"].split(", ")


def rows_at(rows: list[dict], target: str, check: str) -> list[dict]:
    return [row for row in rows if row["target"] == target and check in ids_of(row)]


def rows_of(rows: list[dict], check: str) -> list[dict]:
    return [row for row in rows if check in ids_of(row)]


def test_readme_lists_every_new_condition_and_every_existing_check():
    listed = {entry["check"] for entry in seeded()}
    assert set(NEW_CONDITIONS) <= listed
    assert {"policy-imports-detail", "policy-imports-external", "outward-ring-edge", "detail-constructed-outside-root",
            "component-cycle", "module-cycle", "unstable-dependency", "unused-abstractions"} <= listed


def test_check_reports_exactly_the_seeded_set(tmp_path: Path):
    out = check_output(fixture_root(tmp_path))
    reported = {(row["target"], check) for row in out["rows"] for check in ids_of(row)}
    expected = {(entry["target"], entry["check"]) for entry in seeded()}
    assert reported == expected
    assert out["incomplete"] == []
    assert len(out["rows"]) == len({(row["target"], row["defect"]) for row in out["rows"]})


@pytest.mark.parametrize("check", sorted(NEW_CONDITIONS))
def test_each_new_condition_yields_one_row_per_seeded_target(tmp_path: Path, check: str):
    rule, severity = NEW_CONDITIONS[check]
    rows = check_output(fixture_root(tmp_path))["rows"]
    entries = [entry for entry in seeded() if entry["check"] == check]
    assert entries, check
    for entry in entries:
        (row,) = rows_at(rows, entry["target"], check)
        assert rule in row["rules"] and set(entry["rules"]) <= set(row["rules"])
        assert row["defect"] == entry["defect"]
        assert SEVERITIES.index(row["severity"]) >= SEVERITIES.index(severity)
        assert row["status"] == "enforced" and row["origin"] == "none"
    assert len(rows_of(rows, check)) == len(entries)


def test_entity_importing_a_framework_is_one_row_with_two_rules(tmp_path: Path):
    rows = check_output(fixture_root(tmp_path))["rows"]
    (row,) = [r for r in rows if r["target"] == FRAMEWORK_ROW]
    assert row["rules"] == ["R4", "R17"]
    assert row["defect"] == "policy-depends-on-detail"
    assert ids_of(row) == ["policy-imports-external", "entity-imports-non-entity"]


def test_entity_importing_a_declared_value_type_is_not_a_row(tmp_path: Path):
    rows = check_output(fixture_root(tmp_path))["rows"]
    assert not [r for r in rows if r["target"] == "src/lending/loan.ts -> src/lending/loan-period.ts"]
    root = fixture_root(tmp_path / "again")
    edit_json(root / MODEL, lambda d: d["components"][0]["classify"][0][2].pop("valueType"))
    rows = check_output(root)["rows"]
    (row,) = rows_at(rows, "src/lending/loan.ts -> src/lending/loan-period.ts", "entity-imports-non-entity")
    assert row["defect"] == "entity-depends-outward"


def test_deep_import_is_not_run_without_published_globs(tmp_path: Path):
    root = fixture_root(tmp_path)
    edit_json(root / ADAPTER, lambda d: d["capabilities"].update(symbolImports=False))
    edit_json(root / MODEL, lambda d: d["components"][4].pop("published"))
    out = check_output(root)
    assert not rows_of(out["rows"], "deep-import") and not rows_of(out["rows"], "unconsumed-export")
    assert not [e for e in out["incomplete"] if e["check"] in ("deep-import", "unconsumed-export")]


@pytest.mark.parametrize(("check", "fact"), FACT_CASES)
def test_each_fact_dependent_check_is_incomplete_without_its_fact(tmp_path: Path, check: str, fact: str):
    root = fixture_root(tmp_path)
    edit_json(root / ADAPTER, lambda d: d["capabilities"].update({fact: False}))
    out = check_output(root)
    entries = [e for e in out["incomplete"] if e["check"] == check]
    assert len(entries) == 1 and fact in entries[0]["reason"]
    assert entries[0]["rules"] == [NEW_CONDITIONS[check][0]]
    assert not rows_of(out["rows"], check)


def test_registry_facts_match_the_fact_table():
    script = (
        f"import {{ CHECKS }} from {json.dumps((CHECKS_DIR / 'registry.mjs').as_uri())};"
        "console.log(JSON.stringify(CHECKS.map((c) => [c.id, c.facts, c.rules, c.defect, c.severity])));"
    )
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    by_id = {entry[0]: entry for entry in json.loads(result.stdout)}
    assert set(NEW_CONDITIONS) <= set(by_id)
    for check, (rule, severity) in NEW_CONDITIONS.items():
        _, facts, rules, _, base = by_id[check]
        assert facts == FACTS_OF.get(check, []) and rules == [rule] and base == severity


def test_threshold_knob_changes_thin_component_use(tmp_path: Path):
    root = fixture_root(tmp_path)
    assert [r["target"] for r in rows_of(check_output(root)["rows"], "thin-component-use")] == ["web -> reports"]
    model_edit(root, "set-threshold", "componentUseShare", "0.9")
    thin = [r["target"] for r in rows_of(check_output(root)["rows"], "thin-component-use")]
    assert "web -> reports" in thin and len(thin) > 1
    model_edit(root, "set-threshold", "componentUseShare", "0")
    assert not rows_of(check_output(root)["rows"], "thin-component-use")


def test_thin_component_use_is_incomplete_for_a_pair_whose_edges_name_no_symbols(tmp_path: Path):
    root = fixture_root(tmp_path)

    def drop_symbols(document: dict) -> None:
        for edge in document["edges"]:
            if edge.get("to") == "src/reports/monthly-report.ts":
                edge.pop("symbols")

    edit_json(root / ADAPTER, drop_symbols)
    out = check_output(root)
    assert not rows_at(out["rows"], "web -> reports", "thin-component-use")
    (entry,) = [e for e in out["incomplete"] if e["check"] == "thin-component-use"]
    assert entry["target"] == "web -> reports" and "symbols" in entry["reason"]


def test_distance_knob_changes_distance_over_threshold(tmp_path: Path):
    root = fixture_root(tmp_path)
    assert [r["target"] for r in rows_of(check_output(root)["rows"], "distance-over-threshold")] == ["reports"]
    model_edit(root, "set-threshold", "distanceDeviations", "10")
    assert not rows_of(check_output(root)["rows"], "distance-over-threshold")


def test_unenforced_component_needs_an_incoming_component_edge(tmp_path: Path):
    root = fixture_root(tmp_path)
    targets = [r["target"] for r in rows_of(check_output(root)["rows"], "unenforced-component")]
    assert targets == ["notify"]
    edit_json(root / MODEL, lambda d: d["components"][2].update(enforcement="none"))
    assert [r["target"] for r in rows_of(check_output(root)["rows"], "unenforced-component")] == ["notify"]
    edit_json(root / MODEL, lambda d: d["components"][2].update(enforcement="boundary-lint"))
    assert not rows_of(check_output(root)["rows"], "unenforced-component")


def test_plugin_edge_inside_one_component_is_not_a_finding(tmp_path: Path):
    root = fixture_root(tmp_path)
    edit_json(root / MODEL, lambda d: d["components"][2].update(paths=["src/notify/**", "src/storage/**"]))
    edit_json(root / MODEL, lambda d: d["components"].pop(1))
    rows = check_output(root)["rows"]
    assert not rows_of(rows, "plugin-imports-plugin")


def test_collect_lists_distance_breaches_in_the_current_picture(tmp_path: Path):
    root = fixture_root(tmp_path)
    result = run_arch(["collect"], root)
    assert result.returncode == 0, result.stderr
    text = (root / "docs/architecture/current.md").read_text()
    breaches = text.split("## Threshold breaches")[1]
    assert re.search(r"^- reports: distance [0-9.]+ beyond the project threshold$", breaches, re.MULTILINE)


def run_with_base(tmp_path: Path, head: list[float], base: list[float]) -> list[dict]:
    def graph(distances: list[float]) -> dict:
        components = [{"name": f"c{i}", "fanIn": 1, "fanOut": 1, "instability": 0.5, "abstractness": 0.5,
                       "distance": distance, "zone": None} for i, distance in enumerate(distances)]
        return {"capabilities": {"exports": True}, "rings": [], "units": [], "edges": [], "externals": [],
                "uncovered": [], "components": components, "componentEdges": [],
                "cycles": {"modules": [], "components": []}}

    script = (
        f"import {{ runChecks }} from {json.dumps(RUN_MODULE)};"
        f"import {{ DEFAULT_KINDS, DEFAULT_THRESHOLDS }} from {json.dumps(DEFAULTS_MODULE)};"
        "const model = { kinds: DEFAULT_KINDS, thresholds: DEFAULT_THRESHOLDS, rules: {}, forbidden: [],"
        " exceptions: [], groups: [], components: [], ports: [] };"
        f"const touched = {json.dumps({'units': [], 'components': [f'c{i}' for i in range(len(head))], 'uncovered': []})};"
        f"console.log(JSON.stringify(runChecks({{ graph: {json.dumps(graph(head))}, model,"
        f" baseGraph: {json.dumps(graph(base))}, touched }})));"
    )
    result = run_node(script, tmp_path)
    assert result.returncode == 0, result.stderr
    return rows_of(json.loads(result.stdout)["rows"], "distance-over-threshold")


def test_distance_that_moved_by_the_jump_is_introduced_even_without_being_an_outlier(tmp_path: Path):
    (row,) = run_with_base(tmp_path, head=[0.4, 0.4, 0.4], base=[0.25, 0.4, 0.4])
    assert (row["target"], row["check"], row["origin"], row["rules"]) == ("c0", "distance-over-threshold", "introduced", ["R32"])


def test_distance_that_did_not_move_stays_inherited(tmp_path: Path):
    (row,) = run_with_base(tmp_path, head=[0.1, 0.1, 0.9], base=[0.1, 0.1, 0.9])
    assert (row["target"], row["origin"]) == ("c2", "inherited")


def test_a_small_move_is_not_a_jump(tmp_path: Path):
    assert run_with_base(tmp_path, head=[0.4, 0.4, 0.4], base=[0.35, 0.4, 0.4]) == []
