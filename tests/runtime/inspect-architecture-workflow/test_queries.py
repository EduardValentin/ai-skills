import json
from pathlib import Path

from support import FIXTURE_FLAGS, SKILL_DIR, copy_fixture, git, init_repo, run_arch, run_node


def q(root: Path, *args: str) -> dict:
    result = run_arch(["query", *args, *FIXTURE_FLAGS, "--json"], root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_metrics_table(tmp_path: Path):
    out = q(copy_fixture("payroll", tmp_path / "p"), "metrics")
    assert out["columns"] == ["Component", "Units", "Fan-in", "Fan-out", "I", "A", "D", "Zone"]
    c1 = next(r for r in out["rows"] if r[0] == "C1 domain")
    assert c1[1:] == [5, 4, 0, 0, 0.25, 0.75, "none"]


def test_ring_crossings_outward_is_empty_and_inward_lists_edges(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    assert q(root, "ring-crossings")["rows"] == []
    inward = q(root, "ring-crossings", "--direction", "inward")["rows"]
    assert ["src/adapters/pg-payroll-repository.ts", "adapters", "src/domain/payroll-repository.ts", "entities", "type-import"] in inward


def test_fan_in_and_units(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    importers = {r[0] for r in q(root, "fan-in", "src/domain/clock.ts")["rows"]}
    assert importers == {"src/domain/payroll-use-case.ts", "src/domain/index.ts"}
    ports = {r[0] for r in q(root, "units", "--component", "C1", "--kind", "port")["rows"]}
    assert ports == {"src/domain/clock.ts", "src/domain/payroll-repository.ts"}


def test_ports_derive_implementers_and_consumers(tmp_path: Path):
    rows = q(copy_fixture("payroll", tmp_path / "p"), "ports")["rows"]
    repository = next(r for r in rows if r[0] == "src/domain/payroll-repository.ts:PayrollRepository")
    assert repository[1] == "C1" and repository[3] == "src/adapters/memory-payroll-repository.ts, src/adapters/pg-payroll-repository.ts" and repository[4] == "C2 (1)"
    clock = next(r for r in rows if r[0] == "src/domain/clock.ts:Clock")
    assert clock[3] == "src/adapters/system-clock.ts" and clock[4] == ""


def test_touched_lists_changed_units_with_neighbors(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    (root / "src/domain/employee.ts").write_text("export class Employee { name = 'x'; }\n")
    out = q(root, "touched", "--base", "HEAD")
    row = next(r for r in out["rows"] if r[0] == "src/domain/employee.ts")
    assert row[4] == "modified"
    assert "src/domain/payroll-use-case.ts" in row[5]


def test_volatility_counts_commits_per_component(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    base = git(["rev-parse", "HEAD"], root).stdout.strip()
    (root / "src/web/main.ts").write_text("import './payroll-controller.js'; export {};\n")
    git(["commit", "-qam", "touch web"], root)
    (root / "src/web/main.ts").write_text("import './payroll-controller.js'; export const x = 1;\n")
    git(["commit", "-qam", "touch web again"], root)
    rows = q(root, "volatility", "--since", base)["rows"]
    assert ["C3 web", 2, 1] in rows


def test_uncovered_exit_code(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    assert run_arch(["uncovered", *FIXTURE_FLAGS], root).returncode == 0
    cruise = json.loads((root / "cruise.json").read_text())
    cruise["modules"].append({"source": "src/scripts/seed.ts", "dependencies": []})
    (root / "cruise.json").write_text(json.dumps(cruise))
    (root / "src/scripts").mkdir(); (root / "src/scripts/seed.ts").write_text("export const s = 1;\n")
    result = run_arch(["uncovered", *FIXTURE_FLAGS], root)
    assert result.returncode == 1 and result.stdout.strip() == "src/scripts/seed.ts"


def test_touched_from_a_subdirectory_root_uses_relative_paths(tmp_path: Path):
    repo = tmp_path / "repo"
    sub = repo / "sub"
    copy_fixture("payroll", sub)
    init_repo(repo)
    (sub / "src/domain/employee.ts").write_text("export class Employee { name = 'x'; }\n")
    out = q(sub, "touched", "--base", "HEAD")
    row = next(r for r in out["rows"] if r[0] == "src/domain/employee.ts")
    assert row[4] == "modified"


def test_touched_without_base_prints_usage(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_arch(["query", "touched", *FIXTURE_FLAGS], root)
    assert result.returncode == 1
    assert result.stderr.strip() == "usage: arch query touched --base <ref>"


def test_volatility_without_since_prints_usage(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_arch(["query", "volatility", *FIXTURE_FLAGS], root)
    assert result.returncode == 1
    assert result.stderr.strip() == "usage: arch query volatility --since <ref>"


def test_markdown_rendering(tmp_path: Path):
    result = run_arch(["query", "metrics", *FIXTURE_FLAGS], copy_fixture("payroll", tmp_path / "p"))
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert lines[0] == "| Component | Units | Fan-in | Fan-out | I | A | D | Zone |"
    assert lines[1] == "|---|---|---|---|---|---|---|---|"
    assert any(l.startswith("| C1 domain | 5 | 4 | 0 | 0 | 0.25 | 0.75 | none |") for l in lines)


def test_component_graph_sorts_component_ids_numerically():
    queries = (SKILL_DIR / "scripts" / "lib" / "queries.mjs").as_posix()
    script = (f"import {{ QUERIES }} from '{queries}';"
              "const graph = {componentEdges: [{from:'C10',to:'C2',modules:1},{from:'C3',to:'C10',modules:1},{from:'C3',to:'C2',modules:1}]};"
              "const r = await QUERIES['component-graph'](graph, {}, {positional:[], flags:{}});"
              "process.stdout.write(JSON.stringify(r.rows));")
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [["C3", "C2", 1], ["C3", "C10", 1], ["C10", "C2", 1]]


def _set_components(root: Path, edit) -> None:
    comp = root / "docs/architecture/model/components.json"
    data = json.loads(comp.read_text())
    edit(data["components"])
    comp.write_text(json.dumps(data))


def test_entry_point_globs_expand_to_one_row_per_unit(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    _set_components(root, lambda cs: next(c for c in cs if c["id"] == "C3").update(entryPoints=["src/web/*.ts"]))
    rows = q(root, "entry-points")["rows"]
    assert rows == [
        ["src/web/main.ts", "C3", ["src/web/payroll-controller.ts"]],
        ["src/web/payroll-controller.ts", "C3", ["src/adapters/pg-payroll-repository.ts", "src/adapters/system-clock.ts", "src/domain/payroll-use-case.ts"]],
    ]


def test_externals_query_lists_importers_by_component(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    rows = q(root, "externals")["rows"]
    assert ["pg", "vendor", ["C2"], ["src/adapters/pg-payroll-repository.ts"]] in rows
    assert all(r[1] == "vendor" for r in q(root, "externals", "--tag", "vendor")["rows"])


def test_cycles_query_lists_module_and_component_cycles(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    assert q(root, "cycles")["rows"] == []
    cruise = json.loads((root / "cruise.json").read_text())
    emp = next(m for m in cruise["modules"] if m["source"] == "src/domain/employee.ts")
    emp["dependencies"].append({"module": "../web/payroll-controller", "resolved": "src/web/payroll-controller.ts", "dependencyTypes": ["local", "import"], "dynamic": False, "couldNotResolve": False})
    (root / "cruise.json").write_text(json.dumps(cruise))
    rows = q(root, "cycles")["rows"]
    assert ["component", ["C1", "C2", "C3"]] in rows
    assert any(r[0] == "module" and "src/domain/employee.ts" in r[1] for r in rows)


def test_edges_query_lists_outgoing_and_incoming_edges(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    out = q(root, "edges", "src/domain/clock.ts")
    assert out["columns"] == ["Direction", "Other", "Kind", "Ring direction"]
    assert sorted(out["rows"]) == [
        ["in", "src/domain/index.ts", "import", "through-barrel"],
        ["in", "src/domain/payroll-use-case.ts", "import", "inward"],
    ]
    rows = q(root, "edges", "src/web/payroll-controller.ts")["rows"]
    assert ["out", "src/domain/payroll-use-case.ts", "import", "inward"] in rows
    assert ["in", "src/web/main.ts", "import", "inward"] in rows


def test_edges_without_path_prints_usage(tmp_path: Path):
    result = run_arch(["query", "edges", *FIXTURE_FLAGS], copy_fixture("payroll", tmp_path / "p"))
    assert result.returncode == 1
    assert result.stderr.strip() == "usage: arch query edges <path> | --kind <kind>"


def test_boolean_flags_never_consume_the_next_argument(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_arch(["query", "fan-in", "--json", "src/domain/clock.ts", *FIXTURE_FLAGS], root)
    assert result.returncode == 0, result.stderr
    importers = {r[0] for r in json.loads(result.stdout)["rows"]}
    assert importers == {"src/domain/payroll-use-case.ts", "src/domain/index.ts"}


def test_null_cells_render_empty_except_metric_columns(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    _set_components(root, lambda cs: cs.append({"id": "C4", "name": "island", "paths": ["src/island/**"], "enforcement": "none", "releaseUnit": "", "entryPoints": []}))
    metrics = run_arch(["query", "metrics", *FIXTURE_FLAGS], root)
    assert "| C4 island | 0 | 0 | 0 | undefined | undefined | undefined | none |" in metrics.stdout.splitlines()
    ports = run_arch(["query", "ports", *FIXTURE_FLAGS], root)
    clock = next(l for l in ports.stdout.splitlines() if l.startswith("| src/domain/clock.ts:Clock"))
    assert clock.startswith("| src/domain/clock.ts:Clock | C1 |  | ")
    assert "undefined" not in ports.stdout
    as_json = q(root, "metrics")
    assert set(as_json) == {"columns", "rows"}
    assert next(r for r in as_json["rows"] if r[0] == "C4 island")[4:7] == [None, None, None]


def test_touched_lists_untracked_units_and_skips_deleted_non_units(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    (root / "src/domain/notes.md").write_text("notes\n")
    init_repo(root)
    (root / "src/domain/notes.md").unlink()
    (root / "src/domain/payslip.ts").write_text("export class Payslip {}\n")
    cruise = json.loads((root / "cruise.json").read_text())
    cruise["modules"].append({"source": "src/domain/payslip.ts", "dependencies": []})
    (root / "cruise.json").write_text(json.dumps(cruise))
    facts = json.loads((root / "facts.json").read_text())
    facts["modules"]["src/domain/payslip.ts"] = {"exports": {"abstract": 0, "concrete": 1}, "implements": [], "constructs": [], "signatures": []}
    (root / "facts.json").write_text(json.dumps(facts))
    rows = q(root, "touched", "--base", "HEAD")["rows"]
    paths = {r[0]: r[4] for r in rows}
    assert paths.get("src/domain/payslip.ts") == "added"
    assert "src/domain/notes.md" not in paths


def test_touched_lists_a_deleted_unit(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    (root / "src/web/main.ts").unlink()
    cruise = json.loads((root / "cruise.json").read_text())
    cruise["modules"] = [m for m in cruise["modules"] if m["source"] != "src/web/main.ts"]
    (root / "cruise.json").write_text(json.dumps(cruise))
    rows = q(root, "touched", "--base", "HEAD")["rows"]
    assert ["src/web/main.ts", "C3", "composition-root", "frameworks", "deleted", ""] in rows


def test_ring_crossings_same_lists_edges_within_one_ring(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    rows = q(root, "ring-crossings", "--direction", "same")["rows"]
    assert sorted(rows) == [
        ["src/domain/payroll-repository.ts", "entities", "src/domain/employee.ts", "entities", "type-import"],
        ["src/web/legacy-router.js", "adapters", "src/web/payroll-controller.ts", "adapters", "import"],
        ["src/web/payroll-controller.ts", "adapters", "src/adapters/pg-payroll-repository.ts", "adapters", "constructs"],
        ["src/web/payroll-controller.ts", "adapters", "src/adapters/pg-payroll-repository.ts", "adapters", "import"],
        ["src/web/payroll-controller.ts", "adapters", "src/adapters/system-clock.ts", "adapters", "constructs"],
        ["src/web/payroll-controller.ts", "adapters", "src/adapters/system-clock.ts", "adapters", "import"],
    ]
    inward = q(root, "ring-crossings", "--direction", "inward")["rows"]
    assert all(r[1] != r[3] for r in inward)


def test_touched_with_neighbors_adds_untouched_neighbor_unit_rows(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    (root / "src/domain/employee.ts").write_text("export class Employee { name = 'x'; }\n")
    out = q(root, "touched", "--base", "HEAD", "--with-neighbors")
    assert set(out) == {"touched", "neighbors"}
    assert [r[0] for r in out["touched"]["rows"]] == ["src/domain/employee.ts"]
    assert out["neighbors"]["columns"] == ["Path", "Component", "Kind", "Ring", "Actors", "Abstract", "Concrete"]
    assert [r[0] for r in out["neighbors"]["rows"]] == ["src/adapters/memory-payroll-repository.ts", "src/adapters/pg-payroll-repository.ts", "src/domain/index.ts", "src/domain/payroll-repository.ts", "src/domain/payroll-use-case.ts"]
    assert out["neighbors"]["rows"][4][1:4] == ["C1", "use-case", "use-cases"]
    markdown = run_arch(["query", "touched", "--base", "HEAD", "--with-neighbors", *FIXTURE_FLAGS], root).stdout
    assert "| Path | Component | Kind | Ring | Change | Neighbors |" in markdown
    assert "| Path | Component | Kind | Ring | Actors | Abstract | Concrete |" in markdown


def test_groups_query_lists_groups_added_to_the_model(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    assert q(root, "groups")["rows"] == []
    assert run_arch(["model", "add-group", "core", "components=C1,C2", "absorbs=domain rule changes"], root).returncode == 0
    out = q(root, "groups")
    assert out["columns"] == ["Group", "Components", "Absorbs"]
    assert out["rows"] == [["core", ["C1", "C2"], "domain rule changes"]]


def test_components_query_lists_the_component_record(tmp_path: Path):
    out = q(copy_fixture("payroll", tmp_path / "p"), "components")
    assert out["columns"] == ["Component", "Name", "Enforcement", "Release unit", "Entry points", "Units"]
    assert out["rows"] == [
        ["C1", "domain", "none", "", [], 5],
        ["C2", "adapters", "none", "", [], 3],
        ["C3", "web", "none", "", ["src/web/main.ts"], 3],
    ]


def test_edges_by_kind_without_a_path_lists_every_edge_of_that_kind(tmp_path: Path):
    out = q(copy_fixture("payroll", tmp_path / "p"), "edges", "--kind", "constructs")
    assert out["columns"] == ["From", "To", "Kind", "Ring direction"]
    assert [r[:2] for r in out["rows"]] == [
        ["src/web/payroll-controller.ts", "src/adapters/pg-payroll-repository.ts"],
        ["src/web/payroll-controller.ts", "src/adapters/system-clock.ts"],
        ["src/web/payroll-controller.ts", "src/domain/payroll-use-case.ts"],
    ]
    assert {r[2] for r in out["rows"]} == {"constructs"}



BARREL = "src/domain/index.ts"


def test_barrel_edges_are_through_barrel(tmp_path: Path):
    rows = q(copy_fixture("payroll", tmp_path / "p"), "edges", BARREL)["rows"]
    assert sorted(rows) == [
        ["in", "src/adapters/system-clock.ts", "type-import", "through-barrel"],
        ["out", "src/domain/clock.ts", "import", "through-barrel"],
        ["out", "src/domain/employee.ts", "import", "through-barrel"],
        ["out", "src/domain/payroll-repository.ts", "import", "through-barrel"],
        ["out", "src/domain/payroll-use-case.ts", "import", "through-barrel"],
    ]


def test_ring_crossings_leave_out_barrel_edges(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    for direction in ("outward", "inward", "same"):
        rows = q(root, "ring-crossings", "--direction", direction)["rows"]
        assert not any(BARREL in (r[0], r[2]) for r in rows), direction


def test_ring_crossings_include_barrel_edges_by_their_rings_when_asked(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    assert q(root, "ring-crossings", "--include-barrels")["rows"] == [
        [BARREL, "entities", "src/domain/payroll-use-case.ts", "use-cases", "import"],
    ]
    inward = q(root, "ring-crossings", "--include-barrels", "--direction", "inward")["rows"]
    assert ["src/adapters/system-clock.ts", "adapters", BARREL, "entities", "type-import"] in inward
