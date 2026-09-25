from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import support  # noqa: E402

MAP_SCRIPT = support.SCRIPTS_DIR / "parity_map.py"

MAP_HEADER = "| Id | Prototype component | Real app root | Routes (real → prototype) | States | Viewports | Ignore | Confidence | Notes |"
SEPARATOR = "|---|---|---|---|---|---|---|---|---|"

ROW_C1 = '| C1 | OrderSummary | [data-parity-root="OrderSummary"] | /orders → /orders | default, empty, hover (order-hover.json) | | proto:hook:beta; real:path:section > div:nth-of-type(2) | confirmed | Two roots share the summary |'
ROW_C2 = "| C2 | root:main.checkout | main.checkout | /checkout -> /proto/checkout | default | 375x667, 1440x900 | | obvious | none |"
ROW_C3 = "| C3 | OrderSummary | aside.legacy-summary | /orders-legacy → /orders | default | | | confirmed | none |"

LEDGER_HEAD = """# Parity ledger

Session: GEN-123
Parity map: parity-map.md (committed at the project root)
Viewport set: 375, 1440
Theme: light

## Elements

| Id | Map id | Route | State | Prototype root | Real app root | Change | Verdict | Evidence |
|---|---|---|---|---|---|---|---|---|
"""

LEDGER_TAIL = """
## Design changes

| Id | What changed | Changed first in | Prototype updated | Production updated | Ledger rows |
|---|---|---|---|---|---|
"""


def map_text(*rows: str, header: str = MAP_HEADER) -> str:
    return "# Parity map\n\nOne row per root pair.\n\n" + "\n".join([header, SEPARATOR, *rows]) + "\n"


def ledger_text(*rows: str) -> str:
    return LEDGER_HEAD + "\n".join(rows) + "\n" + LEDGER_TAIL


def ledger_row(row_id: str, map_id: str, route: str, state: str) -> str:
    return f"| {row_id} | {map_id} | {route} | {state} | OrderSummary | [data-parity-root=\"OrderSummary\"] | modified | PENDING | |"


def run_map(*arguments: str):
    return support._run(MAP_SCRIPT, *arguments)


class ParityMapCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.map_path = self.root / "parity-map.md"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_map(self, *rows: str, header: str = MAP_HEADER) -> Path:
        self.map_path.write_text(map_text(*rows, header=header), encoding="utf-8")
        return self.map_path

    def write_ledger(self, *rows: str) -> Path:
        ledger = self.root / "ledger.md"
        ledger.write_text(ledger_text(*rows), encoding="utf-8")
        return ledger

    def write_recipe(self, name: str) -> Path:
        return support.write_json(self.root / "parity-actions" / name, [{"hover": "button"}])


