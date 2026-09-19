from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "skills" / "ui-ux" / "visual-parity-verification" / "scripts"))

import support  # noqa: E402
import diff_snapshots  # noqa: E402


def pair_of(proto_kwargs, real_kwargs):
    proto = support.node("p", own_text="Same", **proto_kwargs)
    real = support.node("p", own_text="Same", **real_kwargs)
    return diff_snapshots.make_pair(proto, real, "text")


def properties(findings):
    return sorted(f["property"] for f in findings)


class CompareTests(unittest.TestCase):
    def test_identical_nodes_have_no_findings(self) -> None:
        self.assertEqual(diff_snapshots.compare_pair(pair_of({}, {}), diff_snapshots.DEFAULT_TOLERANCES), [])

    def test_colors_normalize_before_comparison(self) -> None:
        self.assertEqual(diff_snapshots.normalize_color("rgb(17, 24, 39)"), "rgba(17, 24, 39, 1)")
        self.assertEqual(diff_snapshots.normalize_color("#112233"), "rgba(17, 34, 51, 1)")
        self.assertEqual(diff_snapshots.normalize_color("transparent"), "rgba(0, 0, 0, 0)")
        findings = diff_snapshots.compare_pair(
            pair_of({"style": {"color": "rgb(17, 24, 39)"}}, {"style": {"color": "rgba(17, 24, 39, 1)"}}),
            diff_snapshots.DEFAULT_TOLERANCES,
        )
        self.assertEqual(findings, [])

    def test_color_difference_is_a_style_finding(self) -> None:
        findings = diff_snapshots.compare_pair(
            pair_of({"style": {"color": "rgb(17, 24, 39)"}}, {"style": {"color": "rgb(0, 0, 0)"}}),
            diff_snapshots.DEFAULT_TOLERANCES,
        )
        self.assertEqual(properties(findings), ["color"])
        self.assertEqual(findings[0]["category"], "style")
        self.assertEqual(findings[0]["prototype"], "rgb(17, 24, 39)")
        self.assertEqual(findings[0]["real"], "rgb(0, 0, 0)")

    def test_lengths_within_half_pixel_are_equal(self) -> None:
        findings = diff_snapshots.compare_pair(
            pair_of({"style": {"paddingTop": "8px"}}, {"style": {"paddingTop": "8.4px"}}),
            diff_snapshots.DEFAULT_TOLERANCES,
        )
        self.assertEqual(findings, [])
        findings = diff_snapshots.compare_pair(
            pair_of({"style": {"paddingTop": "8px"}}, {"style": {"paddingTop": "9px"}}),
            diff_snapshots.DEFAULT_TOLERANCES,
        )
        self.assertEqual(properties(findings), ["paddingTop"])

    def test_font_family_compares_as_normalized_list(self) -> None:
        findings = diff_snapshots.compare_pair(
            pair_of({"style": {"fontFamily": '"Inter", sans-serif'}}, {"style": {"fontFamily": "Inter, Sans-Serif"}}),
            diff_snapshots.DEFAULT_TOLERANCES,
        )
        self.assertEqual(findings, [])
        findings = diff_snapshots.compare_pair(
            pair_of({"style": {"fontFamily": "Inter, sans-serif"}}, {"style": {"fontFamily": "Roboto, sans-serif"}}),
            diff_snapshots.DEFAULT_TOLERANCES,
        )
        self.assertEqual(properties(findings), ["fontFamily"])

    def test_normal_line_height_resolves_against_font_size(self) -> None:
        findings = diff_snapshots.compare_pair(
            pair_of({"style": {"fontSize": "20px", "lineHeight": "normal"}}, {"style": {"fontSize": "20px", "lineHeight": "24px"}}),
            diff_snapshots.DEFAULT_TOLERANCES,
        )
        self.assertEqual(findings, [])

    def test_transform_none_equals_identity_matrix(self) -> None:
        findings = diff_snapshots.compare_pair(
            pair_of({"style": {"transform": "none"}}, {"style": {"transform": "matrix(1, 0, 0, 1, 0, 0)"}}),
            diff_snapshots.DEFAULT_TOLERANCES,
        )
        self.assertEqual(findings, [])

    def test_geometry_beyond_tolerance_is_a_geometry_finding(self) -> None:
        findings = diff_snapshots.compare_pair(pair_of({"x": 10}, {"x": 12}), diff_snapshots.DEFAULT_TOLERANCES)
        self.assertEqual(findings[0]["category"], "geometry")
        self.assertEqual(findings[0]["property"], "x")
        self.assertEqual(findings[0]["prototype"], 10)
        self.assertEqual(findings[0]["real"], 12)

    def test_tolerance_override_widens_length_tolerance(self) -> None:
        tolerances = dict(diff_snapshots.DEFAULT_TOLERANCES, lengthPx=2.0)
        findings = diff_snapshots.compare_pair(pair_of({"x": 10}, {"x": 12}), tolerances)
        self.assertEqual(findings, [])

    def test_semantics_differences_are_style_findings_by_name(self) -> None:
        findings = diff_snapshots.compare_pair(
            pair_of({"role": "button", "focusable": True}, {"role": "", "focusable": False}),
            diff_snapshots.DEFAULT_TOLERANCES,
        )
        self.assertEqual(properties(findings), ["focusable", "role", "tabIndex"])
