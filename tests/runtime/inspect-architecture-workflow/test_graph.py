import json
from pathlib import Path

import pytest

from support import SKILL_DIR, copy_fixture, run_arch, run_node

GRAPH = SKILL_DIR / "scripts" / "lib" / "graph.mjs"

_HAS_TYPESCRIPT = run_node(
    "import {createRequire} from 'node:module';"
    "try{createRequire(process.cwd()+'/x.js').resolve('typescript');process.stdout.write('yes')}catch{process.stdout.write('no')}",
    Path.cwd(),
).stdout == "yes"

needs_typescript = pytest.mark.skipif(
    not _HAS_TYPESCRIPT,
    reason="typescript is not resolvable in this environment; the graph command needs it to scan exports",
)


def build(root: Path) -> dict:
    result = run_arch(["graph", "--cruise-json", "cruise.json", "--json"], root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@needs_typescript
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


@needs_typescript
def test_metrics_match_hand_computation(tmp_path: Path):
    g = build(copy_fixture("payroll", tmp_path / "p"))
    c = {x["id"]: x for x in g["components"]}
    # C1 domain: importers outside C1 = pg-payroll-repository, system-clock, payroll-controller -> fanIn 3; fanOut 0
    assert c["C1"]["fanIn"] == 3 and c["C1"]["fanOut"] == 0 and c["C1"]["instability"] == 0
    # C1 exports: Employee (concrete), Clock (abstract), PayrollUseCase (concrete), PayrollRepository (abstract) -> A = 0.5, D = |0.5+0-1| = 0.5
    assert c["C1"]["abstractness"] == 0.5 and c["C1"]["distance"] == 0.5
    # C3 web: fanIn 0, fanOut = domain/payroll-use-case + adapters/pg-payroll-repository + adapters/system-clock = 3 -> I = 1, A = 0 -> D = 0
    assert c["C3"]["fanIn"] == 0 and c["C3"]["fanOut"] == 3 and c["C3"]["instability"] == 1 and c["C3"]["distance"] == 0
    assert {(e["from"], e["to"], e["modules"]) for e in g["componentEdges"]} == {("C2", "C1", 2), ("C3", "C1", 1), ("C3", "C2", 1)}


@needs_typescript
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


@needs_typescript
def test_cycles_are_detected_at_module_and_component_level(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    cruise = json.loads((root / "cruise.json").read_text())
    emp = next(m for m in cruise["modules"] if m["source"] == "src/domain/employee.ts")
    emp["dependencies"].append({"module": "../web/payroll-controller", "resolved": "src/web/payroll-controller.ts", "dependencyTypes": ["local", "import"], "dynamic": False, "couldNotResolve": False, "matchesDoNotFollow": False})
    (root / "cruise.json").write_text(json.dumps(cruise))
    g = build(root)
    assert any(set(cycle) >= {"src/domain/employee.ts", "src/web/payroll-controller.ts"} for cycle in g["cycles"]["modules"])
    assert any(set(cycle) >= {"C1", "C3"} for cycle in g["cycles"]["components"])


@needs_typescript
def test_uncovered_lists_modules_without_component_or_rule(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    (root / "src/scripts").mkdir()
    (root / "src/scripts/seed.ts").write_text("export const seed = 1;\n")
    cruise = json.loads((root / "cruise.json").read_text())
    cruise["modules"].append({"source": "src/scripts/seed.ts", "dependencies": []})
    (root / "cruise.json").write_text(json.dumps(cruise))
    g = build(root)
    assert g["uncovered"] == ["src/scripts/seed.ts"]


@needs_typescript
def test_graph_is_written_to_cache_and_summary_printed(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_arch(["graph", "--cruise-json", "cruise.json"], root)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("graph: 8 units,")
    assert (root / ".architecture/graph/working-tree.json").exists()


def test_tarjan_finds_nested_cycles():
    script = (f"import {{ stronglyConnected }} from '{GRAPH.as_posix()}';"
              "process.stdout.write(JSON.stringify(stronglyConnected(['a','b','c','d'], [['a','b'],['b','a'],['b','c'],['c','d']])));")
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [["a", "b"]]
