from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import support  # noqa: E402

HARNESS = Path(__file__).resolve().parent / "browser" / "harness.mjs"
BROWSER_SCRIPTS = ("snapshot-subtree.browser.js", "find-react-roots.browser.js")


def node_path() -> str | None:
    return shutil.which("node")


class BrowserScriptTests(unittest.TestCase):
    def test_scripts_pass_node_syntax_check(self) -> None:
        node = node_path()
        if node is None:
            self.skipTest("node is not on PATH")
        for name in BROWSER_SCRIPTS:
            completed = subprocess.run([node, "--check", str(support.SCRIPTS_DIR / name)], capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, f"{name}: {completed.stderr}")

    def test_scripts_expose_one_global_and_interpolate_nothing(self) -> None:
        for name, symbol in zip(BROWSER_SCRIPTS, ("paritySnapshot", "parityFindReactRoots")):
            text = (support.SCRIPTS_DIR / name).read_text(encoding="utf-8")
            self.assertIn(f"globalThis.{symbol} = {symbol};", text)
            assignments = re.findall(r"globalThis\.\w+\s*=", text)
            self.assertEqual(assignments, [f"globalThis.{symbol} ="], name)

    def test_jsdom_harness_checks_all_pass(self) -> None:
        node = node_path()
        if node is None:
            self.skipTest("node is not on PATH")
        completed = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, check=False, cwd=support.REPO_ROOT)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        if "skipped" in payload:
            self.skipTest(payload["skipped"])
        failed = sorted(name for name, passed in payload["checks"].items() if not passed)
        self.assertEqual(failed, [], json.dumps(payload["details"], indent=2))
