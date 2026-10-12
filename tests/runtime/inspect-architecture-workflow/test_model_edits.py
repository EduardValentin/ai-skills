import json
from pathlib import Path

from support import FIXTURE_FLAGS, copy_fixture, init_repo, run_arch


def overrides(root: Path) -> list:
    return json.loads((root / "docs/architecture/model/overrides.json").read_text())["overrides"]


def test_add_override_upserts_and_sorts(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    assert run_arch(["model", "add-override", "src/domain/employee.ts", "ring=entities", "kind=boundary-data", "actors=finance,hr"], root).returncode == 0
    assert run_arch(["model", "add-override", "src/adapters/system-clock.ts", "ring=adapters", "kind=gateway"], root).returncode == 0
    assert run_arch(["model", "add-override", "src/domain/employee.ts", "ring=entities", "kind=entity"], root).returncode == 0
    rows = overrides(root)
    assert [r["path"] for r in rows] == ["src/adapters/system-clock.ts", "src/domain/employee.ts"]
    assert rows[1]["kind"] == "entity" and rows[1]["actors"] == []


def test_add_override_rejects_unknown_kind(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_arch(["model", "add-override", "src/domain/employee.ts", "ring=entities", "kind=widget"], root)
    assert result.returncode == 1 and "unknown kind: widget" in result.stderr
    assert overrides(root) == []


def test_remove_override_missing(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_arch(["model", "remove-override", "src/nope.ts"], root)
    assert result.returncode == 1 and "no override for src/nope.ts" in result.stderr


def test_add_port_assigns_next_id(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    assert run_arch(["model", "add-port", "src/domain/employee.ts", "Employees", "owner=C1", "humble=adapters"], root).returncode == 0
    ports = json.loads((root / "docs/architecture/model/boundaries.json").read_text())["ports"]
    assert ports[-1] == {"id": "B3", "path": "src/domain/employee.ts", "symbol": "Employees", "owner": "C1", "humbleSide": "adapters"}


def test_add_component_rejects_duplicate(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_arch(["model", "add-component", "C1", "again", "paths=src/x/**"], root)
    assert result.returncode == 1 and "duplicate component id: C1" in result.stderr


def test_add_rule_before(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    assert run_arch(["model", "add-rule", "match=src/domain/**/*.dto.ts", "ring=entities", "kind=boundary-data", "before=src/domain/**"], root).returncode == 0
    rules = json.loads((root / "docs/architecture/model/rules.json").read_text())["rules"]
    index = [r["match"] for r in rules].index("src/domain/**/*.dto.ts")
    assert rules[index + 1]["match"] == "src/domain/**"


def test_validate_reports_ok(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_arch(["model", "validate", *FIXTURE_FLAGS], root)
    assert result.returncode == 0 and result.stdout.strip() == "model: ok"


def test_remove_rule_removes_exactly_one_and_keeps_order(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    rules_path = root / "docs/architecture/model/rules.json"
    before = [r["match"] for r in json.loads(rules_path.read_text())["rules"]]
    result = run_arch(["model", "remove-rule", "match=src/domain/clock.ts"], root)
    assert result.returncode == 0, result.stderr
    after = [r["match"] for r in json.loads(rules_path.read_text())["rules"]]
    before.remove("src/domain/clock.ts")
    assert after == before


def test_remove_rule_missing(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_arch(["model", "remove-rule", "match=src/nope/**"], root)
    assert result.returncode == 1 and "no rule matching src/nope/**" in result.stderr


def test_remove_component_refuses_while_referenced_then_succeeds_once_unreferenced(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    components_path = root / "docs/architecture/model/components.json"
    assert run_arch(["model", "add-component", "C9", "throwaway", "paths=src/throwaway/**"], root).returncode == 0

    result = run_arch(["model", "remove-component", "C1"], root)
    assert result.returncode == 1
    assert "component C1 is referenced by" in result.stderr
    ids = [c["id"] for c in json.loads(components_path.read_text())["components"]]
    assert "C1" in ids

    result = run_arch(["model", "remove-component", "C9"], root)
    assert result.returncode == 0, result.stderr
    ids = [c["id"] for c in json.loads(components_path.read_text())["components"]]
    assert "C9" not in ids and "C1" in ids


def test_remove_component_missing(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_arch(["model", "remove-component", "C9"], root)
    assert result.returncode == 1 and "no component C9" in result.stderr


def test_validate_passes_with_adapter_warnings(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    cruise = json.loads((root / "cruise.json").read_text())
    emp = next(m for m in cruise["modules"] if m["source"] == "src/domain/employee.ts")
    emp["dependencies"].append({"module": "@app/missing", "resolved": "@app/missing", "dependencyTypes": ["unknown"], "couldNotResolve": True})
    (root / "cruise.json").write_text(json.dumps(cruise))
    result = run_arch(["model", "validate", *FIXTURE_FLAGS], root)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "model: ok"
    assert "unresolved import @app/missing in src/domain/employee.ts" in result.stderr


def test_validate_fails_on_a_model_problem(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    assert run_arch(["model", "add-rule", "match=src/nowhere/**", "ring=entities", "kind=entity"], root).returncode == 0
    result = run_arch(["model", "validate", *FIXTURE_FLAGS], root)
    assert result.returncode == 1
    assert "unused rule: src/nowhere/**" in result.stderr


def test_kinds_come_from_rules_json_when_listed(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    rules_path = root / "docs/architecture/model/rules.json"
    rules = json.loads(rules_path.read_text())
    rules["kinds"] = ["entity", "use-case", "port", "adapter", "controller", "composition-root", "saga"]
    rules_path.write_text(json.dumps(rules))
    accepted = run_arch(["model", "add-override", "src/domain/employee.ts", "ring=use-cases", "kind=saga"], root)
    assert accepted.returncode == 0, accepted.stderr
    refused = run_arch(["model", "add-override", "src/adapters/system-clock.ts", "ring=adapters", "kind=gateway"], root)
    assert refused.returncode == 1 and "unknown kind: gateway" in refused.stderr
    assert [o["kind"] for o in overrides(root)] == ["saga"]


def test_model_without_subcommand_prints_usage(tmp_path: Path):
    result = run_arch(["model"], copy_fixture("payroll", tmp_path / "p"))
    assert result.returncode == 1
    assert result.stderr.strip() == "usage: arch model <validate|add-override|remove-override|add-port|remove-port|add-component|remove-component|add-rule|remove-rule>"


def test_edits_check_required_arguments(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    model_dir = root / "docs/architecture/model"
    before = {f.name: f.read_bytes() for f in model_dir.iterdir()}
    cases = [
        (["add-rule", "ring=entities", "kind=entity"], "usage: arch model add-rule match=<glob> ring=<r> kind=<k> [actors=a,b] [before=<glob>]"),
        (["add-override", "ring=entities", "kind=entity"], "usage: arch model add-override <path> ring=<r> kind=<k> [actors=a,b] [reason=<text>]"),
        (["add-component", "C9", "nine"], "usage: arch model add-component <id> <name> paths=<glob,...> [enforcement=<text>] [release=<text>] [entry=<glob,...>]"),
        (["add-component", "paths=src/x/**"], "usage: arch model add-component <id> <name> paths=<glob,...> [enforcement=<text>] [release=<text>] [entry=<glob,...>]"),
    ]
    for args, usage in cases:
        result = run_arch(["model", *args], root)
        assert result.returncode == 1, args
        assert result.stderr.strip() == usage, args
    assert {f.name: f.read_bytes() for f in model_dir.iterdir()} == before


def test_add_component_refuses_globs_overlapping_tracked_paths(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    components_path = root / "docs/architecture/model/components.json"
    before = components_path.read_bytes()
    result = run_arch(["model", "add-component", "C9", "employees", "paths=src/domain/employee.ts"], root)
    assert result.returncode == 1
    assert "component globs overlap: C1 and C9" in result.stderr
    assert components_path.read_bytes() == before


def test_refused_edit_leaves_the_file_bytes_untouched(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    overrides_path = root / "docs/architecture/model/overrides.json"
    before = overrides_path.read_bytes()
    result = run_arch(["model", "add-override", "src/domain/employee.ts", "ring=nowhere", "kind=entity"], root)
    assert result.returncode == 1 and "unknown ring: nowhere" in result.stderr
    assert overrides_path.read_bytes() == before
