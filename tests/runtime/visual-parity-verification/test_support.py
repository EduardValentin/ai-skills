from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import support  # noqa: E402


class SupportTests(unittest.TestCase):
    def test_snapshot_assigns_nth_of_type_paths(self) -> None:
        root = support.node("section", role="region", name="Orders", children=[
            support.node("h2", own_text="Orders"),
            support.node("p", own_text="one"),
            support.node("p", own_text="two"),
        ])
        snap = support.snapshot(root)
        paths = [child["path"] for child in snap["root"]["children"]]
        self.assertEqual(paths, [
            "section > h2:nth-of-type(1)",
            "section > p:nth-of-type(1)",
            "section > p:nth-of-type(2)",
        ])
        self.assertEqual(snap["rootSummary"]["role"], "region")
        self.assertEqual(snap["viewport"], {"width": 1440, "height": 900})

    def test_node_style_has_every_schema_key(self) -> None:
        schema = (support.REPO_ROOT / "skills" / "ui-ux" / "visual-parity-verification"
                  / "references" / "snapshot-schema.md").read_text(encoding="utf-8")
        for key in support.BASE_STYLE:
            self.assertIn(f"`{key}`", schema, key)
