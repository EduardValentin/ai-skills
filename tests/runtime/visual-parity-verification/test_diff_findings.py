from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "skills" / "ui-ux" / "visual-parity-verification" / "scripts"))

import support  # noqa: E402
import diff_snapshots  # noqa: E402
from parity_diff import findings  # noqa: E402


def compare(proto_children, real_children, pairings=None, tolerances=None):
    proto = support.snapshot(support.node("section", role="region", name="Orders", width=640, height=400, children=proto_children))
    real = support.snapshot(support.node("section", role="region", name="Orders", width=640, height=400, children=real_children))
    return diff_snapshots.compare_snapshots(proto, real, pairings or {}, tolerances or {})


GOOD_CONTRAST = {"ratio": 12.6, "needsAnalyzer": False, "largeText": False}


def compare_roots(proto_root, real_root, tolerances=None):
    return diff_snapshots.compare_snapshots(support.snapshot(proto_root), support.snapshot(real_root), {}, tolerances or {})


def value_cells(*texts: str) -> list[dict]:
    return [support.node("span", own_text=text, x=index * 60, width=50, contrast=GOOD_CONTRAST) for index, text in enumerate(texts)]


class PositionPairFindingTests(unittest.TestCase):
    def test_nameless_value_cells_pair_by_position_and_differ_only_in_content(self) -> None:
        result = compare(value_cells("$10", "$5", "$1"), value_cells("$12", "$7", "$2"))
        cell_pairs = [p for p in result["pairs"] if p["matchedBy"] != "root"]
        self.assertEqual([p["matchedBy"] for p in cell_pairs], ["position", "position", "position"])
        self.assertFalse(any(p["needsReview"] for p in cell_pairs))
        self.assertTrue(all(p["score"] is None and p["signals"] is None for p in cell_pairs))
        self.assertEqual(len(result["findings"]["content"]), 3)
        self.assertEqual(result["findings"]["style"], [])
        self.assertEqual(result["findings"]["geometry"], [])
        self.assertIsNone(result["lowestScore"])
        self.assertEqual(result["verdict"], "MATCH")
        self.assertEqual(findings.review_lines(result), ["review none"])


class RootBoxTests(unittest.TestCase):
    def test_root_box_and_margins_are_context_not_evidence(self) -> None:
        result = compare_roots(
            support.node("section", role="region", name="Orders", x=0, y=0, width=640, height=400, style={"marginBottom": "0px"},
                         children=[support.node("p", own_text="Body", contrast=GOOD_CONTRAST)]),
            support.node("section", role="region", name="Orders", x=24, y=80, width=600, height=520, style={"marginBottom": "32px"},
                         children=[support.node("p", own_text="Body", contrast=GOOD_CONTRAST)]),
        )
        self.assertEqual(result["findings"]["geometry"], [])
        self.assertEqual(result["findings"]["style"], [])
        self.assertEqual(result["verdict"], "MATCH")

    def test_root_padding_is_still_evidence(self) -> None:
        result = compare_roots(
            support.node("section", role="region", name="Orders", width=640, height=400, style={"paddingTop": "0px"}),
            support.node("section", role="region", name="Orders", width=640, height=400, style={"paddingTop": "16px"}),
        )
        self.assertEqual([f["property"] for f in result["findings"]["style"]], ["paddingTop"])
        self.assertEqual(result["verdict"], "DRIFT")

    def test_child_margin_and_geometry_stay_evidence(self) -> None:
        result = compare(
            [support.node("p", own_text="Body", height=20, style={"marginBottom": "0px"})],
            [support.node("p", own_text="Body", height=32, style={"marginBottom": "8px"})],
        )
        self.assertEqual([f["property"] for f in result["findings"]["style"]], ["marginBottom"])
        self.assertEqual([f["property"] for f in result["findings"]["geometry"]], ["height"])
        self.assertEqual(result["verdict"], "DRIFT")


