from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "skills" / "ui-ux" / "visual-parity-verification" / "scripts"))

import support  # noqa: E402
from parity_diff import alignment, comparison, findings, loading  # noqa: E402

DIFF_SCRIPT = support.DIFF_SCRIPT

MODULE_NAMES = {
    loading: (
        "InputError", "load_snapshot", "load_optional_json",
        "decode_gzip_base64_snapshot", "normalize_geometry", "inflate_styles",
        "parse_ignore_entry", "prune_ignored",
    ),
    alignment: (
        "collapse_wrappers", "child_signature", "role_name_key", "text_key", "hook_key", "unique_keys",
        "role_name_signal", "text_signal", "signature_signal", "geometry_signal", "fingerprint_signal",
        "anchor_pass", "fill_pass", "moved_pass", "apply_global_pairings",
        "align_trees", "make_pair", "needs_review",
    ),
    comparison: ("DEFAULT_TOLERANCES", "normalize_color", "values_equal", "compare_pair"),
    findings: (
        "content_exclusions", "siblings_of", "collect_findings",
        "accessibility_findings", "verdict_for", "review_lines", "hook_suggestions",
    ),
}


class ModuleContractTests(unittest.TestCase):
    def test_each_module_exposes_its_listed_names(self) -> None:
        for module, names in MODULE_NAMES.items():
            for name in names:
                self.assertTrue(hasattr(module, name), f"{module.__name__} is missing {name}")


class CliBoundaryTests(unittest.TestCase):
    def test_cli_imports_only_stdlib_and_parity_diff(self) -> None:
        tree = ast.parse(DIFF_SCRIPT.read_text(encoding="utf-8"), filename=str(DIFF_SCRIPT))
        stdlib = set(sys.stdlib_module_names)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    self.assertIn(root, stdlib, f"unexpected import: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module == "__future__":
                    continue
                root = (node.module or "").split(".")[0]
                self.assertIn(root, stdlib | {"parity_diff"}, f"unexpected import: {node.module}")

    def test_cli_stays_under_two_hundred_lines(self) -> None:
        line_count = len(DIFF_SCRIPT.read_text(encoding="utf-8").splitlines())
        self.assertLess(line_count, 200)

    def test_cli_run_writes_no_bytecode_into_the_skill(self) -> None:
        package_cache = support.SCRIPTS_DIR / "parity_diff" / "__pycache__"
        shutil.rmtree(package_cache, ignore_errors=True)
        with tempfile.TemporaryDirectory() as folder:
            root = support.node("section", role="region", name="Orders", width=640, height=400)
            for side in ("prototype", "real"):
                (Path(folder) / f"{side}.json").write_text(json.dumps(support.snapshot(root)), encoding="utf-8")
            env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ"}}
            completed = subprocess.run(
                [str(DIFF_SCRIPT), "--prototype", f"{folder}/prototype.json", "--real", f"{folder}/real.json", "--out", f"{folder}/diff.json"],
                cwd=folder, env=env, capture_output=True, text=True, check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(package_cache.exists(), "the CLI must not write bytecode into the skill folder")
