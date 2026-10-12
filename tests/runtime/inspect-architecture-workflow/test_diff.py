import json
from pathlib import Path

from support import FIXTURE_FLAGS, copy_fixture, git, init_repo, run_arch


def test_diff_reports_move_not_remove_and_add(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    base = git(["rev-parse", "--short=8", "HEAD"], root).stdout.strip()
    # Move employee.ts and adjust the cruise and exports fixtures the same way
    (root / "src/domain/employee.ts").rename(root / "src/domain/employee-record.ts")
    cruise = json.loads((root / "cruise.json").read_text())
    for m in cruise["modules"]:
        if m["source"] == "src/domain/employee.ts": m["source"] = "src/domain/employee-record.ts"
        for d in m["dependencies"]:
            if d.get("resolved") == "src/domain/employee.ts": d["resolved"] = "src/domain/employee-record.ts"
    (root / "cruise.json").write_text(json.dumps(cruise))
    exports = json.loads((root / "exports.json").read_text())
    exports["src/domain/employee-record.ts"] = exports.pop("src/domain/employee.ts")
    (root / "exports.json").write_text(json.dumps(exports))
    git(["add", "-A"], root)
    result = run_arch(["diff", base, *FIXTURE_FLAGS, "--json"], root)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["units"]["moved"] == [{"from": "src/domain/employee.ts", "to": "src/domain/employee-record.ts"}]
    assert out["units"]["added"] == [] and out["units"]["removed"] == []
    assert out["edges"]["added"] == [] and out["edges"]["removed"] == []
    c1 = next(c for c in out["components"] if c["id"] == "C1")
    assert c1["fanIn"] == [3, 3] and c1["movedPastThreshold"] is False


def test_diff_reports_new_outward_edge_and_metric_move(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    base = git(["rev-parse", "--short=8", "HEAD"], root).stdout.strip()
    cruise = json.loads((root / "cruise.json").read_text())
    emp = next(m for m in cruise["modules"] if m["source"] == "src/domain/employee.ts")
    emp["dependencies"].append({"module": "../adapters/system-clock", "resolved": "src/adapters/system-clock.ts", "dependencyTypes": ["local", "import"], "dynamic": False, "couldNotResolve": False, "matchesDoNotFollow": False})
    (root / "cruise.json").write_text(json.dumps(cruise))
    out = json.loads(run_arch(["diff", base, *FIXTURE_FLAGS, "--json"], root).stdout)
    added = out["edges"]["added"]
    assert added == [{"from": "src/domain/employee.ts", "to": "src/adapters/system-clock.ts", "kind": "import", "direction": "outward", "crossesComponent": True}]
    c1 = next(c for c in out["components"] if c["id"] == "C1")
    assert c1["fanOut"] == [0, 1] and c1["movedPastThreshold"] is True
    assert out["cycles"]["new"] == [["C1", "C2"]]


def test_graph_at_commit_uses_a_worktree_and_caches(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    base = git(["rev-parse", "--short=8", "HEAD"], root).stdout.strip()
    (root / "src/domain/employee.ts").write_text("export class Employee { changed = true; }\n")
    result = run_arch(["graph", "--commit", base, *FIXTURE_FLAGS], root)
    assert result.returncode == 0, result.stderr
    assert (root / f".architecture/graph/{base}.json").exists()
    assert git(["worktree", "list"], root).stdout.count("\n") == 1
