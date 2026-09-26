#!/usr/bin/env python3
"""Compare a prototype subtree snapshot with a real app subtree snapshot.

Both inputs are produced by snapshot-subtree.browser.js. The result is one
JSON file with a verdict, aligned pairs, categorized findings and suggestions,
plus a one-line summary on stdout.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from parity_diff import alignment, comparison, findings, loading

CONDITION_FIELDS = (
    ("viewport.width", lambda s: s["viewport"]["width"]),
    ("viewport.height", lambda s: s["viewport"]["height"]),
    ("devicePixelRatio", lambda s: s["devicePixelRatio"]),
    ("zoom", lambda s: s["zoom"]),
    ("colorScheme", lambda s: s["colorScheme"]),
)
ROOT_SIZE_FACTOR = 2.0


def condition_mismatches(proto: dict[str, Any], real: dict[str, Any]) -> list[dict[str, Any]]:
    mismatches = []
    for name, read in CONDITION_FIELDS:
        if read(proto) != read(real):
            mismatches.append({"condition": name, "prototype": read(proto), "real": read(real)})
    return mismatches


def _within_factor(a: float, b: float, factor: float) -> bool:
    if a <= 0 or b <= 0:
        return a == b
    return max(a, b) / min(a, b) <= factor


def _child_signatures_agree(a: list[str], b: list[str]) -> bool:
    longest = max(len(a), len(b))
    return alignment.lcs_length(a, b) >= math.ceil(longest / 2)


def root_incompatibility(proto: dict[str, Any], real: dict[str, Any]) -> dict[str, Any] | None:
    proto_root = dict(proto["rootSummary"], childSignature=alignment.child_signature(proto["root"]))
    real_root = dict(real["rootSummary"], childSignature=alignment.child_signature(real["root"]))
    roles_conflict = bool(proto_root["role"]) and bool(real_root["role"]) and proto_root["role"] != real_root["role"]
    tags_conflict = proto_root["tag"] != real_root["tag"]
    sizes_conflict = any(
        not _within_factor(proto_root[axis], real_root[axis], ROOT_SIZE_FACTOR)
        for axis in ("width", "height")
    )
    children_conflict = not _child_signatures_agree(proto_root["childSignature"], real_root["childSignature"])
    if roles_conflict or tags_conflict or sizes_conflict or children_conflict:
        return {"prototype": proto_root, "real": real_root}
    return None


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
        "findings": {"style": [], "geometry": [], "missing": [], "structure": [], "content": [], "accessibility": [], "ignored": []},
        "collapsed": {"prototype": [], "real": []},
        "suggestions": [],
        "unappliedPairings": [],
        "hookSuggestions": [],
        "lowestScore": None,
    }


def blocked(result: dict[str, Any], reason: str, detail: Any) -> dict[str, Any]:
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


def compare_snapshots(proto: dict[str, Any], real: dict[str, Any], pairings: dict[str, Any], tolerances: dict[str, Any], ignore: dict[str, list[dict[str, str]]] | None = None) -> dict[str, Any]:
    result = base_result(proto, real)
    mismatches = condition_mismatches(proto, real)
    if mismatches:
        return blocked(result, "condition-mismatch", mismatches)
    result["findings"]["ignored"] = loading.prune_ignored_snapshots(proto, real, ignore or {})
    incompatible = root_incompatibility(proto, real)
    if incompatible:
        return blocked(result, "roots-incompatible", incompatible)

    effective_tolerances = dict(comparison.DEFAULT_TOLERANCES, **tolerances)
    proto_root, result["collapsed"]["prototype"] = alignment.collapse_wrappers(proto["root"])
    real_root, result["collapsed"]["real"] = alignment.collapse_wrappers(real["root"])
    context = {"prototypeRoot": proto["rootSummary"], "realRoot": real["rootSummary"]}
    tree_alignment = alignment.align_trees(proto_root, real_root, pairings, context)

    result["pairs"] = [
        {
            "prototype": p["prototype"]["path"],
            "real": p["real"]["path"],
            "matchedBy": p["matchedBy"],
            "score": p["score"],
            "signals": p["signals"],
            "needsReview": alignment.needs_review(p),
            "hooks": {"prototype": alignment.hook_key(p["prototype"]), "real": alignment.hook_key(p["real"])},
        }
        for p in tree_alignment["pairs"]
    ]
    result["suggestions"] = tree_alignment["suggestions"]
    result["unappliedPairings"] = tree_alignment["unappliedPairings"]
    result["hookSuggestions"] = findings.hook_suggestions(result["pairs"])
    scores = [p["score"] for p in tree_alignment["pairs"] if p["matchedBy"] == "score"]
    result["lowestScore"] = min(scores) if scores else None

    result["findings"].update(findings.collect_findings(tree_alignment, result["collapsed"], effective_tolerances))
    result["findings"]["accessibility"] = findings.accessibility_findings(tree_alignment)
    result["verdict"] = findings.verdict_for(result["findings"])
    return result


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prototype", required=True, type=Path, help="prototype snapshot JSON")
    parser.add_argument("--real", required=True, type=Path, help="real app snapshot JSON")
    parser.add_argument("--out", required=True, type=Path, help="where to write the diff JSON")
    parser.add_argument("--pairings", type=Path, help="parity-pairings.json with confirmed manual matches")
    parser.add_argument("--row", help="map id whose pairings apply (parity-pairings.json key)")
    parser.add_argument("--tolerances", type=Path, help="JSON overriding default tolerances")
    parser.add_argument("--ignore-prototype", action="append", default=[], metavar="ENTRY", help="hook:<value> or path:<prefix> to prune from the prototype")
    parser.add_argument("--ignore-real", action="append", default=[], metavar="ENTRY", help="hook:<value> or path:<prefix> to prune from the real app")
    parser.add_argument("--print-review", action="store_true", help="print review lines after summary")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    arguments = parse_arguments(argv)
    if arguments.pairings and not arguments.row:
        print("--pairings is ignored without --row", file=sys.stderr)
    try:
        proto = loading.load_snapshot(arguments.prototype)
        real = loading.load_snapshot(arguments.real)
        all_pairings = loading.load_optional_json(arguments.pairings)
        tolerances = loading.load_optional_json(arguments.tolerances)
        ignore = {"prototype": loading.parse_ignore_entries(arguments.ignore_prototype), "real": loading.parse_ignore_entries(arguments.ignore_real)}
        row_pairings = all_pairings.get(arguments.row, {}) if arguments.row else {}
        result = compare_snapshots(proto, real, row_pairings, tolerances, ignore)
    except loading.InputError as error:
        print(str(error), file=sys.stderr)
        return 2
    write_result(arguments.out, result)
    print(summary_line(result))
    if arguments.print_review:
        for line in findings.review_lines(result):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
