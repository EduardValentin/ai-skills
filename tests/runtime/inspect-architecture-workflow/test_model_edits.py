import json
from pathlib import Path

from support import copy_fixture, git, run_arch

RECORD = "docs/architecture/architecture.json"
GUIDANCE_RULES = {"R3", "R15", "R23", "R24", "R26", "R28", "R29", "R32", "R33", "R37"}
LEGACY_ONLY_RULES = {"R6", "R19", "R21", "R22"}


def payroll(tmp_path: Path) -> Path:
    return copy_fixture("payroll", tmp_path / "p")


def model_file(root: Path) -> Path:
    return root / RECORD


def document(root: Path) -> dict:
    return json.loads(model_file(root).read_text())


def edit(root: Path, *args: str):
    return run_arch(["model", *args], root)


def test_init_legacy_writes_only_non_default_statuses(tmp_path: Path):
    result = edit(tmp_path, "init", "--start", "legacy", "--adapter", "cat adapter.json")
    assert result.returncode == 0, result.stderr
    rules = document(tmp_path)["rules"]
    assert set(rules) == GUIDANCE_RULES | LEGACY_ONLY_RULES
    assert {status for status, _ in rules.values()} == {"advisory"}
    assert all(reason for _, reason in rules.values())
    assert document(tmp_path)["adapter"] == "cat adapter.json"
    (tmp_path / "adapter.json").write_text('{"version": 1, "modules": [{"path": "src/domain/entity.ts"}]}')
    assert edit(tmp_path, "add-component", "domain", "paths=src/domain/**").returncode == 0
    assert edit(tmp_path, "classify", "domain", "**", "entity").returncode == 0
    assert edit(tmp_path, "validate").returncode == 0


def test_init_greenfield_writes_only_the_guidance_rules(tmp_path: Path):
    assert edit(tmp_path, "init", "--start", "greenfield", "--adapter", "cat adapter.json").returncode == 0
    assert set(document(tmp_path)["rules"]) == GUIDANCE_RULES


def test_init_local_adds_record_path_to_local_exclude(tmp_path: Path):
    git(["init", "-q", "-b", "main"], tmp_path)
    result = edit(tmp_path, "init", "--start", "greenfield", "--adapter", "a", "--record-mode", "local")
    assert result.returncode == 0, result.stderr
    assert document(tmp_path)["record"] == "local"
    exclude = (tmp_path / ".git/info/exclude").read_text().splitlines()
    assert "/docs/architecture/" in exclude


def test_init_refuses_to_overwrite_an_existing_model(tmp_path: Path):
    root = payroll(tmp_path)
    before = model_file(root).read_bytes()
    result = edit(root, "init", "--start", "greenfield", "--adapter", "a")
    assert result.returncode == 2 and "arch model" in result.stderr and "already exists" in result.stderr
    assert model_file(root).read_bytes() == before


def test_init_needs_start_and_adapter(tmp_path: Path):
    assert edit(tmp_path, "init", "--adapter", "a").returncode == 2
    assert edit(tmp_path, "init", "--start", "greenfield").returncode == 2
    assert edit(tmp_path, "init", "--start", "someday", "--adapter", "a").returncode == 2


def test_set_rule_per_component(tmp_path: Path):
    root = payroll(tmp_path)
    result = edit(root, "set-rule", "R6@domain", "off", "reason=no delivery code lives here")
    assert result.returncode == 0, result.stderr
    rules = document(root)["rules"]
    assert rules["R6@domain"] == ["off", "no delivery code lives here"]
    assert rules["R6"][0] == "off"


def test_set_rule_needs_a_reason(tmp_path: Path):
    result = edit(payroll(tmp_path), "set-rule", "R6@domain", "off")
    assert result.returncode == 2 and "reason" in result.stderr


