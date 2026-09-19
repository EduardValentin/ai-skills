from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "skills" / "ui-ux" / "visual-parity-verification" / "scripts"))

import support  # noqa: E402
import diff_snapshots  # noqa: E402


def align(proto_children, real_children, pairings=None):
    proto = support.assign_paths(support.node("section", children=proto_children))
    real = support.assign_paths(support.node("section", children=real_children))
    return diff_snapshots.align_trees(proto, real, pairings or {})


def by_rule(alignment):
    return [(p["prototype"]["path"], p["real"]["path"], p["matchedBy"]) for p in alignment["pairs"][1:]]


class AnchorAlignmentTests(unittest.TestCase):
    def test_roots_are_always_the_first_pair(self) -> None:
        alignment = align([], [])
        self.assertEqual(alignment["pairs"][0]["matchedBy"], "root")
        self.assertEqual(alignment["missing"], {"prototype": [], "real": []})

    def test_pairings_win_over_every_other_rule(self) -> None:
        alignment = align(
            [support.node("button", role="button", name="Save"), support.node("button", role="button", name="Cancel")],
            [support.node("button", role="button", name="Cancel"), support.node("button", role="button", name="Save")],
            pairings={"section > button:nth-of-type(1)": "section > button:nth-of-type(1)"},
        )
        rules = by_rule(alignment)
        self.assertIn(("section > button:nth-of-type(1)", "section > button:nth-of-type(1)", "pairing"), rules)
        self.assertEqual([n["name"] for n in alignment["missing"]["prototype"]], ["Cancel"])
        self.assertEqual([n["name"] for n in alignment["missing"]["real"]], ["Save"])

    def test_pairing_across_levels_pairs_and_removes_missing(self) -> None:
        proto_button = support.node("button", role="button", name="Export")
        real_button = support.node("button", role="button", name="Download")
        alignment = align(
            [support.node("nav", children=[proto_button])],
            [real_button],
            pairings={"section > nav:nth-of-type(1) > button:nth-of-type(1)": "section > button:nth-of-type(1)"},
        )
        pairing_pairs = [p for p in alignment["pairs"] if p["matchedBy"] == "pairing"]
        self.assertEqual(len(pairing_pairs), 1)
        pair = pairing_pairs[0]
        self.assertEqual(pair["prototype"]["path"], "section > nav:nth-of-type(1) > button:nth-of-type(1)")
        self.assertEqual(pair["real"]["path"], "section > button:nth-of-type(1)")
        missing_prototype_paths = [n["path"] for n in alignment["missing"]["prototype"]]
        missing_real_paths = [n["path"] for n in alignment["missing"]["real"]]
        self.assertNotIn(pair["prototype"]["path"], missing_prototype_paths)
        self.assertNotIn(pair["real"]["path"], missing_real_paths)
        # The prototype's nav has no counterpart on the real side once its
        # only child is taken by the global pairing, so it is reported missing.
        self.assertIn("section > nav:nth-of-type(1)", missing_prototype_paths)
        self.assertEqual(missing_real_paths, [])

    def test_duplicate_real_target_in_pairings_pairs_once_and_skips_the_rest(self) -> None:
        alignment = align(
            [support.node("button", role="button", name="Save"), support.node("button", role="button", name="Cancel")],
            [support.node("button", role="button", name="Save")],
            pairings={
                "section > button:nth-of-type(1)": "section > button:nth-of-type(1)",
                "section > button:nth-of-type(2)": "section > button:nth-of-type(1)",
            },
        )
        pairing_pairs = [p for p in alignment["pairs"] if p["matchedBy"] == "pairing"]
        self.assertEqual(len(pairing_pairs), 1)
        self.assertEqual(pairing_pairs[0]["prototype"]["path"], "section > button:nth-of-type(1)")
        self.assertEqual(pairing_pairs[0]["real"]["path"], "section > button:nth-of-type(1)")
        # The lower prototype path sorts first and claims the shared real
        # target; the second entry's real node is already detached, so it is
        # skipped.
        self.assertEqual([n["name"] for n in alignment["missing"]["prototype"]], ["Cancel"])
        self.assertEqual(alignment["missing"]["real"], [])

    def test_pairing_with_unknown_path_is_ignored(self) -> None:
        alignment = align(
            [support.node("button", role="button", name="Save")],
            [support.node("button", role="button", name="Save")],
            pairings={"section > span:nth-of-type(9)": "section > span:nth-of-type(9)"},
        )
        self.assertNotIn("pairing", {p["matchedBy"] for p in alignment["pairs"]})
        self.assertIn(
            ("section > button:nth-of-type(1)", "section > button:nth-of-type(1)", "role-name"),
            by_rule(alignment),
        )

    def test_shared_hook_pairs_regardless_of_tag(self) -> None:
        alignment = align(
            [support.node("span", hook="price", own_text="$10")],
            [support.node("strong", hook="price", own_text="$12")],
        )
        self.assertEqual(by_rule(alignment), [("section > span:nth-of-type(1)", "section > strong:nth-of-type(1)", "hook")])

    def test_duplicate_hook_is_not_an_anchor_and_falls_back_to_text(self) -> None:
        alignment = align(
            [support.node("span", hook="price", own_text="$10"), support.node("span", hook="price", own_text="$20")],
            [support.node("strong", hook="price", own_text="$20"), support.node("strong", hook="price", own_text="$10")],
        )
        rules = by_rule(alignment)
        self.assertFalse(any(rule == "hook" for _, _, rule in rules))
        self.assertEqual(
            sorted(rules),
            [("section > span:nth-of-type(1)", "section > strong:nth-of-type(2)", "text"),
             ("section > span:nth-of-type(2)", "section > strong:nth-of-type(1)", "text")],
        )

    def test_unique_role_and_name_pairs(self) -> None:
        alignment = align(
            [support.node("h2", role="heading", name="Orders", own_text="Orders"), support.node("button", role="button", name="Save")],
            [support.node("button", role="button", name="Save"), support.node("h1", role="heading", name="Orders", own_text="Orders")],
        )
        rules = {rule for _, _, rule in by_rule(alignment)}
        self.assertEqual(rules, {"role-name"})
        self.assertEqual(len(alignment["pairs"]), 3)

    def test_duplicate_role_and_name_is_not_an_anchor(self) -> None:
        alignment = align(
            [support.node("button", role="button", name="Delete"), support.node("button", role="button", name="Delete")],
            [support.node("button", role="button", name="Delete")],
        )
        self.assertNotIn("role-name", {rule for _, _, rule in by_rule(alignment)})

    def test_unique_own_text_pairs_when_roles_are_empty(self) -> None:
        alignment = align(
            [support.node("span", own_text="Total"), support.node("span", own_text="Tax")],
            [support.node("div", own_text="Tax"), support.node("div", own_text="Total")],
        )
        self.assertEqual(
            sorted(by_rule(alignment)),
            [("section > span:nth-of-type(1)", "section > div:nth-of-type(2)", "text"),
             ("section > span:nth-of-type(2)", "section > div:nth-of-type(1)", "text")],
        )

    def test_alignment_recurses_into_matched_children(self) -> None:
        alignment = align(
            [support.node("article", role="article", name="Card", children=[support.node("h3", own_text="Inner")])],
            [support.node("article", role="article", name="Card", children=[support.node("h3", own_text="Inner")])],
        )
        paths = [p["prototype"]["path"] for p in alignment["pairs"]]
        self.assertIn("section > article:nth-of-type(1) > h3:nth-of-type(1)", paths)

    def test_container_without_own_text_anchors_by_subtree_text(self) -> None:
        def li(label: str, value: str) -> dict:
            return support.node("li", role="listitem", children=[
                support.node("span", own_text=label),
                support.node("span", own_text=value),
            ])

        alignment = align(
            [li("Subtotal", "$10"), li("Shipping", "$5"), li("Tax", "$1")],
            [li("Subtotal", "$10"), li("Tax", "$1")],
        )
        missing_paths = [n["path"] for n in alignment["missing"]["prototype"]]
        self.assertEqual(missing_paths, ["section > li:nth-of-type(2)"])
        self.assertEqual(alignment["missing"]["real"], [])
        rules = by_rule(alignment)
        self.assertIn(("section > li:nth-of-type(1)", "section > li:nth-of-type(1)", "text"), rules)
        self.assertIn(("section > li:nth-of-type(3)", "section > li:nth-of-type(2)", "text"), rules)

    def test_subtree_text_is_not_an_anchor_when_duplicated(self) -> None:
        def li(label: str, value: str) -> dict:
            return support.node("li", role="listitem", children=[
                support.node("span", own_text=label),
                support.node("span", own_text=value),
            ])

        alignment = align(
            [li("Subtotal", "$10"), li("Subtotal", "$10")],
            [li("Subtotal", "$10")],
        )
        top_level_rules = {rule for proto_path, _, rule in by_rule(alignment) if proto_path.count(">") == 1}
        self.assertNotIn("text", top_level_rules)

    def test_unmatched_nodes_are_missing_on_their_side(self) -> None:
        alignment = align(
            [support.node("h2", role="heading", name="Orders", own_text="Orders"), support.node("img", role="img", name="Logo")],
            [support.node("h2", role="heading", name="Orders", own_text="Orders")],
        )
        self.assertEqual([n["path"] for n in alignment["missing"]["prototype"]], ["section > img:nth-of-type(1)"])
        self.assertEqual(alignment["missing"]["real"], [])


