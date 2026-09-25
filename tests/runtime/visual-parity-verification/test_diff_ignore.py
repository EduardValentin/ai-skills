from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "skills" / "ui-ux" / "visual-parity-verification" / "scripts"))

import support  # noqa: E402
import diff_snapshots  # noqa: E402
from parity_diff import loading  # noqa: E402

GOOD_CONTRAST = {"ratio": 12.6, "needsAnalyzer": False, "largeText": False}


def heading() -> dict:
    return support.node("h2", role="heading", name="Orders", own_text="Orders", contrast=GOOD_CONTRAST)


def body() -> dict:
    return support.node("p", own_text="Body", y=40, contrast=GOOD_CONTRAST)


def badge(text: str = "New", **overrides) -> dict:
    return support.node("span", hook="badge", own_text=text, x=200, width=40, contrast=GOOD_CONTRAST, **overrides)


def parsed(*entries: str) -> list[dict]:
    return [loading.parse_ignore_entry(entry) for entry in entries]


def compare(proto_children, real_children, ignore=None):
    proto = support.snapshot(support.node("section", role="region", name="Orders", width=640, height=400, children=proto_children))
    real = support.snapshot(support.node("section", role="region", name="Orders", width=640, height=400, children=real_children))
    return diff_snapshots.compare_snapshots(proto, real, {}, {}, ignore or {})


class ParseIgnoreEntryTests(unittest.TestCase):
    def test_hook_entry(self) -> None:
        self.assertEqual(loading.parse_ignore_entry("hook:badge"), {"kind": "hook", "value": "badge", "entry": "hook:badge"})

    def test_path_entry_keeps_the_whole_prefix(self) -> None:
        entry = loading.parse_ignore_entry("path:section > div:nth-of-type(1)")
        self.assertEqual(entry, {"kind": "path", "value": "section > div:nth-of-type(1)", "entry": "path:section > div:nth-of-type(1)"})

    def test_unknown_kind_is_an_input_error_naming_the_entry(self) -> None:
        with self.assertRaises(loading.InputError) as raised:
            loading.parse_ignore_entry("foo:bar")
        self.assertIn("foo:bar", str(raised.exception))

    def test_missing_separator_or_empty_value_is_an_input_error(self) -> None:
        for entry in ("badge", "hook:", "path:"):
            with self.subTest(entry=entry), self.assertRaises(loading.InputError):
                loading.parse_ignore_entry(entry)


class PruneIgnoredTests(unittest.TestCase):
    def test_hook_entry_removes_the_matching_subtree(self) -> None:
        root = support.assign_paths(support.node("section", children=[
            heading(),
            support.node("div", hook="badge", children=[support.node("span", own_text="New")]),
            body(),
        ]))
        ignored = loading.prune_ignored(root, parsed("hook:badge"), "prototype")
        self.assertEqual([child["tag"] for child in root["children"]], ["h2", "p"])
        self.assertEqual(ignored, [{"side": "prototype", "path": "section > div:nth-of-type(1)", "entry": "hook:badge"}])

    def test_path_prefix_matches_whole_segments_only(self) -> None:
        spans = [support.node("span", own_text=str(index), children=[support.node("b", own_text="x")]) for index in range(10)]
        root = support.assign_paths(support.node("section", children=spans))
        ignored = loading.prune_ignored(root, parsed("path:section > span:nth-of-type(1)"), "real")
        remaining = [child["path"] for child in root["children"]]
        self.assertNotIn("section > span:nth-of-type(1)", remaining)
        self.assertIn("section > span:nth-of-type(10)", remaining)
        self.assertEqual(len(remaining), 9)
        self.assertEqual(ignored, [{"side": "real", "path": "section > span:nth-of-type(1)", "entry": "path:section > span:nth-of-type(1)"}])

    def test_path_prefix_removes_descendants_by_removing_their_ancestor(self) -> None:
        root = support.assign_paths(support.node("section", children=[
            support.node("div", children=[support.node("span", own_text="inner"), support.node("span", own_text="other")]),
        ]))
        ignored = loading.prune_ignored(root, parsed("path:section > div:nth-of-type(1) > span:nth-of-type(1)"), "prototype")
        self.assertEqual([child["ownText"] for child in root["children"][0]["children"]], ["other"])
        self.assertEqual([item["path"] for item in ignored], ["section > div:nth-of-type(1) > span:nth-of-type(1)"])

    def test_items_come_in_document_order_with_their_own_entry(self) -> None:
        root = support.assign_paths(support.node("section", children=[
            support.node("div", children=[badge("a"), body()]),
            support.node("aside", hook="promo"),
            badge("b"),
        ]))
        ignored = loading.prune_ignored(root, parsed("hook:promo", "hook:badge"), "prototype")
        self.assertEqual(
            [(item["path"], item["entry"]) for item in ignored],
            [
                ("section > div:nth-of-type(1) > span:nth-of-type(1)", "hook:badge"),
                ("section > aside:nth-of-type(1)", "hook:promo"),
                ("section > span:nth-of-type(1)", "hook:badge"),
            ],
        )

    def test_entry_matching_nothing_produces_no_item(self) -> None:
        root = support.assign_paths(support.node("section", children=[heading()]))
        self.assertEqual(loading.prune_ignored(root, parsed("hook:absent", "path:section > nav:nth-of-type(1)"), "prototype"), [])
        self.assertEqual(len(root["children"]), 1)

    def test_entry_matching_the_root_is_an_input_error(self) -> None:
        root = support.assign_paths(support.node("section", hook="orders", children=[heading()]))
        for entry in ("path:section", "hook:orders"):
            with self.subTest(entry=entry), self.assertRaises(loading.InputError) as raised:
                loading.prune_ignored(root, parsed(entry), "prototype")
            self.assertIn(entry, str(raised.exception))


