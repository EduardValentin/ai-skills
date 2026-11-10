import json
from pathlib import Path

from support import copy_fixture, git, init_repo, run_arch

MODEL = "docs/architecture/architecture.json"
CURRENT = "docs/architecture/current.md"


def repo(tmp_path: Path) -> Path:
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    return root


def cache_files(root: Path) -> list[Path]:
    return sorted((root / ".architecture/graph").glob("*.json"))


def summary(root: Path, *extra: str) -> str:
    result = run_arch(["collect", *extra], root)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def edit_json(path: Path, change) -> None:
    document = json.loads(path.read_text())
    change(document)
    path.write_text(json.dumps(document))


def test_collect_prints_the_counts_and_writes_the_cache(tmp_path: Path):
    root = repo(tmp_path)
    assert summary(root) == "collect: 11 units, 20 edges, 3 components, 0 cycles, 0 uncovered"
    assert len(cache_files(root)) == 1


def test_collect_without_a_model_says_to_run_init(tmp_path: Path):
    result = run_arch(["collect"], tmp_path)
    assert result.returncode == 2 and "arch model init" in result.stderr


def test_collect_writes_current_md_without_dates_or_run_numbers(tmp_path: Path):
    root = repo(tmp_path)
    summary(root)
    text = (root / CURRENT).read_text()
    headings = [line for line in text.splitlines() if line.startswith("#")]
    assert headings == ["# Architecture: current picture", "## Counts", "## Metrics", "## Component graph",
                        "## Threshold breaches"]
    assert "rewritten by `arch collect`" in text
    assert "| domain | 5 | 4 | 0 | 0 | 0.5 | 0.5 | none |" in text
    assert "| web | adapters | 1 |" in text
    assert text.rstrip().endswith("None")
    assert not any(word in text.lower() for word in ["generated at", "run ", "previous", "commit", "202"])


def test_current_md_lists_zone_breaches(tmp_path: Path):
    root = repo(tmp_path)
    assert run_arch(["model", "set-threshold", "painMaxAbstractness", "0.5"], root).returncode == 0
    summary(root)
    assert "- domain: zone of pain" in (root / CURRENT).read_text()


def test_collect_ref_does_not_touch_current_md(tmp_path: Path):
    root = repo(tmp_path)
    summary(root)
    before = (root / CURRENT).read_text()
    (root / CURRENT).write_text(before + "\nhand edit\n")
    summary(root, "--ref", "HEAD")
    assert (root / CURRENT).read_text().endswith("hand edit\n")


