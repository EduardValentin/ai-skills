import json
from pathlib import Path

import pytest

from support import FIXTURE_FLAGS, SKILL_DIR, copy_fixture, install_fake_tooling, run_arch, run_node

ADAPTER = SKILL_DIR / "scripts" / "lib" / "adapters" / "typescript.mjs"
PORTS = [
    {"path": "src/domain/payroll-repository.ts", "symbol": "PayrollRepository"},
    {"path": "src/domain/clock.ts", "symbol": "Clock"},
]


def q(root: Path, *args: str, flags: list[str] = FIXTURE_FLAGS) -> dict:
    result = run_arch(["query", *args, *flags, "--json"], root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def graph(root: Path, flags: list[str] = FIXTURE_FLAGS) -> dict:
    result = run_arch(["graph", *flags, "--json"], root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def set_capability(root: Path, name: str, value: bool) -> None:
    facts_file = root / "facts.json"
    facts = json.loads(facts_file.read_text())
    facts["capabilities"][name] = value
    facts_file.write_text(json.dumps(facts))


def test_graph_records_capabilities_and_unit_signatures(tmp_path: Path):
    g = graph(copy_fixture("payroll", tmp_path / "p"))
    assert g["capabilities"] == {"exports": True, "implements": True, "constructs": True, "signatures": True}
    units = {u["path"]: u for u in g["units"]}
    assert units["src/adapters/memory-payroll-repository.ts"]["signatures"] == [
        {"symbol": "memoryPayrollRepository", "types": [{"symbol": "Employee", "path": "src/domain/employee.ts"}]},
    ]


def test_constructs_become_edges_classified_like_imports(tmp_path: Path):
    g = graph(copy_fixture("payroll", tmp_path / "p"))
    constructs = {(e["to"], e["crossesComponent"], e["crossesRing"], e["direction"])
                  for e in g["edges"] if e["kind"] == "constructs"}
    assert constructs == {
        ("src/adapters/pg-payroll-repository.ts", True, False, "same"),
        ("src/adapters/system-clock.ts", True, False, "same"),
        ("src/domain/payroll-use-case.ts", True, True, "inward"),
    }
    assert all(e["from"] == "src/web/payroll-controller.ts" for e in g["edges"] if e["kind"] == "constructs")


def test_signatures_query_lists_one_row_per_imported_type(tmp_path: Path):
    out = q(copy_fixture("payroll", tmp_path / "p"), "signatures", "src/domain/payroll-use-case.ts")
    assert out["columns"] == ["Symbol", "Type", "From"]
    assert out["rows"] == [
        ["PayrollUseCase", "PayrollRepository", "src/domain/payroll-repository.ts"],
        ["PayrollUseCase", "Clock", "src/domain/clock.ts"],
        ["PayrollUseCase", "Employee", "src/domain/employee.ts"],
    ]


def test_signatures_query_without_path_prints_usage(tmp_path: Path):
    result = run_arch(["query", "signatures", *FIXTURE_FLAGS], copy_fixture("payroll", tmp_path / "p"))
    assert result.returncode == 1
    assert result.stderr.strip() == "usage: arch query signatures <path>"


def test_ports_list_nominal_and_structural_implementers_once(tmp_path: Path):
    rows = q(copy_fixture("payroll", tmp_path / "p"), "ports")["rows"]
    repository = next(r for r in rows if r[0] == "src/domain/payroll-repository.ts:PayrollRepository")
    assert repository[3] == "src/adapters/memory-payroll-repository.ts, src/adapters/pg-payroll-repository.ts"


def test_edges_query_shows_constructs_rows(tmp_path: Path):
    rows = q(copy_fixture("payroll", tmp_path / "p"), "edges", "src/web/payroll-controller.ts")["rows"]
    assert ["out", "src/adapters/pg-payroll-repository.ts", "constructs", "same"] in rows
    assert ["out", "src/adapters/system-clock.ts", "constructs", "same"] in rows
    assert ["out", "src/domain/payroll-use-case.ts", "constructs", "inward"] in rows


def test_absent_signatures_capability_is_reported_not_empty(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    set_capability(root, "signatures", False)
    result = run_arch(["query", "signatures", "src/domain/payroll-use-case.ts", *FIXTURE_FLAGS], root)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "not provided by the adapter"
    assert graph(root)["capabilities"]["signatures"] is False


def test_absent_implements_capability_is_reported_in_ports(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    set_capability(root, "implements", False)
    rows = q(root, "ports")["rows"]
    assert all(r[3] == "not provided by the adapter" for r in rows)


def test_absent_constructs_capability_adds_no_constructs_edges(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    set_capability(root, "constructs", False)
    assert not any(e["kind"] == "constructs" for e in graph(root)["edges"])


def test_absent_exports_capability_leaves_abstractness_undefined(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    set_capability(root, "exports", False)
    c1 = next(c for c in graph(root)["components"] if c["id"] == "C1")
    assert c1["abstractness"] is None and c1["distance"] is None and c1["inZone"] is None
    metrics = run_arch(["query", "metrics", *FIXTURE_FLAGS], root)
    assert "| C1 domain | 5 | 4 | 0 | 0 | undefined | undefined | none |" in metrics.stdout.splitlines()


def test_exports_json_is_an_alias_without_constructs_or_signatures(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    g = graph(root, ["--cruise-json", "cruise.json", "--exports-json", "exports.json"])
    assert g["capabilities"] == {"exports": True, "implements": True, "constructs": False, "signatures": False}
    assert not any(e["kind"] == "constructs" for e in g["edges"])
    c1 = next(c for c in g["components"] if c["id"] == "C1")
    assert (c1["units"], c1["fanIn"], c1["abstractness"], c1["distance"]) == (5, 4, 0.5, 0.5)
    result = run_arch(["query", "signatures", "src/domain/payroll-use-case.ts", "--cruise-json", "cruise.json", "--exports-json", "exports.json"], root)
    assert result.returncode == 0 and result.stdout.strip() == "not provided by the adapter"


def _extract(root: Path) -> dict:
    script = (f"import {{ createTypescriptAdapter }} from '{ADAPTER.as_posix()}';"
              "const a = createTypescriptAdapter({root: process.cwd(), tooling: {language:'typescript', roots:['src']}});"
              f"const r = await a.extract({{roots:['src'], dependenciesJsonPath:'cruise.json', ports:{json.dumps(PORTS)}}});"
              "process.stdout.write(JSON.stringify(r));")
    result = run_node(script, root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_adapter_without_a_program_falls_back_to_per_file_facts(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    install_fake_tooling(root)
    out = _extract(root)
    assert out["capabilities"] == {"exports": True, "implements": True, "constructs": False, "signatures": False}
    assert any(w.startswith("cannot build a TypeScript program") for w in out["warnings"])
    assert all("constructs" not in m and "signatures" not in m for m in out["modules"])


def test_adapter_output_equals_the_saved_facts(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    has_ts = run_node("import {createRequire} from 'node:module';try{createRequire(process.cwd()+'/x.js').resolve('typescript');process.stdout.write('yes')}catch{process.stdout.write('no')}", root).stdout == "yes"
    if not has_ts:
        pytest.skip("typescript not resolvable from the fixture")
    saved = json.loads((root / "facts.json").read_text())
    out = _extract(root)
    assert out["capabilities"] == saved["capabilities"]
    assert sorted(m["path"] for m in out["modules"]) == sorted(saved["modules"])
    for module in out["modules"]:
        expected = saved["modules"][module["path"]]
        for field in ("exports", "implements", "constructs", "signatures"):
            assert module[field] == expected[field], (module["path"], field)


FAKE_PROGRAM_TYPESCRIPT = """module.exports = {
  ScriptTarget: { Latest: 99 },
  SyntaxKind: {},
  createSourceFile: () => ({ statements: [] }),
  sys: { readFile: () => "{}" },
  readConfigFile: () => ({ config: {} }),
  parseJsonConfigFileContent: () => ({ options: {} }),
  createProgram: (files, options) => {
    if (options.allowJs !== true || options.checkJs !== false) throw new Error("scripts are not in the program");
    return { getSourceFile: () => undefined, getTypeChecker: () => ({ isTypeAssignableTo: () => false }) };
  },
};
"""


def install_program_without_source_files(root: Path) -> None:
    install_fake_tooling(root)
    (root / "node_modules/typescript/index.js").write_text(FAKE_PROGRAM_TYPESCRIPT)


def add_cruised_module(root: Path, source: str) -> None:
    cruise = json.loads((root / "cruise.json").read_text())
    cruise["modules"].append({"source": source, "dependencies": [], "dependents": [], "orphan": True, "valid": True})
    (root / "cruise.json").write_text(json.dumps(cruise))


def test_a_script_the_program_lacks_comes_from_the_per_file_scan(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    install_program_without_source_files(root)
    out = _extract(root)
    assert out["capabilities"] == {"exports": True, "implements": True, "constructs": True, "signatures": True}
    assert "facts for src/web/legacy-router.js come from the per-file scan" in out["warnings"]
    assert not any(w.startswith("cannot read") for w in out["warnings"])
    router = next(m for m in out["modules"] if m["path"] == "src/web/legacy-router.js")
    assert (router["constructs"], router["signatures"]) == ([], [])


def test_a_module_that_is_not_a_script_gets_empty_facts_without_a_warning(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    (root / "src/web/payroll.css").write_text("body { color: black; }\n")
    add_cruised_module(root, "src/web/payroll.css")
    install_program_without_source_files(root)
    out = _extract(root)
    assert not any("payroll.css" in w for w in out["warnings"])
    stylesheet = next(m for m in out["modules"] if m["path"] == "src/web/payroll.css")
    assert stylesheet == {"path": "src/web/payroll.css", "exports": {"abstract": 0, "concrete": 0}, "implements": [], "constructs": [], "signatures": []}


def test_the_script_module_is_in_the_graph_with_its_saved_facts(tmp_path: Path):
    g = graph(copy_fixture("payroll", tmp_path / "p"))
    router = next(u for u in g["units"] if u["path"] == "src/web/legacy-router.js")
    assert router["exports"] == {"abstract": 0, "concrete": 1}
    assert ("src/web/legacy-router.js", "src/web/payroll-controller.ts", "import") in {(e["from"], e["to"], e["kind"]) for e in g["edges"]}
    assert not any("legacy-router" in w for w in g["warnings"])


def test_the_generic_saved_output_flag_and_the_older_one_build_the_same_graph(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    generic = graph(root, ["--dependencies-json", "cruise.json", "--facts-json", "facts.json"])
    older = graph(root, ["--cruise-json", "cruise.json", "--facts-json", "facts.json"])
    assert generic["edges"] == older["edges"] and generic["units"] == older["units"]
