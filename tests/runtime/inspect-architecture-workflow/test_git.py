import json
from pathlib import Path

from support import SKILL_DIR, copy_fixture, git, init_repo, run_node

CHANGES = (SKILL_DIR / "scripts" / "lib" / "git" / "changes.mjs").as_posix()


def evaluate(root: Path, expression: str):
    script = f"import {{ changedPaths, logNames }} from '{CHANGES}';process.stdout.write(JSON.stringify({expression}));"
    result = run_node(script, root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_changed_paths_report_modified_untracked_and_renamed_files(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    init_repo(root)
    (root / "src/domain/employee.ts").write_text("export class Employee { name = 'x'; }\n")
    (root / "src/domain/notes.md").write_text("notes\n")
    git(["mv", "src/web/main.ts", "src/web/start.ts"], root)
    changes = evaluate(root, "await changedPaths(process.cwd(), 'HEAD')")
    assert {"status": "M", "path": "src/domain/employee.ts"} in changes
    assert {"status": "A", "path": "src/domain/notes.md"} in changes
    assert {"status": "R", "path": "src/web/start.ts", "oldPath": "src/web/main.ts"} in changes


def test_log_names_lists_each_commit_with_its_files_relative_to_the_root(tmp_path: Path):
    repo = tmp_path / "repo"
    sub = repo / "sub"
    copy_fixture("payroll", sub)
    init_repo(repo)
    (sub / "src/web/main.ts").write_text("export {};\n")
    git(["commit", "-qam", "touch"], repo)
    commits = evaluate(sub, "await logNames(process.cwd(), ['HEAD~1..HEAD'])")
    assert [commit["files"] for commit in commits] == [["src/web/main.ts"]]
