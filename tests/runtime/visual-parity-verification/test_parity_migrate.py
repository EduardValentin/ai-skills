from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "skills" / "ui-ux" / "visual-parity-verification" / "scripts"))

import support  # noqa: E402
import parity_states  # noqa: E402

MAP_HEADER = "| Id | Prototype component | Real app root | Routes (real → prototype) | States | Viewports | Ignore | Confidence | Notes |"
SEPARATOR = "|---|---|---|---|---|---|---|---|---|"


def map_text(states_cell: str) -> str:
    return "\n".join([
        "# Parity map", "", MAP_HEADER, SEPARATOR,
        f'| C1 | OrderSummary | [data-parity-root="OrderSummary"] | /orders → /orders | {states_cell} | | | confirmed | none |', "",
    ])


class MigrateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.map_path = self.root / "parity-map.md"
        self.actions = self.root / "parity-actions"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def recipe(self, name: str, steps: list) -> None:
        support.write_json(self.actions / name, steps)

    def test_missing_folder_is_an_error(self) -> None:
        self.map_path.write_text(map_text("default"), encoding="utf-8")
        with self.assertRaises(parity_states.StatesError):
            parity_states.migrate_actions(self.map_path)
        self.assertFalse((self.root / "parity-states.json").exists())

    def test_preambles_pairs_and_prefixes_are_converted(self) -> None:
        self.recipe("wait-ready.json", [{"waitFor": "[data-parity=\"x\"]"}, {"wait": 1500}])
        self.recipe("proto-empty.json", [{"waitFor": "#root"}, {"wait": 800}, {"click": "#dev"}, {"click": "#empty"}])
        self.recipe("real-empty.json", [{"waitFor": "#root"}, {"wait": 800}])
        self.recipe("form4.json", [{"waitFor": "#root"}, {"click": "#a"}, {"click": "#b"}, {"click": "#c"}, {"click": "#d"}, {"wait": 500}])
        self.recipe("form5.json", [{"waitFor": "#root"}, {"click": "#a"}, {"click": "#b"}, {"click": "#c"}, {"click": "#d"}, {"click": "#e"}])
        self.map_path.write_text(map_text("ready (wait-ready.json), empty (proto-empty.json), four (form4.json), five (form5.json)"), encoding="utf-8")
        report = parity_states.migrate_actions(self.map_path)
        states = json.loads((self.root / "parity-states.json").read_text())
        self.assertEqual(states["wait-ready"], [])
        self.assertEqual(states["empty"], {"prototype": [{"click": "#dev"}, {"click": "#empty"}], "real": []})
        self.assertEqual(states["form5-4"], [{"click": "#a"}, {"click": "#b"}, {"click": "#c"}, {"click": "#d"}])
        self.assertEqual(states["form4"], [{"use": "form5-4"}])
        self.assertEqual(states["form5"], [{"use": "form5-4"}, {"click": "#e"}])
        rewritten = self.map_path.read_text()
        self.assertIn("ready (wait-ready), empty (empty), four (form4), five (form5)", rewritten)
        self.assertTrue(any("fragment form5-4" in line for line in report), report)
        self.assertTrue(any("state empty" in line and "proto-empty.json + real-empty.json" in line for line in report), report)
        self.assertTrue((self.actions / "form4.json").exists())

    def test_existing_states_file_is_not_overwritten(self) -> None:
        self.recipe("a.json", [{"click": "#a"}])
        support.write_json(self.root / "parity-states.json", {})
        self.map_path.write_text(map_text("a (a.json)"), encoding="utf-8")
        with self.assertRaises(parity_states.StatesError):
            parity_states.migrate_actions(self.map_path)

    def test_cli_runs_and_check_passes_afterwards(self) -> None:
        self.recipe("open.json", [{"click": "#open"}, {"waitFor": "[role=dialog]"}])
        self.map_path.write_text(map_text("open (open.json)"), encoding="utf-8")
        completed = support.run_map("migrate-actions", str(self.map_path))
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        checked = support.run_map("check", str(self.map_path))
        self.assertEqual(checked.returncode, 0, checked.stdout)


if __name__ == "__main__":
    unittest.main()
