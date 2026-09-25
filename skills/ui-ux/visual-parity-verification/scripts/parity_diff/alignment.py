"""Collapse wrappers and align prototype and real trees into pairs."""

from __future__ import annotations

import copy
from typing import Any

from .comparison import COLOR_KEYS, normalize_color


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


def child_signature(root: dict[str, Any]) -> list[str]:
    roles: list[str] = []

    def visit(children: list[dict[str, Any]]) -> None:
        for child in children:
            if child["wrapper"]:
                visit(child["children"])
            else:
                roles.append(child["role"] or child["tag"])

    visit(root["children"])
    return roles


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


def shape_of(nodes: list[dict[str, Any]]) -> list[str]:
    return [node["role"] or node["tag"] for node in nodes]


def structural_twins(proto_nodes: list[dict[str, Any]], real_nodes: list[dict[str, Any]]) -> bool:
    return bool(proto_nodes) and shape_of(proto_nodes) == shape_of(real_nodes)


def position_pairs(proto_nodes: list[dict[str, Any]], real_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [make_pair(proto, real, "position") for proto, real in zip(proto_nodes, real_nodes)]


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
        gap_proto, gap_real = gaps[gap]
        if structural_twins(gap_proto, gap_real):
            pairs.extend(position_pairs(gap_proto, gap_real))
            continue
        gap_pairs, gap_proto, gap_real = best_scored_pairs(gap_proto, gap_real, context)
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


def needs_review(pair: dict[str, Any]) -> bool:
    return pair["matchedBy"] == "score" and pair["signals"]["roleName"] < 1 and pair["signals"]["text"] == 0
