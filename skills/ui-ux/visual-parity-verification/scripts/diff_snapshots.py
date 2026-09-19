#!/usr/bin/env python3
"""Compare a prototype subtree snapshot with a real app subtree snapshot.

Both inputs are produced by snapshot-subtree.browser.js. The result is one
JSON file with a verdict, aligned pairs, categorized findings and suggestions,
plus a one-line summary on stdout.
"""

from __future__ import annotations

import argparse
import copy
import json
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
VERDICT_ORDER = ("BLOCKED", "DRIFT", "MISSING", "MATCH")


class InputError(Exception):
    pass


def load_snapshot(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise InputError(f"cannot read {path}: {error.strerror}") from error
    except json.JSONDecodeError as error:
        raise InputError(f"{path} is not valid JSON: {error.msg}") from error
    if not isinstance(data, dict) or "root" not in data or "rootSummary" not in data:
        raise InputError(f"{path} is not a snapshot: missing root or rootSummary")
    return data


def load_optional_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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


def text_key(node: dict[str, Any]) -> str | None:
    return node["ownText"] or None


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
    return 1.0 if a["ownText"] and a["ownText"] == b["ownText"] else 0.0


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
    box = node["geometry"]["relative"]
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
    equal = sum(1 for key in FINGERPRINT_KEYS if a["style"].get(key) == b["style"].get(key))
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
        alignment["suggestions"] = [s for s in alignment["suggestions"] if s["path"] not in (proto["path"], real["path"])]


def anchor_pass(proto_children: list[dict[str, Any]], real_children: list[dict[str, Any]], pairings: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    pairs: list[dict[str, Any]] = []
    remaining_proto = list(proto_children)
    remaining_real = list(real_children)

    def take(proto: dict[str, Any], real: dict[str, Any], rule: str) -> None:
        pairs.append(make_pair(proto, real, rule))
        remaining_proto.remove(proto)
        remaining_real.remove(real)

    real_by_path = {node["path"]: node for node in remaining_real}
    for proto in list(remaining_proto):
        target = pairings.get(proto["path"])
        if target in real_by_path and real_by_path[target] in remaining_real:
            take(proto, real_by_path[target], "pairing")

    real_by_hook = {node["hook"]: node for node in remaining_real if node["hook"]}
    for proto in list(remaining_proto):
        if proto["hook"] and proto["hook"] in real_by_hook and real_by_hook[proto["hook"]] in remaining_real:
            take(proto, real_by_hook[proto["hook"]], "hook")

    for rule, key in (("role-name", role_name_key), ("text", text_key)):
        proto_unique = unique_keys(remaining_proto, key)
        real_unique = unique_keys(remaining_real, key)
        for value, proto in proto_unique.items():
            if value in real_unique:
                take(proto, real_unique[value], rule)

    return pairs, remaining_proto, remaining_real


def align_children(proto_children: list[dict[str, Any]], real_children: list[dict[str, Any]], pairings: dict[str, str], context: dict[str, Any], alignment: dict[str, Any]) -> None:
    anchors, remaining_proto, remaining_real = anchor_pass(proto_children, real_children, pairings)
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
        align_children(pair["prototype"]["children"], pair["real"]["children"], pairings, context, alignment)


def align_trees(proto_root: dict[str, Any], real_root: dict[str, Any], pairings: dict[str, str], context: dict[str, Any] | None = None) -> dict[str, Any]:
    alignment: dict[str, Any] = {
        "pairs": [make_pair(proto_root, real_root, "root")],
        "missing": {"prototype": [], "real": []},
        "suggestions": [],
    }
    align_children(proto_root["children"], real_root["children"], pairings, context or {}, alignment)
    moved_pass(alignment)
    for pair in [p for p in alignment["pairs"] if p["matchedBy"] == "moved"]:
        align_children(pair["prototype"]["children"], pair["real"]["children"], pairings, context or {}, alignment)
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
    if result["blocked"]:
        return f"BLOCKED {result['blocked']['reason']}"
    counts = " ".join(f"{name}={len(items)}" for name, items in result["findings"].items())
    lowest = result["lowestScore"]
    lowest_text = "n/a" if lowest is None else f"{lowest:.2f}"
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
    result = base_result(proto, real)
    proto_root, result["collapsed"]["prototype"] = collapse_wrappers(proto["root"])
    real_root, result["collapsed"]["real"] = collapse_wrappers(real["root"])
    context = {"prototypeRoot": proto["rootSummary"], "realRoot": real["rootSummary"]}
    alignment = align_trees(proto_root, real_root, pairings, context)
    result["pairs"] = [
        {"prototype": p["prototype"]["path"], "real": p["real"]["path"], "matchedBy": p["matchedBy"], "score": p["score"], "signals": p["signals"]}
        for p in alignment["pairs"]
    ]
    result["suggestions"] = alignment["suggestions"]
    scores = [p["score"] for p in alignment["pairs"] if p["matchedBy"] == "score"]
    result["lowestScore"] = min(scores) if scores else None
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
    row_pairings = all_pairings.get(arguments.row, {}) if arguments.row else {}
    result = compare_snapshots(proto, real, row_pairings, tolerances)
    write_result(arguments.out, result)
    print(summary_line(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