class CheckTests(ParityMapCase):
    def test_valid_map_passes_silently(self) -> None:
        completed = run_map("check", str(self.write_map(ROW_C1, ROW_C2, ROW_C3)))
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_header_mismatch_prints_expected_and_found(self) -> None:
        old_header = "| Id | Prototype component | Real app root | Routes (real → prototype) | States | Pairing confidence | Notes |"
        completed = run_map("check", str(self.write_map(ROW_C1, header=old_header)))
        self.assertEqual(completed.returncode, 1)
        self.assertIn(MAP_HEADER, completed.stdout)
        self.assertIn(old_header, completed.stdout)

    def test_duplicate_id_fails(self) -> None:
        completed = run_map("check", str(self.write_map(ROW_C1, ROW_C1)))
        self.assertEqual(completed.returncode, 1)
        self.assertIn('row C1: Id "C1" is already used', completed.stdout)

    def test_ids_must_increase_down_the_table(self) -> None:
        completed = run_map("check", str(self.write_map(ROW_C2, ROW_C1)))
        self.assertEqual(completed.returncode, 1)
        self.assertIn('row C1: Id "C1" must be greater than "C2"', completed.stdout)

    def test_id_must_be_c_number(self) -> None:
        completed = run_map("check", str(self.write_map(ROW_C1.replace("| C1 |", "| X1 |"))))
        self.assertEqual(completed.returncode, 1)
        self.assertIn('row X1: Id "X1" is not C<n>', completed.stdout)

    def test_missing_routes_arrow_fails(self) -> None:
        completed = run_map("check", str(self.write_map(ROW_C1.replace("/orders → /orders", "/orders /orders"))))
        self.assertEqual(completed.returncode, 1)
        self.assertIn('row C1: Routes "/orders /orders" is not <real> → <prototype>', completed.stdout)

    def test_bad_viewport_fails(self) -> None:
        completed = run_map("check", str(self.write_map(ROW_C2.replace("375x667, 1440x900", "800x"))))
        self.assertEqual(completed.returncode, 1)
        self.assertIn('row C2: Viewports "800x" is not WxH', completed.stdout)

    def test_bad_ignore_entry_fails(self) -> None:
        completed = run_map("check", str(self.write_map(ROW_C1.replace("proto:hook:beta", "hook:beta"))))
        self.assertEqual(completed.returncode, 1)
        self.assertIn('row C1: Ignore "hook:beta" is not proto:|real: followed by hook:<value>|path:<prefix>', completed.stdout)

    def test_unknown_confidence_fails(self) -> None:
        completed = run_map("check", str(self.write_map(ROW_C1.replace("| confirmed |", "| maybe |"))))
        self.assertEqual(completed.returncode, 1)
        self.assertIn('row C1: Confidence "maybe" is not obvious or confirmed', completed.stdout)

    def test_duplicate_state_name_fails(self) -> None:
        completed = run_map("check", str(self.write_map(ROW_C1.replace("default, empty", "default, default"))))
        self.assertEqual(completed.returncode, 1)
        self.assertIn('row C1: States name "default" is listed twice', completed.stdout)

    def test_empty_states_fails(self) -> None:
        completed = run_map("check", str(self.write_map(ROW_C2.replace("| default |", "|  |"))))
        self.assertEqual(completed.returncode, 1)
        self.assertIn("row C2: States is empty", completed.stdout)

    def test_wrong_cell_count_fails(self) -> None:
        completed = run_map("check", str(self.write_map(ROW_C2[:-len(" none |")] + "|")))
        self.assertEqual(completed.returncode, 1)
        self.assertIn("row C2: expected 9 cells, found 8", completed.stdout)

    def test_missing_action_file_fails_under_project_root(self) -> None:
        completed = run_map("check", str(self.write_map(ROW_C1)), "--project-root", str(self.root))
        self.assertEqual(completed.returncode, 1)
        self.assertIn('row C1: States "hover (order-hover.json)" names a missing file parity-actions/order-hover.json', completed.stdout)

    def test_present_action_file_passes_under_project_root(self) -> None:
        self.write_recipe("order-hover.json")
        completed = run_map("check", str(self.write_map(ROW_C1)), "--project-root", str(self.root))
        self.assertEqual(completed.returncode, 0, completed.stdout)

    def test_every_problem_is_listed_on_its_own_line(self) -> None:
        broken = ROW_C1.replace("| confirmed |", "| maybe |").replace("proto:hook:beta", "hook:beta")
        completed = run_map("check", str(self.write_map(broken)))
        lines = completed.stdout.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(line.startswith(f"{self.map_path}: row C1: ") for line in lines), lines)

    def test_missing_map_file_fails(self) -> None:
        completed = run_map("check", str(self.root / "absent.md"))
        self.assertEqual(completed.returncode, 1)
        self.assertIn("absent.md", completed.stdout + completed.stderr)


