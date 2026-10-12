import json
from pathlib import Path

from support import FIXTURE_FLAGS, copy_fixture, run_arch


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
