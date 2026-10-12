import json
from pathlib import Path

from support import FIXTURE_FLAGS, copy_fixture, git, init_repo, run_arch


def q(root: Path, *args: str) -> dict:
    result = run_arch(["query", *args, *FIXTURE_FLAGS, "--json"], root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_metrics_table(tmp_path: Path):
    out = q(copy_fixture("payroll", tmp_path / "p"), "metrics")
    assert out["columns"] == ["Component", "Units", "Fan-in", "Fan-out", "I", "A", "D", "Zone"]
    c1 = next(r for r in out["rows"] if r[0] == "C1 domain")
    assert c1[1:] == [4, 3, 0, 0, 0.5, 0.5, None]


def test_ring_crossings_outward_is_empty_and_inward_lists_edges(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    assert q(root, "ring-crossings")["rows"] == []
    inward = q(root, "ring-crossings", "--direction", "inward")["rows"]
    assert ["src/adapters/system-clock.ts", "adapters", "src/domain/clock.ts", "entities", "type-import"] in inward


def test_fan_in_and_units(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    importers = {r[0] for r in q(root, "fan-in", "src/domain/clock.ts")["rows"]}
    assert importers == {"src/domain/payroll-use-case.ts", "src/adapters/system-clock.ts"}
    ports = {r[0] for r in q(root, "units", "--component", "C1", "--kind", "port")["rows"]}
    assert ports == {"src/domain/clock.ts", "src/domain/payroll-repository.ts"}


def test_ports_derive_implementers_and_consumers(tmp_path: Path):
    rows = q(copy_fixture("payroll", tmp_path / "p"), "ports")["rows"]
    clock = next(r for r in rows if r[0] == "src/domain/clock.ts:Clock")
    assert clock[1] == "C1" and clock[3] == "src/adapters/system-clock.ts" and clock[4] == "C2 (1)"


def test_touched_lists_changed_units_with_neighbors(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    (root / "src/domain/employee.ts").write_text("export class Employee { name = 'x'; }\n")
    out = q(root, "touched", "--base", "HEAD")
    row = next(r for r in out["rows"] if r[0] == "src/domain/employee.ts")
    assert row[4] == "modified"
    assert "src/domain/payroll-use-case.ts" in row[5]


def test_volatility_counts_commits_per_component(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    base = git(["rev-parse", "HEAD"], root).stdout.strip()
    (root / "src/web/main.ts").write_text("import './payroll-controller.js'; export {};\n")
    git(["commit", "-qam", "touch web"], root)
    (root / "src/web/main.ts").write_text("import './payroll-controller.js'; export const x = 1;\n")
    git(["commit", "-qam", "touch web again"], root)
    rows = q(root, "volatility", "--since", base)["rows"]
    assert ["C3 web", 2, 1] in rows


def test_uncovered_exit_code(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    assert run_arch(["uncovered", *FIXTURE_FLAGS], root).returncode == 0
    cruise = json.loads((root / "cruise.json").read_text())
    cruise["modules"].append({"source": "src/scripts/seed.ts", "dependencies": []})
    (root / "cruise.json").write_text(json.dumps(cruise))
    (root / "src/scripts").mkdir(); (root / "src/scripts/seed.ts").write_text("export const s = 1;\n")
    result = run_arch(["uncovered", *FIXTURE_FLAGS], root)
    assert result.returncode == 1 and result.stdout.strip() == "src/scripts/seed.ts"


def test_touched_from_a_subdirectory_root_uses_relative_paths(tmp_path: Path):
    repo = tmp_path / "repo"
    sub = repo / "sub"
    copy_fixture("payroll", sub)
    init_repo(repo)
    (sub / "src/domain/employee.ts").write_text("export class Employee { name = 'x'; }\n")
    out = q(sub, "touched", "--base", "HEAD")
    row = next(r for r in out["rows"] if r[0] == "src/domain/employee.ts")
    assert row[4] == "modified"


def test_touched_without_base_prints_usage(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_arch(["query", "touched", *FIXTURE_FLAGS], root)
    assert result.returncode == 1
    assert result.stderr.strip() == "usage: arch query touched --base <ref>"


def test_volatility_without_since_prints_usage(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_arch(["query", "volatility", *FIXTURE_FLAGS], root)
    assert result.returncode == 1
    assert result.stderr.strip() == "usage: arch query volatility --since <ref>"


def test_markdown_rendering(tmp_path: Path):
    result = run_arch(["query", "metrics", *FIXTURE_FLAGS], copy_fixture("payroll", tmp_path / "p"))
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert lines[0] == "| Component | Units | Fan-in | Fan-out | I | A | D | Zone |"
    assert lines[1] == "|---|---|---|---|---|---|---|---|"
    assert any(l.startswith("| C1 domain | 4 | 3 | 0 | 0 | 0.5 | 0.5 | undefined |") for l in lines)