def test_set_rule_rejects_unknown_component_and_status(tmp_path: Path):
    root = payroll(tmp_path)
    assert "nowhere" in edit(root, "set-rule", "R6@nowhere", "off", "reason=x").stderr
    assert edit(root, "set-rule", "R6", "maybe", "reason=x").returncode == 2


def test_set_threshold_rejects_unknown_knob(tmp_path: Path):
    result = edit(payroll(tmp_path), "set-threshold", "distanceMaxx", "1")
    assert result.returncode == 2
    assert "distanceMaxx" in result.stderr and "painMinFanIn" in result.stderr


def test_set_threshold_checks_type_and_range(tmp_path: Path):
    root = payroll(tmp_path)
    before = model_file(root).read_bytes()
    for knob, value in [("interfaceUseShare", "1.5"), ("escalationFanIn", "0"), ("escalationFanIn", "2.5"),
                        ("distanceDeviations", "0"), ("painMaxInstability", "high"), ("historyWindow", "")]:
        result = edit(root, "set-threshold", knob, value)
        assert result.returncode == 2, (knob, value)
        assert knob in result.stderr, (knob, value, result.stderr)
    assert model_file(root).read_bytes() == before


def test_set_and_unset_threshold(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "set-threshold", "escalationFanIn", "5").returncode == 0
    assert edit(root, "set-threshold", "historyWindow", "3 months").returncode == 0
    assert document(root)["thresholds"] == {"escalationFanIn": 5, "historyWindow": "3 months"}
    assert edit(root, "unset-threshold", "escalationFanIn").returncode == 0
    assert edit(root, "unset-threshold", "historyWindow").returncode == 0
    assert "thresholds" not in document(root)
    assert edit(root, "unset-threshold", "historyWindow").returncode == 2


def test_explain_names_the_matching_pair(tmp_path: Path):
    result = edit(payroll(tmp_path), "explain", "src/domain/payroll-repository.ts")
    assert result.returncode == 0, result.stderr
    assert "domain, pair 2: **/*-repository.ts -> port" in result.stdout
    assert "ring: entities" in result.stdout and "actors: unknown" in result.stdout


def test_explain_reports_an_unclassified_path(tmp_path: Path):
    result = edit(payroll(tmp_path), "explain", "scripts/build.ts")
    assert result.returncode == 0 and "component: none" in result.stdout and "matched: none" in result.stdout


def test_explain_json(tmp_path: Path):
    out = json.loads(edit(payroll(tmp_path), "explain", "src/domain/clock.ts", "--json").stdout)
    assert out["kind"] == "port" and out["matched"] == {"component": "domain", "index": 2, "pattern": "clock.ts"}


def test_explain_thresholds_lists_default_and_project_value(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "set-threshold", "escalationFanIn", "5").returncode == 0
    lines = edit(root, "explain-thresholds").stdout.splitlines()
    fan_in = next(line for line in lines if line.startswith("escalationFanIn"))
    assert "default 3" in fan_in and "project 5" in fan_in
    share = next(line for line in lines if line.startswith("interfaceUseShare"))
    assert "default 0.5" in share and "project 0.5" in share
    assert len(lines) == 15


def test_edit_writes_one_entry_per_line_and_omits_defaults(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "add-port", "src/domain/employee.ts#Employees", "owner=domain", "defers=storage choice").returncode == 0
    assert edit(root, "add-component", "reports", "paths=src/reports/**").returncode == 0
    text = model_file(root).read_text()
    assert text.endswith("}\n") and not text.endswith("\n\n")
    port_lines = [line for line in text.splitlines() if '"at":' in line]
    assert len(port_lines) == 3
    for omitted in ["valueType", "enforcement", "release", '"rings"', '"thresholds"', '"entry": []']:
        assert omitted not in text
    keys = list(json.loads(text))
    assert keys == ["version", "adapter", "record", "components", "ports", "rules"]
    assert edit(root, "validate").returncode == 0
    assert model_file(root).read_text() == text


