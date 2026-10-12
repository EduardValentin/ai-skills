import json
import os
from pathlib import Path

from support import SKILL_DIR, run_node

GIT = SKILL_DIR / "scripts" / "lib" / "git.mjs"


def test_mirror_node_modules_keeps_in_repository_relative_links(tmp_path: Path):
    top = tmp_path / "repo"
    source = top / "apps/web/node_modules"
    (top / "packages/domain").mkdir(parents=True)
    (source / "@app").mkdir(parents=True)
    (source / "lib").mkdir()
    os.symlink("../../../../packages/domain", source / "@app/domain")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    os.symlink(os.path.relpath(outside, source), source / "far")
    dest = tmp_path / "worktree/apps/web/node_modules"
    script = (f"import {{ mirrorNodeModules }} from '{GIT.as_posix()}';"
              f"await mirrorNodeModules({json.dumps(str(source))}, {json.dumps(str(dest))}, {json.dumps(str(top))});")
    result = run_node(script, tmp_path)
    assert result.returncode == 0, result.stderr
    assert dest.is_dir() and not dest.is_symlink()
    assert os.readlink(dest / "@app/domain") == "../../../../packages/domain"
    assert os.readlink(dest / "lib") == str(source / "lib")
    assert Path(os.readlink(dest / "far")).resolve() == outside.resolve()
