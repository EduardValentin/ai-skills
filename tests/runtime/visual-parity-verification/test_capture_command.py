from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import support  # noqa: E402

CAPTURE_SCRIPT = support.SCRIPTS_DIR / "capture-snapshots.mjs"
FIXTURE = Path(__file__).resolve().parent / "browser" / "fixture.html"
ALLOWED_ENV_KEYS = {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ"}


def node_path() -> str | None:
    return shutil.which("node")


def base_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key in ALLOWED_ENV_KEYS}


def run_capture(args: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    node = node_path()
    assert node is not None
    return subprocess.run(
        [node, str(CAPTURE_SCRIPT), *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


class CaptureCommandTests(unittest.TestCase):
    def test_script_passes_node_syntax_check(self) -> None:
        node = node_path()
        if node is None:
            self.skipTest("node is not on PATH")
        completed = subprocess.run([node, "--check", str(CAPTURE_SCRIPT)], capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_missing_playwright_exits_two(self) -> None:
        if node_path() is None:
            self.skipTest("node is not on PATH")
        with tempfile.TemporaryDirectory() as cwd_dir, tempfile.TemporaryDirectory() as empty_node_path, tempfile.TemporaryDirectory() as out_dir:
            env = base_env()
            env["NODE_PATH"] = empty_node_path
            completed = run_capture(
                [
                    "--out", out_dir,
                    "--viewport", "800x600",
                    "--real-url", "file:///dev/null",
                    "--real-root", "x",
                ],
                cwd=Path(cwd_dir),
                env=env,
            )
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("playwright", completed.stderr)

    def test_usage_error_without_any_side_exits_two(self) -> None:
        if node_path() is None:
            self.skipTest("node is not on PATH")
        with tempfile.TemporaryDirectory() as cwd_dir, tempfile.TemporaryDirectory() as out_dir:
            completed = run_capture(
                ["--out", out_dir, "--viewport", "800x600"],
                cwd=Path(cwd_dir),
                env=base_env(),
            )
            self.assertEqual(completed.returncode, 2)

    def test_side_sub_flag_without_its_url_flag_exits_two(self) -> None:
        if node_path() is None:
            self.skipTest("node is not on PATH")
        with tempfile.TemporaryDirectory() as cwd_dir, tempfile.TemporaryDirectory() as out_dir:
            completed = run_capture(
                [
                    "--out", out_dir,
                    "--viewport", "800x600",
                    "--prototype-url", "file:///dev/null",
                    "--prototype-root", "section",
                    "--real-root", "x",
                ],
                cwd=Path(cwd_dir),
                env=base_env(),
            )
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertEqual(len(completed.stderr.strip().splitlines()), 1)
            self.assertIn("--real-root", completed.stderr)

    def test_real_capture_writes_file_and_matches_itself(self) -> None:
        if node_path() is None:
            self.skipTest("node is not on PATH")
        node_path_env = os.environ.get("NODE_PATH")
        if not node_path_env:
            self.skipTest("NODE_PATH is not set; playwright cannot resolve for a real capture")

        env = base_env()
        env["NODE_PATH"] = node_path_env

        with tempfile.TemporaryDirectory() as out_dir:
            completed = run_capture(
                [
                    "--real-url", f"file://{FIXTURE}",
                    "--real-root", "OrderSummary",
                    "--viewport", "800x600",
                    "--out", out_dir,
                ],
                cwd=support.REPO_ROOT,
                env=env,
            )
            if completed.returncode == 2 and "playwright is not installed" in completed.stderr:
                self.skipTest("playwright does not resolve through this NODE_PATH")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(completed.stdout.startswith("real 800x600"), completed.stdout)

            snapshot_path = Path(out_dir) / "real-800x600.json"
            self.assertTrue(snapshot_path.exists())

            diff_out = Path(out_dir) / "diff.json"
            diff_completed = support.run_diff(
                "--prototype", str(snapshot_path),
                "--real", str(snapshot_path),
                "--out", str(diff_out),
            )
            self.assertEqual(diff_completed.returncode, 0, diff_completed.stderr)
            result = support.read_json(diff_out)
            self.assertEqual(result["verdict"], "MATCH")


if __name__ == "__main__":
    unittest.main()