def test_refused_edit_leaves_the_file_untouched(tmp_path: Path):
    root = payroll(tmp_path)
    before = model_file(root).read_bytes()
    removed = edit(root, "remove-component", "domain")
    assert removed.returncode == 2 and "ports[0].owner" in removed.stderr
    ghost = edit(root, "add-port", "src/domain/x.ts#X", "owner=ghost")
    assert ghost.returncode == 2
    assert model_file(root).read_bytes() == before


def test_add_and_remove_component(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "add-component", "reports", "paths=src/reports/**,src/extra/**").returncode == 0
    assert document(root)["components"][-1] == {"name": "reports", "paths": ["src/reports/**", "src/extra/**"]}
    assert edit(root, "add-component", "reports", "paths=src/x/**").returncode == 2
    assert edit(root, "remove-component", "reports").returncode == 0
    assert edit(root, "remove-component", "reports").returncode == 2


def test_classify_inserts_before_a_pattern_and_replaces_in_place(tmp_path: Path):
    root = payroll(tmp_path)
    result = edit(root, "classify", "domain", "**/*-service.ts", "use-case", "before=**/*-repository.ts",
                  "reason=services are use cases")
    assert result.returncode == 0, result.stderr
    pairs = document(root)["components"][0]["classify"]
    assert pairs[1] == ["**/*-service.ts", "use-case", {"reason": "services are use cases"}]
    assert edit(root, "classify", "domain", "**/*-service.ts", "entity", "actors=hr,finance").returncode == 0
    pairs = document(root)["components"][0]["classify"]
    assert [p[0] for p in pairs].count("**/*-service.ts") == 1
    assert pairs[1][1:] == ["entity", {"actors": ["hr", "finance"]}]
    assert edit(root, "classify", "domain", "x.ts", "entity", "before=missing").returncode == 2
    assert edit(root, "classify", "domain", "x.ts", "widget").returncode == 2


def test_classify_records_a_value_type_and_drops_it_again(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "classify", "domain", "money.ts", "mixed", "ring=entities", "value-type=true").returncode == 0
    assert document(root)["components"][0]["classify"][-1] == ["money.ts", "mixed", {"ring": "entities", "valueType": True}]
    assert edit(root, "classify", "domain", "money.ts", "mixed", "ring=entities", "value-type=false").returncode == 0
    assert document(root)["components"][0]["classify"][-1] == ["money.ts", "mixed", {"ring": "entities"}]
    refused = edit(root, "classify", "domain", "money.ts", "mixed", "value-type=maybe")
    assert refused.returncode == 2 and "value-type" in refused.stderr


def test_classify_without_before_appends_and_unclassify_removes(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "classify", "adapters", "odd.ts", "adapter", "ring=frameworks").returncode == 0
    assert document(root)["components"][1]["classify"][-1] == ["odd.ts", "adapter", {"ring": "frameworks"}]
    assert edit(root, "unclassify", "adapters", "odd.ts").returncode == 0
    assert edit(root, "unclassify", "adapters", "odd.ts").returncode == 2


def test_add_and_remove_port(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "add-port", "src/domain/employee.ts#Employees", "owner=domain", "humble=adapters").returncode == 0
    assert document(root)["ports"][-1] == {"at": "src/domain/employee.ts#Employees", "owner": "domain", "humble": "adapters"}
    assert edit(root, "remove-port", "src/domain/employee.ts#Employees").returncode == 0
    assert edit(root, "remove-port", "src/domain/employee.ts#Employees").returncode == 2
    assert edit(root, "add-port", "src/domain/employee.ts", "owner=domain").returncode == 2


