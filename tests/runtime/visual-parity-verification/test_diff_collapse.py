from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "skills" / "ui-ux" / "visual-parity-verification" / "scripts"))

import support  # noqa: E402
import diff_snapshots  # noqa: E402


class CollapseTests(unittest.TestCase):
    def test_wrapper_children_are_reparented_in_order(self) -> None:
        root = support.node("section", children=[
            support.node("h2", own_text="Title"),
            support.node("div", wrapper=True, children=[
                support.node("p", own_text="one"),
                support.node("p", own_text="two"),
            ]),
            support.node("button", own_text="Save", role="button", name="Save"),
        ])
        support.assign_paths(root)
        collapsed_root, collapsed = diff_snapshots.collapse_wrappers(root)
        self.assertEqual([c["ownText"] for c in collapsed_root["children"]], ["Title", "one", "two", "Save"])
        self.assertEqual(collapsed, [{"path": "section > div:nth-of-type(1)", "tag": "div", "childCount": 2}])

    def test_nested_wrappers_collapse_recursively(self) -> None:
        root = support.node("section", children=[
            support.node("div", wrapper=True, children=[
                support.node("div", wrapper=True, children=[
                    support.node("span", own_text="deep"),
                ]),
            ]),
        ])
        support.assign_paths(root)
        collapsed_root, collapsed = diff_snapshots.collapse_wrappers(root)
        self.assertEqual(collapsed_root["children"][0]["ownText"], "deep")
        self.assertEqual(len(collapsed), 2)

    def test_root_is_never_collapsed(self) -> None:
        root = support.node("div", wrapper=True, children=[support.node("p", own_text="x")])
        support.assign_paths(root)
        collapsed_root, collapsed = diff_snapshots.collapse_wrappers(root)
        self.assertEqual(collapsed_root["tag"], "div")
        self.assertEqual(collapsed, [])

    def test_input_tree_is_not_mutated(self) -> None:
        root = support.node("section", children=[
            support.node("div", wrapper=True, children=[support.node("p", own_text="x")]),
        ])
        support.assign_paths(root)
        diff_snapshots.collapse_wrappers(root)
        self.assertTrue(root["children"][0]["wrapper"])

    def test_result_records_collapsed_per_side(self) -> None:
        proto = support.snapshot(support.node("section", width=640, height=300, children=[
            support.node("div", wrapper=True, children=[support.node("p", own_text="x")]),
        ]))
        real = support.snapshot(support.node("section", width=640, height=300, children=[
            support.node("p", own_text="x"),
        ]))
        result = diff_snapshots.compare_snapshots(proto, real, {}, {})
        self.assertEqual(len(result["collapsed"]["prototype"]), 1)
        self.assertEqual(result["collapsed"]["real"], [])
