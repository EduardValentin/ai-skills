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

    def test_invalid_json_recipe_is_an_error(self) -> None:
        self.actions.mkdir(parents=True, exist_ok=True)
        (self.actions / "broken.json").write_text("{not json", encoding="utf-8")
        self.map_path.write_text(map_text("broken (broken.json)"), encoding="utf-8")
        with self.assertRaises(parity_states.StatesError) as caught:
            parity_states.migrate_actions(self.map_path)
        self.assertIn("cannot read recipe", str(caught.exception))
        self.assertFalse((self.root / "parity-states.json").exists())
        completed = support.run_map("migrate-actions", str(self.map_path))
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("cannot read recipe", completed.stderr)

    def test_non_list_recipe_is_an_error(self) -> None:
        self.recipe("shape.json", {"click": "#a"})
        self.map_path.write_text(map_text("shape (shape.json)"), encoding="utf-8")
        with self.assertRaises(parity_states.StatesError) as caught:
            parity_states.migrate_actions(self.map_path)
        self.assertIn("recipe must be a JSON array of steps", str(caught.exception))
        self.assertFalse((self.root / "parity-states.json").exists())
        completed = support.run_map("migrate-actions", str(self.map_path))
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("recipe must be a JSON array of steps", completed.stderr)

    def test_bare_recipe_is_base_with_prototype_override(self) -> None:
        self.recipe("proto-zzz.json", [{"click": "#special"}])
        self.recipe("zzz.json", [{"click": "#base"}])
        self.map_path.write_text(map_text("zzz (zzz.json)"), encoding="utf-8")
        report = parity_states.migrate_actions(self.map_path)
        states = json.loads((self.root / "parity-states.json").read_text())
        self.assertEqual(states["zzz"], {"prototype": [{"click": "#special"}], "real": [{"click": "#base"}]})
        self.assertTrue(any("state zzz" in line and "proto-zzz.json" in line and "zzz.json" in line for line in report), report)

    def test_bare_recipe_is_base_with_real_override(self) -> None:
        self.recipe("aaa.json", [{"click": "#base"}])
        self.recipe("real-aaa.json", [{"click": "#special"}])
        self.map_path.write_text(map_text("aaa (aaa.json)"), encoding="utf-8")
        report = parity_states.migrate_actions(self.map_path)
        states = json.loads((self.root / "parity-states.json").read_text())
        self.assertEqual(states["aaa"], {"prototype": [{"click": "#base"}], "real": [{"click": "#special"}]})
        self.assertTrue(any("state aaa" in line and "aaa.json" in line and "real-aaa.json" in line for line in report), report)

    def test_fragment_name_collision_avoids_clobbering_existing_state(self) -> None:
        self.recipe("a.json", [{"click": "#1"}, {"click": "#2"}, {"click": "#3"}, {"click": "#a"}])
        self.recipe("b.json", [{"click": "#1"}, {"click": "#2"}, {"click": "#3"}, {"click": "#b"}])
        self.recipe("a-3.json", [{"click": "#keep"}])
        self.map_path.write_text(map_text("a (a.json), b (b.json), existing (a-3.json)"), encoding="utf-8")
        report = parity_states.migrate_actions(self.map_path)
        states = json.loads((self.root / "parity-states.json").read_text())
        self.assertEqual(states["a-3"], [{"click": "#keep"}])
        self.assertEqual(states["a-3-2"], [{"click": "#1"}, {"click": "#2"}, {"click": "#3"}])
        self.assertEqual(states["a"], [{"use": "a-3-2"}, {"click": "#a"}])
        self.assertEqual(states["b"], [{"use": "a-3-2"}, {"click": "#b"}])
        self.assertTrue(any("a-3-2" in line and "a-3" in line for line in report), report)

    def test_three_recipes_consolidate_into_one_fragment(self) -> None:
        shared = [{"click": "#1"}, {"click": "#2"}, {"click": "#3"}]
        self.recipe("a.json", shared + [{"click": "#a"}])
        self.recipe("b.json", shared + [{"click": "#b"}])
        self.recipe("c.json", shared + [{"click": "#c"}])
        self.map_path.write_text(map_text("a (a.json), b (b.json), c (c.json)"), encoding="utf-8")
        report = parity_states.migrate_actions(self.map_path)
        states = json.loads((self.root / "parity-states.json").read_text())
        fragment_lines = [line for line in report if line.startswith("fragment ")]
        self.assertEqual(len(fragment_lines), 1, report)
        for name, suffix in (("a", "#a"), ("b", "#b"), ("c", "#c")):
            self.assertEqual(len(states[name]), 2)
            self.assertIn("use", states[name][0])
            self.assertEqual(states[name][1], {"click": suffix})
            resolved = parity_states.state_sides(states, name)
            self.assertEqual(resolved["prototype"], shared + [{"click": suffix}])

    def test_strip_readiness_takes_one_waitfor_then_one_wait(self) -> None:
        self.assertEqual(
            parity_states.strip_readiness([{"waitFor": "#a"}, {"waitFor": "#b"}, {"click": "#c"}, {"wait": 100}]),
            [{"waitFor": "#b"}, {"click": "#c"}],
        )
        self.assertEqual(parity_states.strip_readiness([{"wait": 500}, {"click": "#c"}]), [{"click": "#c"}])

    def test_references_are_rewritten_only_in_the_states_cell(self) -> None:
        self.recipe("open.json", [{"click": "#a"}])
        row = '| C1 | OrderSummary | [data-parity-root="OrderSummary"] | /orders → /orders | open (open.json) | | | confirmed | see (foo.json) |'
        self.map_path.write_text("\n".join(["# Parity map", "", MAP_HEADER, SEPARATOR, row, ""]), encoding="utf-8")
        report = parity_states.migrate_actions(self.map_path)
        rewritten = self.map_path.read_text()
        self.assertIn("| open (open) | | | confirmed | see (foo.json) |", rewritten)
        self.assertTrue(any(line.startswith("rewrote 1 references") for line in report), report)


if __name__ == "__main__":
    unittest.main()