def test_add_group_needs_members_and_absorbs(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "add-group", "core", "members=domain,adapters").returncode == 2
    assert edit(root, "add-group", "core", "absorbs=rule changes").returncode == 2
    assert edit(root, "add-group", "core", "members=domain,ghost", "absorbs=rule changes").returncode == 2
    assert edit(root, "add-group", "core", "members=domain,adapters", "absorbs=rule changes").returncode == 0
    assert document(root)["groups"] == [{"name": "core", "members": ["domain", "adapters"], "absorbs": "rule changes"}]
    assert edit(root, "remove-group", "core").returncode == 0
    assert "groups" not in document(root)
    assert edit(root, "remove-group", "core").returncode == 2


def test_forbidden_edges_and_exceptions(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "add-forbidden-edge", "domain", "ring:frameworks", "reason=policy must not know frameworks").returncode == 0
    assert edit(root, "add-forbidden-edge", "domain", "ring:nowhere", "reason=x").returncode == 2
    assert edit(root, "add-exception", "web", "src/domain/clock.ts", "rule=R5", "reason=migration").returncode == 0
    assert edit(root, "add-exception", "web", "adapters", "reason=temporary").returncode == 0
    doc = document(root)
    assert doc["forbidden"] == [{"from": "domain", "to": "ring:frameworks", "reason": "policy must not know frameworks"}]
    assert doc["exceptions"][0] == {"from": "web", "to": "src/domain/clock.ts", "rule": "R5", "reason": "migration"}
    assert edit(root, "remove-exception", "web", "adapters").returncode == 0
    assert edit(root, "remove-forbidden-edge", "domain", "ring:frameworks").returncode == 0
    assert edit(root, "remove-forbidden-edge", "domain", "ring:frameworks").returncode == 2
    assert [e["to"] for e in document(root)["exceptions"]] == ["src/domain/clock.ts"]


def test_set_adapter(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "set-adapter", "node tools/adapter.mjs").returncode == 0
    assert document(root)["adapter"] == "node tools/adapter.mjs"


def test_validate_reports_every_problem_and_exits_2(tmp_path: Path):
    root = payroll(tmp_path)
    doc = document(root)
    doc["ports"][0]["owner"] = "ghost"
    model_file(root).write_text(json.dumps(doc))
    result = edit(root, "validate")
    assert result.returncode == 2 and "ports[0].owner" in result.stderr


def test_validate_without_a_model_says_how_to_create_one(tmp_path: Path):
    result = edit(tmp_path, "validate")
    assert result.returncode == 2 and "arch model init" in result.stderr


def test_unknown_subcommand_and_unknown_argument(tmp_path: Path):
    root = payroll(tmp_path)
    assert "add-component" in edit(root, "frobnicate").stderr
    assert edit(root, "frobnicate").returncode == 2
    assert edit(root, "add-component", "x", "paths=a/**", "colour=red").returncode == 2
    assert edit(root, "validate", "--start", "legacy").returncode == 2


def test_record_environment_variable_selects_the_record_directory(tmp_path: Path):
    root = payroll(tmp_path)
    (root / "alt").mkdir()
    model_file(root).rename(root / "alt/architecture.json")
    assert edit(root, "validate").returncode == 2
    env = {"ARCH_RECORD_DIR": "alt"}
    assert run_arch(["model", "validate"], root, env).returncode == 0
    assert run_arch(["model", "set-adapter", "cat ./adapter.json"], root, env).returncode == 0
    assert json.loads((root / "alt/architecture.json").read_text())["adapter"] == "cat ./adapter.json"
    assert run_arch(["model", "validate", "--record", "alt"], root).returncode == 0


def test_set_threshold_rejects_non_finite_numbers(tmp_path: Path):
    root = payroll(tmp_path)
    before = model_file(root).read_bytes()
    for value in ["Infinity", "-Infinity", "NaN"]:
        assert edit(root, "set-threshold", "distanceDeviations", value).returncode == 2, value
    assert model_file(root).read_bytes() == before


