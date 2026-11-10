import json
from pathlib import Path

from support import SKILL_DIR, copy_fixture, run_node

MODEL = SKILL_DIR / "scripts" / "lib" / "model.mjs"


def node_eval(expr: str, cwd: Path) -> str:
    script = f"import * as m from '{MODEL.as_posix()}';const model = await m.loadModel(process.cwd());process.stdout.write(JSON.stringify({expr}));"
    result = run_node(script, cwd)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_classify_uses_override_then_first_rule(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    out = json.loads(node_eval("[m.classify(model,'src/domain/payroll-use-case.ts'), m.classify(model,'src/domain/employee.ts')]", root))
    assert out[0]["kind"] == "use-case" and out[0]["ring"] == "use-cases" and out[0]["component"] == "C1" and out[0]["source"] == "rule"
    assert out[1]["kind"] == "entity"


def test_barrel_is_a_default_kind_and_the_fixture_classifies_its_barrel(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    out = json.loads(node_eval("[m.KINDS.includes('barrel'), m.classify(model,'src/domain/index.ts')]", root))
    assert out[0] is True
    assert out[1]["kind"] == "barrel" and out[1]["ring"] == "entities" and out[1]["component"] == "C1"


def test_override_beats_rule(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    overrides = root / "docs/architecture/model/overrides.json"
    overrides.write_text(json.dumps({"version": 1, "overrides": [{"path": "src/domain/employee.ts", "ring": "entities", "kind": "boundary-data", "actors": ["finance"]}]}))
    out = json.loads(node_eval("m.classify(model,'src/domain/employee.ts')", root))
    assert out["kind"] == "boundary-data" and out["actors"] == ["finance"] and out["source"] == "override"


def test_unclassified_path_returns_nulls(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    out = json.loads(node_eval("m.classify(model,'scripts/build.ts')", root))
    assert out == {"component": None, "ring": None, "kind": None, "actors": [], "source": None}


def test_validate_rejects_overlapping_component_globs(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    comp = root / "docs/architecture/model/components.json"
    data = json.loads(comp.read_text())
    data["components"].append({"id": "C9", "name": "domain-orders", "paths": ["src/domain/**"], "enforcement": "none", "releaseUnit": "", "entryPoints": []})
    comp.write_text(json.dumps(data))
    out = json.loads(node_eval("m.validateModel(model, new Set(['src/domain/employee.ts']))", root))
    assert any("overlap" in p and "C1" in p and "C9" in p for p in out)


def test_validate_reports_group_problems(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    boundaries = root / "docs/architecture/model/boundaries.json"
    data = json.loads(boundaries.read_text())
    data["groups"] = [
        {"name": "core", "components": ["C1", "C9"], "absorbs": "domain rule changes"},
        {"name": "core", "components": ["C1"], "absorbs": "duplicate"},
    ]
    boundaries.write_text(json.dumps(data))
    out = json.loads(node_eval("m.validateModel(model, new Set(['src/domain/employee.ts']))", root))
    assert "group core: not a component: C9" in out
    assert "duplicate group name: core" in out


def test_validate_reports_stale_override_and_unknown_kind(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    (root / "docs/architecture/model/overrides.json").write_text(json.dumps({"version": 1, "overrides": [{"path": "src/gone.ts", "ring": "entities", "kind": "widget", "actors": []}]}))
    out = json.loads(node_eval("m.validateModel(model, new Set(['src/domain/employee.ts']))", root))
    assert "stale override: src/gone.ts" in out
    assert any("unknown kind: widget" in p for p in out)


def test_write_model_file_is_canonical(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    script = (f"import * as m from '{MODEL.as_posix()}';const model = await m.loadModel(process.cwd());"
              "await m.writeModelFile(model,'overrides',{version:1,overrides:[{path:'b.ts',ring:'entities',kind:'entity',actors:[]},{path:'a.ts',ring:'entities',kind:'entity',actors:[]}]});")
    result = run_node(script, root)
    assert result.returncode == 0, result.stderr
    text = (root / "docs/architecture/model/overrides.json").read_text()
    lines = text.splitlines()
    assert lines[0] == "{"
    assert lines[1] == '  "version": 1,'
    assert lines[2] == '  "overrides": ['
    assert lines[3].startswith('    { "path": "a.ts"')
    assert lines[4].startswith('    { "path": "b.ts"')
    assert text.endswith("]\n}\n")
