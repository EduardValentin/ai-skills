from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "skills" / "ui-ux" / "visual-parity-verification" / "scripts"))

import support  # noqa: E402
import diff_snapshots  # noqa: E402


class InflateStylesTests(unittest.TestCase):
    def test_round_trip_through_delta_and_inflate_matches_original(self) -> None:
        root = support.node("section", role="region", name="Orders", children=[
            support.node("h2", own_text="Orders", style={"fontSize": "20px", "color": "rgb(1, 1, 1)"}),
            support.node("div", children=[
                support.node("p", own_text="one", style={"color": "rgb(9, 9, 9)"}),
            ]),
        ])
        snap = support.snapshot(root)
        original = copy.deepcopy(snap["root"])

        delta = support.delta_snapshot(snap)
        diff_snapshots.inflate_styles(delta["root"])

        self.assertEqual(delta["root"], original)

    def test_identity_on_snapshot_that_already_carries_full_styles(self) -> None:
        root = support.node("section", children=[
            support.node("h2", own_text="Orders", style={"fontSize": "20px"}),
        ])
        before = copy.deepcopy(root)
        diff_snapshots.inflate_styles(root)
        self.assertEqual(root, before)

    def test_child_overriding_one_key_inherits_the_rest_from_parent(self) -> None:
        parent = support.node("section")
        child = support.node("h2")
        child["style"] = {"fontSize": "20px"}
        parent["children"] = [child]

        diff_snapshots.inflate_styles(parent)

        inflated_child = parent["children"][0]
        self.assertEqual(inflated_child["style"]["fontSize"], "20px")
        for key, value in parent["style"].items():
            if key == "fontSize":
                continue
            self.assertEqual(inflated_child["style"][key], value)
        self.assertEqual(set(inflated_child["style"]), set(parent["style"]))

    def test_load_snapshot_normalizes_old_relative_viewport_geometry_shape(self) -> None:
        old_shape_snapshot = {
            "url": "http://localhost/orders",
            "viewport": {"width": 1440, "height": 900},
            "devicePixelRatio": 1,
            "zoom": 1,
            "colorScheme": "light",
            "capturedAt": "2026-09-19T10:00:00.000Z",
            "rootSelector": "section",
            "rootSummary": {"tag": "section", "role": "region", "name": "Orders", "width": 640, "height": 300},
            "root": {
                "path": "section",
                "tag": "section",
                "hook": None,
                "ownText": "",
                "role": "region",
                "name": "Orders",
                "nameFrom": "author",
                "focusable": False,
                "tabIndex": -1,
                "state": {},
                "style": dict(support.BASE_STYLE),
                "geometry": {
                    "relative": {"x": 0, "y": 0, "width": 640, "height": 300},
                    "viewport": {"x": 10, "y": 50, "width": 640, "height": 300},
                },
                "contrast": None,
                "wrapper": False,
                "children": [
                    {
                        "path": "section > h2:nth-of-type(1)",
                        "tag": "h2",
                        "hook": None,
                        "ownText": "Orders",
                        "role": "heading",
                        "name": "Orders",
                        "nameFrom": "content",
                        "focusable": False,
                        "tabIndex": -1,
                        "state": {},
                        "style": {"fontSize": "20px"},
                        "geometry": {
                            "relative": {"x": 16, "y": 16, "width": 300, "height": 28},
                            "viewport": {"x": 26, "y": 66, "width": 300, "height": 28},
                        },
                        "contrast": None,
                        "wrapper": False,
                        "children": [],
                    },
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "old-shape.json"
            support.write_json(path, old_shape_snapshot)
            loaded = diff_snapshots.load_snapshot(path)

        self.assertEqual(loaded["root"]["geometry"], {"x": 0, "y": 0, "width": 640, "height": 300})
        child = loaded["root"]["children"][0]
        self.assertEqual(child["geometry"], {"x": 16, "y": 16, "width": 300, "height": 28})
        self.assertEqual(child["style"]["fontSize"], "20px")
        self.assertEqual(child["style"]["color"], support.BASE_STYLE["color"])


if __name__ == "__main__":
    unittest.main()
