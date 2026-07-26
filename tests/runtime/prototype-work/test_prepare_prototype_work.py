"""User-observable contract tests for the prototype preparation helper."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    REPO_ROOT
    / "skills"
    / "ui-ux"
    / "prototype-work"
    / "scripts"
    / "prepare-prototype-work.sh"
)


def write_react_app(app_root: Path, name: str) -> None:
    app_root.mkdir(parents=True)
    (app_root / "package.json").write_text(
        json.dumps(
            {
                "name": name,
                "private": True,
                "scripts": {"dev": "vite"},
                "dependencies": {"react": "18.3.1"},
            }
        ),
        encoding="utf-8",
    )


def run_helper(project_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "PROTOTYPE_WORK_SKIP_INSTALL": "1",
            "PROTOTYPE_WORK_SKIP_NODE_CHECK": "1",
        }
    )
    return subprocess.run(
        [str(SCRIPT), "--project-root", str(project_root), *arguments],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


class PreparePrototypeWorkTests(unittest.TestCase):
    def test_auto_detection_selects_the_only_react_prototype(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            only_app = project_root / "designs" / "account"
            write_react_app(only_app, "fake-account-prototype")

            completed = run_helper(project_root)

            self.assertEqual(completed.returncode, 0)
            self.assertIn(f"Ready: app={only_app.resolve()}", completed.stdout)

    def test_auto_detection_rejects_ambiguous_react_prototypes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            first_app = project_root / "designs" / "account"
            second_app = project_root / "designs" / "checkout"
            write_react_app(first_app, "fake-account-prototype")
            write_react_app(second_app, "fake-checkout-prototype")

            completed = run_helper(project_root)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Multiple React prototype apps found", completed.stderr)
            self.assertIn(str(first_app.resolve()), completed.stderr)
            self.assertIn(str(second_app.resolve()), completed.stderr)
            self.assertIn("rerun with --app-root", completed.stderr)
            self.assertNotIn("Ready:", completed.stdout)

    def test_explicit_app_root_selects_one_app_when_multiple_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            first_app = project_root / "designs" / "account"
            selected_app = project_root / "designs" / "checkout"
            write_react_app(first_app, "fake-account-prototype")
            write_react_app(selected_app, "fake-checkout-prototype")

            completed = run_helper(project_root, "--app-root", str(selected_app))

            self.assertEqual(completed.returncode, 0)
            self.assertIn(f"Ready: app={selected_app.resolve()}", completed.stdout)
            self.assertNotIn("Multiple React prototype apps found", completed.stderr)


if __name__ == "__main__":
    unittest.main()
