from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "skills" / "ui-ux" / "visual-parity-verification" / "scripts"))

import support  # noqa: E402
from parity_diff import alignment, comparison  # noqa: E402


def pair_of(proto_kwargs, real_kwargs):
    proto = support.node("p", own_text="Same", **proto_kwargs)
    real = support.node("p", own_text="Same", **real_kwargs)
    return alignment.make_pair(proto, real, "text")


def properties(findings):
    return sorted(f["property"] for f in findings)


class CompareTests(unittest.TestCase):
    def test_identical_nodes_have_no_findings(self) -> None:
        self.assertEqual(comparison.compare_pair(pair_of({}, {}), comparison.DEFAULT_TOLERANCES), [])

    def test_colors_normalize_before_comparison(self) -> None:
        self.assertEqual(comparison.normalize_color("rgb(17, 24, 39)"), "rgba(17, 24, 39, 1)")
        self.assertEqual(comparison.normalize_color("#112233"), "rgba(17, 34, 51, 1)")
        self.assertEqual(comparison.normalize_color("transparent"), "rgba(0, 0, 0, 0)")
        findings = comparison.compare_pair(
            pair_of({"style": {"color": "rgb(17, 24, 39)"}}, {"style": {"color": "rgba(17, 24, 39, 1)"}}),
            comparison.DEFAULT_TOLERANCES,
        )
        self.assertEqual(findings, [])

    def test_color_difference_is_a_style_finding(self) -> None:
        findings = comparison.compare_pair(
            pair_of({"style": {"color": "rgb(17, 24, 39)"}}, {"style": {"color": "rgb(0, 0, 0)"}}),
            comparison.DEFAULT_TOLERANCES,
        )
        self.assertEqual(properties(findings), ["color"])
        self.assertEqual(findings[0]["category"], "style")
        self.assertEqual(findings[0]["prototype"], "rgb(17, 24, 39)")
        self.assertEqual(findings[0]["real"], "rgb(0, 0, 0)")

    def test_lengths_within_half_pixel_are_equal(self) -> None:
        findings = comparison.compare_pair(
            pair_of({"style": {"paddingTop": "8px"}}, {"style": {"paddingTop": "8.4px"}}),
            comparison.DEFAULT_TOLERANCES,
        )
        self.assertEqual(findings, [])
        findings = comparison.compare_pair(
            pair_of({"style": {"paddingTop": "8px"}}, {"style": {"paddingTop": "9px"}}),
            comparison.DEFAULT_TOLERANCES,
        )
        self.assertEqual(properties(findings), ["paddingTop"])

    def test_font_family_compares_as_normalized_list(self) -> None:
        findings = comparison.compare_pair(
            pair_of({"style": {"fontFamily": '"Inter", sans-serif'}}, {"style": {"fontFamily": "Inter, Sans-Serif"}}),
            comparison.DEFAULT_TOLERANCES,
        )
        self.assertEqual(findings, [])
        findings = comparison.compare_pair(
            pair_of({"style": {"fontFamily": "Inter, sans-serif"}}, {"style": {"fontFamily": "Roboto, sans-serif"}}),
            comparison.DEFAULT_TOLERANCES,
        )
        self.assertEqual(properties(findings), ["fontFamily"])

    def test_normal_line_height_resolves_against_font_size(self) -> None:
        findings = comparison.compare_pair(
            pair_of({"style": {"fontSize": "20px", "lineHeight": "normal"}}, {"style": {"fontSize": "20px", "lineHeight": "24px"}}),
            comparison.DEFAULT_TOLERANCES,
        )
        self.assertEqual(findings, [])

    def test_transform_none_equals_identity_matrix(self) -> None:
        findings = comparison.compare_pair(
            pair_of({"style": {"transform": "none"}}, {"style": {"transform": "matrix(1, 0, 0, 1, 0, 0)"}}),
            comparison.DEFAULT_TOLERANCES,
        )
        self.assertEqual(findings, [])

    def test_geometry_beyond_tolerance_is_a_geometry_finding(self) -> None:
        findings = comparison.compare_pair(pair_of({"x": 10}, {"x": 12}), comparison.DEFAULT_TOLERANCES)
        self.assertEqual(findings[0]["category"], "geometry")
        self.assertEqual(findings[0]["property"], "x")
        self.assertEqual(findings[0]["prototype"], 10)
        self.assertEqual(findings[0]["real"], 12)

    def test_tolerance_override_widens_length_tolerance(self) -> None:
        tolerances = dict(comparison.DEFAULT_TOLERANCES, lengthPx=2.0)
        findings = comparison.compare_pair(pair_of({"x": 10}, {"x": 12}), tolerances)
        self.assertEqual(findings, [])

    def test_border_color_is_skipped_when_border_style_is_none_on_both_sides(self) -> None:
        findings = comparison.compare_pair(
            pair_of(
                {"style": {"borderTopStyle": "none", "borderTopColor": "rgb(17, 24, 39)"}},
                {"style": {"borderTopStyle": "none", "borderTopColor": "rgb(0, 0, 0)"}},
            ),
            comparison.DEFAULT_TOLERANCES,
        )
        self.assertEqual(findings, [])

    def test_border_color_is_reported_when_border_style_is_solid(self) -> None:
        findings = comparison.compare_pair(
            pair_of(
                {"style": {"borderTopStyle": "solid", "borderTopWidth": "1px", "borderTopColor": "rgb(17, 24, 39)"}},
                {"style": {"borderTopStyle": "solid", "borderTopWidth": "1px", "borderTopColor": "rgb(0, 0, 0)"}},
            ),
            comparison.DEFAULT_TOLERANCES,
        )
        self.assertEqual(properties(findings), ["borderTopColor"])

    def test_exclude_style_skips_only_the_named_keys(self) -> None:
        pair = pair_of(
            {"style": {"marginTop": "0px", "marginBottom": "0px"}},
            {"style": {"marginTop": "8px", "marginBottom": "8px"}},
        )
        self.assertEqual(properties(comparison.compare_pair(pair, comparison.DEFAULT_TOLERANCES)), ["marginBottom", "marginTop"])
        self.assertEqual(
            properties(comparison.compare_pair(pair, comparison.DEFAULT_TOLERANCES, exclude_style=("marginTop",))),
            ["marginBottom"],
        )

    def test_exclude_style_leaves_semantic_and_geometry_findings_alone(self) -> None:
        pair = pair_of({"x": 0, "role": "button"}, {"x": 10, "role": ""})
        self.assertEqual(
            properties(comparison.compare_pair(pair, comparison.DEFAULT_TOLERANCES, exclude_style=("role",))),
            ["role", "x"],
        )

    def test_semantics_differences_are_style_findings_by_name(self) -> None:
        findings = comparison.compare_pair(
            pair_of({"role": "button", "focusable": True}, {"role": "", "focusable": False}),
            comparison.DEFAULT_TOLERANCES,
        )
        self.assertEqual(properties(findings), ["focusable", "role", "tabIndex"])
