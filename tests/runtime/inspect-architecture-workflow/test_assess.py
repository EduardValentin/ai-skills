import json
import shutil
from pathlib import Path

from support import FIXTURE_FLAGS, SKILL_DIR, copy_fixture, git, init_repo, run_arch, run_node

ASSESS = SKILL_DIR / "scripts" / "lib" / "assess.mjs"
COLUMNS = "| Workflow | Target | Rule | Origin | Verdict | Severity | Evidence | Change | Escalation |"


def seed_edge(root: Path, source: str, resolved: str) -> None:
    cruise = json.loads((root / "cruise.json").read_text())
    module = next(m for m in cruise["modules"] if m["source"] == source)
    module["dependencies"].append({"module": resolved, "resolved": resolved, "dependencyTypes": ["local", "import"],
                                   "dynamic": False, "couldNotResolve": False, "matchesDoNotFollow": False})
    (root / "cruise.json").write_text(json.dumps(cruise))


def assess_rows(root: Path, *args: str) -> list[dict]:
    result = run_arch(["assess", *args, *FIXTURE_FLAGS, "--json"], root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def find(rows: list[dict], target: str, rule: str) -> dict:
    matches = [r for r in rows if r["target"] == target and r["rule"] == rule]
    assert len(matches) == 1, rows
    return matches[0]


def test_unseeded_fixture_has_no_rows_in_audit_mode(tmp_path: Path):
    assert assess_rows(copy_fixture("payroll", tmp_path / "p")) == []


def test_markdown_header_equals_the_documented_columns(tmp_path: Path):
    result = run_arch(["assess", *FIXTURE_FLAGS], copy_fixture("payroll", tmp_path / "p"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == COLUMNS
    assert COLUMNS in (SKILL_DIR / "references/command.md").read_text()


def test_seeded_component_cycle_yields_cycle_rows(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, "src/domain/employee.ts", "src/web/payroll-controller.ts")
    rows = assess_rows(root)
    component_cycle = find(rows, "C1 -> C2 -> C3", "R30")
    assert component_cycle["workflow"] == "W6" and component_cycle["severity"] == "blocker"
    assert component_cycle["verdict"] == "SHOULD_CHANGE" and component_cycle["origin"] == "introduced"
    members = sorted(["src/adapters/pg-payroll-repository.ts", "src/domain/employee.ts", "src/domain/payroll-repository.ts",
                      "src/domain/payroll-use-case.ts", "src/web/payroll-controller.ts"])
    module_cycle = find(rows, " -> ".join(members), "R30")
    assert module_cycle["workflow"] == "W6" and module_cycle["severity"] == "blocker"
    policy_edge = find(rows, "src/domain/employee.ts -> src/web/payroll-controller.ts", "R4")
    assert policy_edge["workflow"] == "W1" and policy_edge["severity"] == "blocker"


def test_seeded_outward_edge_into_a_depended_on_component_escalates_by_rule_3(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, "src/domain/employee.ts", "src/domain/payroll-use-case.ts")
    row = find(assess_rows(root), "src/domain/employee.ts -> src/domain/payroll-use-case.ts", "R4")
    assert row["workflow"] == "W1" and row["severity"] == "blocker" and row["escalation"] == ["rule 3"]


def test_outward_edge_into_a_lightly_depended_on_component_is_not_escalated(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, "src/adapters/system-clock.ts", "src/web/main.ts")
    rows = assess_rows(root)
    row = find(rows, "src/adapters/system-clock.ts -> src/web/main.ts", "R4")
    assert row["escalation"] == [] and row["severity"] == "blocker"
    stability = find(rows, "C3 -> C2", "R31")
    assert stability["workflow"] == "W6" and stability["severity"] == "major"


def two_component_change(tmp_path: Path) -> Path:
    root = copy_fixture("payroll", tmp_path / "p")
    (root / ".gitignore").write_text(".architecture/\n")
    init_repo(root)
    (root / "src/domain/employee.ts").write_text("export class Employee { changed = true; }\n")
    (root / "src/web/main.ts").write_text("export const changed = true;\n")
    return root


def test_change_across_components_without_groups_asks_for_them_until_a_group_covers_it(tmp_path: Path):
    root = two_component_change(tmp_path)
    rows = assess_rows(root, "--base", "HEAD")
    assert [(r["workflow"], r["rule"], r["severity"]) for r in rows] == [("W6", "R28", "minor")]
    added = run_arch(["model", "add-group", "payroll", "components=C1,C3", "absorbs=payroll rules"], root)
    assert added.returncode == 0, added.stderr
    assert assess_rows(root, "--base", "HEAD") == []


def test_change_spreading_past_the_recorded_groups_yields_r27(tmp_path: Path):
    root = two_component_change(tmp_path)
    assert run_arch(["model", "add-group", "core", "components=C1,C2", "absorbs=storage"], root).returncode == 0
    row = find(assess_rows(root, "--base", "HEAD"), "C3", "R27")
    assert row["workflow"] == "W6" and row["severity"] == "major"


def test_origin_follows_the_diff_against_the_base(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    (root / ".gitignore").write_text(".architecture/\n")
    seed_edge(root, "src/adapters/system-clock.ts", "src/web/main.ts")
    init_repo(root)
    seed_edge(root, "src/adapters/memory-payroll-repository.ts", "src/web/main.ts")
    rows = assess_rows(root, "--base", "HEAD")
    assert find(rows, "src/adapters/system-clock.ts -> src/web/main.ts", "R4")["origin"] == "left"
    assert find(rows, "src/adapters/memory-payroll-repository.ts -> src/web/main.ts", "R4")["origin"] == "introduced"


def test_base_without_a_model_marks_every_row_left_and_warns(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    model = tmp_path / "model"
    shutil.move(root / "docs", model)
    init_repo(root)
    shutil.move(model, root / "docs")
    seed_edge(root, "src/adapters/system-clock.ts", "src/web/main.ts")
    (root / "src/domain/employee.ts").write_text("export class Employee { changed = true; }\n")
    (root / "src/web/main.ts").write_text("export const changed = true;\n")
    result = run_arch(["assess", "--base", "HEAD", *FIXTURE_FLAGS, "--json"], root)
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)
    assert rows and {r["origin"] for r in rows} == {"left"}
    assert "no architecture model at HEAD" in result.stderr


def run_assess(tmp_path: Path, graph: dict, model: dict, touched: list[str] | None) -> list[dict]:
    script = (f"import {{ assess }} from {json.dumps(ASSESS.as_uri())};"
              f"console.log(JSON.stringify(assess({{ graph: {json.dumps(graph)}, model: {json.dumps(model)},"
              f" touchedComponents: {json.dumps(touched)} }})));")
    result = run_node(script, tmp_path)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def component(cid: str, fan_in: int, fan_out: int, instability, abstractness, zone, abstract_exports: int = 0) -> dict:
    return {"id": cid, "fanIn": fan_in, "fanOut": fan_out, "instability": instability, "abstractness": abstractness,
            "distance": None, "abstractExports": abstract_exports, "inZone": zone}


def empty_graph(components: list[dict]) -> dict:
    return {"units": [], "edges": [], "externals": [], "components": components, "componentEdges": [],
            "cycles": {"modules": [], "components": []}}


def test_zone_of_pain_is_assessed_only_when_the_change_touches_the_component(tmp_path: Path):
    graph = empty_graph([component("C1", 5, 0, 0, 0.1, "pain"), component("C2", 0, 3, 1, 0, None)])
    model = {"boundaries": {"groups": []}}
    assert run_assess(tmp_path, graph, model, None) == []
    row = find(run_assess(tmp_path, graph, model, ["C1"]), "C1", "R31, R32")
    assert row["severity"] == "major" and row["escalation"] == ["rule 3"]


def test_abstract_component_without_outside_consumers_is_a_minor_row(tmp_path: Path):
    graph = empty_graph([component("C1", 0, 2, 1, 0.9, "uselessness", abstract_exports=3)])
    row = find(run_assess(tmp_path, graph, {"boundaries": {"groups": []}}, None), "C1", "R31, R32")
    assert row["severity"] == "minor" and row["escalation"] == []
