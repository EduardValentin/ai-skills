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

    def test_shared_hook_pairs_regardless_of_tag(self) -> None:
        alignment = align(
            [support.node("span", hook="price", own_text="$10")],
            [support.node("strong", hook="price", own_text="$12")],
        )
        self.assertEqual(by_rule(alignment), [("section > span:nth-of-type(1)", "section > strong:nth-of-type(1)", "hook")])

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

    def test_unmatched_nodes_are_missing_on_their_side(self) -> None:
        alignment = align(
            [support.node("h2", role="heading", name="Orders", own_text="Orders"), support.node("img", role="img", name="Logo")],
            [support.node("h2", role="heading", name="Orders", own_text="Orders")],
        )
        self.assertEqual([n["path"] for n in alignment["missing"]["prototype"]], ["section > img:nth-of-type(1)"])
        self.assertEqual(alignment["missing"]["real"], [])