class FindingTests(unittest.TestCase):
    def test_content_mismatch_excludes_text_geometry_but_keeps_style(self) -> None:
        result = compare(
            [support.node("p", role="paragraph", own_text="Total: $10", width=80, style={"fontSize": "16px"}, contrast=GOOD_CONTRAST)],
            [support.node("p", role="paragraph", own_text="Total: $1,240.50", width=140, style={"fontSize": "18px"}, contrast=GOOD_CONTRAST)],
        )
        self.assertEqual([f["property"] for f in result["findings"]["style"]], ["fontSize"])
        self.assertEqual(result["findings"]["geometry"], [])
        self.assertEqual(result["findings"]["content"][0]["prototype"], "Total: $10")
        self.assertEqual(result["verdict"], "DRIFT")

    def test_content_mismatch_excludes_own_position(self) -> None:
        result = compare(
            [support.node("p", hook="total", own_text="Total: $10", x=0, y=0)],
            [support.node("p", hook="total", own_text="Total: $1,240.50", x=48, y=12)],
        )
        self.assertEqual(result["findings"]["geometry"], [])
        self.assertEqual(result["verdict"], "MATCH")

    def test_content_mismatch_excludes_following_sibling_offsets(self) -> None:
        result = compare(
            [support.node("span", role="cell", own_text="Short", x=0, width=40), support.node("span", role="cell", own_text="Next", x=48, width=40)],
            [support.node("span", role="cell", own_text="Much longer text", x=0, width=120), support.node("span", role="cell", own_text="Next", x=128, width=40)],
        )
        self.assertEqual(result["findings"]["geometry"], [])
        self.assertEqual(result["verdict"], "MATCH")

    def test_content_mismatch_excludes_preceding_sibling_position(self) -> None:
        result = compare(
            [support.node("span", role="cell", own_text="Label", x=0, width=40),
             support.node("span", role="cell", own_text="Short", x=48, width=40)],
            [support.node("span", role="cell", own_text="Label", x=20, width=60),
             support.node("span", role="cell", own_text="Much longer text", x=68, width=120)],
        )
        self.assertEqual([f["property"] for f in result["findings"]["geometry"]], ["width"])
        label_finding = result["findings"]["geometry"][0]
        self.assertEqual(label_finding["path"], "section > span:nth-of-type(1)")
        self.assertEqual(label_finding["prototype"], 40)
        self.assertEqual(label_finding["real"], 60)

    def test_missing_node_is_missing_verdict(self) -> None:
        result = compare(
            [support.node("h2", role="heading", name="Orders", own_text="Orders"), support.node("img", role="img", name="Logo")],
            [support.node("h2", role="heading", name="Orders", own_text="Orders")],
        )
        self.assertEqual(result["verdict"], "MISSING")
        self.assertEqual(result["findings"]["missing"][0], {"side": "prototype", "path": "section > img:nth-of-type(1)", "tag": "img", "role": "img", "name": "Logo", "suggestion": None})

    def test_drift_outranks_missing(self) -> None:
        result = compare(
            [support.node("h2", role="heading", name="Orders", own_text="Orders", style={"color": "rgb(1, 1, 1)"}), support.node("img", role="img", name="Logo")],
            [support.node("h2", role="heading", name="Orders", own_text="Orders", style={"color": "rgb(2, 2, 2)"})],
        )
        self.assertEqual(result["verdict"], "DRIFT")
        self.assertEqual(len(result["findings"]["missing"]), 1)

    def test_structure_findings_do_not_affect_verdict(self) -> None:
        result = compare(
            [support.node("div", wrapper=True, children=[support.node("p", own_text="x")])],
            [support.node("p", own_text="x")],
        )
        self.assertEqual(result["verdict"], "MATCH")
        self.assertEqual(result["findings"]["structure"][0]["kind"], "collapsed-count")
        self.assertEqual(result["findings"]["structure"][0]["prototype"], 1)
        self.assertEqual(result["findings"]["structure"][0]["real"], 0)

    def test_moved_node_is_a_structure_finding_and_compared(self) -> None:
        result = compare(
            [support.node("header", role="banner", name="Toolbar", children=[support.node("button", role="button", name="Export", style={"color": "rgb(1, 1, 1)"})]),
             support.node("h2", role="heading", name="Orders", own_text="Orders")],
            [support.node("header", role="banner", name="Toolbar"),
             support.node("h2", role="heading", name="Orders", own_text="Orders"),
             support.node("button", role="button", name="Export", style={"color": "rgb(9, 9, 9)"})],
        )
        moved = [f for f in result["findings"]["structure"] if f["kind"] == "moved"]
        self.assertEqual(moved[0]["prototype"], "section > header:nth-of-type(1) > button:nth-of-type(1)")
        self.assertEqual(moved[0]["real"], "section > button:nth-of-type(1)")
        self.assertEqual([f["property"] for f in result["findings"]["style"]], ["color"])
        self.assertEqual(result["findings"]["missing"], [])

    def test_low_contrast_is_an_accessibility_finding_on_both_sides(self) -> None:
        low = {"ratio": 2.1, "needsAnalyzer": False, "largeText": False}
        result = compare(
            [support.node("p", own_text="Hint", contrast=low)],
            [support.node("p", own_text="Hint", contrast=low)],
        )
        checks = sorted((f["side"], f["check"]) for f in result["findings"]["accessibility"])
        self.assertEqual(checks, [("prototype", "contrast"), ("real", "contrast")])
        self.assertEqual(result["findings"]["accessibility"][0]["threshold"], 4.5)
        self.assertEqual(result["verdict"], "MATCH")

    def test_large_text_uses_three_to_one(self) -> None:
        large = {"ratio": 3.2, "needsAnalyzer": False, "largeText": True}
        result = compare([support.node("h1", own_text="Big", contrast=large)], [support.node("h1", own_text="Big", contrast=large)])
        self.assertEqual(result["findings"]["accessibility"], [])

    def test_unmeasurable_contrast_is_an_accessibility_finding_not_blocked(self) -> None:
        unmeasurable = {"ratio": None, "needsAnalyzer": True, "largeText": False}
        result = compare([support.node("p", own_text="On gradient", contrast=unmeasurable)], [support.node("p", own_text="On gradient", contrast=GOOD_CONTRAST)])
        self.assertEqual(result["verdict"], "MATCH")
        self.assertIsNone(result["blocked"])
        accessibility = result["findings"]["accessibility"]
        self.assertEqual(len(accessibility), 1)
        self.assertEqual(accessibility[0]["check"], "contrast-unmeasurable")
        self.assertEqual(accessibility[0]["path"], "section > p:nth-of-type(1)")

    def test_name_from_content_is_not_compared_when_both_sides_derive_from_content(self) -> None:
        result = compare(
            [support.node("button", hook="item", role="button", name="Item one", name_from="content", own_text="Item one")],
            [support.node("button", hook="item", role="button", name="Item two", name_from="content", own_text="Item two")],
        )
        self.assertEqual(result["findings"]["style"], [])
        self.assertEqual(len(result["findings"]["content"]), 1)
        self.assertEqual(result["verdict"], "MATCH")

    def test_name_is_compared_when_either_side_is_authored(self) -> None:
        result = compare(
            [support.node("li", hook="item", role="listitem", name="Item one", name_from="content", own_text="Item one")],
            [support.node("li", hook="item", role="listitem", name="Item two", name_from="author", own_text="Item two")],
        )
        self.assertEqual([f["property"] for f in result["findings"]["style"]], ["name"])

    def test_needs_review_flag(self) -> None:
        result = compare(
            [
                support.node("h2", role="heading", name="Orders", own_text="Orders"),
                support.node("div", hook="group-review", children=[
                    support.node("article", role="article", name="", y=0, children=[support.node("span", own_text="Foo")]),
                ]),
                support.node("div", hook="group-equal", children=[
                    support.node("article", role="article", name="", children=[support.node("span", own_text="Same")]),
                    support.node("article", role="article", name="", children=[support.node("span", own_text="Same")]),
                ]),
            ],
            [
                support.node("h2", role="heading", name="Orders", own_text="Orders"),
                support.node("div", hook="group-review", children=[
                    support.node("article", role="article", name="", y=4, children=[support.node("span", own_text="Bar")]),
                    support.node("span", own_text="Extra"),
                ]),
                support.node("div", hook="group-equal", children=[
                    support.node("article", role="article", name="", children=[support.node("span", own_text="Same")]),
                    support.node("article", role="article", name="", children=[support.node("span", own_text="Same")]),
                    support.node("span", own_text="Extra"),
                ]),
            ],
        )
        pairs_by_prototype = {p["prototype"]: p for p in result["pairs"]}

        anchored = pairs_by_prototype["section > h2:nth-of-type(1)"]
        self.assertEqual(anchored["matchedBy"], "role-name")
        self.assertFalse(anchored["needsReview"])

        review_pair = pairs_by_prototype["section > div:nth-of-type(1) > article:nth-of-type(1)"]
        self.assertEqual(review_pair["matchedBy"], "score")
        self.assertEqual(review_pair["signals"]["roleName"], 0.5)
        self.assertEqual(review_pair["signals"]["text"], 0.0)
        self.assertTrue(review_pair["needsReview"])

        equal_text_pairs = [
            pairs_by_prototype[path]
            for path in (
                "section > div:nth-of-type(2) > article:nth-of-type(1)",
                "section > div:nth-of-type(2) > article:nth-of-type(2)",
            )
        ]
        for pair in equal_text_pairs:
            self.assertEqual(pair["matchedBy"], "score")
            self.assertEqual(pair["signals"]["text"], 1.0)
            self.assertFalse(pair["needsReview"])

    def test_interactive_node_without_role_or_name_is_flagged(self) -> None:
        heading = support.node("h2", role="heading", name="Orders", own_text="Orders")
        result = compare(
            [heading, support.node("div", focusable=True, own_text="Go", role="", name="")],
            [heading, support.node("button", role="button", name="Go", own_text="Go")],
        )
        self.assertIsNone(result["blocked"])
        checks = {(f["side"], f["check"]) for f in result["findings"]["accessibility"]}
        self.assertIn(("prototype", "missing-role"), checks)

    def test_summary_line_reports_counts(self) -> None:
        result = compare([support.node("p", own_text="x", style={"color": "rgb(1, 1, 1)"})], [support.node("p", own_text="x", style={"color": "rgb(2, 2, 2)"})])
        line = diff_snapshots.summary_line(result)
        self.assertTrue(line.startswith("DRIFT style=1 geometry=0 missing=0 structure=0 content=0 accessibility=0"), line)

    def test_review_lines_with_review_pair_and_suggestion(self) -> None:
        proto_children = [
            support.node("h2", role="heading", name="Orders", own_text="Orders"),
            support.node("div", hook="group", children=[
                support.node("article", role="article", name="", own_text="Foo"),
            ]),
            support.node("span", role="doc-subtitle", own_text="Extra Proto"),
        ]
        real_children = [
            support.node("h2", role="heading", name="Orders", own_text="Orders"),
            support.node("div", hook="group", children=[
                support.node("article", role="article", name="", own_text="Bar"),
                support.node("span", own_text="Extra"),
            ]),
            support.node("span", own_text="Extra Real"),
        ]
        result = compare(proto_children, real_children)

        lines = findings.review_lines(result)
        review_pairs = [l for l in lines if l.startswith("review ") and "<->" in l]
        suggestions = [l for l in lines if l.startswith("suggest ")]

        self.assertEqual(len(review_pairs), 1)
        self.assertEqual(
            review_pairs[0],
            "review section > div:nth-of-type(1) > article:nth-of-type(1) "
            "<-> section > div:nth-of-type(1) > article:nth-of-type(1) "
            "score=0.53 roleName=0.5 text=0.0",
        )
        self.assertGreaterEqual(len(suggestions), 1)
        for suggestion in suggestions:
            self.assertIn("score=", suggestion)
            self.assertIn("->", suggestion)

    def test_review_lines_with_identical_snapshots(self) -> None:
        result = compare([support.node("p", own_text="Same")], [support.node("p", own_text="Same")])
        lines = findings.review_lines(result)
        self.assertEqual(lines, ["review none"])

    def test_print_review_flag_outputs_review_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            proto_snap = support.write_json(tmp_path / "proto.json", support.snapshot(support.node("p", own_text="Foo")))
            real_snap = support.write_json(tmp_path / "real.json", support.snapshot(support.node("p", own_text="Bar")))
            out_file = tmp_path / "out.json"

            result = support.run_diff(
                "--prototype", str(proto_snap),
                "--real", str(real_snap),
                "--out", str(out_file),
                "--print-review",
            )

            lines = result.stdout.strip().split("\n")
            self.assertEqual(len(lines), 2)
            self.assertTrue(lines[0].startswith("MATCH") or lines[0].startswith("DRIFT"))
            self.assertEqual(lines[1], "review none")

    def test_print_review_flag_reports_blocked_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            proto_snap = support.write_json(
                tmp_path / "proto.json", support.snapshot(support.node("p", own_text="Same"), width=1440)
            )
            real_snap = support.write_json(
                tmp_path / "real.json", support.snapshot(support.node("p", own_text="Same"), width=1024)
            )
            out_file = tmp_path / "out.json"

            result = support.run_diff(
                "--prototype", str(proto_snap),
                "--real", str(real_snap),
                "--out", str(out_file),
                "--print-review",
            )

            lines = result.stdout.strip().split("\n")
            self.assertEqual(len(lines), 2)
            self.assertTrue(lines[0].startswith("BLOCKED"))
            self.assertEqual(lines[1], "review blocked")

    def test_without_print_review_flag_outputs_only_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            proto_snap = support.write_json(tmp_path / "proto.json", support.snapshot(support.node("p", own_text="Same")))
            real_snap = support.write_json(tmp_path / "real.json", support.snapshot(support.node("p", own_text="Same")))
            out_file = tmp_path / "out.json"

            result = support.run_diff(
                "--prototype", str(proto_snap),
                "--real", str(real_snap),
                "--out", str(out_file),
            )

            lines = result.stdout.strip().split("\n")
            self.assertEqual(len(lines), 1)