def align_with_roots(proto_children, real_children, pairings=None):
    proto = support.assign_paths(support.node("section", width=640, height=400, children=proto_children))
    real = support.assign_paths(support.node("section", width=640, height=400, children=real_children))
    context = {
        "prototypeRoot": {"width": 640, "height": 400},
        "realRoot": {"width": 640, "height": 400},
    }
    return diff_snapshots.align_trees(proto, real, pairings or {}, context)


class FillAlignmentTests(unittest.TestCase):
    def test_extra_node_perturbs_only_its_gap(self) -> None:
        proto_children = [
            support.node("h2", role="heading", name="Orders", own_text="Orders", y=0),
            support.node("img", role="img", name="", y=40, x=0, width=24, height=24),
            support.node("img", role="img", name="", y=40, x=60, width=24, height=24),
            support.node("button", role="button", name="Save", y=100),
        ]
        real_children = [
            support.node("h2", role="heading", name="Orders", own_text="Orders", y=0),
            support.node("img", role="img", name="", y=40, x=0, width=24, height=24),
            support.node("span", own_text="New", y=40, x=30, width=24, height=24),
            support.node("img", role="img", name="", y=40, x=60, width=24, height=24),
            support.node("button", role="button", name="Save", y=100),
        ]
        alignment = align_with_roots(proto_children, real_children)
        scored = {(p["prototype"]["path"], p["real"]["path"]) for p in alignment["pairs"] if p["matchedBy"] == "score"}
        self.assertEqual(scored, {
            ("section > img:nth-of-type(1)", "section > img:nth-of-type(1)"),
            ("section > img:nth-of-type(2)", "section > img:nth-of-type(2)"),
        })
        self.assertEqual([n["tag"] for n in alignment["missing"]["real"]], ["span"])
        self.assertEqual(alignment["missing"]["prototype"], [])

    def test_same_role_and_name_duplicates_fall_to_scoring_by_geometry(self) -> None:
        proto_children = [
            support.node("button", role="button", name="Delete", y=0),
            support.node("button", role="button", name="Delete", y=200),
        ]
        real_children = [
            support.node("button", role="button", name="Delete", y=205),
            support.node("button", role="button", name="Delete", y=3),
        ]
        alignment = align_with_roots(proto_children, real_children)
        pairs = {(p["prototype"]["path"], p["real"]["path"]) for p in alignment["pairs"][1:]}
        self.assertEqual(pairs, {
            ("section > button:nth-of-type(1)", "section > button:nth-of-type(2)"),
            ("section > button:nth-of-type(2)", "section > button:nth-of-type(1)"),
        })
        self.assertTrue(all(p["matchedBy"] == "score" for p in alignment["pairs"][1:]))
        self.assertTrue(all(p["score"] >= diff_snapshots.THRESHOLD for p in alignment["pairs"][1:]))

    def test_geometry_and_fingerprint_alone_cannot_reach_threshold(self) -> None:
        proto = support.node("div", y=10, own_text="Alpha")
        real = support.node("div", y=10, own_text="Beta")
        score, signals = diff_snapshots.score_pair(proto, real, {
            "prototypeRoot": {"width": 640, "height": 400},
            "realRoot": {"width": 640, "height": 400},
        })
        self.assertEqual(signals["roleName"], 0.0)
        self.assertEqual(signals["text"], 0.0)
        self.assertEqual(signals["signature"], 0.5)
        self.assertLess(score, diff_snapshots.THRESHOLD)

    def test_fingerprint_signal_normalizes_color_syntax(self) -> None:
        proto = support.node("div", own_text="Alpha", style={"color": "rgba(255, 255, 255, 1)"})
        real = support.node("div", own_text="Beta", style={"color": "rgb(255, 255, 255)"})
        _, signals = diff_snapshots.score_pair(proto, real, {
            "prototypeRoot": {"width": 640, "height": 400},
            "realRoot": {"width": 640, "height": 400},
        })
        self.assertEqual(signals["fingerprint"], 1.0)

    def test_rejected_leftover_carries_best_suggestion(self) -> None:
        proto_children = [support.node("p", own_text="Shipping estimate", y=0)]
        real_children = [support.node("p", own_text="Delivery estimate", y=300)]
        alignment = align_with_roots(proto_children, real_children)
        self.assertEqual(len(alignment["missing"]["prototype"]), 1)
        suggestion = alignment["suggestions"][0]
        self.assertEqual(suggestion["side"], "prototype")
        self.assertEqual(suggestion["path"], "section > p:nth-of-type(1)")
        self.assertEqual(suggestion["candidate"], "section > p:nth-of-type(1)")
        self.assertLess(suggestion["score"], diff_snapshots.THRESHOLD)

    def test_subtree_signature_distinguishes_cards(self) -> None:
        card_a = support.node("article", role="article", name="", y=0, children=[
            support.node("h3", role="heading", name="One", own_text="One"),
            support.node("button", role="button", name="Open"),
        ])
        card_b = support.node("article", role="article", name="", y=200, children=[
            support.node("img", role="img", name="Cover"),
            support.node("p", own_text="text"),
        ])
        real_a = support.node("article", role="article", name="", y=200, children=[
            support.node("h3", role="heading", name="One", own_text="One"),
            support.node("button", role="button", name="Open"),
        ])
        real_b = support.node("article", role="article", name="", y=0, children=[
            support.node("img", role="img", name="Cover"),
            support.node("p", own_text="text"),
        ])
        alignment = align_with_roots([card_a, card_b], [real_a, real_b])
        top_level = [(p["prototype"]["path"], p["real"]["path"]) for p in alignment["pairs"][1:3]]
        self.assertIn(("section > article:nth-of-type(1)", "section > article:nth-of-type(1)"), top_level)

    def test_node_moved_to_another_parent_is_paired_as_moved(self) -> None:
        proto_children = [
            support.node("header", role="banner", name="Toolbar", children=[
                support.node("button", role="button", name="Export"),
            ]),
            support.node("h2", role="heading", name="Orders", own_text="Orders"),
        ]
        real_children = [
            support.node("header", role="banner", name="Toolbar"),
            support.node("h2", role="heading", name="Orders", own_text="Orders"),
            support.node("button", role="button", name="Export"),
        ]
        alignment = align_with_roots(proto_children, real_children)
        moved = [p for p in alignment["pairs"] if p["matchedBy"] == "moved"]
        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0]["prototype"]["path"], "section > header:nth-of-type(1) > button:nth-of-type(1)")
        self.assertEqual(moved[0]["real"]["path"], "section > button:nth-of-type(1)")
        self.assertEqual(alignment["missing"], {"prototype": [], "real": []})
