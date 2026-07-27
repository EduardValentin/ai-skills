"""User-observable contract tests for the prototype preparation helper."""

from __future__ import annotations

import json
import os
import shutil
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


def write_non_react_app(app_root: Path, name: str) -> None:
    app_root.mkdir(parents=True)
    (app_root / "package.json").write_text(
        json.dumps(
            {
                "name": name,
                "private": True,
                "scripts": {"dev": "vite"},
            }
        ),
        encoding="utf-8",
    )


def write_package(app_root: Path, package: dict[str, object]) -> None:
    app_root.mkdir(parents=True)
    (app_root / "package.json").write_text(
        json.dumps(package),
        encoding="utf-8",
    )


def write_raw_package(app_root: Path, package_json: str) -> None:
    app_root.mkdir(parents=True)
    (app_root / "package.json").write_text(package_json, encoding="utf-8")


def read_only_command_path(root: Path) -> str:
    bin_root = root / "bin"
    bin_root.mkdir()
    for command in ("awk", "bash", "dirname", "find", "grep", "node", "sed", "sort"):
        executable = shutil.which(command)
        if executable is None:
            raise AssertionError(f"Required test command is unavailable: {command}")
        (bin_root / command).symlink_to(executable)
    return str(bin_root)


def failing_find_command_path(root: Path) -> str:
    bin_root = Path(read_only_command_path(root))
    find_command = bin_root / "find"
    find_command.unlink()
    find_command.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$FAKE_FIND_PACKAGE\"\n"
        "exit 1\n",
        encoding="utf-8",
    )
    find_command.chmod(0o755)
    return str(bin_root)


