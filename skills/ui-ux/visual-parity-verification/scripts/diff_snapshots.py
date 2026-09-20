#!/usr/bin/env python3
"""Compare a prototype subtree snapshot with a real app subtree snapshot.

Both inputs are produced by snapshot-subtree.browser.js. The result is one
JSON file with a verdict, aligned pairs, categorized findings and suggestions,
plus a one-line summary on stdout.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import gzip
import json
import re
import sys
from pathlib import Path
from typing import Any

CONDITION_FIELDS = (
    ("viewport.width", lambda s: s["viewport"]["width"]),
    ("viewport.height", lambda s: s["viewport"]["height"]),
    ("devicePixelRatio", lambda s: s["devicePixelRatio"]),
    ("zoom", lambda s: s["zoom"]),
    ("colorScheme", lambda s: s["colorScheme"]),
)
ROOT_SIZE_FACTOR = 2.0


class InputError(Exception):
    pass


def normalize_geometry(root: dict[str, Any]) -> None:
    """Rewrite the 2026-09-19 `{"relative": box, "viewport": box}` geometry
    shape to the flat box, in place, so old snapshots still load."""

    def walk(node: dict[str, Any]) -> None:
        geometry = node.get("geometry")
        if isinstance(geometry, dict) and "relative" in geometry:
            node["geometry"] = geometry["relative"]
        for child in node["children"]:
            walk(child)

    walk(root)


def inflate_styles(root: dict[str, Any]) -> dict[str, Any]:
    """Fill each node's `style` from its parent's already-inflated style,
    undoing the delta encoding snapshot-subtree.browser.js emits. Identity
    on a tree whose nodes already carry full styles."""

    def walk(node: dict[str, Any], parent_style: dict[str, Any] | None) -> None:
        if parent_style is not None:
            node["style"] = {**parent_style, **node["style"]}
        for child in node["children"]:
            walk(child, node["style"])

    walk(root, None)
    return root


def decode_gzip_base64_snapshot(path: Path, encoded: str) -> Any:
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except binascii.Error as error:
        raise InputError(f"{path} has invalid base64: {error}") from error
    try:
        decompressed = gzip.decompress(compressed)
    except (OSError, EOFError) as error:
        raise InputError(f"{path} has invalid or truncated gzip data: {error}") from error
    try:
        text = decompressed.decode("utf-8")
    except UnicodeDecodeError as error:
        raise InputError(f"{path} has invalid utf-8: {error}") from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise InputError(f"{path} is not valid JSON: {error.msg}") from error


def load_snapshot(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise InputError(f"cannot read {path}: {error.strerror}") from error
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise InputError(f"{path} is not valid JSON: {error.msg}") from error
    data = decode_gzip_base64_snapshot(path, parsed) if isinstance(parsed, str) else parsed
    if not isinstance(data, dict) or "root" not in data or "rootSummary" not in data:
        raise InputError(f"{path} is not a snapshot: missing root or rootSummary")
    normalize_geometry(data["root"])
    inflate_styles(data["root"])
    return data


def load_optional_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise InputError(f"cannot read {path}: {error.strerror}") from error
    except json.JSONDecodeError as error:
        raise InputError(f"{path} is not valid JSON: {error.msg}") from error


def condition_mismatches(proto: dict[str, Any], real: dict[str, Any]) -> list[dict[str, Any]]:
    mismatches = []
    for name, read in CONDITION_FIELDS:
        if read(proto) != read(real):
            mismatches.append({"condition": name, "prototype": read(proto), "real": read(real)})
    return mismatches


def root_incompatibility(proto: dict[str, Any], real: dict[str, Any]) -> dict[str, Any] | None:
    proto_root, real_root = proto["rootSummary"], real["rootSummary"]
    roles_conflict = bool(proto_root["role"]) and bool(real_root["role"]) and proto_root["role"] != real_root["role"]
    sizes_conflict = any(
        not _within_factor(proto_root[axis], real_root[axis], ROOT_SIZE_FACTOR)
        for axis in ("width", "height")
    )
    if roles_conflict or sizes_conflict:
        return {"prototype": proto_root, "real": real_root}
    return None


def _within_factor(a: float, b: float, factor: float) -> bool:
    if a <= 0 or b <= 0:
        return a == b
    return max(a, b) / min(a, b) <= factor


def collapse_wrappers(root: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    collapsed: list[dict[str, Any]] = []
    copied = copy.deepcopy(root)

    def flatten(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept: list[dict[str, Any]] = []
        for child in children:
            if child["wrapper"]:
                collapsed.append({"path": child["path"], "tag": child["tag"], "childCount": len(child["children"])})
                kept.extend(flatten(child["children"]))
            else:
                child["children"] = flatten(child["children"])
                kept.append(child)
        return kept

    copied["children"] = flatten(copied["children"])
    return copied, collapsed


def make_pair(proto: dict[str, Any], real: dict[str, Any], matched_by: str, score: float | None = None, signals: dict[str, float] | None = None) -> dict[str, Any]:
    return {"prototype": proto, "real": real, "matchedBy": matched_by, "score": score, "signals": signals}


def role_name_key(node: dict[str, Any]) -> str | None:
    if node["role"] and node["name"]:
        return f"{node['role']}\u0000{node['name']}"
    return None


def text_identity(node: dict[str, Any]) -> str:
    if node["ownText"]:
        return node["ownText"]
    parts: list[str] = []

    def visit(children: list[dict[str, Any]]) -> None:
        for child in children:
            if child["ownText"]:
                parts.append(child["ownText"])
            visit(child["children"])

    visit(node["children"])
    return " ".join(parts)


def text_key(node: dict[str, Any]) -> str | None:
    return text_identity(node) or None


def hook_key(node: dict[str, Any]) -> str | None:
    return node["hook"] or None


def unique_keys(nodes: list[dict[str, Any]], key) -> dict[str, dict[str, Any]]:
    seen: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        value = key(node)
        if value is not None:
            seen.setdefault(value, []).append(node)
    return {value: found[0] for value, found in seen.items() if len(found) == 1}


WEIGHTS = {"roleName": 0.35, "text": 0.20, "signature": 0.20, "geometry": 0.15, "fingerprint": 0.10}
THRESHOLD = 0.45
FINGERPRINT_KEYS = ("fontSize", "fontWeight", "color", "effectiveBackground", "borderTopLeftRadius")


def role_name_signal(a: dict[str, Any], b: dict[str, Any]) -> float:
    if not a["role"] or a["role"] != b["role"]:
        return 0.0
    if a["name"] and b["name"]:
        return 1.0 if a["name"] == b["name"] else 0.0
    return 0.5


def text_signal(a: dict[str, Any], b: dict[str, Any]) -> float:
    identity_a, identity_b = text_identity(a), text_identity(b)
    return 1.0 if identity_a and identity_a == identity_b else 0.0


def signature(node: dict[str, Any]) -> list[str]:
    roles: list[str] = []
    pending = list(node["children"])
    while pending:
        child = pending.pop(0)
        roles.append(child["role"] or child["tag"])
        pending = list(child["children"]) + pending
    return roles


def lcs_length(a: list[str], b: list[str]) -> int:
    previous = [0] * (len(b) + 1)
    for item in a:
        current = [0]
        for index, other in enumerate(b):
            current.append(previous[index] + 1 if item == other else max(previous[index + 1], current[index]))
        previous = current
    return previous[-1]


def signature_signal(a: dict[str, Any], b: dict[str, Any]) -> float:
    sa, sb = signature(a), signature(b)
    if not sa and not sb:
        return 0.5
    return lcs_length(sa, sb) / max(len(sa), len(sb))


def normalized_box(node: dict[str, Any], root: dict[str, Any]) -> tuple[float, float, float, float]:
    box = node["geometry"]
    width = root.get("width") or 1
    height = root.get("height") or 1
    return (
        (box["x"] + box["width"] / 2) / width,
        (box["y"] + box["height"] / 2) / height,
        box["width"] / width,
        box["height"] / height,
    )


def geometry_signal(a: dict[str, Any], b: dict[str, Any], context: dict[str, Any]) -> float:
    na = normalized_box(a, context.get("prototypeRoot", {}))
    nb = normalized_box(b, context.get("realRoot", {}))
    distance = sum(abs(x - y) for x, y in zip(na, nb))
    return max(0.0, 1.0 - distance)


def fingerprint_signal(a: dict[str, Any], b: dict[str, Any]) -> float:
    equal = 0
    for key in FINGERPRINT_KEYS:
        value_a, value_b = a["style"].get(key), b["style"].get(key)
        if key in COLOR_KEYS:
            equal += normalize_color(str(value_a)) == normalize_color(str(value_b))
        else:
            equal += value_a == value_b
    return equal / len(FINGERPRINT_KEYS)


def score_pair(a: dict[str, Any], b: dict[str, Any], context: dict[str, Any]) -> tuple[float, dict[str, float]]:
    signals = {
        "roleName": role_name_signal(a, b),
        "text": text_signal(a, b),
        "signature": signature_signal(a, b),
        "geometry": geometry_signal(a, b, context),
        "fingerprint": fingerprint_signal(a, b),
    }
    score = sum(WEIGHTS[name] * value for name, value in signals.items())
    return round(score, 4), signals


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


CONTRAST_NORMAL = 4.5
CONTRAST_LARGE = 3.0
INTERACTIVE_ROLES = frozenset({"button", "link", "checkbox", "radio", "switch", "tab", "menuitem", "combobox", "textbox", "slider", "option"})


def content_exclusions(pair: dict[str, Any], siblings: list[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    exclusions: dict[str, tuple[str, ...]] = {pair["prototype"]["path"]: ("x", "y", "width", "height")}
    for sibling in siblings:
        exclusions[sibling["path"]] = ("x", "y")
    return exclusions


def siblings_of(parent_pair: dict[str, Any] | None, node: dict[str, Any]) -> list[dict[str, Any]]:
    if parent_pair is None:
        return []
    return [child for child in parent_pair["prototype"]["children"] if child is not node]


def collect_findings(alignment: dict[str, Any], collapsed: dict[str, list[dict[str, Any]]], tolerances: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    findings: dict[str, list[dict[str, Any]]] = {"style": [], "geometry": [], "missing": [], "structure": [], "content": [], "accessibility": []}
    parent_of: dict[str, dict[str, Any]] = {}
    for pair in alignment["pairs"]:
        for child in pair["prototype"]["children"]:
            parent_of[child["path"]] = pair

    exclusions: dict[str, tuple[str, ...]] = {}
    for pair in alignment["pairs"]:
        proto, real = pair["prototype"], pair["real"]
        if proto["ownText"] != real["ownText"]:
            findings["content"].append({"path": proto["path"], "realPath": real["path"], "prototype": proto["ownText"], "real": real["ownText"]})
            for path, keys in content_exclusions(pair, siblings_of(parent_of.get(proto["path"]), proto)).items():
                exclusions[path] = tuple(sorted(set(exclusions.get(path, ())) | set(keys)))

    for pair in alignment["pairs"]:
        proto, real = pair["prototype"], pair["real"]
        skip_name = proto.get("nameFrom") == "content" and real.get("nameFrom") == "content"
        for finding in compare_pair(pair, tolerances, exclusions.get(proto["path"], ()), skip_name=skip_name):
            findings[finding["category"]].append(finding)
        if pair["matchedBy"] == "moved":
            findings["structure"].append({"kind": "moved", "prototype": pair["prototype"]["path"], "real": pair["real"]["path"]})

    suggestions_by_path = {(s["side"], s["path"]): s for s in alignment["suggestions"]}
    for side in ("prototype", "real"):
        for node in alignment["missing"][side]:
            suggestion = suggestions_by_path.get((side, node["path"]))
            findings["missing"].append({
                "side": side, "path": node["path"], "tag": node["tag"], "role": node["role"], "name": node["name"],
                "suggestion": None if suggestion is None else {"candidate": suggestion["candidate"], "score": suggestion["score"]},
            })

    if len(collapsed["prototype"]) != len(collapsed["real"]):
        findings["structure"].append({"kind": "collapsed-count", "prototype": len(collapsed["prototype"]), "real": len(collapsed["real"])})
    return findings


def accessibility_findings(alignment: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    nodes_by_side = {"prototype": [], "real": []}
    for pair in alignment["pairs"]:
        nodes_by_side["prototype"].append(pair["prototype"])
        nodes_by_side["real"].append(pair["real"])
    for side in ("prototype", "real"):
        nodes_by_side[side].extend(alignment["missing"][side])
    for side, nodes in nodes_by_side.items():
        for node in nodes:
            key = (side, node["path"])
            if key in seen:
                continue
            seen.add(key)
            interactive = node["focusable"] or node["role"] in INTERACTIVE_ROLES
            if interactive and not node["role"]:
                findings.append({"side": side, "path": node["path"], "check": "missing-role"})
            if node["role"] in INTERACTIVE_ROLES and not node["name"]:
                findings.append({"side": side, "path": node["path"], "check": "missing-name"})
            contrast = node.get("contrast")
            if contrast is None or not node["ownText"]:
                continue
            if contrast["needsAnalyzer"] or contrast["ratio"] is None:
                findings.append({"side": side, "path": node["path"], "check": "contrast-unmeasurable"})
                continue
            threshold = CONTRAST_LARGE if contrast["largeText"] else CONTRAST_NORMAL
            if contrast["ratio"] < threshold:
                findings.append({"side": side, "path": node["path"], "check": "contrast", "ratio": contrast["ratio"], "threshold": threshold})
    return findings


def needs_review(pair: dict[str, Any]) -> bool:
    return pair["matchedBy"] == "score" and pair["signals"]["roleName"] < 1 and pair["signals"]["text"] == 0


def verdict_for(findings: dict[str, list[dict[str, Any]]]) -> str:
    if findings["style"] or findings["geometry"]:
        return "DRIFT"
    if findings["missing"]:
        return "MISSING"
    return "MATCH"


def gap_index(node: dict[str, Any], ordered: list[dict[str, Any]], anchors_on_side: list[dict[str, Any]]) -> int:
    position = ordered.index(node)
    return sum(1 for anchor in anchors_on_side if ordered.index(anchor) < position)


def best_scored_pairs(proto_nodes: list[dict[str, Any]], real_nodes: list[dict[str, Any]], context: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    remaining_proto = list(proto_nodes)
    remaining_real = list(real_nodes)
    pairs: list[dict[str, Any]] = []
    while remaining_proto and remaining_real:
        best: tuple[float, dict[str, float], dict[str, Any], dict[str, Any]] | None = None
        for proto in remaining_proto:
            for real in remaining_real:
                score, signals = score_pair(proto, real, context)
                if best is None or score > best[0] or (score == best[0] and proto["tag"] == real["tag"] and best[2]["tag"] != best[3]["tag"]):
                    best = (score, signals, proto, real)
        if best is None or best[0] < THRESHOLD:
            break
        score, signals, proto, real = best
        pairs.append(make_pair(proto, real, "score", score, signals))
        remaining_proto.remove(proto)
        remaining_real.remove(real)
    return pairs, remaining_proto, remaining_real


def fill_pass(anchors: list[dict[str, Any]], proto_children: list[dict[str, Any]], real_children: list[dict[str, Any]], remaining_proto: list[dict[str, Any]], remaining_real: list[dict[str, Any]], context: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    proto_anchors = [pair["prototype"] for pair in anchors]
    real_anchors = [pair["real"] for pair in anchors]
    gaps: dict[int, tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {}
    for node in remaining_proto:
        gaps.setdefault(gap_index(node, proto_children, proto_anchors), ([], []))[0].append(node)
    for node in remaining_real:
        gaps.setdefault(gap_index(node, real_children, real_anchors), ([], []))[1].append(node)
    pairs: list[dict[str, Any]] = []
    leftover_proto: list[dict[str, Any]] = []
    leftover_real: list[dict[str, Any]] = []
    for gap in sorted(gaps):
        gap_pairs, gap_proto, gap_real = best_scored_pairs(gaps[gap][0], gaps[gap][1], context)
        pairs.extend(gap_pairs)
        leftover_proto.extend(gap_proto)
        leftover_real.extend(gap_real)
    global_pairs, leftover_proto, leftover_real = best_scored_pairs(leftover_proto, leftover_real, context)
    pairs.extend(global_pairs)
    return pairs, leftover_proto, leftover_real


def suggest(side: str, node: dict[str, Any], candidates: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any] | None:
    best: tuple[float, dict[str, Any]] | None = None
    for candidate in candidates:
        proto, real = (node, candidate) if side == "prototype" else (candidate, node)
        score, _ = score_pair(proto, real, context)
        if best is None or score > best[0]:
            best = (score, candidate)
    if best is None:
        return None
    return {"side": side, "path": node["path"], "candidate": best[1]["path"], "score": best[0]}


def moved_pass(alignment: dict[str, Any]) -> None:
    proto_unique = unique_keys(alignment["missing"]["prototype"], role_name_key)
    real_unique = unique_keys(alignment["missing"]["real"], role_name_key)
    for key, proto in proto_unique.items():
        real = real_unique.get(key)
        if real is None:
            continue
        alignment["pairs"].append(make_pair(proto, real, "moved"))
        alignment["missing"]["prototype"].remove(proto)
        alignment["missing"]["real"].remove(real)
        alignment["suggestions"] = [
            s for s in alignment["suggestions"]
            if (s["side"], s["path"]) not in (("prototype", proto["path"]), ("real", real["path"]))
        ]


def anchor_pass(proto_children: list[dict[str, Any]], real_children: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    pairs: list[dict[str, Any]] = []
    remaining_proto = list(proto_children)
    remaining_real = list(real_children)

    def take(proto: dict[str, Any], real: dict[str, Any], rule: str) -> None:
        pairs.append(make_pair(proto, real, rule))
        remaining_proto.remove(proto)
        remaining_real.remove(real)

    for rule, key in (("hook", hook_key), ("role-name", role_name_key), ("text", text_key)):
        proto_unique = unique_keys(remaining_proto, key)
        real_unique = unique_keys(remaining_real, key)
        for value, proto in proto_unique.items():
            if value in real_unique:
                take(proto, real_unique[value], rule)

    return pairs, remaining_proto, remaining_real


def align_children(proto_children: list[dict[str, Any]], real_children: list[dict[str, Any]], context: dict[str, Any], alignment: dict[str, Any]) -> None:
    anchors, remaining_proto, remaining_real = anchor_pass(proto_children, real_children)
    scored, leftover_proto, leftover_real = fill_pass(anchors, proto_children, real_children, remaining_proto, remaining_real, context)
    pairs = anchors + scored
    alignment["pairs"].extend(pairs)
    for node in leftover_proto:
        suggestion = suggest("prototype", node, leftover_real, context)
        if suggestion:
            alignment["suggestions"].append(suggestion)
    for node in leftover_real:
        suggestion = suggest("real", node, leftover_proto, context)
        if suggestion:
            alignment["suggestions"].append(suggestion)
    alignment["missing"]["prototype"].extend(leftover_proto)
    alignment["missing"]["real"].extend(leftover_real)
    for pair in pairs:
        align_children(pair["prototype"]["children"], pair["real"]["children"], context, alignment)


def index_by_path(root: dict[str, Any]) -> dict[str, tuple[dict[str, Any], dict[str, Any] | None]]:
    index: dict[str, tuple[dict[str, Any], dict[str, Any] | None]] = {}

    def walk(node: dict[str, Any], parent: dict[str, Any] | None) -> None:
        index[node["path"]] = (node, parent)
        for child in node["children"]:
            walk(child, node)

    walk(root, None)
    return index


def apply_global_pairings(proto_root: dict[str, Any], real_root: dict[str, Any], pairings: dict[str, str], alignment: dict[str, Any]) -> list[dict[str, Any]]:
    proto_index = index_by_path(proto_root)
    real_index = index_by_path(real_root)
    pairs: list[dict[str, Any]] = []
    for proto_path in sorted(pairings):
        real_path = pairings[proto_path]
        proto_entry = proto_index.get(proto_path)
        real_entry = real_index.get(real_path)
        if proto_entry is None or real_entry is None:
            continue
        proto_node, proto_parent = proto_entry
        real_node, real_parent = real_entry
        if proto_parent is None or real_parent is None:
            continue
        if proto_node not in proto_parent["children"] or real_node not in real_parent["children"]:
            continue
        proto_parent["children"].remove(proto_node)
        real_parent["children"].remove(real_node)
        pair = make_pair(proto_node, real_node, "pairing")
        alignment["pairs"].append(pair)
        pairs.append(pair)
    return pairs


def align_trees(proto_root: dict[str, Any], real_root: dict[str, Any], pairings: dict[str, str], context: dict[str, Any] | None = None) -> dict[str, Any]:
    alignment: dict[str, Any] = {
        "pairs": [make_pair(proto_root, real_root, "root")],
        "missing": {"prototype": [], "real": []},
        "suggestions": [],
    }
    global_pairs = apply_global_pairings(proto_root, real_root, pairings, alignment)
    align_children(proto_root["children"], real_root["children"], context or {}, alignment)
    moved_pass(alignment)
    for pair in [p for p in alignment["pairs"] if p["matchedBy"] == "moved"]:
        align_children(pair["prototype"]["children"], pair["real"]["children"], context or {}, alignment)
    for pair in global_pairs:
        align_children(pair["prototype"]["children"], pair["real"]["children"], context or {}, alignment)
    return alignment


def conditions_of(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "viewport": snapshot["viewport"],
        "devicePixelRatio": snapshot["devicePixelRatio"],
        "zoom": snapshot["zoom"],
        "colorScheme": snapshot["colorScheme"],
    }


def base_result(proto: dict[str, Any], real: dict[str, Any]) -> dict[str, Any]:
    return {
        "verdict": "MATCH",
        "conditions": conditions_of(proto),
        "urls": {"prototype": proto["url"], "real": real["url"]},
        "rootSummaries": {"prototype": proto["rootSummary"], "real": real["rootSummary"]},
        "blocked": None,
        "pairs": [],
        "findings": {"style": [], "geometry": [], "missing": [], "structure": [], "content": [], "accessibility": []},
        "collapsed": {"prototype": [], "real": []},
        "suggestions": [],
        "lowestScore": None,
    }


def blocked(reason: str, detail: Any, proto: dict[str, Any], real: dict[str, Any]) -> dict[str, Any]:
    result = base_result(proto, real)
    result["verdict"] = "BLOCKED"
    result["blocked"] = {"reason": reason, "detail": detail}
    return result


def summary_line(result: dict[str, Any]) -> str:
    counts = " ".join(f"{name}={len(items)}" for name, items in result["findings"].items())
    lowest = result["lowestScore"]
    lowest_text = "n/a" if lowest is None else f"{lowest:.2f}"
    if result["blocked"]:
        return f"BLOCKED {result['blocked']['reason']} {counts} lowestScore={lowest_text}"
    return f"{result['verdict']} {counts} lowestScore={lowest_text}"


def write_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def compare_snapshots(proto: dict[str, Any], real: dict[str, Any], pairings: dict[str, Any], tolerances: dict[str, Any]) -> dict[str, Any]:
    mismatches = condition_mismatches(proto, real)
    if mismatches:
        return blocked("condition-mismatch", mismatches, proto, real)
    incompatible = root_incompatibility(proto, real)
    if incompatible:
        return blocked("roots-incompatible", incompatible, proto, real)

    effective_tolerances = dict(DEFAULT_TOLERANCES, **tolerances)
    result = base_result(proto, real)
    proto_root, result["collapsed"]["prototype"] = collapse_wrappers(proto["root"])
    real_root, result["collapsed"]["real"] = collapse_wrappers(real["root"])
    context = {"prototypeRoot": proto["rootSummary"], "realRoot": real["rootSummary"]}
    alignment = align_trees(proto_root, real_root, pairings, context)

    result["pairs"] = [
        {
            "prototype": p["prototype"]["path"],
            "real": p["real"]["path"],
            "matchedBy": p["matchedBy"],
            "score": p["score"],
            "signals": p["signals"],
            "needsReview": needs_review(p),
        }
        for p in alignment["pairs"]
    ]
    result["suggestions"] = alignment["suggestions"]
    scores = [p["score"] for p in alignment["pairs"] if p["matchedBy"] == "score"]
    result["lowestScore"] = min(scores) if scores else None

    result["findings"] = collect_findings(alignment, result["collapsed"], effective_tolerances)
    result["findings"]["accessibility"] = accessibility_findings(alignment)
    result["verdict"] = verdict_for(result["findings"])
    return result


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prototype", required=True, type=Path, help="prototype snapshot JSON")
    parser.add_argument("--real", required=True, type=Path, help="real app snapshot JSON")
    parser.add_argument("--out", required=True, type=Path, help="where to write the diff JSON")
    parser.add_argument("--pairings", type=Path, help="pairings.json with confirmed manual matches")
    parser.add_argument("--row", help="ledger row id whose pairings apply")
    parser.add_argument("--tolerances", type=Path, help="JSON overriding default tolerances")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    arguments = parse_arguments(argv)
    try:
        proto = load_snapshot(arguments.prototype)
        real = load_snapshot(arguments.real)
        all_pairings = load_optional_json(arguments.pairings)
        tolerances = load_optional_json(arguments.tolerances)
    except InputError as error:
        print(str(error), file=sys.stderr)
        return 2
    if arguments.pairings and not arguments.row:
        print("--pairings is ignored without --row", file=sys.stderr)
    row_pairings = all_pairings.get(arguments.row, {}) if arguments.row else {}
    result = compare_snapshots(proto, real, row_pairings, tolerances)
    write_result(arguments.out, result)
    print(summary_line(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
