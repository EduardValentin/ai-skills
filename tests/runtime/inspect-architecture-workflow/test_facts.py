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
    assert "| C1 domain | 4 | 4 | 0 | 0 | undefined | undefined | none |" in metrics.stdout.splitlines()


def test_exports_json_is_an_alias_without_constructs_or_signatures(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    g = graph(root, ["--cruise-json", "cruise.json", "--exports-json", "exports.json"])
    assert g["capabilities"] == {"exports": True, "implements": True, "constructs": False, "signatures": False}
    assert not any(e["kind"] == "constructs" for e in g["edges"])
    c1 = next(c for c in g["components"] if c["id"] == "C1")
    assert (c1["units"], c1["fanIn"], c1["abstractness"], c1["distance"]) == (4, 4, 0.5, 0.5)
    result = run_arch(["query", "signatures", "src/domain/payroll-use-case.ts", "--cruise-json", "cruise.json", "--exports-json", "exports.json"], root)
    assert result.returncode == 0 and result.stdout.strip() == "not provided by the adapter"


def _extract(root: Path) -> dict:
    script = (f"import {{ createTypescriptAdapter }} from '{ADAPTER.as_posix()}';"
              "const a = createTypescriptAdapter({root: process.cwd(), tooling: {language:'typescript', roots:['src']}});"
              f"const r = await a.extract({{roots:['src'], cruiseJsonPath:'cruise.json', ports:{json.dumps(PORTS)}}});"
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