def test_base_ref_uses_the_current_model(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    (root / MODEL).rename(tmp_path / "architecture.json")
    init_repo(root)
    (root / MODEL).write_text((tmp_path / "architecture.json").read_text())
    git(["add", "-A"], root)
    git(["commit", "-q", "-m", "model"], root)
    assert summary(root, "--ref", "HEAD~1").startswith("collect: 11 units")
    assert git(["worktree", "list"], root).stdout.strip().count("\n") == 0


def test_ref_build_reads_the_committed_tree_and_removes_its_worktree(tmp_path: Path):
    root = repo(tmp_path)
    edit_json(root / "adapter.json", lambda d: d["modules"].pop())
    assert summary(root, "--ref", "HEAD").startswith("collect: 11 units")
    assert git(["worktree", "list"], root).stdout.count("\n") == 1


def test_ref_build_works_from_a_repository_subdirectory(tmp_path: Path):
    repository = tmp_path / "repo"
    package = repository / "pkg"
    copy_fixture("payroll", package)
    init_repo(repository)
    assert summary(package, "--ref", "HEAD").startswith("collect: 11 units")
    assert git(["worktree", "list"], repository).stdout.count("\n") == 1


def test_unknown_ref_exits_2_naming_the_ref(tmp_path: Path):
    result = run_arch(["collect", "--ref", "nope"], repo(tmp_path))
    assert result.returncode == 2 and '"nope"' in result.stderr


def test_dirty_tree_edit_invalidates_the_cache(tmp_path: Path):
    root = repo(tmp_path)
    before = summary(root)
    with (root / "src/domain/clock.ts").open("a") as handle:
        handle.write("// edit\n")
    summary(root)
    assert len(cache_files(root)) == 2
    edit_json(root / "adapter.json", lambda d: d["modules"].pop())
    assert summary(root) != before
    assert len(cache_files(root)) == 3


def test_unchanged_tree_reuses_the_cache(tmp_path: Path):
    root = repo(tmp_path)
    summary(root)
    summary(root)
    assert len(cache_files(root)) == 1


def test_untracked_file_edit_invalidates_the_cache(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    edit_json(root / MODEL, lambda d: d.update(adapter="cat out.json"))
    init_repo(root)
    (root / "out.json").write_text((root / "adapter.json").read_text())
    before = summary(root)
    edit_json(root / "out.json", lambda d: d["modules"].pop())
    assert summary(root) != before
    assert len(cache_files(root)) == 2


def test_model_edit_invalidates_the_cache(tmp_path: Path):
    root = repo(tmp_path)
    summary(root)
    assert run_arch(["model", "set-threshold", "painMinFanIn", "5"], root).returncode == 0
    summary(root)
    assert len(cache_files(root)) == 2


def test_collect_ignores_the_architecture_directory_locally_once(tmp_path: Path):
    root = repo(tmp_path)
    summary(root)
    summary(root)
    exclude = (root / ".git/info/exclude").read_text().splitlines()
    assert exclude.count(".architecture/") == 1
    assert not (root / ".gitignore").exists()
    assert ".architecture" not in git(["status", "--porcelain"], root).stdout


def test_collect_leaves_an_existing_ignore_alone(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    (root / ".gitignore").write_text(".architecture/\n")
    init_repo(root)
    summary(root)
    assert ".architecture/" not in (root / ".git/info/exclude").read_text().splitlines()


def test_outside_a_repository_the_adapter_document_is_hashed_with_a_warning(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_arch(["collect"], root)
    assert result.returncode == 0, result.stderr
    assert "not a git repository" in result.stderr
    assert len(cache_files(root)) == 1


def test_adapter_failure_exits_2(tmp_path: Path):
    root = repo(tmp_path)
    edit_json(root / MODEL, lambda d: d.update(adapter="exit 3"))
    result = run_arch(["collect"], root)
    assert result.returncode == 2 and "adapter command" in result.stderr


def validate(root: Path):
    return run_arch(["model", "validate"], root)


def test_validate_passes_on_the_payroll_fixture(tmp_path: Path):
    result = validate(copy_fixture("payroll", tmp_path / "p"))
    assert result.returncode == 0, result.stderr


def test_validate_fails_on_a_pair_matching_no_module(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    edit_json(root / MODEL, lambda d: d["components"][1]["classify"].insert(0, ["nothing-*.ts", "gateway"]))
    result = validate(root)
    assert result.returncode == 2
    assert "adapters" in result.stderr and "nothing-*.ts" in result.stderr


def test_validate_fails_on_a_port_whose_file_is_gone(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    def drop(d):
        d["modules"] = [m for m in d["modules"] if m["path"] != "src/domain/clock.ts"]
        d["edges"] = [e for e in d["edges"] if "src/domain/clock.ts" not in (e.get("from"), e.get("to"))]
    edit_json(root / "adapter.json", drop)
    result = validate(root)
    assert result.returncode == 2 and "src/domain/clock.ts#Clock" in result.stderr


def test_validate_fails_when_two_components_match_the_same_module(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    edit_json(root / MODEL, lambda d: d["components"][2].update(paths=["src/web/**", "src/adapters/system-clock.ts"]))
    result = validate(root)
    assert result.returncode == 2
    assert "src/adapters/system-clock.ts" in result.stderr and "adapters" in result.stderr and "web" in result.stderr


def test_validate_fails_on_a_forbidden_or_exception_path_matching_no_module(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    edit_json(root / MODEL, lambda d: d.update(forbidden=[{"from": "web", "to": "src/nowhere/**", "reason": "x"}]))
    result = validate(root)
    assert result.returncode == 2 and "src/nowhere/**" in result.stderr
    edit_json(root / MODEL, lambda d: d.update(forbidden=[], exceptions=[{"from": "src/gone.ts", "to": "domain", "reason": "x"}]))
    result = validate(root)
    assert result.returncode == 2 and "src/gone.ts" in result.stderr


def test_validate_keeps_component_and_ring_ends(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    edit_json(root / MODEL, lambda d: d.update(forbidden=[{"from": "web", "to": "ring:entities", "reason": "x"}]))
    assert validate(root).returncode == 0


def test_validate_reports_the_model_result_then_the_tooling_error(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    edit_json(root / MODEL, lambda d: d.update(adapter="exit 3"))
    result = validate(root)
    assert result.returncode == 2
    assert "model: ok" in result.stdout and "adapter command" in result.stderr
