import json

import pytest
from datetime import datetime, timezone
from pathlib import Path

from support import SKILL_DIR, copy_fixture, git, init_repo, run_arch, run_node

MODEL = "docs/architecture/architecture.json"
ADAPTER = "adapter.json"
STORE = ".architecture/findings.json"
EMPLOYEE = "src/domain/employee.ts"
CLOCK = "src/adapters/system-clock.ts"
MAIN = "src/web/main.ts"
CONTROLLER = "src/web/payroll-controller.ts"
EMPLOYEE_TO_CLOCK = f"{EMPLOYEE} -> {CLOCK}"
NO_MODEL_LINE = "no architecture model; run a baseline audit to enable the full review"


def edit_json(path: Path, change) -> None:
    document = json.loads(path.read_text())
    change(document)
    path.write_text(json.dumps(document))


def workspace(tmp_path: Path) -> Path:
    root = copy_fixture("payroll", tmp_path / "p")
    edit_json(root / MODEL, lambda d: d["rules"].update({"R38": ["off", "payroll records no enforcement"]}))
    edit_json(root / ADAPTER, lambda d: d["capabilities"].update(typeChecks=True))
    (root / ".gitignore").write_text(".architecture/\n")
    init_repo(root)
    return root


def seed_policy_to_detail_edge(root: Path) -> None:
    edit_json(root / ADAPTER, lambda d: d["edges"].append({"from": EMPLOYEE, "to": CLOCK, "kind": "import"}))


def touch(root: Path, *paths: str) -> None:
    for path in paths:
        (root / path).write_text((root / path).read_text() + "\n// changed\n")


def write_json(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document))
    return path


def check_file(root: Path, tmp_path: Path, *args: str) -> Path:
    result = run_arch(["check", *args, "--json"], root)
    assert result.returncode in (0, 1), result.stderr
    path = tmp_path / "check.json"
    path.write_text(result.stdout)
    return path


def judged(tmp_path: Path, *findings: dict, questions: list[str] | None = None) -> Path:
    return write_json(tmp_path / "judged.json", {"findings": list(findings), "questions": questions or []})


def finding(judgment: str = "unit-serves-several-actors", target: str = EMPLOYEE, **overrides) -> dict:
    base = {
        "judgment": judgment,
        "target": target,
        "consequence": "Payroll and reporting changes now edit the same unit.",
        "correction": "Split the reporting behavior into its own unit.",
        "evidence": [f"{EMPLOYEE}:1"],
        "wider": False,
    }
    return {**base, **overrides}


def with_origin(findings: tuple[dict, ...], origin: str | None) -> tuple[dict, ...]:
    stated = [{"origin": origin, **f} for f in findings]
    return tuple({k: v for k, v in f.items() if v is not None} for f in stated)


def add(root: Path, flow: str, check: Path, *args: str):
    return run_arch(["findings", "add", "--flow", flow, "--check", str(check), *args], root)


def change_review(root: Path, tmp_path: Path, *findings: dict, base: str = "main", extra: tuple[str, ...] = ()):
    check = check_file(root, tmp_path, "--base", base)
    stated = with_origin(findings, "introduced")
    args = ["--judged", str(judged(tmp_path, *stated)), "--base", base, *extra] if findings else ["--base", base]
    return add(root, "change-review", check, *args)


def audit(root: Path, tmp_path: Path, *findings: dict):
    check = check_file(root, tmp_path)
    args = ["--judged", str(judged(tmp_path, *findings))] if findings else []
    return add(root, "audit", check, *args)


def store(root: Path) -> dict:
    return json.loads((root / STORE).read_text())


def stored(root: Path, target: str) -> dict:
    matches = [f for f in store(root)["findings"] if f["target"] == target]
    assert len(matches) == 1, store(root)
    return matches[0]


def assert_refused(result, root: Path, *fragments: str) -> None:
    assert result.returncode == 2, result.stdout + result.stderr
    for fragment in fragments:
        assert fragment in result.stderr, result.stderr
    assert not (root / STORE).exists()


