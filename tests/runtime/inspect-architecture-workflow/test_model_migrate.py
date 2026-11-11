import json
from pathlib import Path

from support import copy_fixture, git, run_arch

RECORD = "docs/architecture"


def payroll_with_old_model(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    new_file = root / RECORD / "architecture.json"
    expected = json.loads(new_file.read_text())
    new_file.unlink()
    copy_fixture("legacy-model", root)
    return root, expected


def migrate(root: Path):
    return run_arch(["model", "migrate"], root)


def test_migrate_converts_the_four_file_model(tmp_path: Path):
    root, expected = payroll_with_old_model(tmp_path)
    result = migrate(root)
    assert result.returncode == 0, result.stderr
    expected["adapter"] = ""
    del expected["rules"]
    assert json.loads((root / RECORD / "architecture.json").read_text()) == expected


def test_migrate_prints_the_adapter_instruction_and_keeps_the_old_files(tmp_path: Path):
    root, _ = payroll_with_old_model(tmp_path)
    result = migrate(root)
    assert "adapter" in result.stdout and "set-adapter" in result.stdout
    for name in ["components", "rules", "overrides", "boundaries"]:
        assert (root / RECORD / "model" / f"{name}.json").exists()


def test_migrate_output_is_valid_once_the_adapter_is_set(tmp_path: Path):
    root, _ = payroll_with_old_model(tmp_path)
    migrate(root)
    assert run_arch(["model", "validate"], root).returncode == 2
    assert run_arch(["model", "set-adapter", "cat adapter.json"], root).returncode == 0
    assert run_arch(["model", "validate"], root).returncode == 0


def test_migrate_turns_overrides_into_exact_path_pairs_placed_first(tmp_path: Path):
    root, _ = payroll_with_old_model(tmp_path)
    overrides = root / RECORD / "model/overrides.json"
    overrides.write_text(json.dumps({"version": 1, "overrides": [
        {"path": "src/domain/employee.ts", "ring": "entities", "kind": "boundary-data", "actors": ["hr"],
         "reason": "shared record"}]}))
    assert migrate(root).returncode == 0
    domain = json.loads((root / RECORD / "architecture.json").read_text())["components"][0]
    assert domain["classify"][0] == ["employee.ts", "boundary-data",
                                     {"ring": "entities", "actors": ["hr"], "reason": "shared record"}]


def test_migrate_carries_groups_by_component_name(tmp_path: Path):
    root, _ = payroll_with_old_model(tmp_path)
    boundaries = root / RECORD / "model/boundaries.json"
    data = json.loads(boundaries.read_text())
    data["groups"] = [{"name": "core", "components": ["C1", "C2"], "absorbs": "rule changes"}]
    boundaries.write_text(json.dumps(data))
    assert migrate(root).returncode == 0
    groups = json.loads((root / RECORD / "architecture.json").read_text())["groups"]
    assert groups == [{"name": "core", "members": ["domain", "adapters"], "absorbs": "rule changes"}]


def test_migrate_refuses_to_overwrite_a_model(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = migrate(root)
    assert result.returncode == 2 and "already exists" in result.stderr


def test_migrate_without_old_files_says_what_is_missing(tmp_path: Path):
    result = migrate(tmp_path)
    assert result.returncode == 2 and "components.json" in result.stderr


def test_migrate_refuses_a_rule_that_falls_under_no_component(tmp_path: Path):
    root, _ = payroll_with_old_model(tmp_path)
    rules = root / RECORD / "model/rules.json"
    data = json.loads(rules.read_text())
    data["rules"].append({"match": "scripts/**", "ring": "frameworks", "kind": "config", "actors": []})
    rules.write_text(json.dumps(data))
    result = migrate(root)
    assert result.returncode == 2 and "scripts/**" in result.stderr
    assert not (root / RECORD / "architecture.json").exists()


def test_migrate_maps_component_ids_inside_shapes(tmp_path: Path):
    root, _ = payroll_with_old_model(tmp_path)
    boundaries = root / RECORD / "model/boundaries.json"
    data = json.loads(boundaries.read_text())
    data["shapes"] = [{"name": "payroll-flow", "owner": "C1", "components": ["C1", "C3"]}]
    boundaries.write_text(json.dumps(data))
    assert migrate(root).returncode == 0
    shapes = json.loads((root / RECORD / "architecture.json").read_text())["shapes"]
    assert shapes == [{"name": "payroll-flow", "owner": "domain", "components": ["domain", "web"]}]


def test_migrate_gives_a_rule_to_the_component_with_the_longest_matching_prefix(tmp_path: Path):
    root, _ = payroll_with_old_model(tmp_path)
    components = root / RECORD / "model/components.json"
    data = json.loads(components.read_text())
    data["components"].append({"id": "C4", "name": "reports", "paths": ["src/domain/reports/*.ts"],
                               "enforcement": "none", "releaseUnit": "", "entryPoints": []})
    components.write_text(json.dumps(data))
    rules = root / RECORD / "model/rules.json"
    old = json.loads(rules.read_text())
    old["rules"].insert(0, {"match": "src/domain/reports/*.ts", "ring": "use-cases", "kind": "use-case", "actors": []})
    rules.write_text(json.dumps(old))
    assert migrate(root).returncode == 0
    names = {c["name"]: c for c in json.loads((root / RECORD / "architecture.json").read_text())["components"]}
    assert names["reports"]["classify"] == [["*.ts", "use-case"]]
    assert ["reports/*.ts", "use-case"] not in names["domain"]["classify"]


def test_migrate_takes_the_record_mode_and_excludes_a_local_record(tmp_path: Path):
    root, _ = payroll_with_old_model(tmp_path)
    git(["init", "-q", "-b", "main"], root)
    result = run_arch(["model", "migrate", "--record-mode", "local"], root)
    assert result.returncode == 0, result.stderr
    assert json.loads((root / RECORD / "architecture.json").read_text())["record"] == "local"
    assert "/docs/architecture/" in (root / ".git/info/exclude").read_text().splitlines()
