import json
import shlex
from pathlib import Path

from support import SKILL_DIR, copy_fixture, git, init_repo, run_arch, run_node

LEDGER_LIB = SKILL_DIR / "scripts" / "lib" / "ledger.mjs"
TEMPLATE = SKILL_DIR / "assets" / "ledger" / "ledger.md"
ROW_COLUMNS = ["Workflow", "Target", "Rule", "Origin", "Verdict", "Severity", "Evidence", "Change", "Escalation", "Protects"]
EDGE = "src/domain/payroll.ts -> src/adapters/pg.ts"
RING_CHANGE = "Invert the dependency through a port"


def row(workflow="W1", target=EDGE, rule="R4", origin="introduced", verdict="SHOULD_CHANGE", severity="blocker",
        evidence="policy imports a detail", change=RING_CHANGE, escalation="", protects="") -> list[str]:
    return [workflow, target, rule, origin, verdict, severity, evidence, change, escalation, protects]


def table(rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(ROW_COLUMNS) + " |", "|" + "|".join("---" for _ in ROW_COLUMNS) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def project(tmp_path: Path) -> Path:
    root = tmp_path / "p"
    (root / "src").mkdir(parents=True)
    (root / "src" / "index.ts").write_text("export {};\n")
    (root / ".gitignore").write_text(".architecture/\n")
    init_repo(root)
    return root


def head(root: Path) -> str:
    return git(["rev-parse", "--short=8", "HEAD"], root).stdout.strip()


def write_lines(root: Path, name: str, lines: list[str]) -> Path:
    file = root / ".architecture" / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("\n".join(lines) + "\n")
    return file


def add_run(root: Path, rows: list[list[str]], *extra: str, mode="audit", scope="repository"):
    rows_file = root / ".architecture" / "rows.md"
    rows_file.parent.mkdir(parents=True, exist_ok=True)
    rows_file.write_text(table(rows))
    if mode == "change-review" and "--base" not in extra:
        extra = (*extra, "--base", "main")
    if mode == "plan-review" and "--plan" not in extra:
        extra = (*extra, "--plan", "docs/plan.md")
    result = run_arch(["ledger", "add-run", "--mode", mode, "--scope", scope, "--rows", str(rows_file), *extra], root)
    assert result.returncode == 0, result.stderr
    return result


def parsed(root: Path) -> dict:
    script = (f"import {{ readFileSync }} from 'node:fs';\nimport {{ parseLedger }} from {json.dumps(str(LEDGER_LIB))};\n"
              f"console.log(JSON.stringify(parseLedger(readFileSync('.architecture/ledger.md', 'utf8'))));")
    result = run_node(script, root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def findings(root: Path) -> dict[str, dict]:
    return {f["id"]: f for f in parsed(root)["findings"]}


def seed_ledger(root: Path, finding_rows: list[str]) -> None:
    text = TEMPLATE.read_text()
    run_log = "| Run | Date | Commit | Mode | Scope | Key | Verdict | Blocker | Major | Minor | OK |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
    text = text.replace(run_log, run_log + "| 1 | 2026-10-01 | abc12345 | audit | repository | audit | SHOULD_CHANGE | 1 | 1 | 0 | 0 |\n", 1)
    marker = "| ID | Workflow | Target | Rule | Origin | Verdict | Severity | Evidence | Change | Protects | Run |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
    text = text.replace(marker, marker + "".join(line + "\n" for line in finding_rows))
    (root / ".architecture").mkdir(exist_ok=True)
    (root / ".architecture" / "ledger.md").write_text(text)


def test_template_round_trips_byte_for_byte(tmp_path: Path):
    script = (f"import {{ readFileSync }} from 'node:fs';\nimport {{ parseLedger, writeLedger }} from {json.dumps(str(LEDGER_LIB))};\n"
              f"const text = readFileSync({json.dumps(str(TEMPLATE))}, 'utf8');\n"
              f"process.stdout.write(writeLedger(parseLedger(text)));")
    result = run_node(script, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == TEMPLATE.read_text()
    assert "| Run | Date | Commit | Mode | Scope | Key | Verdict | Blocker | Major | Minor | OK |" in result.stdout


def test_seeded_ledger_round_trips_byte_for_byte(tmp_path: Path):
    root = project(tmp_path)
    seed_ledger(root, [f"| F1 | W1 | {EDGE} | R4 | introduced | SHOULD_CHANGE | blocker | a \\| b | {RING_CHANGE} |  | 1 |"])
    script = (f"import {{ readFileSync }} from 'node:fs';\nimport {{ parseLedger, writeLedger }} from {json.dumps(str(LEDGER_LIB))};\n"
              f"const text = readFileSync('.architecture/ledger.md', 'utf8');\n"
              f"process.stdout.write(writeLedger(parseLedger(text)));")
    result = run_node(script, root)
    assert result.returncode == 0, result.stderr
    assert result.stdout == (root / ".architecture/ledger.md").read_text()
    assert findings(root)["F1"]["evidence"] == "a | b"


def test_missing_ledger_starts_from_the_template_and_logs_the_run(tmp_path: Path):
    root = project(tmp_path)
    result = add_run(root, [row()])
    text = (root / ".architecture/ledger.md").read_text()
    for heading in ["## Run log", "## Changes", "## Findings", "## Acceptances", "## Pending record updates", "## Improvement map"]:
        assert heading in text
    run = parsed(root)["runs"][0]
    assert run["run"] == "1" and run["commit"] == head(root) and run["mode"] == "audit"
    assert (run["verdict"], run["blocker"], run["major"], run["minor"], run["ok"]) == ("SHOULD_CHANGE", "1", "0", "0", "0")
    assert result.stdout.strip().startswith(f"| 1 | ") and head(root) in result.stdout


def test_two_runs_with_the_same_target_and_rule_keep_the_id(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [row()])
    add_run(root, [row(evidence="policy still imports a detail"), row(target="src/b.ts", rule="R9", workflow="W2", severity="minor")])
    found = findings(root)
    assert sorted(found) == ["F1", "F2"]
    assert found["F1"]["target"] == EDGE and found["F1"]["run"] == "2" and found["F1"]["evidence"] == "policy still imports a detail"
    assert found["F2"]["target"] == "src/b.ts"
    assert len(parsed(root)["runs"]) == 2


def test_duplicate_incoming_rows_keep_the_fuller_evidence(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [row(evidence="short"), row(evidence="the longer evidence")])
    found = findings(root)
    assert list(found) == ["F1"] and found["F1"]["evidence"] == "the longer evidence"


def test_compliant_target_resolves_with_the_commit(tmp_path: Path):
    root = project(tmp_path)
    seed_ledger(root, [f"| F1 | W1 | {EDGE} | R4 | introduced | SHOULD_CHANGE | blocker | policy imports a detail | {RING_CHANGE} |  | 1 |"])
    evaluated = write_lines(root, "evaluated.txt", ["src/domain/payroll.ts"])
    add_run(root, [], "--evaluated", str(evaluated))
    f1 = findings(root)["F1"]
    assert f1["verdict"] == "RESOLVED" and f1["run"] == "2" and head(root) in f1["evidence"]


def test_unevaluated_target_is_carried_forward(tmp_path: Path):
    root = project(tmp_path)
    seed_ledger(root, [f"| F1 | W1 | {EDGE} | R4 | introduced | SHOULD_CHANGE | blocker | policy imports a detail | {RING_CHANGE} |  | 1 |"])
    evaluated = write_lines(root, "evaluated.txt", ["src/elsewhere.ts"])
    add_run(root, [], "--evaluated", str(evaluated))
    f1 = findings(root)["F1"]
    assert f1["verdict"] == "SHOULD_CHANGE" and f1["run"] == "1"


def test_skipped_workflow_rows_are_carried_forward_and_not_resolved(tmp_path: Path):
    root = project(tmp_path)
    seed_ledger(root, ["| F1 | W6 | C1 -> C2 | R31 | introduced | SHOULD_CHANGE | major | I(C1) < I(C2) | Reverse the dependency |  | 1 |"])
    evaluated = write_lines(root, "evaluated.txt", ["C1", "C2", "C1 -> C2"])
    result = add_run(root, [], "--evaluated", str(evaluated), "--skipped", "W6,W7", mode="change-review", scope="diff main")
    f1 = findings(root)["F1"]
    assert f1["verdict"] == "SHOULD_CHANGE" and f1["run"] == "1" and f1["evidence"] == "I(C1) < I(C2)"
    assert "skipped W6, W7" in parsed(root)["runs"][1]["scope"]
    assert "skipped W6, W7" in result.stdout


def test_renamed_target_resolves_the_old_row_and_opens_one_new_row(tmp_path: Path):
    root = project(tmp_path)
    seed_ledger(root, ["| F1 | W2 | src/old.ts | R9 | introduced | SHOULD_CHANGE | minor | mixes two actors | Split by actor |  | 1 |"])
    removed = write_lines(root, "removed.txt", ["src/old.ts"])
    evaluated = write_lines(root, "evaluated.txt", ["src/new.ts"])
    add_run(root, [row(workflow="W2", target="src/new.ts", rule="R9", severity="minor", evidence="mixes two actors", change="Split by actor")],
            "--evaluated", str(evaluated), "--removed", str(removed))
    found = findings(root)
    assert sorted(found) == ["F1", "F2"]
    assert found["F1"]["verdict"] == "RESOLVED" and "target removed" in found["F1"]["evidence"]
    assert found["F2"]["target"] == "src/new.ts" and found["F2"]["verdict"] == "SHOULD_CHANGE"
    assert [f["target"] for f in found.values()].count("src/new.ts") == 1


def test_accept_one_off_writes_the_acceptance_and_survives_the_next_run(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [row()])
    result = run_arch(["ledger", "accept", "F1", "--one-off", "--by", "Eduard", "--reason", "legacy import, ticket scope"], root)
    assert result.returncode == 0, result.stderr
    ledger = parsed(root)
    acceptance = ledger["acceptances"][0]
    assert (acceptance["finding"], acceptance["kind"], acceptance["reason"], acceptance["by"]) == ("F1", "one-off", "legacy import, ticket scope", "Eduard")
    assert ledger["findings"][0]["verdict"] == "ACCEPTED"
    add_run(root, [row()], mode="change-review", scope="diff main")
    f1 = findings(root)["F1"]
    assert f1["verdict"] == "ACCEPTED" and f1["run"] == "2"


def test_accepted_row_resolves_once_the_target_complies(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [row()])
    assert run_arch(["ledger", "accept", "F1", "--one-off", "--by", "Eduard", "--reason", "later"], root).returncode == 0
    evaluated = write_lines(root, "evaluated.txt", ["src/domain/payroll.ts"])
    add_run(root, [], "--evaluated", str(evaluated))
    assert findings(root)["F1"]["verdict"] == "RESOLVED"


R27_EVIDENCE = "{0} shares no recorded group with {1}; groups holding {0}: {2}"


def payroll_project(tmp_path: Path) -> Path:
    root = copy_fixture("payroll", tmp_path / "p")
    (root / ".gitignore").write_text(".architecture/\n")
    init_repo(root)
    return root


def run_printed_model_command(root: Path, stdout: str) -> None:
    line = next(l for l in stdout.splitlines() if l.startswith("arch model add-group"))
    result = run_arch(shlex.split(line)[1:], root)
    assert result.returncode == 0, result.stderr


def test_accept_standing_creates_a_group_from_the_evidence_when_none_holds_the_target(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [row(workflow="W6", target="C3", rule="R27", severity="major", evidence=R27_EVIDENCE.format("C3", "C1, C2", "none"), change="Split the change")])
    result = run_arch(["ledger", "accept", "F1", "--standing", "--by", "Eduard", "--reason", "invoices change with billing"], root)
    assert result.returncode == 0, result.stderr
    assert 'arch model add-group <name> components=C1,C2,C3 absorbs="<to be stated>"' in result.stdout
    acceptance = parsed(root)["acceptances"][0]
    assert acceptance["kind"] == "standing" and "group" in acceptance["promoted"]


def test_accept_standing_widens_every_group_the_evidence_names(tmp_path: Path):
    root = payroll_project(tmp_path)
    assert run_arch(["model", "add-group", "core", "components=C1,C2", "absorbs=core rules"], root).returncode == 0
    assert run_arch(["model", "add-group", "side", "components=C1", "absorbs=side rules"], root).returncode == 0
    add_run(root, [row(workflow="W6", target="C1", rule="R27", severity="major", evidence=R27_EVIDENCE.format("C1", "C3", "core, side"), change="Split the change")])
    result = run_arch(["ledger", "accept", "F1", "--standing", "--by", "Eduard", "--reason", "web moves with the domain"], root)
    assert result.returncode == 0, result.stderr
    assert 'arch model add-group core components=C1,C2,C3 absorbs="core rules"' in result.stdout
    assert 'arch model add-group side components=C1,C3 absorbs="side rules"' in result.stdout
    assert parsed(root)["acceptances"][0]["promoted"] == "model/boundaries.json groups core, side; decisions.md Cohesion groups"


def test_the_printed_widening_command_widens_the_current_group(tmp_path: Path):
    root = payroll_project(tmp_path)
    assert run_arch(["model", "add-group", "billing", "components=C1", "absorbs=billing rules"], root).returncode == 0
    add_run(root, [
        row(workflow="W6", target="C1", rule="R27", severity="major", evidence=R27_EVIDENCE.format("C1", "C2", "billing"), change="Split the change"),
    ])
    first = run_arch(["ledger", "accept", "F1", "--standing", "--by", "Eduard", "--reason", "payroll moves with billing"], root)
    assert first.returncode == 0, first.stderr
    assert 'arch model add-group billing components=C1,C2 absorbs="billing rules"' in first.stdout
    run_printed_model_command(root, first.stdout)
    groups = json.loads((root / "docs/architecture/model/boundaries.json").read_text())["groups"]
    assert next(g for g in groups if g["name"] == "billing")["components"] == ["C1", "C2"]


def test_accepting_again_updates_the_acceptance_row(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [row()])
    assert run_arch(["ledger", "accept", "F1", "--one-off", "--by", "Eduard", "--reason", "for now"], root).returncode == 0
    assert parsed(root)["acceptances"][0]["promoted"] == "none"
    assert run_arch(["ledger", "accept", "F1", "--standing", "--by", "Ana", "--reason", "shared clock"], root).returncode == 0
    acceptances = parsed(root)["acceptances"]
    assert len(acceptances) == 1
    assert (acceptances[0]["kind"], acceptances[0]["by"], acceptances[0]["reason"]) == ("standing", "Ana", "shared clock")
    assert acceptances[0]["promoted"].startswith("decisions.md intended exception")


def test_accept_standing_on_an_edge_row_prints_an_intended_exception(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [row()])
    result = run_arch(["ledger", "accept", "F1", "--standing", "--by", "Eduard", "--reason", "shared clock"], root)
    assert result.returncode == 0, result.stderr
    assert "Intended exceptions" in result.stdout and "src/domain/payroll.ts" in result.stdout and "shared clock" in result.stdout


def test_accept_unknown_finding_fails(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [row()])
    result = run_arch(["ledger", "accept", "F9", "--one-off", "--by", "Eduard", "--reason", "x"], root)
    assert result.returncode == 1 and "no finding F9" in result.stderr


def test_map_orders_changes_by_severity_then_rows_and_names_them(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [
        row(target="src/a.ts -> src/x.ts", severity="major", change="Extract a port for payments", protects="UC-1"),
        row(target="src/b.ts -> src/x.ts", severity="major", change="Extract a port for payments", protects="UC-2"),
        row(target="src/c.ts -> src/y.ts", severity="major", change="Move the clock behind a port"),
        row(target="src/d.ts -> src/z.ts", severity="blocker", change="Break the cycle"),
        row(target="src/e.ts -> src/z.ts", severity="minor", change="Rename nothing", verdict="OK"),
    ])
    result = run_arch(["ledger", "map"], root)
    assert result.returncode == 0, result.stderr
    ledger = parsed(root)
    assert [(c["change"], c["description"]) for c in ledger["changes"]] == [
        ("CH-A", "Break the cycle"), ("CH-B", "Extract a port for payments"), ("CH-C", "Move the clock behind a port")]
    assert [(m["order"], m["change"], m["severity"], m["rows"]) for m in ledger["map"]] == [
        ("1", "CH-A", "blocker", "1"), ("2", "CH-B", "major", "2"), ("3", "CH-C", "major", "1")]
    assert ledger["map"][1]["protects"] == "UC-1, UC-2"
    by_target = {f["target"]: f for f in ledger["findings"]}
    assert by_target["src/a.ts -> src/x.ts"]["change"] == "CH-B"
    assert "Direction:" in result.stdout and "1. CH-A" in result.stdout and "3. CH-C" in result.stdout
    again = run_arch(["ledger", "map"], root)
    assert again.returncode == 0 and [c["description"] for c in parsed(root)["changes"]][0] == "Break the cycle"


def test_map_prints_the_return_contract_lines(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [row(severity="major (base minor)", escalation="rule 3"), row(target="src/q.ts", rule="R9", verdict="OK", severity="", change="")])
    result = run_arch(["ledger", "map", "--agents", "1 mapping, 0 fact, 1 evaluation"], root)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "Verdict: SHOULD_CHANGE — 0 blocker, 1 major, 0 minor open; 1 targets OK; 1 changes named"
    assert lines[1] == "Pre-existing: 0 blocker, 0 major, 0 minor (not blocking)"
    assert lines[2] == "Carried: 0 open from earlier scopes (not blocking)"
    assert lines[3] == "Escalation: 0 rows lifted by rule 1, 0 by rule 2, 1 by rule 3, 0 by rule 4"
    assert "Agents: 2 dispatched (1 mapping, 0 fact, 1 evaluation)" in lines


def test_run_verdict_counts_introduced_rows_and_rule_2_lifts_only(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [row(origin="left", severity="major")], mode="change-review", scope="diff main")
    result = run_arch(["ledger", "map"], root)
    assert result.stdout.splitlines()[0].startswith("Verdict: OK — 0 blocker, 0 major, 0 minor open")
    assert result.stdout.splitlines()[1] == "Pre-existing: 0 blocker, 1 major, 0 minor (not blocking)"

    add_run(root, [row(origin="left", severity="blocker (base major)", evidence="fixing it first shrinks UC-1 [rule 2]")], mode="change-review", scope="diff main")
    lifted = run_arch(["ledger", "map"], root).stdout.splitlines()
    assert lifted[0].startswith("Verdict: SHOULD_CHANGE — 1 blocker, 0 major")
    assert lifted[3].startswith("Escalation: 0 rows lifted by rule 1, 1 by rule 2")

    add_run(root, [row(origin="introduced", severity="major")], mode="change-review", scope="diff main")
    assert run_arch(["ledger", "map"], root).stdout.startswith("Verdict: SHOULD_CHANGE — 0 blocker, 1 major")


def test_add_run_rejects_an_unknown_mode(tmp_path: Path):
    root = project(tmp_path)
    rows_file = write_lines(root, "rows.md", table([]).splitlines())
    result = run_arch(["ledger", "add-run", "--mode", "survey", "--scope", "x", "--rows", str(rows_file)], root)
    assert result.returncode == 1 and "usage: arch ledger add-run" in result.stderr


def test_severity_cell_keeps_the_base_and_reads_the_first_word(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [
        row(target="src/a.ts -> src/x.ts", severity="major (base minor)", change="Lifted change"),
        row(target="src/b.ts -> src/x.ts", severity="major (base minor)", escalation="rule 3", change="Assessed change"),
        row(target="src/c.ts -> src/x.ts", severity="minor", change="A minor change"),
    ])
    by_target = {f["target"]: f for f in parsed(root)["findings"]}
    assert by_target["src/a.ts -> src/x.ts"]["severity"] == "major (base minor)"
    assert by_target["src/b.ts -> src/x.ts"]["severity"] == "major (base minor)"
    assert by_target["src/c.ts -> src/x.ts"]["severity"] == "minor"
    result = run_arch(["ledger", "map"], root)
    assert result.stdout.splitlines()[0].startswith("Verdict: SHOULD_CHANGE \u2014 0 blocker, 2 major, 1 minor open")
    assert [(m["change"], m["severity"]) for m in parsed(root)["map"]] == [("CH-A", "major"), ("CH-B", "major"), ("CH-C", "minor")]
    assert [c["description"] for c in parsed(root)["changes"]][2] == "A minor change"


def test_duplicate_rows_keep_the_highest_severity_and_every_mark(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [
        row(severity="blocker (base major)", escalation="rule 2", evidence="short"),
        row(severity="major (base minor)", evidence="the evaluator's longer evidence [rule 1]"),
    ])
    found = findings(root)
    assert list(found) == ["F1"]
    assert found["F1"]["severity"] == "blocker (base major)"
    assert found["F1"]["evidence"] == "the evaluator's longer evidence [rule 1] [rule 2]"


def test_fix_loop_keeps_counting_open_rows_of_the_same_key(tmp_path: Path):
    root = project(tmp_path)
    first_base = head(root)
    add_run(root, [row(target="src/old/a.ts -> src/old/b.ts", severity="major", change="Older change")], mode="audit", scope="repository")
    add_run(root, [row(severity="major")], mode="change-review", scope="diff main", )
    first = run_arch(["ledger", "map"], root).stdout.splitlines()
    assert first[0].startswith("Verdict: SHOULD_CHANGE \u2014 0 blocker, 1 major")
    assert first[2] == "Carried: 1 open from earlier scopes (not blocking)"

    printed = add_run(root, [], mode="change-review", scope="second round of the ticket").stdout
    assert "| SHOULD_CHANGE | 0 | 1 | 0 | 0 |" in printed
    runs = parsed(root)["runs"]
    assert (runs[2]["verdict"], runs[2]["key"], runs[0]["key"]) == ("SHOULD_CHANGE", first_base, "audit")
    second = run_arch(["ledger", "map"], root).stdout.splitlines()
    assert second[0].startswith("Verdict: SHOULD_CHANGE \u2014 0 blocker, 1 major")
    assert second[2] == "Carried: 1 open from earlier scopes (not blocking)"

    (root / "src" / "later.ts").write_text("export {};\n")
    git(["add", "-A"], root)
    git(["commit", "-q", "-m", "later"], root)
    add_run(root, [], mode="change-review", scope="diff main")
    third = run_arch(["ledger", "map"], root).stdout.splitlines()
    assert third[0].startswith("Verdict: OK \u2014 0 blocker, 0 major")
    assert third[2] == "Carried: 2 open from earlier scopes (not blocking)"


def test_plan_review_keys_runs_by_the_plan_path(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [row(severity="major")], "--plan", "docs/plans/payroll.md", mode="plan-review", scope="task 3")
    assert parsed(root)["runs"][0]["key"] == "docs/plans/payroll.md"
    rows_file = write_lines(root, "rows.md", table([]).splitlines())
    missing = run_arch(["ledger", "add-run", "--mode", "plan-review", "--scope", "x", "--rows", str(rows_file)], root)
    assert missing.returncode == 1 and "usage: arch ledger add-run" in missing.stderr
    missing_base = run_arch(["ledger", "add-run", "--mode", "change-review", "--scope", "x", "--rows", str(rows_file)], root)
    assert missing_base.returncode == 1 and "usage: arch ledger add-run" in missing_base.stderr


def test_duplicates_of_equal_severity_keep_the_base(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [
        row(severity="major (base minor)", evidence="short"), row(severity="major", evidence="the longer evidence"),
        row(target="src/b.ts", severity="major", evidence="the longer evidence"), row(target="src/b.ts", severity="major (base minor)", evidence="short"),
    ])
    found = findings(root)
    assert found["F1"]["severity"] == "major (base minor)" and found["F1"]["evidence"] == "the longer evidence"
    assert found["F2"]["severity"] == "major (base minor)" and found["F2"]["evidence"] == "the longer evidence"


def test_an_audit_that_evaluates_everything_resolves_a_vanished_assessed_row(tmp_path: Path):
    root = project(tmp_path)
    everything = write_lines(root, "evaluated.txt", ["*"])
    add_run(root, [row(evidence="policy unit depends on a detail unit")], "--evaluated", str(everything))
    assert run_arch(["ledger", "map"], root).stdout.startswith("Verdict: SHOULD_CHANGE")
    add_run(root, [], "--evaluated", str(everything))
    f1 = findings(root)["F1"]
    assert f1["verdict"] == "RESOLVED" and f1["evidence"].endswith(f"resolved at {head(root)}")
    assert run_arch(["ledger", "map"], root).stdout.startswith("Verdict: OK")


def test_standing_acceptance_of_a_lifted_r27_row_reads_the_group_without_the_mark(tmp_path: Path):
    root = payroll_project(tmp_path)
    assert run_arch(["model", "add-group", "billing", "components=C1,C2", "absorbs=billing rules"], root).returncode == 0
    evidence = R27_EVIDENCE.format("C1", "C3", "billing") + " [rule 2]"
    add_run(root, [row(workflow="W6", target="C1", rule="R27", severity="blocker (base major)", evidence=evidence, change="Split the change")])
    result = run_arch(["ledger", "accept", "F1", "--standing", "--by", "Eduard", "--reason", "web moves with billing"], root)
    assert result.returncode == 0, result.stderr
    assert 'arch model add-group billing components=C1,C2,C3 absorbs="billing rules"' in result.stdout
    assert parsed(root)["acceptances"][0]["promoted"] == "model/boundaries.json group billing; decisions.md Cohesion groups"


def test_plan_keys_are_normalized_relative_to_the_root(tmp_path: Path):
    root = project(tmp_path)
    add_run(root, [row(severity="major")], "--plan", "./docs/p.md", mode="plan-review")
    add_run(root, [], "--plan", "docs/p.md", mode="plan-review")
    add_run(root, [], "--plan", str(root / "docs" / "p.md"), mode="plan-review")
    assert {r["key"] for r in parsed(root)["runs"]} == {"docs/p.md"}
    assert run_arch(["ledger", "map"], root).stdout.startswith("Verdict: SHOULD_CHANGE")


def test_an_escalation_mark_without_a_base_severity_is_refused(tmp_path: Path):
    root = project(tmp_path)
    for marked in (row(severity="major", escalation="rule 3"), row(severity="blocker", evidence="fixing it first shrinks UC-1 [rule 2]")):
        rows_file = write_lines(root, "rows.md", table([marked]).splitlines())
        result = run_arch(["ledger", "add-run", "--mode", "audit", "--scope", "x", "--rows", str(rows_file)], root)
        assert result.returncode == 1
        assert f"row {EDGE} R4: an escalation mark needs a base severity" in result.stderr
    assert not (root / ".architecture" / "ledger.md").exists()
