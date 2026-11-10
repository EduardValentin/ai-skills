import json
from pathlib import Path

from support import SKILL_DIR, copy_fixture, run_arch, run_node

LIB = SKILL_DIR / "scripts" / "lib" / "graph"
METRICS = (LIB / "metrics.mjs").as_posix()
CYCLES = (LIB / "cycles.mjs").as_posix()
ADAPTER_FILE = "adapter.json"


def collect_json(root: Path, *extra: str) -> dict:
    result = run_arch(["collect", "--json", *extra], root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def edit_adapter(root: Path, change) -> None:
    path = root / ADAPTER_FILE
    document = json.loads(path.read_text())
    change(document)
    path.write_text(json.dumps(document))


def payroll(tmp_path: Path) -> Path:
    return copy_fixture("payroll", tmp_path / "p")


def test_two_builds_of_the_same_inputs_are_byte_identical(tmp_path: Path):
    root = payroll(tmp_path)
    first = run_arch(["collect", "--json"], root).stdout
    second = run_arch(["collect", "--json"], root).stdout
    assert first == second
    assert "generatedAt" not in first


def test_graph_units_and_edges_are_classified(tmp_path: Path):
    graph = collect_json(payroll(tmp_path))
    assert graph["version"] == 6
    units = {unit["path"]: unit for unit in graph["units"]}
    assert units["src/domain/payroll-use-case.ts"]["kind"] == "use-case"
    assert units["src/domain/payroll-use-case.ts"]["component"] == "domain"
    assert units["src/web/main.ts"]["kind"] == "composition-root"
    edges = {(e["from"], e["to"], e["kind"]): e for e in graph["edges"]}
    inward = edges[("src/adapters/pg-payroll-repository.ts", "src/domain/payroll-repository.ts", "type-import")]
    assert inward["crossesComponent"] is True and inward["direction"] == "inward"
    inside = edges[("src/domain/payroll-use-case.ts", "src/domain/employee.ts", "import")]
    assert inside["crossesComponent"] is False and inside["direction"] == "inward"


def test_components_are_named(tmp_path: Path):
    graph = collect_json(payroll(tmp_path))
    pairs = {(e["from"], e["to"], e["modules"]) for e in graph["componentEdges"]}
    assert pairs == {("adapters", "domain", 3), ("web", "domain", 1), ("web", "adapters", 1)}
    assert {"from": "web", "to": "domain", "modules": 1} in graph["componentEdges"]
    assert [c["name"] for c in graph["components"]] == ["domain", "adapters", "web"]


def test_metrics_match_hand_computation(tmp_path: Path):
    graph = collect_json(payroll(tmp_path))
    components = {c["name"]: c for c in graph["components"]}
    domain, web = components["domain"], components["web"]
    assert (domain["fanIn"], domain["fanOut"], domain["instability"]) == (4, 0, 0)
    assert (domain["abstractness"], domain["distance"]) == (0.5, 0.5)
    assert (web["fanIn"], web["fanOut"], web["instability"], web["distance"]) == (0, 1, 1, 0)


def test_component_with_no_edges_has_null_metrics_not_nan(tmp_path: Path):
    root = payroll(tmp_path)
    assert run_arch(["model", "add-component", "island", "paths=src/island/**"], root).returncode == 0
    graph = collect_json(root)
    island = next(c for c in graph["components"] if c["name"] == "island")
    assert island["units"] == 0
    assert (island["instability"], island["abstractness"], island["distance"], island["zone"]) == (None,) * 4
    assert "NaN" not in json.dumps(graph)


def test_zone_uses_project_thresholds(tmp_path: Path):
    root = payroll(tmp_path)
    domain = lambda: next(c for c in collect_json(root)["components"] if c["name"] == "domain")
    assert domain()["zone"] is None
    assert run_arch(["model", "set-threshold", "painMaxAbstractness", "0.5"], root).returncode == 0
    assert domain()["zone"] == "pain"
    assert run_arch(["model", "set-threshold", "painMinFanIn", "5"], root).returncode == 0
    assert domain()["zone"] is None
    assert run_arch(["model", "set-threshold", "painMinFanIn", "1"], root).returncode == 0
    assert domain()["zone"] == "pain"


def test_cycles_are_detected_at_module_and_component_level(tmp_path: Path):
    root = payroll(tmp_path)
    edit_adapter(root, lambda d: d["edges"].append(
        {"from": "src/domain/employee.ts", "to": "src/web/payroll-controller.ts", "kind": "import"}))
    graph = collect_json(root)
    assert any({"src/domain/employee.ts", "src/web/payroll-controller.ts"} <= set(c) for c in graph["cycles"]["modules"])
    assert any({"domain", "web"} <= set(c) for c in graph["cycles"]["components"])


def test_uncovered_lists_units_without_component_or_kind(tmp_path: Path):
    root = payroll(tmp_path)
    edit_adapter(root, lambda d: d["modules"].append({"path": "src/scripts/seed.ts"}))
    assert collect_json(root)["uncovered"] == ["src/scripts/seed.ts"]


def test_externals_list_their_importers(tmp_path: Path):
    graph = collect_json(payroll(tmp_path))
    externals = {e["name"]: e for e in graph["externals"]}
    assert externals["pg"] == {"name": "pg", "tag": "vendor", "importers": ["src/adapters/pg-payroll-repository.ts"]}


def test_edges_with_a_barrel_at_either_end_keep_through_barrel(tmp_path: Path):
    edges = {(e["from"], e["to"]): e for e in collect_json(payroll(tmp_path))["edges"]}
    assert edges[("src/adapters/system-clock.ts", "src/domain/index.ts")]["direction"] == "through-barrel"
    assert edges[("src/domain/index.ts", "src/domain/payroll-use-case.ts")]["direction"] == "through-barrel"


def test_graph_records_capabilities_and_unit_signatures(tmp_path: Path):
    graph = collect_json(payroll(tmp_path))
    assert graph["capabilities"]["signatures"] is True
    units = {u["path"]: u for u in graph["units"]}
    assert units["src/adapters/memory-payroll-repository.ts"]["signatures"] == [
        {"symbol": "memoryPayrollRepository", "types": [{"symbol": "Employee", "path": "src/domain/employee.ts"}]},
    ]


def test_constructs_become_edges_classified_like_imports(tmp_path: Path):
    graph = collect_json(payroll(tmp_path))
    constructs = {(e["to"], e["crossesComponent"], e["direction"]) for e in graph["edges"] if e["kind"] == "constructs"}
    assert constructs == {
        ("src/adapters/pg-payroll-repository.ts", True, "same"),
        ("src/adapters/system-clock.ts", True, "same"),
        ("src/domain/payroll-use-case.ts", True, "inward"),
    }
    assert all(e["from"] == "src/web/payroll-controller.ts" for e in graph["edges"] if e["kind"] == "constructs")


def test_absent_signatures_capability_leaves_signatures_unknown(tmp_path: Path):
    root = payroll(tmp_path)
    edit_adapter(root, lambda d: d["capabilities"].update(signatures=False))
    graph = collect_json(root)
    assert graph["capabilities"]["signatures"] is False
    assert all(u["signatures"] is None for u in graph["units"])


def test_absent_constructs_capability_adds_no_constructs_edges(tmp_path: Path):
    root = payroll(tmp_path)
    edit_adapter(root, lambda d: d["capabilities"].update(constructs=False))
    assert not any(e["kind"] == "constructs" for e in collect_json(root)["edges"])


def test_absent_exports_capability_leaves_abstractness_undefined(tmp_path: Path):
    root = payroll(tmp_path)
    edit_adapter(root, lambda d: d["capabilities"].update(exports=False))
    domain = next(c for c in collect_json(root)["components"] if c["name"] == "domain")
    assert (domain["abstractness"], domain["distance"], domain["zone"]) == (None, None, None)


def test_the_script_module_is_in_the_graph_with_its_saved_facts(tmp_path: Path):
    graph = collect_json(payroll(tmp_path))
    router = next(u for u in graph["units"] if u["path"] == "src/web/legacy-router.js")
    assert router["exports"] == {"abstract": 0, "concrete": 1}
    assert ("src/web/legacy-router.js", "src/web/payroll-controller.ts", "import") in {
        (e["from"], e["to"], e["kind"]) for e in graph["edges"]}
    assert not any("legacy-router" in w for w in graph["warnings"])


def test_tarjan_finds_nested_cycles():
    script = (f"import {{ stronglyConnected }} from '{CYCLES}';"
              "process.stdout.write(JSON.stringify(stronglyConnected(['a','b','c','d'],"
              " [['a','b'],['b','a'],['b','c'],['c','d']])));")
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [["a", "b"]]


def test_cycle_members_sort_numerically():
    script = (f"import {{ stronglyConnected }} from '{CYCLES}';"
              "process.stdout.write(JSON.stringify(stronglyConnected(['c10','c2','c3'],"
              " [['c10','c2'],['c2','c10'],['c3','c2'],['c2','c3']])));")
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [["c2", "c3", "c10"]]


THRESHOLDS = {"painMaxInstability": 0.2, "painMaxAbstractness": 0.2, "painMinFanIn": 3,
              "uselessMinAbstractness": 0.8, "uselessMinInstability": 0.8}


def zone_of(abstract: int, concrete: int, importers: int, imports_out: int) -> str | None:
    units = [{"path": "c/x.ts", "component": "c", "kind": "entity", "exports": {"abstract": abstract, "concrete": concrete}}]
    edges = []
    for i in range(importers):
        units.append({"path": f"in{i}.ts", "component": f"i{i}", "kind": "entity", "exports": {"abstract": 0, "concrete": 1}})
        edges.append({"from": f"in{i}.ts", "to": "c/x.ts"})
    if imports_out:
        units.append({"path": "c/y.ts", "component": "c", "kind": "entity", "exports": {"abstract": 0, "concrete": 0}})
        units.append({"path": "out.ts", "component": "o", "kind": "entity", "exports": {"abstract": 0, "concrete": 1}})
        for source in ["c/x.ts", "c/y.ts"][:imports_out]:
            edges.append({"from": source, "to": "out.ts"})
    script = (f"import {{ componentMetrics }} from '{METRICS}';"
              f"const [c] = componentMetrics({json.dumps(units)}, {json.dumps(edges)}, [{{name:'c'}}], {json.dumps(THRESHOLDS)});"
              "process.stdout.write(JSON.stringify(c.zone));")
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_zone_classification():
    assert zone_of(abstract=0, concrete=5, importers=3, imports_out=0) == "pain"
    assert zone_of(abstract=0, concrete=5, importers=2, imports_out=0) is None
    assert zone_of(abstract=5, concrete=0, importers=0, imports_out=2) == "uselessness"
    assert zone_of(abstract=1, concrete=1, importers=1, imports_out=1) is None
