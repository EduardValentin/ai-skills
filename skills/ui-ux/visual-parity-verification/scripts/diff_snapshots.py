#!/usr/bin/env python3
"""Compare a prototype subtree snapshot with a real app subtree snapshot.

Both inputs are produced by snapshot-subtree.browser.js. The result is one
JSON file with a verdict, aligned pairs, categorized findings and suggestions,
plus a one-line summary on stdout.
"""

from __future__ import annotations

import argparse
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
    return base_result(proto, real)


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
