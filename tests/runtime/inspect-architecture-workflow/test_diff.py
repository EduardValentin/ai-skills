import json
from pathlib import Path

import shutil

from support import FIXTURE_FLAGS, SKILL_DIR, copy_fixture, git, init_repo, run_arch, run_node

DIFF = SKILL_DIR / "scripts" / "lib" / "diff.mjs"


def test_diff_reports_move_not_remove_and_add(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    base = git(["rev-parse", "--short=8", "HEAD"], root).stdout.strip()
    # Move employee.ts and adjust the cruise and facts fixtures the same way
    (root / "src/domain/employee.ts").rename(root / "src/domain/employee-record.ts")
    cruise = json.loads((root / "cruise.json").read_text())
    for m in cruise["modules"]:
        if m["source"] == "src/domain/employee.ts": m["source"] = "src/domain/employee-record.ts"
        for d in m["dependencies"]:
            if d.get("resolved") == "src/domain/employee.ts": d["resolved"] = "src/domain/employee-record.ts"
    (root / "cruise.json").write_text(json.dumps(cruise))
    facts = json.loads((root / "facts.json").read_text())
    facts["modules"]["src/domain/employee-record.ts"] = facts["modules"].pop("src/domain/employee.ts")
    (root / "facts.json").write_text(json.dumps(facts))
    git(["add", "-A"], root)
    result = run_arch(["diff", base, *FIXTURE_FLAGS, "--json"], root)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["units"]["moved"] == [{"from": "src/domain/employee.ts", "to": "src/domain/employee-record.ts"}]
    assert out["units"]["added"] == [] and out["units"]["removed"] == []
    assert out["edges"]["added"] == [] and out["edges"]["removed"] == []
    c1 = next(c for c in out["components"] if c["id"] == "C1")
    assert c1["fanIn"] == [4, 4] and c1["movedPastThreshold"] is False


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
    # Dirty cruise.json too, dropping a module: if the build ever read this
    # working-tree file instead of the worktree's committed one, the cache
    # would end up with 8 units instead of 9.
    cruise = json.loads((root / "cruise.json").read_text())
    cruise["modules"] = [m for m in cruise["modules"] if m["source"] != "src/web/main.ts"]
    (root / "cruise.json").write_text(json.dumps(cruise))
    result = run_arch(["graph", "--commit", base, *FIXTURE_FLAGS], root)
    assert result.returncode == 0, result.stderr
    cached = root / f".architecture/graph/{base}.json"
    assert cached.exists()
    assert len(json.loads(cached.read_text())["units"]) == 9
    assert git(["worktree", "list"], root).stdout.count("\n") == 1


def test_graph_at_commit_works_from_a_repository_subdirectory(tmp_path: Path):
    repo = tmp_path / "repo"
    pkg = repo / "pkg"
    copy_fixture("payroll", pkg)
    init_repo(repo)
    base = git(["rev-parse", "--short=8", "HEAD"], repo).stdout.strip()
    (pkg / "src/domain/employee.ts").write_text("export class Employee { changed = true; }\n")
    result = run_arch(["graph", "--commit", base, *FIXTURE_FLAGS], pkg)
    assert result.returncode == 0, result.stderr
    assert (pkg / f".architecture/graph/{base}.json").exists()
    assert git(["worktree", "list"], repo).stdout.count("\n") == 1


def test_diff_reports_removed_when_rename_target_is_not_covered(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    base = git(["rev-parse", "--short=8", "HEAD"], root).stdout.strip()
    (root / "scripts").mkdir()
    (root / "src/domain/employee.ts").rename(root / "scripts/employee.ts")
    cruise = json.loads((root / "cruise.json").read_text())
    cruise["modules"] = [m for m in cruise["modules"] if m["source"] != "src/domain/employee.ts"]
    for m in cruise["modules"]:
        m["dependencies"] = [d for d in m["dependencies"] if d.get("resolved") != "src/domain/employee.ts"]
    (root / "cruise.json").write_text(json.dumps(cruise))
    facts = json.loads((root / "facts.json").read_text())
    facts["modules"].pop("src/domain/employee.ts")
    (root / "facts.json").write_text(json.dumps(facts))
    git(["add", "-A"], root)
    out = json.loads(run_arch(["diff", base, *FIXTURE_FLAGS, "--json"], root).stdout)
    assert out["units"]["moved"] == []
    assert out["units"]["removed"] == ["src/domain/employee.ts"]


def test_diff_reports_base_only_component_with_null_head_metrics(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    base = git(["rev-parse", "--short=8", "HEAD"], root).stdout.strip()
    components_path = root / "docs/architecture/model/components.json"
    components = json.loads(components_path.read_text())
    components["components"] = [c for c in components["components"] if c["id"] != "C3"]
    components_path.write_text(json.dumps(components))
    out = json.loads(run_arch(["diff", base, *FIXTURE_FLAGS, "--json"], root).stdout)
    c3 = next(c for c in out["components"] if c["id"] == "C3")
    assert c3["fanOut"] == [1, None]


def _add_dependency(root: Path, source: str, target: str) -> None:
    cruise = json.loads((root / "cruise.json").read_text())
    module = next(m for m in cruise["modules"] if m["source"] == source)
    module["dependencies"].append({"module": target, "resolved": target, "dependencyTypes": ["local", "import"], "dynamic": False, "couldNotResolve": False})
    (root / "cruise.json").write_text(json.dumps(cruise))


def _moved(d0: float, d1: float) -> bool:
    graph = lambda d: {"commit": "x", "units": [], "edges": [], "components": [{"id": "C1", "distance": d}], "cycles": {"modules": [], "components": []}}
    script = (f"import {{ diffGraphs }} from '{DIFF.as_posix()}';"
              f"const r = diffGraphs({json.dumps(graph(d0))}, {json.dumps(graph(d1))}, new Map());"
              "process.stdout.write(JSON.stringify(r.components[0].movedPastThreshold));")
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_distance_threshold_includes_the_boundary():
    assert _moved(0.5, 0.6) is True
    assert _moved(0.5, 0.59) is False
    assert _moved(0.6, 0.5) is True


def test_diff_against_a_base_without_a_model_says_how_to_proceed(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    model = root / "docs/architecture/model"
    saved = tmp_path / "model"
    shutil.move(str(model), str(saved))
    init_repo(root)
    first = git(["rev-parse", "--short=8", "HEAD"], root).stdout.strip()
    shutil.move(str(saved), str(model))
    git(["add", "-A"], root)
    git(["commit", "-q", "-m", "model"], root)
    result = run_arch(["diff", first, *FIXTURE_FLAGS], root)
    assert result.returncode == 1
    assert result.stderr.strip() == (f'no architecture model at {first}; evaluate the working tree with '
                                     f'"arch query touched --base {first}" (change-review.md, Map step 4)')
    graph = run_arch(["graph", "--commit", first, *FIXTURE_FLAGS], root)
    assert graph.returncode == 1
    assert graph.stderr.strip() == f"no architecture model at {first}"


def test_diff_markdown_renders_missing_values_with_the_query_renderer(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    base = git(["rev-parse", "--short=8", "HEAD"], root).stdout.strip()
    components_path = root / "docs/architecture/model/components.json"
    components = json.loads(components_path.read_text())
    components["components"] = [c for c in components["components"] if c["id"] != "C3"]
    components_path.write_text(json.dumps(components))
    result = run_arch(["diff", base, *FIXTURE_FLAGS], root)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert "| Component | Fan-in | Fan-out | I | A | D | Moved |" in lines
    c3 = next(l for l in lines if l.startswith("| C3 |"))
    assert c3 == "| C3 | 0 ->  | 1 ->  | 1 -> undefined | 0 -> undefined | 0 -> undefined | false |"
    assert " - " not in c3 and "-> -" not in result.stdout


def test_diff_reports_module_cycles(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    base = git(["rev-parse", "--short=8", "HEAD"], root).stdout.strip()
    _add_dependency(root, "src/domain/employee.ts", "src/domain/payroll-use-case.ts")
    result = run_arch(["diff", base, *FIXTURE_FLAGS, "--json"], root)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["cycles"]["modules"] == {"new": [["src/domain/employee.ts", "src/domain/payroll-use-case.ts"]], "gone": []}
    assert out["cycles"]["new"] == []
    markdown = run_arch(["diff", base, *FIXTURE_FLAGS], root).stdout
    assert "+ src/domain/employee.ts -> src/domain/payroll-use-case.ts" in markdown.split("## Cycles")[1]


def test_diff_against_head_on_a_dirty_tree(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    _add_dependency(root, "src/domain/employee.ts", "src/adapters/system-clock.ts")
    result = run_arch(["diff", "HEAD", *FIXTURE_FLAGS, "--json"], root)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert [(e["from"], e["to"]) for e in out["edges"]["added"]] == [("src/domain/employee.ts", "src/adapters/system-clock.ts")]
    assert out["units"]["added"] == [] and out["units"]["removed"] == []
