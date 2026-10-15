import json
import shutil
from pathlib import Path

from support import FIXTURE_FLAGS, SKILL_DIR, copy_fixture, init_repo, run_arch, run_node

ASSESS = SKILL_DIR / "scripts" / "lib" / "assess.mjs"
COLUMNS = "| Workflow | Target | Rule | Origin | Verdict | Severity | Evidence | Change | Escalation |"
CONTROLLER = "src/web/payroll-controller.ts"
CONSTRUCTION_ROWS = [(f"{CONTROLLER} -> src/adapters/pg-payroll-repository.ts", "R7"),
                     (f"{CONTROLLER} -> src/adapters/system-clock.ts", "R7")]


def seed_edge(root: Path, source: str, resolved: str, dynamic: bool = False) -> None:
    cruise = json.loads((root / "cruise.json").read_text())
    module = next(m for m in cruise["modules"] if m["source"] == source)
    module["dependencies"].append({"module": resolved, "resolved": resolved, "dependencyTypes": ["local", "import"],
                                   "dynamic": dynamic, "couldNotResolve": False, "matchesDoNotFollow": False})
    (root / "cruise.json").write_text(json.dumps(cruise))


def touch(root: Path, *paths: str) -> None:
    for p in paths:
        (root / p).write_text((root / p).read_text() + "\n// changed\n")