class IgnoreComparisonTests(unittest.TestCase):
    def test_prototype_only_badge_is_missing_without_an_ignore_entry(self) -> None:
        result = compare([heading(), badge(), body()], [heading(), body()])
        self.assertEqual(result["verdict"], "MISSING")
        self.assertEqual(result["findings"]["ignored"], [])

    def test_ignored_prototype_badge_turns_missing_into_match(self) -> None:
        result = compare([heading(), badge(), body()], [heading(), body()], {"prototype": parsed("hook:badge"), "real": []})
        self.assertEqual(result["verdict"], "MATCH")
        self.assertEqual(result["findings"]["missing"], [])
        self.assertEqual(result["findings"]["ignored"], [{"side": "prototype", "path": "section > span:nth-of-type(1)", "entry": "hook:badge"}])
        self.assertEqual(
            diff_snapshots.summary_line(result),
            "MATCH style=0 geometry=0 missing=0 structure=0 content=0 accessibility=0 ignored=1 lowestScore=n/a",
        )

    def test_ignore_real_is_symmetric(self) -> None:
        result = compare([heading(), body()], [heading(), badge(), body()], {"prototype": [], "real": parsed("hook:badge")})
        self.assertEqual(result["verdict"], "MATCH")
        self.assertEqual(result["findings"]["ignored"][0]["side"], "real")

    def test_ignored_category_does_not_change_the_verdict(self) -> None:
        result = compare(
            [heading(), badge(), body()],
            [heading(), support.node("p", own_text="Body", y=40, style={"color": "rgb(9, 9, 9)"}, contrast=GOOD_CONTRAST)],
            {"prototype": parsed("hook:badge"), "real": []},
        )
        self.assertEqual(result["verdict"], "DRIFT")
        self.assertEqual(len(result["findings"]["ignored"]), 1)

    def test_pruning_runs_before_the_root_preflight(self) -> None:
        proto_children = [badge("a"), badge("b"), badge("c"), body()]
        self.assertEqual(compare(proto_children, [body()])["blocked"]["reason"], "roots-incompatible")
        result = compare(proto_children, [body()], {"prototype": parsed("hook:badge"), "real": []})
        self.assertIsNone(result["blocked"])
        self.assertEqual(result["verdict"], "MATCH")
        self.assertEqual(len(result["findings"]["ignored"]), 3)

    def test_blocked_result_carries_the_ignored_key(self) -> None:
        proto = support.snapshot(support.node("section", children=[body()]), width=1440)
        real = support.snapshot(support.node("section", children=[body()]), width=1024)
        result = diff_snapshots.compare_snapshots(proto, real, {}, {}, {"prototype": parsed("hook:badge"), "real": []})
        self.assertEqual(result["blocked"]["reason"], "condition-mismatch")
        self.assertEqual(result["findings"]["ignored"], [])
        self.assertEqual(list(result["findings"])[-1], "ignored")


class IgnoreCliTests(unittest.TestCase):
    def run_cli(self, tmp_path: Path, proto_children, real_children, *arguments: str):
        proto_snap = support.write_json(tmp_path / "proto.json", support.snapshot(support.node("section", children=proto_children)))
        real_snap = support.write_json(tmp_path / "real.json", support.snapshot(support.node("section", children=real_children)))
        out_file = tmp_path / "out.json"
        completed = support.run_diff("--prototype", str(proto_snap), "--real", str(real_snap), "--out", str(out_file), *arguments)
        return completed, out_file

    def test_repeatable_ignore_flags_prune_both_sides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            completed, out_file = self.run_cli(
                Path(tmp_dir),
                [heading(), badge(), support.node("aside", hook="promo"), body()],
                [heading(), body(), support.node("footer", hook="legal")],
                "--ignore-prototype", "hook:badge", "--ignore-prototype", "hook:promo", "--ignore-real", "path:section > footer:nth-of-type(1)",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(completed.stdout.startswith("MATCH "), completed.stdout)
            self.assertIn(" ignored=3 lowestScore=", completed.stdout)
            ignored = support.read_json(out_file)["findings"]["ignored"]
            self.assertEqual([(item["side"], item["entry"]) for item in ignored], [
                ("prototype", "hook:badge"), ("prototype", "hook:promo"), ("real", "path:section > footer:nth-of-type(1)"),
            ])

    def test_invalid_entry_exits_two_naming_the_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            completed, out_file = self.run_cli(Path(tmp_dir), [body()], [body()], "--ignore-prototype", "foo:bar")
            self.assertEqual(completed.returncode, 2)
            self.assertIn("foo:bar", completed.stderr)
            self.assertEqual(completed.stdout, "")
            self.assertFalse(out_file.exists())

    def test_entry_matching_the_root_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            completed, out_file = self.run_cli(Path(tmp_dir), [body()], [body()], "--ignore-real", "path:section")
            self.assertEqual(completed.returncode, 2)
            self.assertIn("path:section", completed.stderr)
            self.assertFalse(out_file.exists())


if __name__ == "__main__":
    unittest.main()