def test_init_rerun_and_repeat_leave_one_exclude_entry(tmp_path: Path):
    git(["init", "-q", "-b", "main"], tmp_path)
    args = ["init", "--start", "greenfield", "--adapter", "a", "--record-mode", "local"]
    assert edit(tmp_path, *args).returncode == 0
    exclude = tmp_path / ".git/info/exclude"
    first = exclude.read_text()
    assert edit(tmp_path, *args).returncode == 2
    assert exclude.read_text() == first
    model_file(tmp_path).unlink()
    assert edit(tmp_path, *args).returncode == 0
    assert exclude.read_text() == first
    assert first.splitlines().count("/docs/architecture/") == 1


def test_init_local_exclude_entry_is_relative_to_the_repository_through_a_symlink(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(["init", "-q", "-b", "main"], repo)
    link = tmp_path / "link"
    link.symlink_to(repo)
    result = run_arch(["model", "init", "--start", "greenfield", "--adapter", "a", "--record-mode", "local"], link)
    assert result.returncode == 0, result.stderr
    assert "/docs/architecture/" in (repo / ".git/info/exclude").read_text().splitlines()


def test_remove_exception_selects_by_rule(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "add-exception", "web", "adapters", "rule=R5", "reason=a").returncode == 0
    assert edit(root, "add-exception", "web", "adapters", "rule=R7", "reason=b").returncode == 0
    refused = edit(root, "remove-exception", "web", "adapters")
    assert refused.returncode == 2 and "R5" in refused.stderr and "R7" in refused.stderr
    assert edit(root, "remove-exception", "web", "adapters", "rule=R5").returncode == 0
    assert [e["rule"] for e in document(root)["exceptions"]] == ["R7"]
    assert edit(root, "add-exception", "web", "adapters", "reason=any rule").returncode == 0
    assert edit(root, "remove-exception", "web", "adapters").returncode == 0
    assert [e["rule"] for e in document(root)["exceptions"]] == ["R7"]


def test_empty_adapter_refusal_says_to_run_set_adapter(tmp_path: Path):
    root = payroll(tmp_path)
    doc = document(root)
    doc["adapter"] = ""
    model_file(root).write_text(json.dumps(doc))
    for args in (["validate"], ["set-threshold", "escalationFanIn", "4"]):
        result = edit(root, *args)
        assert result.returncode == 2 and 'arch model set-adapter "<command>"' in result.stderr, args
    assert edit(root, "set-adapter", "cat adapter.json").returncode == 0


def test_unset_rule_removes_the_entry(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "set-rule", "R6@domain", "off", "reason=x").returncode == 0
    assert edit(root, "unset-rule", "R6@domain").returncode == 0
    assert list(document(root)["rules"]) == ["R6"]
    assert edit(root, "unset-rule", "R6").returncode == 0
    assert "rules" not in document(root)
    assert edit(root, "unset-rule", "R6").returncode == 2


def fresh_model(tmp_path: Path) -> Path:
    root = copy_fixture("payroll", tmp_path / "p")
    model_file(root).unlink()
    assert edit(root, "init", "--start", "greenfield", "--adapter", "cat adapter.json").returncode == 0
    return root


def test_classifier_sequence_works_on_a_component_just_added(tmp_path: Path):
    root = fresh_model(tmp_path)
    steps = [
        ["add-component", "domain", "paths=src/domain/**"],
        ["classify", "domain", "**/*-repository.ts", "port"],
        ["classify", "domain", "**", "entity"],
        ["add-port", "src/domain/clock.ts#Clock", "owner=domain"],
        ["validate"],
    ]
    for step in steps:
        result = edit(root, *step)
        assert result.returncode == 0, f"{step}: {result.stderr}"
    assert document(root)["components"][0]["classify"] == [["**/*-repository.ts", "port"], ["**", "entity"]]


def test_unclassify_on_a_component_without_pairs_is_a_clear_refusal(tmp_path: Path):
    root = fresh_model(tmp_path)
    assert edit(root, "add-component", "domain", "paths=src/domain/**").returncode == 0
    result = edit(root, "unclassify", "domain", "**")
    assert result.returncode == 2 and "has no pattern" in result.stderr


def test_init_writes_a_model_with_no_component(tmp_path: Path):
    root = fresh_model(tmp_path)
    assert "components" in document(root) and document(root)["components"] == []


def test_validate_on_a_model_without_components_says_to_add_the_first(tmp_path: Path):
    root = fresh_model(tmp_path)
    result = edit(root, "validate")
    assert result.returncode == 2 and "arch model add-component" in result.stderr


def test_add_and_remove_upcoming(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "add-upcoming", "move payroll to a queue").returncode == 0
    assert document(root)["upcoming"] == ["move payroll to a queue"]
    duplicate = edit(root, "add-upcoming", "move payroll to a queue")
    assert duplicate.returncode == 2 and "already" in duplicate.stderr
    assert edit(root, "remove-upcoming", "move payroll to a queue").returncode == 0
    assert "upcoming" not in document(root)
    assert edit(root, "remove-upcoming", "move payroll to a queue").returncode == 2


def test_exception_to_star_is_accepted_for_a_unit_or_component_source(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "add-exception", "web", "*", "reason=accepted").returncode == 0
    assert {"from": "web", "to": "*", "reason": "accepted"} in document(root)["exceptions"]


def test_exception_cannot_start_at_star(tmp_path: Path):
    result = edit(payroll(tmp_path), "add-exception", "*", "web", "reason=x")
    assert result.returncode == 2 and '"*"' in result.stderr


def test_validate_keeps_a_star_exception_whose_source_exists(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "add-exception", "web", "*", "reason=accepted").returncode == 0
    assert edit(root, "validate").returncode == 0


def test_validate_fails_on_a_star_exception_whose_source_matches_nothing(tmp_path: Path):
    root = payroll(tmp_path)
    assert edit(root, "add-exception", "src/gone.ts", "*", "reason=x").returncode == 0
    result = edit(root, "validate")
    assert result.returncode == 2 and "src/gone.ts" in result.stderr


def test_validate_prints_ok_only_when_the_graph_checks_pass(tmp_path: Path):
    ok = edit(payroll(tmp_path / "ok"), "validate")
    assert ok.returncode == 0 and ok.stdout.strip() == "model: ok"


def test_validate_with_a_model_that_does_not_fit_the_code_does_not_print_ok(tmp_path: Path):
    root = payroll(tmp_path)
    doc = document(root)
    doc["components"][1]["classify"].insert(0, ["nothing-*.ts", "gateway"])
    model_file(root).write_text(json.dumps(doc))
    result = edit(root, "validate")
    assert result.returncode == 2
    assert "model: ok" not in result.stdout
    assert "model does not fit the code:" in result.stderr
    assert "nothing-*.ts" in result.stderr


def test_validate_with_a_failing_adapter_prints_model_file_ok_then_the_tooling_error(tmp_path: Path):
    root = payroll(tmp_path)
    doc = document(root)
    doc["adapter"] = "exit 3"
    model_file(root).write_text(json.dumps(doc))
    result = edit(root, "validate")
    assert result.returncode == 2
    assert result.stdout.strip() == "model file: ok"
    assert "adapter command" in result.stderr


def test_status_reports_a_present_model_without_running_the_adapter(tmp_path: Path):
    root = payroll(tmp_path)
    doc = document(root)
    doc["adapter"] = "exit 3"
    model_file(root).write_text(json.dumps(doc))
    result = edit(root, "status")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"model: present at {model_file(root)}"
    as_json = json.loads(edit(root, "status", "--json").stdout)
    assert as_json == {"model": True, "path": str(model_file(root))}


def test_status_reports_an_absent_model_with_exit_zero(tmp_path: Path):
    result = edit(tmp_path, "status")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "model: absent; run a baseline audit"
    as_json = json.loads(edit(tmp_path, "status", "--json").stdout)
    assert as_json == {"model": False, "path": str(model_file(tmp_path))}