def assess_output(root: Path, *args: str) -> dict:
    result = run_arch(["assess", *args, *FIXTURE_FLAGS, "--json"], root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def assess_rows(root: Path, *args: str) -> list[dict]:
    return assess_output(root, *args)["rows"]


def keys(rows: list[dict]) -> list[tuple[str, str]]:
    return [(r["target"], r["rule"]) for r in rows]


def find(rows: list[dict], target: str, rule: str) -> dict:
    matches = [r for r in rows if r["target"] == target and r["rule"] == rule]
    assert len(matches) == 1, rows
    return matches[0]


def repo(tmp_path: Path) -> Path:
    root = copy_fixture("payroll", tmp_path / "p")
    (root / ".gitignore").write_text(".architecture/\n")
    return root


def test_unseeded_fixture_has_only_the_construction_rows_in_audit_mode(tmp_path: Path):
    out = assess_output(copy_fixture("payroll", tmp_path / "p"))
    assert keys(out["rows"]) == CONSTRUCTION_ROWS and out["notProvided"] == []
    row = out["rows"][0]
    assert row["workflow"] == "W1" and row["severity"] == "blocker" and row["origin"] == "introduced"


def test_markdown_header_equals_the_documented_columns(tmp_path: Path):
    result = run_arch(["assess", *FIXTURE_FLAGS], copy_fixture("payroll", tmp_path / "p"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == COLUMNS
    assert COLUMNS in (SKILL_DIR / "references/command.md").read_text()


def test_seeded_component_cycle_yields_cycle_rows(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, "src/domain/employee.ts", CONTROLLER)
    rows = assess_rows(root)
    component_cycle = find(rows, "C1 -> C2 -> C3", "R30")
    assert component_cycle["workflow"] == "W6" and component_cycle["severity"] == "blocker"
    members = sorted(["src/adapters/pg-payroll-repository.ts", "src/adapters/system-clock.ts", "src/domain/employee.ts", "src/domain/index.ts",
                      "src/domain/payroll-repository.ts", "src/domain/payroll-use-case.ts", CONTROLLER])
    assert find(rows, " -> ".join(members), "R30")["severity"] == "blocker"
    assert find(rows, f"src/domain/employee.ts -> {CONTROLLER}", "R4")["workflow"] == "W1"


def test_rule_3_is_recorded_only_when_it_lifts_the_severity(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, "src/domain/employee.ts", "src/domain/payroll-use-case.ts")
    row = find(assess_rows(root), "src/domain/employee.ts -> src/domain/payroll-use-case.ts", "R4")
    assert row["severity"] == "blocker" and row["escalation"] == []


def test_outward_edge_between_components_yields_the_stability_row(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, "src/adapters/system-clock.ts", "src/web/main.ts")
    rows = assess_rows(root)
    assert find(rows, "src/adapters/system-clock.ts -> src/web/main.ts", "R4")["escalation"] == []
    assert find(rows, "C3 -> C2", "R31")["severity"] == "major"


def two_component_change(tmp_path: Path) -> Path:
    root = repo(tmp_path)
    init_repo(root)
    touch(root, "src/domain/employee.ts", "src/web/main.ts")
    return root


def test_change_across_components_without_groups_asks_for_them_until_a_group_covers_it(tmp_path: Path):
    root = two_component_change(tmp_path)
    rows = assess_rows(root, "--base", "HEAD")
    assert [(r["workflow"], r["rule"], r["severity"]) for r in rows] == [("W6", "R28", "minor")]
    added = run_arch(["model", "add-group", "payroll", "components=C1,C3", "absorbs=payroll rules"], root)
    assert added.returncode == 0, added.stderr
    assert assess_rows(root, "--base", "HEAD") == []


def test_r27_rows_are_the_touched_components_that_share_no_group_with_some_other_touched_component(tmp_path: Path):
    root = repo(tmp_path)
    init_repo(root)
    touch(root, "src/domain/employee.ts", "src/adapters/system-clock.ts", "src/web/main.ts")
    assert run_arch(["model", "add-group", "storage", "components=C1,C2", "absorbs=storage"], root).returncode == 0
    assert run_arch(["model", "add-group", "delivery", "components=C2,C3", "absorbs=delivery"], root).returncode == 0
    rows = [r for r in assess_rows(root, "--base", "HEAD") if r["rule"] == "R27"]
    assert keys(rows) == [("C1", "R27"), ("C3", "R27")]
    assert rows[0]["evidence"] == "C1 shares no recorded group with C3; groups holding C1: storage"
    assert rows[1]["evidence"] == "C3 shares no recorded group with C1; groups holding C3: delivery"
    assert {r["severity"] for r in rows} == {"major"}


def test_r27_evidence_says_none_when_no_group_holds_the_component(tmp_path: Path):
    root = two_component_change(tmp_path)
    assert run_arch(["model", "add-group", "core", "components=C1,C2", "absorbs=storage"], root).returncode == 0
    rows = assess_rows(root, "--base", "HEAD")
    assert keys(rows) == [("C1", "R27"), ("C3", "R27")]
    assert rows[1]["evidence"] == "C3 shares no recorded group with C1; groups holding C3: none"


def test_edge_origin_follows_the_pair_against_the_base(tmp_path: Path):
    root = repo(tmp_path)
    seed_edge(root, "src/adapters/system-clock.ts", "src/web/main.ts")
    init_repo(root)
    seed_edge(root, "src/adapters/memory-payroll-repository.ts", "src/web/main.ts")
    seed_edge(root, "src/adapters/system-clock.ts", "src/web/main.ts", dynamic=True)
    touch(root, "src/adapters/system-clock.ts", "src/adapters/memory-payroll-repository.ts")
    rows = assess_rows(root, "--base", "HEAD")
    assert find(rows, "src/adapters/system-clock.ts -> src/web/main.ts", "R4")["origin"] == "left"
    assert find(rows, "src/adapters/memory-payroll-repository.ts -> src/web/main.ts", "R4")["origin"] == "introduced"


def test_a_cycle_the_change_only_shrinks_is_left_in_place(tmp_path: Path):
    root = repo(tmp_path)
    pristine = (root / "cruise.json").read_text()
    seed_edge(root, "src/domain/employee.ts", "src/domain/payroll-use-case.ts")
    seed_edge(root, "src/domain/employee.ts", CONTROLLER)
    init_repo(root)
    (root / "cruise.json").write_text(pristine)
    seed_edge(root, "src/domain/employee.ts", "src/domain/payroll-use-case.ts")
    touch(root, "src/domain/employee.ts")
    rows = assess_rows(root, "--base", "HEAD")
    target = " -> ".join(["src/domain/employee.ts", "src/domain/payroll-repository.ts", "src/domain/payroll-use-case.ts"])
    assert find(rows, target, "R30")["origin"] == "left"


def test_a_cycle_closed_by_an_added_edge_is_introduced(tmp_path: Path):
    root = repo(tmp_path)
    init_repo(root)
    seed_edge(root, "src/domain/employee.ts", "src/domain/payroll-use-case.ts")
    touch(root, "src/domain/employee.ts")
    rows = assess_rows(root, "--base", "HEAD")
    target = " -> ".join(["src/domain/employee.ts", "src/domain/payroll-repository.ts", "src/domain/payroll-use-case.ts"])
    assert find(rows, target, "R30")["origin"] == "introduced"


def test_rows_outside_the_change_are_not_emitted_with_a_base(tmp_path: Path):
    root = repo(tmp_path)
    init_repo(root)
    seed_edge(root, "src/adapters/system-clock.ts", "src/web/main.ts")
    touch(root, "src/domain/employee.ts")
    assert assess_rows(root, "--base", "HEAD") == []
    touch(root, "src/adapters/system-clock.ts")
    assert ("src/adapters/system-clock.ts -> src/web/main.ts", "R4") in keys(assess_rows(root, "--base", "HEAD"))


def test_base_without_a_model_marks_rows_left_except_the_change_and_warns(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    model = tmp_path / "model"
    shutil.move(root / "docs", model)
    init_repo(root)
    shutil.move(model, root / "docs")
    seed_edge(root, "src/adapters/system-clock.ts", "src/web/main.ts")
    touch(root, "src/domain/employee.ts", "src/web/main.ts")
    result = run_arch(["assess", "--base", "HEAD", *FIXTURE_FLAGS, "--json"], root)
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)["rows"]
    assert {(r["rule"], r["origin"]) for r in rows} == {("R4", "left"), ("R30", "left"), ("R31", "left"), ("R28", "introduced")}
    assert "no architecture model at HEAD" in result.stderr


def test_absent_facts_are_reported_not_silently_empty(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    facts = json.loads((root / "facts.json").read_text())
    facts["capabilities"]["exports"] = False
    facts["capabilities"]["constructs"] = False
    (root / "facts.json").write_text(json.dumps(facts))
    result = run_arch(["assess", *FIXTURE_FLAGS, "--json"], root)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out == {"rows": [], "notProvided": ["abstractness", "constructs"]}
    assert "abstractness rows not provided by the adapter; evaluate R31 and R32 from a fact slice" in result.stderr
    assert "construction rows not provided by the adapter; evaluate R7 from a fact slice" in result.stderr


def run_assess(tmp_path: Path, graph: dict, touched: dict | None) -> dict:
    script = (f"import {{ assess }} from {json.dumps(ASSESS.as_uri())};"
              f"console.log(JSON.stringify(assess({{ graph: {json.dumps(graph)}, model: {{ boundaries: {{ groups: [] }} }},"
              f" touched: {json.dumps(touched)} }})));")
    result = run_node(script, tmp_path)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def component(cid: str, fan_in: int, fan_out: int, instability, abstractness, zone, abstract_exports: int = 0) -> dict:
    return {"id": cid, "fanIn": fan_in, "fanOut": fan_out, "instability": instability, "abstractness": abstractness,
            "distance": None, "abstractExports": abstract_exports, "inZone": zone}


def empty_graph(components: list[dict]) -> dict:
    return {"capabilities": {"exports": True, "constructs": True}, "rings": ["entities", "use-cases", "adapters", "frameworks"],
            "units": [], "edges": [], "externals": [], "components": components, "componentEdges": [],
            "cycles": {"modules": [], "components": []}}


def test_zone_of_pain_is_assessed_only_when_the_change_touches_the_component(tmp_path: Path):
    graph = empty_graph([component("C1", 5, 0, 0, 0.1, "pain"), component("C2", 0, 3, 1, 0, None)])
    assert run_assess(tmp_path, graph, None)["rows"] == []
    row = find(run_assess(tmp_path, graph, {"units": [], "components": ["C1"]})["rows"], "C1", "R31, R32")
    assert row["severity"] == "major" and row["escalation"] == []


def test_abstract_component_without_outside_consumers_is_a_minor_row(tmp_path: Path):
    graph = empty_graph([component("C1", 0, 2, 1, 0.9, "uselessness", abstract_exports=3)])
    row = find(run_assess(tmp_path, graph, None)["rows"], "C1", "R31, R32")
    assert row["severity"] == "minor" and row["escalation"] == []


def test_cycle_targets_sort_members_numerically(tmp_path: Path):
    graph = empty_graph([component("C2", 1, 1, 0.5, None, None), component("C10", 1, 1, 0.5, None, None)])
    graph["cycles"]["components"] = [["C2", "C10"]]
    assert keys(run_assess(tmp_path, graph, None)["rows"]) == [("C2 -> C10", "R30")]


def test_construction_of_a_policy_kind_is_not_a_row_under_custom_rings(tmp_path: Path):
    graph = empty_graph([])
    graph["rings"] = ["entities", "use-cases", "adapters"]
    graph["units"] = [
        {"path": "web/controller.ts", "component": None, "ring": "adapters", "kind": "controller"},
        {"path": "app/use-case.ts", "component": None, "ring": "use-cases", "kind": "use-case"},
        {"path": "db/gateway.ts", "component": None, "ring": "adapters", "kind": "gateway"},
    ]
    graph["edges"] = [
        {"from": "web/controller.ts", "to": "app/use-case.ts", "kind": "constructs", "direction": "inward"},
        {"from": "web/controller.ts", "to": "db/gateway.ts", "kind": "constructs", "direction": "same"},
    ]
    assert keys(run_assess(tmp_path, graph, None)["rows"]) == [("web/controller.ts -> db/gateway.ts", "R7")]


def construction_graph(constructing_kind: str, constructed_kind: str) -> dict:
    graph = empty_graph([])
    graph["units"] = [
        {"path": "src/a.ts", "component": None, "ring": "adapters", "kind": constructing_kind},
        {"path": "src/b.ts", "component": None, "ring": "adapters", "kind": constructed_kind},
    ]
    graph["edges"] = [{"from": "src/a.ts", "to": "src/b.ts", "kind": "constructs", "direction": "same"}]
    return graph


def test_construction_by_a_test_config_or_composition_root_is_not_a_row(tmp_path: Path):
    for kind in ("test", "config", "composition-root"):
        assert run_assess(tmp_path, construction_graph(kind, "adapter"), None)["rows"] == [], kind


def test_construction_of_a_unit_that_is_not_a_detail_kind_is_not_a_row(tmp_path: Path):
    for kind in ("mixed", "test", "config", "composition-root", "entity"):
        assert run_assess(tmp_path, construction_graph("controller", kind), None)["rows"] == [], kind
    assert keys(run_assess(tmp_path, construction_graph("controller", "gateway"), None)["rows"]) == [("src/a.ts -> src/b.ts", "R7")]


def test_assessed_change_text_names_the_move(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, "src/domain/employee.ts", "src/adapters/system-clock.ts")
    seed_edge(root, "src/domain/clock.ts", "src/adapters/system-clock.ts")
    rows = assess_rows(root)
    ring_changes = {r["change"] for r in rows if r["rule"] == "R4" and r["target"].endswith("-> src/adapters/system-clock.ts")}
    assert len(ring_changes) == 1 and "src/adapters/system-clock.ts" in ring_changes.pop()
    construction_changes = {r["change"] for r in rows if r["rule"] == "R7"}
    assert len(construction_changes) == 1 and CONTROLLER in construction_changes.pop()


def test_base_without_a_model_marks_cohesion_rows_and_edges_of_added_units_introduced(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    model = tmp_path / "model"
    shutil.move(root / "docs", model)
    init_repo(root)
    shutil.move(model, root / "docs")
    (root / "src/domain/bonus.ts").write_text("export const bonus = 1;\n")
    cruise = json.loads((root / "cruise.json").read_text())
    cruise["modules"].append({"source": "src/domain/bonus.ts", "dependencies": []})
    (root / "cruise.json").write_text(json.dumps(cruise))
    seed_edge(root, "src/domain/bonus.ts", "src/web/main.ts")
    seed_edge(root, "src/adapters/system-clock.ts", "src/web/main.ts")
    touch(root, "src/web/main.ts", "src/adapters/system-clock.ts")
    rows = assess_rows(root, "--base", "HEAD")
    assert find(rows, "src/domain/bonus.ts -> src/web/main.ts", "R4")["origin"] == "introduced"
    assert find(rows, "src/adapters/system-clock.ts -> src/web/main.ts", "R4")["origin"] == "left"
    assert find(rows, "docs/architecture/model/boundaries.json", "R28")["origin"] == "introduced"


BARREL = "src/domain/index.ts"


def test_an_outward_edge_through_a_barrel_is_not_a_crossing(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, BARREL, "src/adapters/memory-payroll-repository.ts")
    rows = assess_rows(root)
    assert not any(r["rule"] == "R4" and BARREL in r["target"] for r in rows), rows


def test_an_outward_edge_not_through_a_barrel_is_still_a_crossing(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, "src/domain/employee.ts", "src/adapters/memory-payroll-repository.ts")
    assert find(assess_rows(root), "src/domain/employee.ts -> src/adapters/memory-payroll-repository.ts", "R4")["severity"] == "blocker"


def test_ring_and_construction_rows_skip_an_edge_with_a_barrel_at_either_end(tmp_path: Path):
    for constructing, constructed in (("controller", "barrel"), ("barrel", "gateway")):
        assert run_assess(tmp_path, construction_graph(constructing, constructed), None)["rows"] == [], (constructing, constructed)
    graph = construction_graph("entity", "barrel")
    graph["edges"] = [{"from": "src/a.ts", "to": "src/b.ts", "kind": "import", "direction": "outward"}]
    assert run_assess(tmp_path, graph, None)["rows"] == []