def run_helper(
    project_root: Path,
    *arguments: str,
    command_path: str | None = None,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if command_path is not None:
        env["PATH"] = command_path
    if environment is not None:
        env.update(environment)
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

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn(f"app-root: {only_app.resolve()}", completed.stdout)

    def test_auto_detection_finds_a_deeply_nested_react_prototype(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            only_app = (
                project_root
                / "designs"
                / "areas"
                / "account"
                / "prototypes"
                / "desktop"
                / "reference"
            )
            write_react_app(only_app, "fake-account-prototype")

            completed = run_helper(project_root)

            self.assertEqual(completed.returncode, 0)
            self.assertIn(f"app-root: {only_app.resolve()}", completed.stdout)

    def test_auto_detection_rejects_a_project_without_a_react_prototype(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            (project_root / "designs").mkdir(parents=True)

            completed = run_helper(project_root)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Could not find a React package.json", completed.stderr)
            self.assertNotIn("app-root:", completed.stdout)

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

    def test_auto_detection_prunes_node_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            only_app = project_root / "designs" / "account"
            dependency_app = (
                project_root
                / "designs"
                / "shared"
                / "node_modules"
                / "fake-react-package"
            )
            write_react_app(only_app, "fake-account-prototype")
            write_react_app(dependency_app, "fake-react-dependency")

            completed = run_helper(project_root)

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn(f"app-root: {only_app.resolve()}", completed.stdout)
            self.assertNotIn(str(dependency_app.resolve()), completed.stdout)

    def test_auto_detection_fails_when_filesystem_traversal_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "project"
            app_root = project_root / "designs" / "account"
            write_react_app(app_root, "fake-account-prototype")

            completed = run_helper(
                project_root,
                command_path=failing_find_command_path(temp_root),
                environment={
                    "FAKE_FIND_PACKAGE": str(app_root / "package.json"),
                },
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Could not scan", completed.stderr)
            self.assertNotIn("app-root:", completed.stdout)

    def test_explicit_app_root_selects_one_app_when_multiple_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            first_app = project_root / "designs" / "account"
            selected_app = project_root / "designs" / "checkout"
            write_react_app(first_app, "fake-account-prototype")
            write_react_app(selected_app, "fake-checkout-prototype")

            completed = run_helper(project_root, "--app-root", str(selected_app))

            self.assertEqual(completed.returncode, 0)
            self.assertIn(f"app-root: {selected_app.resolve()}", completed.stdout)
            self.assertNotIn("Multiple React prototype apps found", completed.stderr)

    def test_locator_outputs_non_executable_app_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            app_root = project_root / "designs" / "account"
            write_react_app(app_root, "fake-account-prototype")

            completed = run_helper(project_root, "--app-root", str(app_root))

            self.assertEqual(completed.returncode, 0)
            self.assertEqual(
                completed.stdout.splitlines(),
                [
                    f"app-root: {app_root.resolve()}",
                    f"package-json: {(app_root / 'package.json').resolve()}",
                    "dev-script: present",
                ],
            )
            self.assertNotIn("run dev", completed.stdout)
            self.assertNotIn("corepack", completed.stdout)
            self.assertNotIn("nvm", completed.stdout)
            self.assertNotIn("install", completed.stdout)

    def test_explicit_app_root_must_be_a_react_app(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            app_root = project_root / "designs" / "static-site"
            write_non_react_app(app_root, "fake-static-site")

            completed = run_helper(project_root, "--app-root", str(app_root))

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("not a React app", completed.stderr)
            self.assertNotIn("app-root:", completed.stdout)

    def test_explicit_app_root_requires_a_non_empty_scripts_dev(self) -> None:
        invalid_packages = {
            "unrelated top-level dev": {
                "name": "fake-account-prototype",
                "dev": "vite",
                "scripts": {"build": "vite build"},
                "dependencies": {"react": "18.3.1"},
            },
            "empty scripts.dev": {
                "name": "fake-account-prototype",
                "scripts": {"dev": ""},
                "dependencies": {"react": "18.3.1"},
            },
            "null scripts.dev": {
                "name": "fake-account-prototype",
                "scripts": {"dev": None},
                "dependencies": {"react": "18.3.1"},
            },
        }

        for label, package in invalid_packages.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as temp_dir:
                    project_root = Path(temp_dir) / "project"
                    app_root = project_root / "designs" / "account"
                    write_package(app_root, package)

                    completed = run_helper(
                        project_root,
                        "--app-root",
                        str(app_root),
                    )

                    self.assertNotEqual(completed.returncode, 0)
                    self.assertIn("must define scripts.dev", completed.stderr)
                    self.assertNotIn("app-root:", completed.stdout)

    def test_explicit_app_root_requires_structurally_valid_package_json(self) -> None:
        invalid_manifests = {
            "malformed JSON": (
                '{"dependencies":{"react":"18.3.1"},'
                '"scripts":{"dev":"vite"'
            ),
            "nested scripts.dev": json.dumps(
                {
                    "dependencies": {"react": "18.3.1"},
                    "scripts": {"tools": {"dev": "vite"}},
                }
            ),
            "unrelated nested react key": json.dumps(
                {
                    "metadata": {"react": "18.3.1"},
                    "scripts": {"dev": "vite"},
                }
            ),
        }

        for label, manifest in invalid_manifests.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as temp_dir:
                    project_root = Path(temp_dir) / "project"
                    app_root = project_root / "designs" / "account"
                    write_raw_package(app_root, manifest)

                    completed = run_helper(
                        project_root,
                        "--app-root",
                        str(app_root),
                    )

                    self.assertNotEqual(completed.returncode, 0)
                    self.assertNotIn("app-root:", completed.stdout)

    def test_locator_does_not_require_a_package_manager(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "project"
            app_root = project_root / "designs" / "account"
            write_react_app(app_root, "fake-account-prototype")

            completed = run_helper(
                project_root,
                "--app-root",
                str(app_root),
                command_path=read_only_command_path(temp_root),
            )

            self.assertEqual(completed.returncode, 0)
            self.assertIn(f"app-root: {app_root.resolve()}", completed.stdout)

    def test_locator_supports_paths_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project with spaces"
            app_root = project_root / "designs" / "account prototype"
            write_react_app(app_root, "fake-account-prototype")

            completed = run_helper(project_root, "--app-root", str(app_root))

            self.assertEqual(completed.returncode, 0)
            self.assertIn(f"app-root: {app_root.resolve()}", completed.stdout)


if __name__ == "__main__":
    unittest.main()