class RowTests(ParityMapCase):
    def test_row_parses_states_viewports_and_both_ignore_sides(self) -> None:
        completed = run_map("row", str(self.write_map(ROW_C1, ROW_C2)), "C1")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        row = json.loads(completed.stdout)
        self.assertEqual(row, {
            "id": "C1",
            "protoComponent": "OrderSummary",
            "realRoot": '[data-parity-root="OrderSummary"]',
            "protoRoute": "/orders",
            "realRoute": "/orders",
            "states": [
                {"name": "default", "actions": None},
                {"name": "empty", "actions": None},
                {"name": "hover", "actions": "order-hover.json"},
            ],
            "viewports": [],
            "ignore": {"prototype": ["hook:beta"], "real": ["path:section > div:nth-of-type(2)"]},
            "confidence": "confirmed",
            "notes": "Two roots share the summary",
        })

    def test_row_with_selector_prototype_emits_proto_root_and_viewport_subset(self) -> None:
        completed = run_map("row", str(self.write_map(ROW_C1, ROW_C2)), "C2")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        row = json.loads(completed.stdout)
        self.assertNotIn("protoComponent", row)
        self.assertEqual(row["protoRoot"], "main.checkout")
        self.assertEqual(row["realRoot"], "main.checkout")
        self.assertEqual((row["realRoute"], row["protoRoute"]), ("/checkout", "/proto/checkout"))
        self.assertEqual(row["viewports"], ["375x667", "1440x900"])
        self.assertEqual(row["ignore"], {"prototype": [], "real": []})
        self.assertEqual(row["confidence"], "obvious")

    def test_unknown_id_exits_one(self) -> None:
        completed = run_map("row", str(self.write_map(ROW_C1)), "C9")
        self.assertEqual(completed.returncode, 1)
        self.assertIn("C9", completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_row_on_an_invalid_map_reports_the_check_problems(self) -> None:
        completed = run_map("row", str(self.write_map(ROW_C1.replace("| confirmed |", "| maybe |"))), "C1")
        self.assertEqual(completed.returncode, 1)
        self.assertIn('Confidence "maybe"', completed.stdout + completed.stderr)


class ManifestTests(ParityMapCase):
    def manifest(self, ledger: Path, *extra: str, map_path: Path | None = None):
        out = self.root / "manifest.json"
        completed = run_map(
            "manifest", str(map_path or self.map_path),
            "--ledger", str(ledger),
            "--prototype-url", "http://localhost:5173",
            "--real-url", "http://localhost:8000",
            "--viewports", "375x667,1024x768,1440x900",
            "--out", str(out),
            *extra,
        )
        return completed, out

    def test_manifest_top_level_and_row_shape(self) -> None:
        self.write_map(ROW_C1, ROW_C2, ROW_C3)
        ledger = self.write_ledger(ledger_row("L1", "C1", "/orders", "default"))
        completed, out = self.manifest(ledger)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        manifest = support.read_json(out)
        self.assertEqual(manifest["prototypeUrl"], "http://localhost:5173")
        self.assertEqual(manifest["realUrl"], "http://localhost:8000")
        self.assertEqual(manifest["viewports"], ["375x667", "1024x768", "1440x900"])
        self.assertEqual(manifest["rows"], [{
            "id": "L1",
            "mapId": "C1",
            "protoRoute": "/orders",
            "realRoute": "/orders",
            "protoComponent": "OrderSummary",
            "realRoot": '[data-parity-root="OrderSummary"]',
            "viewports": ["375x667", "1024x768", "1440x900"],
            "ignore": {"prototype": ["hook:beta"], "real": ["path:section > div:nth-of-type(2)"]},
            "protoActions": None,
            "realActions": None,
            "shareProto": "L1",
        }])

    def test_prototype_is_shared_by_route_component_and_actions(self) -> None:
        self.write_recipe("order-hover.json")
        self.write_map(ROW_C1, ROW_C2, ROW_C3)
        ledger = self.write_ledger(
            ledger_row("L1", "C1", "/orders", "default"),
            ledger_row("L2", "C3", "/orders-legacy", "default"),
            ledger_row("L3", "C1", "/orders", "hover"),
            ledger_row("L4", "C2", "/checkout", "default"),
            ledger_row("L5", "C1", "/orders", "empty"),
        )
        completed, out = self.manifest(ledger, "--project-root", str(self.root))
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        rows = {row["id"]: row for row in support.read_json(out)["rows"]}
        self.assertEqual(rows["L1"]["shareProto"], "L1")
        self.assertEqual(rows["L2"]["shareProto"], "L1")
        self.assertEqual(rows["L3"]["shareProto"], "L3")
        self.assertEqual(rows["L4"]["shareProto"], "L4")
        self.assertEqual(rows["L5"]["shareProto"], "L1")
        recipe = str(self.root / "parity-actions" / "order-hover.json")
        self.assertEqual((rows["L3"]["protoActions"], rows["L3"]["realActions"]), (recipe, recipe))
        self.assertEqual(rows["L2"]["realRoot"], "aside.legacy-summary")

    def test_actions_path_defaults_to_the_map_directory(self) -> None:
        self.write_map(ROW_C1)
        ledger = self.write_ledger(ledger_row("L1", "C1", "/orders", "hover"))
        completed, out = self.manifest(ledger)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        row = support.read_json(out)["rows"][0]
        self.assertEqual(row["protoActions"], str(self.root / "parity-actions" / "order-hover.json"))

    def test_selector_prototype_row_emits_proto_root_and_its_viewport_subset(self) -> None:
        self.write_map(ROW_C1, ROW_C2)
        ledger = self.write_ledger(ledger_row("L1", "C2", "/checkout", "default"))
        completed, out = self.manifest(ledger)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        row = support.read_json(out)["rows"][0]
        self.assertNotIn("protoComponent", row)
        self.assertEqual(row["protoRoot"], "main.checkout")
        self.assertEqual(row["viewports"], ["375x667", "1440x900"])

    def test_only_viewports_intersects_each_row(self) -> None:
        self.write_map(ROW_C1, ROW_C2)
        ledger = self.write_ledger(
            ledger_row("L1", "C1", "/orders", "default"),
            ledger_row("L2", "C2", "/checkout", "default"),
        )
        completed, out = self.manifest(ledger, "--only-viewports", "1024x768,1440x900")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        rows = {row["id"]: row for row in support.read_json(out)["rows"]}
        self.assertEqual(rows["L1"]["viewports"], ["1024x768", "1440x900"])
        self.assertEqual(rows["L2"]["viewports"], ["1440x900"])
        self.assertEqual(support.read_json(out)["viewports"], ["375x667", "1024x768", "1440x900"])

    def test_row_left_without_viewports_is_kept_and_warned(self) -> None:
        self.write_map(ROW_C1, ROW_C2)
        ledger = self.write_ledger(ledger_row("L1", "C2", "/checkout", "default"))
        completed, out = self.manifest(ledger, "--only-viewports", "1024x768")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(support.read_json(out)["rows"][0]["viewports"], [])
        self.assertIn("L1", completed.stderr)
        self.assertIn("no viewports", completed.stderr)

    def test_missing_map_id_exits_one(self) -> None:
        self.write_map(ROW_C1)
        ledger = self.write_ledger(ledger_row("L1", "C7", "/orders", "default"))
        completed, out = self.manifest(ledger)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("ledger row L1: map id C7 is not in", completed.stderr)
        self.assertFalse(out.exists())

    def test_unknown_state_exits_one(self) -> None:
        self.write_map(ROW_C1)
        ledger = self.write_ledger(ledger_row("L1", "C1", "/orders", "focused"))
        completed, out = self.manifest(ledger)
        self.assertEqual(completed.returncode, 1)
        self.assertIn('ledger row L1: state "focused" is not in map row C1 States', completed.stderr)
        self.assertFalse(out.exists())

    def test_route_mismatch_warns_but_uses_the_map_route(self) -> None:
        self.write_map(ROW_C1)
        ledger = self.write_ledger(ledger_row("L1", "C1", "/orders?tab=open", "default"))
        completed, out = self.manifest(ledger)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("ledger row L1: route /orders?tab=open differs from map row C1 real route /orders", completed.stderr)
        self.assertEqual(support.read_json(out)["rows"][0]["realRoute"], "/orders")

    def test_non_pending_rows_are_included(self) -> None:
        self.write_map(ROW_C1)
        ledger = self.write_ledger(ledger_row("L1", "C1", "/orders", "default").replace("| PENDING |", "| MATCH |"))
        completed, out = self.manifest(ledger)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual([row["id"] for row in support.read_json(out)["rows"]], ["L1"])

    def test_manifest_runs_check_first(self) -> None:
        self.write_map(ROW_C1.replace("| confirmed |", "| maybe |"))
        ledger = self.write_ledger(ledger_row("L1", "C1", "/orders", "default"))
        completed, out = self.manifest(ledger)
        self.assertEqual(completed.returncode, 1)
        self.assertIn('row C1: Confidence "maybe" is not obvious or confirmed', completed.stdout)
        self.assertFalse(out.exists())

    def test_missing_action_file_fails_manifest_under_project_root(self) -> None:
        self.write_map(ROW_C1)
        ledger = self.write_ledger(ledger_row("L1", "C1", "/orders", "default"))
        completed, out = self.manifest(ledger, "--project-root", str(self.root))
        self.assertEqual(completed.returncode, 1)
        self.assertIn("names a missing file parity-actions/order-hover.json", completed.stdout)
        self.assertFalse(out.exists())

    def test_bad_viewports_flag_exits_two(self) -> None:
        self.write_map(ROW_C1)
        ledger = self.write_ledger(ledger_row("L1", "C1", "/orders", "default"))
        completed, _ = self.manifest(ledger, "--only-viewports", "wide")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("wide", completed.stderr)


if __name__ == "__main__":
    unittest.main()
