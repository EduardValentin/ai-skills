from __future__ import annotations

import json
import os
import re
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
FIXTURE_URL = f"file://{FIXTURE}"
FIXTURE_DIR_URL = f"file://{FIXTURE.parent}/"
FIXTURE_DIRECT_CHILDREN = 9
"""h2, p, p (through the wrapper div), button, label, the unparseable-bg div,
button, span, span (through the colors div); the img is a childless wrapper."""
ROOT_LINE = r'\d+ nodes children=9 root=section region "Order summary" [\d.]+x[\d.]+'


def node_path() -> str | None:
    return shutil.which("node")


def base_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key in ALLOWED_ENV_KEYS}


def write_json(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def manifest_row(row_id: str, share: str, viewports: list[str], **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": row_id,
        "mapId": "C1",
        "protoRoute": "fixture.html",
        "realRoute": "fixture.html",
        "protoRoot": "OrderSummary",
        "realRoot": "OrderSummary",
        "viewports": viewports,
        "ignore": {"prototype": [], "real": []},
        "protoActions": None,
        "realActions": None,
        "shareProto": share,
    }
    row.update(overrides)
    return row


def manifest(rows: list[dict[str, object]], viewports: list[str]) -> dict[str, object]:
    return {"prototypeUrl": FIXTURE_DIR_URL, "realUrl": FIXTURE_DIR_URL, "viewports": viewports, "rows": rows}


def summary_lines(stdout: str, side: str) -> list[str]:
    return [line for line in stdout.splitlines() if line.startswith(f"{side} ")]


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


class CaptureParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        if node_path() is None:
            self.skipTest("node is not on PATH")

    def run_in_temp(self, args: list[str], files: dict[str, object] | None = None) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as cwd_dir:
            cwd = Path(cwd_dir)
            for name, data in (files or {}).items():
                write_json(cwd / name, data)
            return run_capture(["--out", str(cwd / "out"), *args], cwd=cwd, env=base_env())

    def test_manifest_with_real_url_exits_two(self) -> None:
        completed = self.run_in_temp(
            ["--manifest", "manifest.json", "--real-url", FIXTURE_URL, "--real-root", "x"],
            files={"manifest.json": manifest([], ["800x600"])},
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(len(completed.stderr.strip().splitlines()), 1)
        self.assertIn("--manifest cannot be combined with --real-url, --real-root", completed.stderr)

    def test_unknown_recipe_step_exits_two_naming_index_and_file(self) -> None:
        completed = self.run_in_temp(
            ["--viewport", "800x600", "--real-url", FIXTURE_URL, "--real-root", "x", "--real-actions", "steps.json"],
            files={"steps.json": [{"hover": "button"}, {"dance": "button"}]},
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("steps.json", completed.stderr)
        self.assertIn("step 1", completed.stderr)
        self.assertIn("dance", completed.stderr)

    def test_header_without_separator_exits_two(self) -> None:
        completed = self.run_in_temp(
            ["--viewport", "800x600", "--real-url", FIXTURE_URL, "--real-root", "x", "--real-header", "Authorization"],
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn('--real-header must be "Name: value"', completed.stderr)

    def test_timeout_zero_exits_two(self) -> None:
        completed = self.run_in_temp(
            ["--viewport", "800x600", "--real-url", FIXTURE_URL, "--real-root", "x", "--timeout", "0"],
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("--timeout must be a positive integer", completed.stderr)

    def test_prototype_actions_without_prototype_url_exits_two(self) -> None:
        completed = self.run_in_temp(
            ["--viewport", "800x600", "--real-url", FIXTURE_URL, "--real-root", "x", "--prototype-actions", "steps.json"],
            files={"steps.json": []},
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("--prototype-actions requires --prototype-url", completed.stderr)


class CaptureBrowserTests(unittest.TestCase):
    def setUp(self) -> None:
        if node_path() is None:
            self.skipTest("node is not on PATH")
        node_path_env = os.environ.get("NODE_PATH")
        if not node_path_env:
            self.skipTest("NODE_PATH is not set; playwright cannot resolve for a real capture")
        self.env = base_env()
        self.env["NODE_PATH"] = node_path_env

    def capture(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        completed = run_capture(args, cwd=support.REPO_ROOT, env=self.env)
        if completed.returncode == 2 and "playwright is not installed" in completed.stderr:
            self.skipTest("playwright does not resolve through this NODE_PATH")
        return completed

    def test_manifest_shares_prototype_and_captures_real_per_row(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            out = Path(work) / "out"
            manifest_path = write_json(
                Path(work) / "manifest.json",
                manifest([manifest_row("R1", "R1", ["800x600"]), manifest_row("R2", "R1", ["800x600"])], ["800x600"]),
            )
            completed = self.capture(["--manifest", str(manifest_path), "--out", str(out)])
            self.assertEqual(completed.returncode, 0, completed.stderr)

            proto_r1 = out / "R1" / "prototype-800x600.json"
            proto_r2 = out / "R2" / "prototype-800x600.json"
            self.assertTrue(proto_r1.exists() and proto_r2.exists(), completed.stdout)
            self.assertEqual(proto_r1.read_bytes(), proto_r2.read_bytes())
            self.assertTrue((out / "R1" / "real-800x600.json").exists())
            self.assertTrue((out / "R2" / "real-800x600.json").exists())

            proto_lines = summary_lines(completed.stdout, "prototype")
            self.assertEqual(len(proto_lines), 2, completed.stdout)
            self.assertRegex(proto_lines[0], rf"^prototype 800x600 {ROOT_LINE} -> {re.escape(str(proto_r1))}$")
            self.assertRegex(proto_lines[1], rf"^prototype 800x600 {ROOT_LINE} \(shared from R1\) -> {re.escape(str(proto_r2))}$")

            real_lines = summary_lines(completed.stdout, "real")
            self.assertEqual(len(real_lines), 2, completed.stdout)
            for row_id, line in zip(["R1", "R2"], real_lines):
                self.assertRegex(line, rf"^real 800x600 {ROOT_LINE} -> {re.escape(str(out / row_id / 'real-800x600.json'))}$")

    def test_manifest_captures_source_prototype_on_demand_for_earlier_rows(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            out = Path(work) / "out"
            manifest_path = write_json(
                Path(work) / "manifest.json",
                manifest([manifest_row("R1", "R2", ["800x600"]), manifest_row("R2", "R2", ["800x600"])], ["800x600"]),
            )
            completed = self.capture(["--manifest", str(manifest_path), "--out", str(out)])
            self.assertEqual(completed.returncode, 0, completed.stderr)
            proto_lines = summary_lines(completed.stdout, "prototype")
            self.assertEqual(len(proto_lines), 2, completed.stdout)
            self.assertTrue(proto_lines[0].endswith(f" -> {out / 'R2' / 'prototype-800x600.json'}"), proto_lines[0])
            self.assertNotIn("(shared", proto_lines[0])
            self.assertTrue(proto_lines[1].endswith(f" (shared from R2) -> {out / 'R1' / 'prototype-800x600.json'}"), proto_lines[1])

    def test_only_viewports_filters_files_and_skips_rows_left_empty(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            out = Path(work) / "out"
            manifest_path = write_json(
                Path(work) / "manifest.json",
                manifest(
                    [manifest_row("R1", "R1", ["800x600", "400x700"]), manifest_row("R3", "R3", ["400x700"])],
                    ["800x600", "400x700"],
                ),
            )
            completed = self.capture(["--manifest", str(manifest_path), "--out", str(out), "--only-viewports", "800x600"])
            self.assertEqual(completed.returncode, 0, completed.stderr)
            written = sorted(str(path.relative_to(out)) for path in out.rglob("*.json"))
            self.assertEqual(written, ["R1/prototype-800x600.json", "R1/real-800x600.json"])
            self.assertEqual(completed.stderr.strip(), "skip R3: no viewports")

    def test_recipe_with_hover_and_wait_runs_against_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            out = Path(work) / "out"
            recipe = write_json(Path(work) / "hover.json", [{"hover": "button"}, {"wait": 50}])
            completed = self.capture(
                [
                    "--real-url", FIXTURE_URL,
                    "--real-root", "OrderSummary",
                    "--real-actions", str(recipe),
                    "--real-header", "X-Parity: 1",
                    "--viewport", "800x600",
                    "--out", str(out),
                ],
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stderr, "")
            self.assertTrue((out / "real-800x600.json").exists())
            self.assertRegex(completed.stdout, rf"^real 800x600 {ROOT_LINE} -> ")

    def test_failing_recipe_step_prints_step_line_and_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            out = Path(work) / "out"
            recipe = write_json(Path(work) / "bad.json", [{"wait": 1}, {"click": "#no-such-element"}])
            completed = self.capture(
                [
                    "--real-url", FIXTURE_URL,
                    "--real-root", "OrderSummary",
                    "--real-actions", str(recipe),
                    "--timeout", "500",
                    "--viewport", "800x600",
                    "--out", str(out),
                ],
            )
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertEqual(len(completed.stderr.strip().splitlines()), 1, completed.stderr)
            self.assertTrue(completed.stderr.startswith("real 800x600 step 1 click: "), completed.stderr)
            self.assertFalse((out / "real-800x600.json").exists())


if __name__ == "__main__":
    unittest.main()
