"""Tolerances and value comparison for one aligned pair of nodes."""

from __future__ import annotations

import re
from typing import Any

DEFAULT_TOLERANCES: dict[str, Any] = {"lengthPx": 0.5, "normalLineHeightFactor": 1.2}
COLOR_KEYS = frozenset({
    "color", "backgroundColor", "effectiveBackground",
    "borderTopColor", "borderRightColor", "borderBottomColor", "borderLeftColor", "outlineColor",
})
GEOMETRY_KEYS = ("x", "y", "width", "height")
SEMANTIC_KEYS = ("role", "name", "focusable", "tabIndex", "state")
IDENTITY_MATRIX = "matrix(1, 0, 0, 1, 0, 0)"
_PX = re.compile(r"^(-?\d+(?:\.\d+)?)px$")
_RGB = re.compile(r"^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)$")
_RGB_SLASH = re.compile(r"^rgba?\(\s*(\d+)\s+(\d+)\s+(\d+)\s*(?:/\s*([\d.]+%?)\s*)?\)$")


def parse_px(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    match = _PX.match(value.strip())
    return float(match.group(1)) if match else None


def normalize_color(value: str) -> str:
    text = value.strip().lower()
    if text == "transparent":
        return "rgba(0, 0, 0, 0)"
    if text.startswith("#"):
        digits = text[1:]
        if len(digits) in (3, 4):
            digits = "".join(ch * 2 for ch in digits)
        if len(digits) in (6, 8):
            r, g, b = (int(digits[i:i + 2], 16) for i in (0, 2, 4))
            alpha = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1
            return f"rgba({r}, {g}, {b}, {_format_alpha(alpha)})"
        return text
    match = _RGB.match(text) or _RGB_SLASH.match(text)
    if match:
        r, g, b, alpha = match.groups()
        alpha_value = 1.0 if alpha is None else (float(alpha[:-1]) / 100 if alpha.endswith("%") else float(alpha))
        return f"rgba({int(r)}, {int(g)}, {int(b)}, {_format_alpha(alpha_value)})"
    return text


def _format_alpha(alpha: float) -> str:
    rounded = round(alpha, 3)
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:g}"


def normalize_font_family(value: str) -> list[str]:
    return [part.strip().strip("'\"").lower() for part in value.split(",") if part.strip()]


def resolve_line_height(value: str, font_size: str, tolerances: dict[str, Any]) -> float | None:
    if value.strip() == "normal":
        size = parse_px(font_size)
        return None if size is None else size * tolerances["normalLineHeightFactor"]
    return parse_px(value)


def values_equal(key: str, a: Any, b: Any, tolerances: dict[str, Any], font_size_a: str = "", font_size_b: str = "") -> bool:
    if key in COLOR_KEYS:
        return normalize_color(str(a)) == normalize_color(str(b))
    if key == "fontFamily":
        return normalize_font_family(str(a)) == normalize_font_family(str(b))
    if key == "lineHeight":
        ra, rb = resolve_line_height(str(a), font_size_a, tolerances), resolve_line_height(str(b), font_size_b, tolerances)
        if ra is not None and rb is not None:
            return abs(ra - rb) <= tolerances["lengthPx"]
        return str(a) == str(b)
    if key == "transform":
        return (a if a != "none" else IDENTITY_MATRIX) == (b if b != "none" else IDENTITY_MATRIX)
    pa, pb = parse_px(a), parse_px(b)
    if pa is not None and pb is not None:
        return abs(pa - pb) <= tolerances["lengthPx"]
    return a == b


EDGE_COLOR_SOURCES = {
    "borderTopColor": ("borderTopStyle", "borderTopWidth"),
    "borderRightColor": ("borderRightStyle", "borderRightWidth"),
    "borderBottomColor": ("borderBottomStyle", "borderBottomWidth"),
    "borderLeftColor": ("borderLeftStyle", "borderLeftWidth"),
    "outlineColor": ("outlineStyle", "outlineWidth"),
}


def is_invisible_edge_color(key: str, proto_style: dict[str, Any], real_style: dict[str, Any]) -> bool:
    sources = EDGE_COLOR_SOURCES.get(key)
    if sources is None:
        return False
    style_key, width_key = sources
    if proto_style.get(style_key) == "none" and real_style.get(style_key) == "none":
        return True
    return parse_px(proto_style.get(width_key)) == 0 and parse_px(real_style.get(width_key)) == 0


def compare_pair(pair: dict[str, Any], tolerances: dict[str, Any], exclude_geometry: tuple[str, ...] = (), *, skip_name: bool = False) -> list[dict[str, Any]]:
    proto, real = pair["prototype"], pair["real"]
    findings: list[dict[str, Any]] = []

    def record(category: str, key: str, a: Any, b: Any) -> None:
        findings.append({"category": category, "path": proto["path"], "realPath": real["path"], "property": key, "prototype": a, "real": b})

    for key in SEMANTIC_KEYS:
        if key == "name" and skip_name:
            continue
        if proto.get(key) != real.get(key):
            record("style", key, proto.get(key), real.get(key))
    for key in sorted(set(proto["style"]) | set(real["style"])):
        if is_invisible_edge_color(key, proto["style"], real["style"]):
            continue
        a, b = proto["style"].get(key), real["style"].get(key)
        if not values_equal(key, a, b, tolerances, proto["style"].get("fontSize", ""), real["style"].get("fontSize", "")):
            record("style", key, a, b)
    for key in GEOMETRY_KEYS:
        if key in exclude_geometry:
            continue
        a, b = proto["geometry"][key], real["geometry"][key]
        if abs(float(a) - float(b)) > tolerances["lengthPx"]:
            record("geometry", key, a, b)
    return findings
