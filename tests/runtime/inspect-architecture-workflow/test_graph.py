import json
from pathlib import Path

from support import FIXTURE_FLAGS, SKILL_DIR, copy_fixture, git, init_repo, install_fake_tooling, run_arch, run_node

GRAPH = SKILL_DIR / "scripts" / "lib" / "graph.mjs"


def build(root: Path) -> dict:
    result = run_arch(["graph", *FIXTURE_FLAGS, "--json"], root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_graph_units_and_edges_are_classified(tmp_path: Path):
    g = build(copy_fixture("payroll", tmp_path / "p"))
    units = {u["path"]: u for u in g["units"]}
    assert units["src/domain/payroll-use-case.ts"]["kind"] == "use-case"
    assert units["src/domain/payroll-use-case.ts"]["component"] == "C1"
    assert units["src/web/main.ts"]["kind"] == "composition-root"
    e = next(x for x in g["edges"] if x["from"] == "src/adapters/system-clock.ts" and x["to"] == "src/domain/clock.ts")
    assert e["crossesComponent"] is True and e["direction"] == "inward"
    e2 = next(x for x in g["edges"] if x["from"] == "src/domain/payroll-use-case.ts" and x["to"] == "src/domain/employee.ts")
    assert e2["direction"] == "inward" and e2["crossesComponent"] is False


def test_metrics_match_hand_computation(tmp_path: Path):
    g = build(copy_fixture("payroll", tmp_path / "p"))
    c = {x["id"]: x for x in g["components"]}
    # C1 domain: importers outside C1 = pg-payroll-repository, memory-payroll-repository, system-clock, payroll-controller -> fanIn 4; fanOut 0
    assert c["C1"]["fanIn"] == 4 and c["C1"]["fanOut"] == 0 and c["C1"]["instability"] == 0
    # C1 exports: Employee (concrete), Clock (abstract), PayrollUseCase (concrete), PayrollRepository (abstract) -> A = 0.5, D = |0.5+0-1| = 0.5
    assert c["C1"]["abstractness"] == 0.5 and c["C1"]["distance"] == 0.5
    # C3 web: fanIn 0, fanOut = modules inside C3 that import outside it: only payroll-controller.ts -> 1 -> I = 1, A = 0 -> D = 0
    assert c["C3"]["fanIn"] == 0 and c["C3"]["fanOut"] == 1 and c["C3"]["instability"] == 1 and c["C3"]["distance"] == 0
    assert {(e["from"], e["to"], e["modules"]) for e in g["componentEdges"]} == {("C2", "C1", 3), ("C3", "C1", 1), ("C3", "C2", 1)}


def test_component_with_no_edges_has_null_metrics_not_nan(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    comp = root / "docs/architecture/model/components.json"
    data = json.loads(comp.read_text())
    data["components"].append({"id": "C4", "name": "island", "paths": ["src/island/**"], "enforcement": "none", "releaseUnit": "", "entryPoints": []})
    comp.write_text(json.dumps(data))
    g = build(root)
    c = next(x for x in g["components"] if x["id"] == "C4")
    assert c["units"] == 0 and c["instability"] is None and c["abstractness"] is None and c["distance"] is None
    assert "NaN" not in json.dumps(g)


def test_cycles_are_detected_at_module_and_component_level(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    cruise = json.loads((root / "cruise.json").read_text())
    emp = next(m for m in cruise["modules"] if m["source"] == "src/domain/employee.ts")
    emp["dependencies"].append({"module": "../web/payroll-controller", "resolved": "src/web/payroll-controller.ts", "dependencyTypes": ["local", "import"], "dynamic": False, "couldNotResolve": False, "matchesDoNotFollow": False})
    (root / "cruise.json").write_text(json.dumps(cruise))
    g = build(root)
    assert any(set(cycle) >= {"src/domain/employee.ts", "src/web/payroll-controller.ts"} for cycle in g["cycles"]["modules"])
    assert any(set(cycle) >= {"C1", "C3"} for cycle in g["cycles"]["components"])


def test_uncovered_lists_modules_without_component_or_rule(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    (root / "src/scripts").mkdir()
    (root / "src/scripts/seed.ts").write_text("export const seed = 1;\n")
    cruise = json.loads((root / "cruise.json").read_text())
    cruise["modules"].append({"source": "src/scripts/seed.ts", "dependencies": []})
    (root / "cruise.json").write_text(json.dumps(cruise))
    g = build(root)
    assert g["uncovered"] == ["src/scripts/seed.ts"]


def test_graph_is_written_to_cache_and_summary_printed(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_arch(["graph", *FIXTURE_FLAGS], root)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("graph: 9 units, 15 edges,")
    assert (root / ".architecture/graph/working-tree.json").exists()


def test_component_edges_sort_numerically_by_component_id():
    model = {
        "components": {"components": [{"id": "C2", "paths": ["c2/**"]}, {"id": "C3", "paths": ["c3/**"]}, {"id": "C10", "paths": ["c10/**"]}]},
        "rules": {"rings": ["entities", "use-cases", "adapters", "frameworks"], "rules": [], "frameworks": []},
        "overrides": {"overrides": []},
    }
    extracted = {
        "modules": [
            {"path": "c2/x.ts", "exports": {"abstract": 0, "concrete": 1}, "implements": []},
            {"path": "c3/x.ts", "exports": {"abstract": 0, "concrete": 1}, "implements": []},
            {"path": "c10/x.ts", "exports": {"abstract": 0, "concrete": 1}, "implements": []},
        ],
        "edges": [
            {"from": "c10/x.ts", "to": "c2/x.ts", "kind": "import"},
            {"from": "c3/x.ts", "to": "c10/x.ts", "kind": "import"},
            {"from": "c3/x.ts", "to": "c2/x.ts", "kind": "import"},
        ],
        "warnings": [],
    }
    script = (f"import {{ buildGraph }} from '{GRAPH.as_posix()}';"
              f"const g = buildGraph({{model:{json.dumps(model)}, extracted:{json.dumps(extracted)}, commit:'t'}});"
              "process.stdout.write(JSON.stringify(g.componentEdges.map(e => [e.from, e.to, e.modules])));")
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [["C3", "C2", 1], ["C3", "C10", 1], ["C10", "C2", 1]]


def test_tarjan_finds_nested_cycles():
    script = (f"import {{ stronglyConnected }} from '{GRAPH.as_posix()}';"
              "process.stdout.write(JSON.stringify(stronglyConnected(['a','b','c','d'], [['a','b'],['b','a'],['b','c'],['c','d']])));")
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [["a", "b"]]


def test_cycle_members_sort_numerically():
    script = (f"import {{ stronglyConnected }} from '{GRAPH.as_posix()}';"
              "process.stdout.write(JSON.stringify(stronglyConnected(['C10','C2','C3'], [['C10','C2'],['C2','C10'],['C3','C2'],['C2','C3']])));")
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [["C2", "C3", "C10"]]


def test_empty_roots_fall_back_to_the_project_root(tmp_path: Path):
    script = (f"import {{ sourceRoots }} from '{GRAPH.as_posix()}';"
              "process.stdout.write(JSON.stringify([sourceRoots({components:{tooling:{roots:[]}}}), sourceRoots({components:{}}), sourceRoots({components:{tooling:{roots:['src']}}})]));")
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [["."], ["."], ["src"]]
    root = copy_fixture("payroll", tmp_path / "p")
    comp = root / "docs/architecture/model/components.json"
    data = json.loads(comp.read_text())
    data["tooling"]["roots"] = []
    comp.write_text(json.dumps(data))
    assert len(build(root)["units"]) == 9


def _clean_repo_with_tooling(tmp_path: Path) -> tuple[Path, str]:
    root = copy_fixture("payroll", tmp_path / "p")
    install_fake_tooling(root)
    init_repo(root)
    return root, git(["rev-parse", "--short=8", "HEAD"], root).stdout.strip()


def test_clean_tree_reuses_the_commit_keyed_cache(tmp_path: Path):
    root, head = _clean_repo_with_tooling(tmp_path)
    first = run_arch(["graph", "--json"], root)
    assert first.returncode == 0, first.stderr
    cached = root / f".architecture/graph/{head}.json"
    assert cached.exists()
    stamp = json.loads(first.stdout)["generatedAt"]
    second = run_arch(["graph", "--json"], root)
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["generatedAt"] == stamp


def test_cached_graph_of_an_older_version_is_rebuilt(tmp_path: Path):
    root, head = _clean_repo_with_tooling(tmp_path)
    assert run_arch(["graph"], root).returncode == 0
    cached = root / f".architecture/graph/{head}.json"
    old = json.loads(cached.read_text())
    old["version"] = 1
    old["generatedAt"] = "2000-01-01T00:00:00.000Z"
    cached.write_text(json.dumps(old))
    result = run_arch(["graph", "--json"], root)
    assert result.returncode == 0, result.stderr
    rebuilt = json.loads(result.stdout)
    assert rebuilt["version"] == 4 and rebuilt["generatedAt"] != "2000-01-01T00:00:00.000Z"
    assert json.loads(cached.read_text())["version"] == 4


def _zone_of(abstract: int, concrete: int, importers: int, imports_out: int) -> str | None:
    units = [{"path": "c/x.ts", "component": "C", "exports": {"abstract": abstract, "concrete": concrete}}]
    edges = []
    for i in range(importers):
        units.append({"path": f"in{i}.ts", "component": f"I{i}", "exports": {"abstract": 0, "concrete": 1}})
        edges.append({"from": f"in{i}.ts", "to": "c/x.ts"})
    if imports_out:
        units.append({"path": "c/y.ts", "component": "C", "exports": {"abstract": 0, "concrete": 0}})
        units.append({"path": "out.ts", "component": "O", "exports": {"abstract": 0, "concrete": 1}})
        for source in ["c/x.ts", "c/y.ts"][:imports_out]:
            edges.append({"from": source, "to": "out.ts"})
    script = (f"import {{ metricsFor }} from '{GRAPH.as_posix()}';"
              f"const [c] = metricsFor({json.dumps(units)}, {json.dumps(edges)}, [{{id:'C', name:'c'}}]);"
              "process.stdout.write(JSON.stringify(c.inZone));")
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_zone_classification():
    assert _zone_of(abstract=0, concrete=5, importers=3, imports_out=0) == "pain"
    assert _zone_of(abstract=0, concrete=5, importers=2, imports_out=0) is None
    assert _zone_of(abstract=5, concrete=0, importers=0, imports_out=2) == "uselessness"
    assert _zone_of(abstract=1, concrete=1, importers=1, imports_out=1) is None
