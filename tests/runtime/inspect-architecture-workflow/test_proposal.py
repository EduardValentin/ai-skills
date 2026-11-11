import json
from pathlib import Path

from support import copy_fixture, init_repo, run_arch

MODEL = "docs/architecture/architecture.json"
ADAPTER = "adapter.json"
CLOCK = "src/adapters/system-clock.ts"
RULE = "src/domain/overtime-rule.ts"


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


def proposal(tmp_path: Path, **document) -> Path:
    path = tmp_path / "proposal.json"
    path.write_text(json.dumps({"version": 1, **document}))
    return path


def check_proposal(root: Path, file: Path):
    return run_arch(["check", "--proposal", str(file), "--json"], root)


def rows_of(result) -> list[dict]:
    assert result.returncode in (0, 1), result.stderr
    return json.loads(result.stdout)["rows"]


def test_proposal_edge_from_policy_to_detail_is_introduced(tmp_path):
    root = workspace(tmp_path)
    file = proposal(tmp_path, modules=[{"path": RULE}], edges=[{"from": RULE, "to": CLOCK, "kind": "import"}])
    result = check_proposal(root, file)
    assert result.returncode == 1
    row = next(r for r in rows_of(result) if r["target"] == f"{RULE} -> {CLOCK}" and "R4" in r["rules"])
    assert (row["origin"], row["severity"], row["defect"]) == ("introduced", "blocker", "policy-depends-on-detail")


def test_proposal_leaves_existing_findings_inherited_or_out_of_scope(tmp_path):
    root = workspace(tmp_path)
    file = proposal(tmp_path, modules=[{"path": RULE}], edges=[])
    rows = rows_of(check_proposal(root, file))
    assert all(r["origin"] != "introduced" for r in rows)
    assert all("payroll-controller" not in r["target"] for r in rows)


def test_proposal_unknown_becomes_a_clarification(tmp_path):
    root = workspace(tmp_path)
    file = proposal(tmp_path, unknown=[{"task": "Task 3", "fact": "which store keeps the rules"}])
    output = json.loads(check_proposal(root, file).stdout)
    entry = next(e for e in output["incomplete"] if e.get("clarification"))
    assert entry["task"] == "Task 3" and entry["fact"] == "which store keeps the rules"
    assert "Task 3" in entry["reason"] and "which store keeps the rules" in entry["reason"]


def test_proposal_classify_entry_covers_a_module_the_model_does_not(tmp_path):
    root = workspace(tmp_path)
    helper = "tools/rate-helper.ts"
    edges = [{"from": helper, "to": CLOCK, "kind": "import"}]
    bare = json.loads(check_proposal(root, proposal(tmp_path, modules=[{"path": helper}], edges=edges)).stdout)
    assert any(e["target"] == helper for e in bare["incomplete"])
    classified = proposal(tmp_path, modules=[{"path": helper}], edges=edges,
                          classify=[{"path": helper, "kind": "entity", "component": "domain"}])
    output = json.loads(check_proposal(root, classified).stdout)
    assert not any(e["target"] == helper for e in output["incomplete"])
    assert any(r["target"] == f"{helper} -> {CLOCK}" for r in output["rows"])


def test_proposal_removed_edge_takes_the_finding_away(tmp_path):
    root = workspace(tmp_path)
    controller = "src/web/payroll-controller.ts"
    pg = "src/adapters/pg-payroll-repository.ts"
    edit_json(root / MODEL, lambda d: d["rules"].update({"R7": ["off", "baseline"]}))
    file = proposal(tmp_path, modules=[{"path": controller}], removedEdges=[{"from": controller, "to": pg}])
    rows = rows_of(check_proposal(root, file))
    assert not any(r["target"] == f"{controller} -> {pg}" for r in rows)


def test_proposal_cannot_be_combined_with_base(tmp_path):
    root = workspace(tmp_path)
    result = run_arch(["check", "--proposal", str(proposal(tmp_path)), "--base", "main"], root)
    assert result.returncode == 2 and "--proposal" in result.stderr and "--base" in result.stderr


def test_invalid_proposal_names_each_problem(tmp_path):
    root = workspace(tmp_path)
    file = proposal(tmp_path, modules=[{"name": "x"}], edges=[{"from": RULE}], extra=1)
    result = check_proposal(root, file)
    assert result.returncode == 2
    for fragment in ("modules[0].path: is required", "modules[0].name", "edges[0]", "extra"):
        assert fragment in result.stderr, result.stderr


def test_unreadable_proposal_is_a_usage_error(tmp_path):
    root = workspace(tmp_path)
    missing = run_arch(["check", "--proposal", str(tmp_path / "nope.json")], root)
    assert missing.returncode == 2 and "nope.json" in missing.stderr
    broken = tmp_path / "broken.json"
    broken.write_text("{")
    assert run_arch(["check", "--proposal", str(broken)], root).returncode == 2


def test_proposal_without_a_model_prints_the_baseline_line(tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    result = run_arch(["check", "--proposal", str(proposal(tmp_path))], bare)
    assert result.returncode == 0 and "no architecture model" in result.stdout