def test_finding_without_evidence_is_refused(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    result = change_review(root, tmp_path, finding(evidence=[]))
    assert_refused(result, root, EMPLOYEE, "no evidence")


def test_finding_without_consequence_or_correction_is_refused(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    result = change_review(root, tmp_path, finding(consequence="", correction=""))
    assert_refused(result, root, "no consequence", "no correction")


def test_evidence_line_beyond_the_file_is_refused(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    result = change_review(root, tmp_path, finding(evidence=[f"{EMPLOYEE}:999"]))
    assert_refused(result, root, f"{EMPLOYEE}:999", "line 999")


def test_evidence_in_a_missing_file_is_refused(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    result = change_review(root, tmp_path, finding(evidence=["src/domain/ghost.ts:1"]))
    assert_refused(result, root, "src/domain/ghost.ts", "does not exist")


def write_plan(root: Path) -> str:
    plan = "docs/plans/payroll.md"
    (root / plan).parent.mkdir(parents=True)
    (root / plan).write_text("# Payroll plan\n\n## Rule storage\n\nThe new rule lives in the domain.\n")
    return plan


def plan_review(root: Path, tmp_path: Path, plan: str, *findings: dict):
    proposal = write_json(
        tmp_path / "proposal.json",
        {"version": 1, "modules": [{"path": "src/domain/overtime-rule.ts"}],
         "edges": [{"from": "src/domain/overtime-rule.ts", "to": "src/domain/employee.ts", "kind": "import"}]},
    )
    check = check_file(root, tmp_path, "--proposal", str(proposal))
    return add(root, "plan-review", check, "--judged", str(judged(tmp_path, *with_origin(findings, "introduced"))),
               "--plan", plan,
               "--proposal", str(proposal))


def test_plan_review_evidence_must_be_an_existing_plan_heading(tmp_path):
    root = workspace(tmp_path)
    plan = write_plan(root)
    target = "src/domain/overtime-rule.ts"
    refused = plan_review(root, tmp_path, plan, finding(target=target, evidence=[f"{plan}#Missing section"]))
    assert_refused(refused, root, "Missing section", plan)
    code_line = plan_review(root, tmp_path, plan, finding(target=target, evidence=[f"{EMPLOYEE}:1"]))
    assert_refused(code_line, root, "plan section", f"{plan}#<heading>")
    accepted = plan_review(root, tmp_path, plan, finding(target=target, evidence=[f"{plan}#Rule storage"]))
    assert accepted.returncode == 0, accepted.stderr
    assert stored(root, target)["scope"] == f"plan:{plan}"


def test_finding_for_a_rule_that_is_off_is_dropped_and_listed(tmp_path):
    root = workspace(tmp_path)
    touch(root, "src/domain/payroll-use-case.ts")
    result = change_review(root, tmp_path, finding("use-case-names-its-details", "src/domain/payroll-use-case.ts"))
    assert result.returncode == 0, result.stderr
    assert "Dropped: 1 (1 rule off)" in result.stdout
    assert store(root)["lastRun"]["dropped"] == [
        {"target": "src/domain/payroll-use-case.ts", "judgment": "use-case-names-its-details", "reason": "rule off"}
    ]
    assert store(root)["findings"] == []


def test_out_of_scope_finding_needs_the_wider_mark(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    refused = change_review(root, tmp_path, finding(target=CONTROLLER))
    assert_refused(refused, root, CONTROLLER, "wider")
    accepted = change_review(root, tmp_path, finding(target=CONTROLLER, wider=True))
    assert accepted.returncode == 0, accepted.stderr
    assert "Wider observations: 1" in accepted.stdout
    assert "Verdict: OK" in accepted.stdout


def test_lift_needs_a_confirmed_upcoming_change(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    lifted = finding(liftedBy="a second payroll country")
    refused = change_review(root, tmp_path, lifted)
    assert_refused(refused, root, "a second payroll country", "--upcoming")
    accepted = change_review(root, tmp_path, lifted, extra=("--upcoming", "a second payroll country"))
    assert accepted.returncode == 0, accepted.stderr
    record = stored(root, EMPLOYEE)
    assert record["severity"] == "blocker" and 2 in record["lifts"]
    assert store(root)["lastRun"]["upcoming"] == ["a second payroll country"]


def test_lift_may_name_an_upcoming_change_recorded_in_the_model(tmp_path):
    root = workspace(tmp_path)
    edit_json(root / MODEL, lambda d: d.update(upcoming=["a second payroll country"]))
    touch(root, EMPLOYEE)
    result = change_review(root, tmp_path, finding(liftedBy="a second payroll country"))
    assert result.returncode == 0, result.stderr


def test_lift_accepts_an_upcoming_change_added_with_the_model_command(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    added = run_arch(["model", "add-upcoming", "a second payroll country"], root)
    assert added.returncode == 0, added.stderr
    result = change_review(root, tmp_path, finding(liftedBy="a second payroll country"))
    assert result.returncode == 0, result.stderr
    assert 2 in stored(root, EMPLOYEE)["lifts"]


def test_severity_must_match_the_judgment_entry(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    result = change_review(root, tmp_path, finding(severity="minor", rules=["R10"], defect="x"))
    assert_refused(result, root, "severity", "rules", "defect", "judgment entry")


def test_unknown_judgment_and_unrecognized_target_are_refused(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    unknown = change_review(root, tmp_path, finding(judgment="made-up"))
    assert_refused(unknown, root, "made-up", "judgment")
    target = change_review(root, tmp_path, finding(target="src/domain/ghost.ts"))
    assert_refused(target, root, "src/domain/ghost.ts", "target")


def test_judged_severity_comes_from_the_judgment_entry(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    result = change_review(root, tmp_path, finding())
    assert result.returncode == 0, result.stderr
    record = stored(root, EMPLOYEE)
    assert (record["severity"], record["provenance"], record["origin"]) == ("major", "judged", "introduced")
    assert record["rules"] == ["R10"] and record["defect"] == "several-actors-in-one-unit"


def test_judged_and_checked_findings_of_one_defect_merge(tmp_path):
    root = workspace(tmp_path)
    seed_policy_to_detail_edge(root)
    touch(root, EMPLOYEE)
    judged_finding = finding("query-inside-policy", EMPLOYEE_TO_CLOCK, evidence=[f"{EMPLOYEE}:1"])
    result = change_review(root, tmp_path, judged_finding)
    assert result.returncode == 0, result.stderr
    record = stored(root, EMPLOYEE_TO_CLOCK)
    assert record["provenance"] == "both" and record["severity"] == "blocker"
    assert {"R4", "R22"} <= set(record["rules"])
    assert record["consequence"] == judged_finding["consequence"]
    assert f"{EMPLOYEE}:1" in record["evidence"] and len(record["evidence"]) == 2
    matching = [f for f in store(root)["findings"] if f["target"] == EMPLOYEE_TO_CLOCK]
    assert len(matching) == 1


def test_fixed_finding_is_deleted_on_the_next_change_review(tmp_path):
    root = workspace(tmp_path)
    seed_policy_to_detail_edge(root)
    touch(root, EMPLOYEE)
    first = change_review(root, tmp_path)
    assert first.returncode == 0, first.stderr
    assert any(f["target"] == EMPLOYEE_TO_CLOCK for f in store(root)["findings"])
    edit_json(root / ADAPTER, lambda d: d["edges"].pop())
    second = change_review(root, tmp_path)
    assert second.returncode == 0, second.stderr
    assert store(root)["findings"] == []


def test_change_review_keeps_findings_outside_the_touched_scope(tmp_path):
    root = workspace(tmp_path)
    seed_policy_to_detail_edge(root)
    touch(root, EMPLOYEE)
    assert change_review(root, tmp_path).returncode == 0
    git(["add", "-A"], root)
    git(["commit", "-q", "-m", "second"], root)
    touch(root, MAIN)
    result = change_review(root, tmp_path, base="HEAD")
    assert result.returncode == 0, result.stderr
    targets = {f["target"] for f in store(root)["findings"]}
    assert EMPLOYEE_TO_CLOCK in targets
    assert store(root)["lastRun"]["findingKeys"] == []
    assert "Verdict: OK: 0 blocker, 0 major, 0 minor blocking" in result.stdout


def test_audit_replaces_every_stored_code_finding(tmp_path):
    root = workspace(tmp_path)
    seed_policy_to_detail_edge(root)
    touch(root, EMPLOYEE)
    assert change_review(root, tmp_path).returncode == 0
    edit_json(root / ADAPTER, lambda d: d["edges"].pop())
    assert audit(root, tmp_path).returncode == 0
    assert all(f["target"] != EMPLOYEE_TO_CLOCK for f in store(root)["findings"])


def test_verdict_should_change_on_introduced_enforced_major(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    result = change_review(root, tmp_path, finding())
    assert result.returncode == 0, result.stderr
    assert "Verdict: SHOULD_CHANGE: 0 blocker, 1 major, 0 minor blocking" in result.stdout
    assert "R10 One actor per module" in result.stdout
    assert f"{EMPLOYEE}: Payroll and reporting changes now edit the same unit. Fix: Split" in result.stdout


def test_verdict_ok_when_only_inherited(tmp_path):
    root = workspace(tmp_path)
    seed_policy_to_detail_edge(root)
    git(["add", "-A"], root)
    git(["commit", "-q", "-m", "seeded"], root)
    touch(root, EMPLOYEE)
    result = change_review(root, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Verdict: OK: 0 blocker, 0 major, 0 minor blocking" in result.stdout
    assert "Inherited: 3 blocker, 1 major, 0 minor (not blocking)" in result.stdout


def test_inherited_finding_with_a_confirmed_lift_blocks(tmp_path):
    root = workspace(tmp_path)
    seed_policy_to_detail_edge(root)
    git(["add", "-A"], root)
    git(["commit", "-q", "-m", "seeded"], root)
    touch(root, EMPLOYEE)
    lifted = finding("query-inside-policy", EMPLOYEE_TO_CLOCK, liftedBy="a second payroll country")
    result = change_review(root, tmp_path, lifted, extra=("--upcoming", "a second payroll country"))
    assert result.returncode == 0, result.stderr
    assert stored(root, EMPLOYEE_TO_CLOCK)["origin"] == "inherited"
    assert "Verdict: SHOULD_CHANGE: 1 blocker, 0 major, 0 minor blocking" in result.stdout


def test_verdict_incomplete_needs_a_model(tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    check = check_file(bare, tmp_path)
    result = add(bare, "change-review", check, "--base", "main")
    assert result.returncode == 0, result.stderr
    assert "Verdict: OK" in result.stdout and NO_MODEL_LINE in result.stdout
    assert not (bare / STORE).exists()

    root = workspace(tmp_path / "with-model")
    proposal = write_json(
        tmp_path / "proposal.json",
        {"version": 1, "modules": [], "edges": [], "unknown": [{"task": "Task 3", "fact": "which table stores rules"}]},
    )
    plan = write_plan(root)
    proposal_check = check_file(root, tmp_path, "--proposal", str(proposal))
    incomplete = add(root, "plan-review", proposal_check, "--plan", plan, "--proposal", str(proposal))
    assert incomplete.returncode == 0, incomplete.stderr
    assert "Verdict: INCOMPLETE" in incomplete.stdout
    assert "Incomplete: 1 conditions (1 clarification requests)" in incomplete.stdout


def test_incomplete_entry_for_a_rule_that_is_off_does_not_block(tmp_path):
    root = workspace(tmp_path)
    edit_json(root / ADAPTER, lambda d: d["capabilities"].update(typeChecks=False))
    edit_json(root / MODEL, lambda d: d["rules"].update({"R13": ["off", "no interface substitution here"]}))
    touch(root, EMPLOYEE)
    result = change_review(root, tmp_path)
    assert "Verdict: OK" in result.stdout


def test_advisory_finding_never_blocks(tmp_path):
    root = workspace(tmp_path)
    set_rule = run_arch(["model", "set-rule", "R7", "advisory", "reason=constructed in tests only"], root)
    assert set_rule.returncode == 0, set_rule.stderr
    result = audit(root, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Verdict: OK" in result.stdout and "Advisory: 2 findings" in result.stdout


def test_audit_counts_every_enforced_finding(tmp_path):
    root = workspace(tmp_path)
    result = audit(root, tmp_path, finding())
    assert result.returncode == 0, result.stderr
    assert "Verdict: SHOULD_CHANGE: 2 blocker, 1 major, 0 minor blocking" in result.stdout
    assert all(f["origin"] == "none" for f in store(root)["findings"])


def test_list_prints_the_stored_contract_with_titled_rules(tmp_path):
    root = workspace(tmp_path)
    assert audit(root, tmp_path).returncode == 0
    listed = run_arch(["findings", "list"], root)
    assert listed.returncode == 0, listed.stderr
    assert listed.stdout.startswith("# Architecture audit: ")
    assert "R7 Lower-level components are plugins" in listed.stdout
    assert "Rules not enforced: R6 Use cases own their boundaries (off: one delivery mechanism" in listed.stdout
    as_json = json.loads(run_arch(["findings", "list", "--json"], root).stdout)
    assert as_json["verdict"] == "SHOULD_CHANGE" and as_json["blocking"]["blocker"] == 2


def test_corrections_group_identical_text_and_order_by_severity(tmp_path):
    root = workspace(tmp_path)
    assert audit(root, tmp_path, finding()).returncode == 0
    corrections = json.loads(run_arch(["findings", "list", "--json"], root).stdout)["corrections"]
    assert [c["severity"] for c in corrections] == ["blocker", "major"]
    assert corrections[0]["findings"] == 2 and len(corrections[0]["targets"]) == 2


def test_findings_store_holds_no_dates_or_run_numbers(tmp_path):
    root = workspace(tmp_path)
    assert audit(root, tmp_path).returncode == 0
    last_run = store(root)["lastRun"]
    assert set(last_run) == {
        "flow", "scope", "base", "plan", "incomplete", "skipped", "notRun", "upcoming", "questions", "findingKeys",
        "covered", "dropped",
    }
    assert store(root)["version"] == 1


def test_findings_store_directory_is_ignored(tmp_path):
    root = copy_fixture("payroll", tmp_path / "p")
    edit_json(root / ADAPTER, lambda d: d["capabilities"].update(typeChecks=True))
    init_repo(root)
    assert audit(root, tmp_path).returncode == 0
    ignored = git(["check-ignore", "-q", STORE], root)
    assert ignored.returncode == 0


def commit_at(root: Path, path: str, when: str) -> None:
    (root / path).write_text((root / path).read_text() + "\n// edit\n")
    stamp = {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    git(["add", "-A"], root, stamp)
    git(["commit", "-q", "-m", f"edit {path}"], root, stamp)


def test_rank_orders_by_component_volatility(tmp_path):
    root = workspace(tmp_path)
    recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")
    git(["commit", "-q", "--amend", "--no-edit", "--date=2000-01-01T00:00:00"], root,
        {"GIT_COMMITTER_DATE": "2000-01-01T00:00:00"})
    commit_at(root, CLOCK, recent)
    commit_at(root, CONTROLLER, recent)
    commit_at(root, CONTROLLER, recent)
    commit_at(root, "src/web/legacy-router.js", recent)
    findings = [finding(target=EMPLOYEE), finding(target=CLOCK, evidence=[f"{CLOCK}:1"])]
    assert audit(root, tmp_path, *findings).returncode == 0
    ranked = run_arch(["findings", "list", "--rank"], root)
    assert ranked.returncode == 0, ranked.stderr
    web, adapters = ranked.stdout.index("web (3 commits)"), ranked.stdout.index("adapters (1 commit)")
    assert web < adapters
    assert "domain: R10 One actor per module x1" in ranked.stdout
    assert ranked.stdout.index("no commits in 6 months") < ranked.stdout.index("domain: R10")


def test_rank_is_only_for_an_audit(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    assert change_review(root, tmp_path).returncode == 0
    result = run_arch(["findings", "list", "--rank"], root)
    assert result.returncode == 2 and "audit" in result.stderr


def test_add_without_a_subcommand_or_flow_is_a_usage_error(tmp_path):
    root = workspace(tmp_path)
    assert run_arch(["findings"], root).returncode == 2
    missing_flow = run_arch(["findings", "add", "--check", "x.json"], root)
    assert missing_flow.returncode == 2 and "--flow" in missing_flow.stderr
    bad_flow = run_arch(["findings", "add", "--flow", "review", "--check", "x.json"], root)
    assert bad_flow.returncode == 2 and "audit, change-review, plan-review" in bad_flow.stderr


def test_inherited_judged_finding_in_scope_does_not_block(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    result = change_review(root, tmp_path, finding(origin="inherited"))
    assert result.returncode == 0, result.stderr
    assert stored(root, EMPLOYEE)["origin"] == "inherited"
    assert "Verdict: OK" in result.stdout and "Inherited: 0 blocker, 1 major, 0 minor" in result.stdout


def test_inherited_judged_finding_with_a_confirmed_lift_blocks(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    lifted = finding(origin="inherited", liftedBy="a second payroll country")
    result = change_review(root, tmp_path, lifted, extra=("--upcoming", "a second payroll country"))
    assert result.returncode == 0, result.stderr
    assert "Verdict: SHOULD_CHANGE: 1 blocker, 0 major, 0 minor blocking" in result.stdout


def test_wider_on_an_in_scope_target_is_reported_apart_and_never_blocks(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    blocking = change_review(root, tmp_path, finding())
    assert "Verdict: SHOULD_CHANGE" in blocking.stdout, blocking.stdout + blocking.stderr
    result = change_review(root, tmp_path, finding(wider=True))
    assert result.returncode == 0, result.stderr
    assert "Wider observations: 1" in result.stdout
    assert "Verdict: OK" in result.stdout
    assert stored(root, EMPLOYEE)["wider"] is True


def test_plan_judgment_takes_the_literal_plan_target_in_plan_review(tmp_path):
    root = workspace(tmp_path)
    plan = write_plan(root)
    plan_finding = finding("structure-consequence-unstated", "plan", evidence=[f"{plan}#Rule storage"])
    accepted = plan_review(root, tmp_path, plan, plan_finding)
    assert accepted.returncode == 0, accepted.stderr
    assert stored(root, "plan")["defect"] == "structure-consequence-unstated"
    unit_judgment = finding("unit-serves-several-actors", "plan", evidence=[f"{plan}#Rule storage"])
    refused = plan_review(root, tmp_path, plan, unit_judgment)
    assert refused.returncode == 2 and "does not apply to" in refused.stderr, refused.stderr


def test_plan_target_outside_plan_review_is_refused(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    result = change_review(root, tmp_path, finding("structure-consequence-unstated", "plan"))
    assert_refused(result, root, '"plan"', "plan-review")


def test_missing_origin_in_change_review_is_refused(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    result = change_review(root, tmp_path, finding(origin=None))
    assert_refused(result, root, "no origin", "introduced", "inherited")


def test_origin_in_an_audit_is_refused(tmp_path):
    root = workspace(tmp_path)
    check = check_file(root, tmp_path)
    judged_file = judged(tmp_path, finding(origin="introduced"))
    result = add(root, "audit", check, "--judged", str(judged_file))
    assert_refused(result, root, "origin", "audit")


def test_merged_finding_with_a_wider_judged_part_is_not_wider_and_keeps_the_check_origin(tmp_path):
    merge = (SKILL_DIR / "scripts" / "lib" / "findings" / "merge.mjs").as_uri()
    common = {"target": "t", "defect": "d", "rules": ["R4"], "severity": "major", "baseSeverity": "major",
              "lifts": [], "status": "enforced", "correction": "c", "evidence": ["e"], "component": None}
    checked = {**common, "provenance": "check", "origin": "inherited", "consequence": "", "wider": False}
    judged_part = {**common, "provenance": "judged", "origin": "introduced", "consequence": "x", "wider": True}
    script = (f"import {{ mergeFindings }} from {json.dumps(merge)};"
              f"console.log(JSON.stringify(mergeFindings({json.dumps([checked, judged_part])})));")
    result = run_node(script, tmp_path)
    assert result.returncode == 0, result.stderr
    [merged] = json.loads(result.stdout)
    assert merged["wider"] is False and merged["origin"] == "inherited" and merged["provenance"] == "both"


def test_check_without_the_same_base_is_refused(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    audit_check = check_file(root, tmp_path)
    no_base = add(root, "change-review", audit_check, "--base", "main")
    assert_refused(no_base, root, "not made with --base", "arch check --base")
    check = check_file(root, tmp_path, "--base", "main")
    git(["add", "-A"], root)
    git(["commit", "-q", "-m", "second"], root)
    other = add(root, "change-review", check, "--base", "HEAD")
    assert_refused(other, root, "compared against", "same --base")


def test_check_without_the_same_proposal_is_refused(tmp_path):
    root = workspace(tmp_path)
    plan = write_plan(root)
    first = write_json(tmp_path / "first.json", {"version": 1})
    second = write_json(tmp_path / "second.json", {"version": 1})
    check = check_file(root, tmp_path, "--proposal", str(first))
    other = add(root, "plan-review", check, "--plan", plan, "--proposal", str(second))
    assert_refused(other, root, "ran on proposal", "same --proposal")
    plain = check_file(root, tmp_path)
    missing = add(root, "plan-review", plain, "--plan", plan, "--proposal", str(first))
    assert_refused(missing, root, "not made with --proposal")


def test_audit_with_a_base_check_is_refused(tmp_path):
    root = workspace(tmp_path)
    check = check_file(root, tmp_path, "--base", "main")
    result = add(root, "audit", check)
    assert_refused(result, root, "whole codebase", "without --base")


def test_stale_check_is_refused(tmp_path):
    root = workspace(tmp_path)
    check = check_file(root, tmp_path)
    touch(root, EMPLOYEE)
    result = add(root, "audit", check)
    assert_refused(result, root, "stale", "Rerun arch check")


def test_judgment_applies_only_to_its_target_kinds(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    component = change_review(root, tmp_path, finding("unit-serves-several-actors", "domain"))
    assert_refused(component, root, "does not apply to", "It applies to:")
    unit_for_component = change_review(root, tmp_path, finding("zone-of-pain-changing", EMPLOYEE))
    assert unit_for_component.returncode == 2 and "does not apply to" in unit_for_component.stderr
    plan_judgment = change_review(root, tmp_path, finding("structure-consequence-unstated", EMPLOYEE))
    assert_refused(plan_judgment, root, "plan (plan-review only)")
    test_suite = change_review(root, tmp_path, finding("tests-change-without-behavior-change", EMPLOYEE))
    assert_refused(test_suite, root, "test-suite")


def test_judgment_for_a_component_accepts_a_component_name(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    result = change_review(root, tmp_path, finding("zone-of-pain-changing", "domain"))
    assert result.returncode == 0, result.stderr


def test_invalid_store_is_refused_with_the_way_out(tmp_path):
    root = workspace(tmp_path)
    assert audit(root, tmp_path).returncode == 0
    (root / STORE).write_text(json.dumps({"version": 1, "findings": [{"target": "x"}], "lastRun": None}))
    result = run_arch(["findings", "list"], root)
    assert result.returncode == 2
    assert "Delete .architecture/findings.json and rerun the flow" in result.stderr


def test_rank_without_a_model_says_to_init(tmp_path):
    root = workspace(tmp_path)
    assert audit(root, tmp_path).returncode == 0
    (root / MODEL).unlink()
    result = run_arch(["findings", "list", "--rank"], root)
    assert result.returncode == 2 and "arch model init" in result.stderr


def test_run_findings_are_matched_by_scope_too(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    assert change_review(root, tmp_path, finding()).returncode == 0
    data = store(root)
    data["findings"].append({**data["findings"][0], "scope": "plan:docs/plans/other.md"})
    (root / STORE).write_text(json.dumps(data))
    listed = json.loads(run_arch(["findings", "list", "--json"], root).stdout)
    assert len(listed["findings"]) == 1 and listed["findings"][0]["scope"] == "code"


WORK = ".architecture/work"


def work_check(root: Path, *args: str):
    result = run_arch(["check", *args, "--out", f"{WORK}/check.json"], root)
    assert result.returncode in (0, 1), result.stderr
    assert result.stdout.startswith(f"wrote {WORK}/check.json: "), result.stdout
    return result


def write_work(root: Path, name: str, document: dict) -> str:
    path = root / WORK / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document))
    return f"{WORK}/{name}"


def test_change_review_round_trip_inside_the_repository(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    work_check(root, "--base", "main")
    judged_path = write_work(root, "judged.json", {"findings": [{**finding(), "origin": "introduced"}]})
    added = run_arch(["findings", "add", "--flow", "change-review", "--check", f"{WORK}/check.json",
                      "--judged", judged_path, "--base", "main"], root)
    assert added.returncode == 0, added.stderr
    listed = run_arch(["findings", "list"], root)
    assert listed.returncode == 0 and "Verdict: SHOULD_CHANGE" in listed.stdout
    assert git(["status", "--porcelain", "--", ".architecture"], root).stdout == ""


def test_plan_review_round_trip_inside_the_repository(tmp_path):
    root = workspace(tmp_path)
    plan = write_plan(root)
    proposal = write_work(root, "proposal.json", {"version": 1, "modules": [{"path": "src/domain/overtime-rule.ts"}]})
    work_check(root, "--proposal", proposal)
    entry = {**finding(target="src/domain/overtime-rule.ts", evidence=[f"{plan}#Rule storage"]), "origin": "introduced"}
    judged_path = write_work(root, "judged.json", {"findings": [entry]})
    added = run_arch(["findings", "add", "--flow", "plan-review", "--check", f"{WORK}/check.json",
                      "--judged", judged_path, "--plan", plan, "--proposal", proposal], root)
    assert added.returncode == 0, added.stderr
    assert stored(root, "src/domain/overtime-rule.ts")["scope"] == f"plan:{plan}"


def test_files_inside_the_project_outside_the_work_directory_are_refused(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    work_check(root, "--base", "main")
    (root / "judged.json").write_text(json.dumps({"findings": []}))
    result = run_arch(["findings", "add", "--flow", "change-review", "--check", f"{WORK}/check.json",
                       "--judged", "judged.json", "--base", "main"], root)
    assert_refused(result, root, "--judged judged.json", ".architecture/work/", "reviewed state")
    (root / "proposal.json").write_text(json.dumps({"version": 1}))
    proposal = run_arch(["check", "--proposal", "proposal.json"], root)
    assert proposal.returncode == 2 and ".architecture/work/" in proposal.stderr
    out = run_arch(["check", "--out", "check.json"], root)
    assert out.returncode == 2 and ".architecture/work/" in out.stderr


def test_source_edit_between_check_and_add_is_still_stale_with_work_files(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    work_check(root, "--base", "main")
    touch(root, EMPLOYEE)
    result = run_arch(["findings", "add", "--flow", "change-review", "--check", f"{WORK}/check.json",
                       "--base", "main"], root)
    assert_refused(result, root, "stale")


def test_audit_reads_several_judged_files_in_order(tmp_path):
    root = workspace(tmp_path)
    check = check_file(root, tmp_path)
    first = write_json(tmp_path / "first.json", {"findings": [finding()], "questions": ["Who owns payroll?"]})
    second = write_json(
        tmp_path / "second.json",
        {
            "findings": [finding("handler-holds-business-logic", CONTROLLER, evidence=[f"{CONTROLLER}:1"])],
            "questions": ["Is the web layer replaced soon?"],
        },
    )
    result = add(root, "audit", check, "--judged", str(first), "--judged", str(second), "--json")
    assert result.returncode == 0, result.stderr
    assert stored(root, EMPLOYEE)["provenance"] == "judged"
    assert stored(root, CONTROLLER)["provenance"] == "judged"
    assert store(root)["lastRun"]["questions"] == ["Who owns payroll?", "Is the web layer replaced soon?"]


def test_refusal_names_the_judged_file_and_the_finding(tmp_path):
    root = workspace(tmp_path)
    check = check_file(root, tmp_path)
    first = write_json(tmp_path / "first.json", {"findings": [finding()]})
    second = write_json(tmp_path / "second.json", {"findings": [finding(target=CONTROLLER, evidence=[])]})
    result = add(root, "audit", check, "--judged", str(first), "--judged", str(second))
    assert_refused(result, root, str(second), f"findings[0] ({CONTROLLER})", "has no evidence")
    assert str(first) not in result.stderr


def test_missing_check_file_says_to_create_it_with_arch_check_out(tmp_path):
    root = workspace(tmp_path)
    missing = root / ".architecture/work/check.json"
    result = add(root, "audit", missing)
    assert result.returncode == 2
    assert "arch check" in result.stderr and "--out .architecture/work/check.json" in result.stderr
    assert "> <file>" not in result.stderr


def blocked_change_review(root: Path, tmp_path: Path):
    touch(root, EMPLOYEE)
    first = change_review(root, tmp_path, finding())
    assert "Verdict: SHOULD_CHANGE" in first.stdout, first.stdout + first.stderr
    return first


def test_exception_for_a_unit_with_star_target_drops_the_judged_finding(tmp_path):
    root = workspace(tmp_path)
    blocked_change_review(root, tmp_path)
    accepted = run_arch(["model", "add-exception", EMPLOYEE, "*", "reason=accepted by the user"], root)
    assert accepted.returncode == 0, accepted.stderr
    rerun = change_review(root, tmp_path, finding())
    assert rerun.returncode == 0, rerun.stderr
    assert "Verdict: OK" in rerun.stdout
    assert "Dropped: 1 (1 covered by an exception)" in rerun.stdout
    dropped = store(root)["lastRun"]["dropped"]
    assert dropped == [{"target": EMPLOYEE, "judgment": "unit-serves-several-actors", "reason": "covered by an exception"}]
    listed = run_arch(["findings", "list"], root)
    assert "Dropped: 1 (1 covered by an exception)" in listed.stdout


def test_exception_naming_the_component_and_rule_covers_a_judged_finding(tmp_path):
    root = workspace(tmp_path)
    blocked_change_review(root, tmp_path)
    other = run_arch(["model", "add-exception", "domain", "*", "rule=R11", "reason=other rule"], root)
    assert other.returncode == 0, other.stderr
    assert "Verdict: SHOULD_CHANGE" in change_review(root, tmp_path, finding()).stdout
    right = run_arch(["model", "add-exception", "domain", "*", "rule=R10", "reason=accepted"], root)
    assert right.returncode == 0, right.stderr
    assert "Verdict: OK" in change_review(root, tmp_path, finding()).stdout


def test_exception_with_a_real_destination_does_not_cover_a_unit_finding(tmp_path):
    root = workspace(tmp_path)
    blocked_change_review(root, tmp_path)
    assert run_arch(["model", "add-exception", EMPLOYEE, CLOCK, "reason=an edge only"], root).returncode == 0
    assert "Verdict: SHOULD_CHANGE" in change_review(root, tmp_path, finding()).stdout


def test_rule_set_off_drops_the_judged_finding_on_rerun(tmp_path):
    root = workspace(tmp_path)
    blocked_change_review(root, tmp_path)
    assert run_arch(["model", "set-rule", "R10", "off", "reason=accepted"], root).returncode == 0
    rerun = change_review(root, tmp_path, finding())
    assert rerun.returncode == 0, rerun.stderr
    assert "Verdict: OK" in rerun.stdout and "Dropped: 1 (1 rule off)" in rerun.stdout


def test_rule_set_advisory_reports_the_judged_finding_without_blocking(tmp_path):
    root = workspace(tmp_path)
    blocked_change_review(root, tmp_path)
    assert run_arch(["model", "set-rule", "R10", "advisory", "reason=migrating"], root).returncode == 0
    rerun = change_review(root, tmp_path, finding())
    assert rerun.returncode == 0, rerun.stderr
    assert "Verdict: OK" in rerun.stdout and "Advisory: 1 finding" in rerun.stdout
    assert "Dropped: 0" in rerun.stdout


def test_dropped_count_includes_the_check_rows_covered_by_exceptions(tmp_path):
    root = workspace(tmp_path)
    seed_policy_to_detail_edge(root)
    assert run_arch(["model", "add-exception", EMPLOYEE, CLOCK, "reason=intended"], root).returncode == 0
    result = audit(root, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Dropped: 1 (1 covered by an exception)" in result.stdout


def judged_port_finding() -> dict:
    return finding("consumer-uses-few-interface-members", "src/domain/clock.ts#Clock",
                   evidence=["src/domain/clock.ts:1"])


@pytest.mark.parametrize(
    "ends",
    [
        ("src/domain/clock.ts#Clock", "*"),
        ("src/domain/clock.ts", "*"),
        ("domain", "*"),
    ],
)
def test_every_exception_end_form_covers_a_judged_port_finding(tmp_path, ends):
    root = workspace(tmp_path)
    touch(root, "src/domain/clock.ts")
    first = change_review(root, tmp_path, judged_port_finding())
    assert "Verdict: SHOULD_CHANGE" in first.stdout, first.stdout + first.stderr
    assert run_arch(["model", "add-exception", *ends, "reason=accepted"], root).returncode == 0
    rerun = change_review(root, tmp_path, judged_port_finding())
    assert "Verdict: OK" in rerun.stdout, rerun.stdout


def test_port_exception_does_not_cover_a_sibling_port_or_the_unit(tmp_path):
    root = workspace(tmp_path)
    touch(root, EMPLOYEE)
    assert run_arch(["model", "add-exception", "src/domain/employee.ts#Other", "*", "reason=x"], root).returncode == 0
    assert "Verdict: SHOULD_CHANGE" in change_review(root, tmp_path, finding()).stdout


def test_ring_exception_covers_a_judged_unit_finding(tmp_path):
    root = workspace(tmp_path)
    blocked_change_review(root, tmp_path)
    assert run_arch(["model", "add-exception", "ring:entities", "*", "reason=accepted"], root).returncode == 0
    assert "Verdict: OK" in change_review(root, tmp_path, finding()).stdout
