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
    pairs, remaining_proto, remaining_real = anchor_pass(proto_children, real_children, pairings)
    alignment["pairs"].extend(pairs)
    alignment["missing"]["prototype"].extend(remaining_proto)
    alignment["missing"]["real"].extend(remaining_real)
    for pair in pairs:
        align_children(pair["prototype"]["children"], pair["real"]["children"], pairings, context, alignment)


def align_trees(proto_root: dict[str, Any], real_root: dict[str, Any], pairings: dict[str, str], context: dict[str, Any] | None = None) -> dict[str, Any]:
    alignment: dict[str, Any] = {
        "pairs": [make_pair(proto_root, real_root, "root")],
        "missing": {"prototype": [], "real": []},
        "suggestions": [],
    }
    align_children(proto_root["children"], real_root["children"], pairings, context or {}, alignment)
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
    alignment = align_trees(proto_root, real_root, pairings)
    result["pairs"] = [
        {"prototype": p["prototype"]["path"], "real": p["real"]["path"], "matchedBy": p["matchedBy"], "score": p["score"], "signals": p["signals"]}
        for p in alignment["pairs"]
    ]
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
