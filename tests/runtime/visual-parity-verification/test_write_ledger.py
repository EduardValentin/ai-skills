from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import support  # noqa: E402

LEDGER = """# Parity ledger

Session: GEN-123
Component map: component-map.md
Viewport set: 375, 767, 768, 1023, 1024, 1440
Theme: light

## Elements

| Id | Map id | Route | State | Prototype root | Real app root | Change | Verdict | Evidence |
|---|---|---|---|---|---|---|---|---|
| L1 | C1 | /orders | default | OrderSummary | [data-parity-root="OrderSummary"] | modified | PENDING | |
| L2 | C1 | /orders | empty | OrderSummary | [data-parity-root="OrderSummary"] | modified | PENDING | |

## Design changes

| Id | What changed | Changed first in | Prototype updated | Production updated | Ledger rows |
|---|---|---|---|---|---|
| D1 | none | prototype | yes | yes | L1 |
"""


def diff_result(verdict, style=(), missing=(), blocked=None, lowest=None):
    return {
        "verdict": verdict,
        "conditions": {"viewport": {"width": 1440, "height": 900}, "devicePixelRatio": 1, "zoom": 1, "colorScheme": "light"},
        "urls": {"prototype": "http://localhost:5173/orders", "real": "http://localhost:8000/orders"},
        "rootSummaries": {},
        "blocked": blocked,
        "pairs": [],
        "findings": {"style": list(style), "geometry": [], "missing": list(missing), "structure": [], "content": [], "accessibility": []},
        "collapsed": {"prototype": [], "real": []},
        "suggestions": [],
        "lowestScore": lowest,
    }


class WriteLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = self.root / "ledger.md"
        self.ledger.write_text(LEDGER, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_diff(self, name, result):
        return support.write_json(self.root / "diffs" / name, result)

    def rows(self):
        return [line for line in self.ledger.read_text(encoding="utf-8").splitlines() if line.startswith("| L")]

    def test_match_writes_verdict_and_conditions_only_into_row(self) -> None:
        diff = self.write_diff("L1-1440x900.json", diff_result("MATCH"))
        completed = support.run_ledger("--ledger", str(self.ledger), "--row", "L1", "--diff", str(diff))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        l1, l2 = self.rows()
        self.assertIn("| MATCH |", l1)
        self.assertIn("1440x900: MATCH", l1)
        self.assertIn("diffs/L1-1440x900.json", l1)
        self.assertEqual(l2, "| L2 | C1 | /orders | empty | OrderSummary | [data-parity-root=\"OrderSummary\"] | modified | PENDING | |")

    def test_everything_outside_the_two_cells_is_byte_identical(self) -> None:
        diff = self.write_diff("L1-1440x900.json", diff_result("MATCH"))
        support.run_ledger("--ledger", str(self.ledger), "--row", "L1", "--diff", str(diff))
        before = LEDGER.splitlines()
        after = self.ledger.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(before), len(after))
        for old, new in zip(before, after):
            if old.startswith("| L1 "):
                self.assertEqual(old.split("|")[:8], new.split("|")[:8])
            else:
                self.assertEqual(old, new)

    def test_worst_verdict_across_viewports_wins(self) -> None:
        match = self.write_diff("L1-1440x900.json", diff_result("MATCH"))
        drift = self.write_diff("L1-375x800.json", diff_result("DRIFT", style=[{"path": "section > p:nth-of-type(1)", "realPath": "section > p:nth-of-type(1)", "property": "fontSize", "prototype": "16px", "real": "14px"}], lowest=0.61))
        drift_result = support.read_json(drift)
        drift_result["conditions"]["viewport"] = {"width": 375, "height": 800}
        support.write_json(drift, drift_result)
        support.run_ledger("--ledger", str(self.ledger), "--row", "L1", "--diff", str(match), "--diff", str(drift))
        l1 = self.rows()[0]
        self.assertIn("| DRIFT |", l1)
        self.assertIn("375x800: DRIFT style=1", l1)
        self.assertIn("section > p:nth-of-type(1) fontSize: 16px vs 14px", l1)

    def test_pipes_in_evidence_are_escaped(self) -> None:
        drift = self.write_diff("L1-1440x900.json", diff_result("DRIFT", style=[{"path": "section > p:nth-of-type(1)", "realPath": "x", "property": "fontFamily", "prototype": "A | B", "real": "C"}]))
        support.run_ledger("--ledger", str(self.ledger), "--row", "L1", "--diff", str(drift))
        l1 = self.rows()[0]
        self.assertIn("A \\| B", l1)
        self.assertEqual(l1.count(" | "), 8)

    def test_blocked_and_missing_ordering(self) -> None:
        missing = self.write_diff("L1-1440x900.json", diff_result("MISSING", missing=[{"side": "real", "path": "section > img:nth-of-type(1)", "tag": "img", "role": "img", "name": "Logo", "suggestion": None}]))
        blocked = self.write_diff("L1-375x800.json", diff_result("BLOCKED", blocked={"reason": "unmeasurable-contrast", "detail": [{"side": "real", "path": "section > p:nth-of-type(1)"}]}))
        support.run_ledger("--ledger", str(self.ledger), "--row", "L1", "--diff", str(missing), "--diff", str(blocked))
        l1 = self.rows()[0]
        self.assertIn("| BLOCKED |", l1)
        self.assertIn("unmeasurable-contrast", l1)
        self.assertIn("missing real section > img:nth-of-type(1)", l1)

    def test_missing_row_refuses_without_writing(self) -> None:
        diff = self.write_diff("L9-1440x900.json", diff_result("MATCH"))
        completed = support.run_ledger("--ledger", str(self.ledger), "--row", "L9", "--diff", str(diff))
        self.assertEqual(completed.returncode, 1)
        self.assertIn("L9", completed.stderr)
        self.assertEqual(self.ledger.read_text(encoding="utf-8"), LEDGER)

    def test_header_mismatch_refuses(self) -> None:
        self.ledger.write_text(LEDGER.replace("| Prototype root |", "| Prototype selector |"), encoding="utf-8")
        diff = self.write_diff("L1-1440x900.json", diff_result("MATCH"))
        completed = support.run_ledger("--ledger", str(self.ledger), "--row", "L1", "--diff", str(diff))
        self.assertEqual(completed.returncode, 1)
        self.assertIn("header", completed.stderr)

    def test_missing_ledger_file_refuses_cleanly(self) -> None:
        missing_ledger = self.root / "does-not-exist.md"
        diff = self.write_diff("L1-1440x900.json", diff_result("MATCH"))
        completed = support.run_ledger("--ledger", str(missing_ledger), "--row", "L1", "--diff", str(diff))
        self.assertEqual(completed.returncode, 1)
        self.assertIn(str(missing_ledger), completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)


class AppendGapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.temp.name) / "ledger.md"
        self.ledger.write_text(LEDGER, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_appends_pending_row_with_next_id(self) -> None:
        completed = support.run_ledger(
            "--ledger", str(self.ledger), "--append-gap", "--map-id", "C1", "--route", "/orders",
            "--state", "default", "--prototype-root", "OrderTotals", "--real-root", "#order-totals",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "L3")
        lines = self.ledger.read_text(encoding="utf-8").splitlines()
        row = next(line for line in lines if line.startswith("| L3 "))
        self.assertEqual(row, "| L3 | C1 | /orders | default | OrderTotals | #order-totals | provenance gap | PENDING |  |")
        index = lines.index(row)
        self.assertTrue(lines[index - 1].startswith("| L2 "))
        self.assertEqual(lines[index + 1], "")

    def test_append_changes_nothing_else(self) -> None:
        support.run_ledger(
            "--ledger", str(self.ledger), "--append-gap", "--map-id", "C1", "--route", "/orders",
            "--state", "default", "--prototype-root", "OrderTotals", "--real-root", "#order-totals",
        )
        after = self.ledger.read_text(encoding="utf-8").splitlines()
        before = LEDGER.splitlines()
        self.assertEqual([l for l in after if not l.startswith("| L3 ")], before)

    def test_append_requires_every_field(self) -> None:
        completed = support.run_ledger("--ledger", str(self.ledger), "--append-gap", "--map-id", "C1")
        self.assertEqual(completed.returncode, 1)
        self.assertIn("--route", completed.stderr)
