"""Categorize aligned pairs into findings, accessibility checks and a verdict."""

from __future__ import annotations

from typing import Any

from .comparison import compare_pair

CONTRAST_NORMAL = 4.5
CONTRAST_LARGE = 3.0
INTERACTIVE_ROLES = frozenset({"button", "link", "checkbox", "radio", "switch", "tab", "menuitem", "combobox", "textbox", "slider", "option"})
ROOT_GEOMETRY_EXCLUSIONS = ("x", "y", "width", "height")
ROOT_STYLE_EXCLUSIONS = ("marginTop", "marginRight", "marginBottom", "marginLeft")


def content_exclusions(pair: dict[str, Any], siblings: list[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    exclusions: dict[str, tuple[str, ...]] = {pair["prototype"]["path"]: ("x", "y", "width", "height")}
    for sibling in siblings:
        exclusions[sibling["path"]] = ("x", "y")
    return exclusions


def siblings_of(family: list[dict[str, Any]] | None, node: dict[str, Any]) -> list[dict[str, Any]]:
    """Siblings from the pre-detachment children list, so a globally paired
    node still shields and is shielded by the nodes it was rendered among."""
    if family is None:
        return []
    return [child for child in family if child is not node]


def families_by_member(original_children: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {child["path"]: family for family in original_children.values() for child in family}


def collect_findings(alignment: dict[str, Any], collapsed: dict[str, list[dict[str, Any]]], tolerances: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    findings: dict[str, list[dict[str, Any]]] = {"style": [], "geometry": [], "missing": [], "structure": [], "content": [], "accessibility": []}
    family_of = families_by_member(alignment["originalChildren"])

    exclusions: dict[str, tuple[str, ...]] = {}
    for pair in alignment["pairs"]:
        proto, real = pair["prototype"], pair["real"]
        if proto["ownText"] != real["ownText"]:
            findings["content"].append({"path": proto["path"], "realPath": real["path"], "prototype": proto["ownText"], "real": real["ownText"]})
            for path, keys in content_exclusions(pair, siblings_of(family_of.get(proto["path"]), proto)).items():
                exclusions[path] = tuple(sorted(set(exclusions.get(path, ())) | set(keys)))

    for pair in alignment["pairs"]:
        proto, real = pair["prototype"], pair["real"]
        skip_name = proto.get("nameFrom") == "content" and real.get("nameFrom") == "content"
        is_root = pair["matchedBy"] == "root"
        exclude_geometry = exclusions.get(proto["path"], ()) + (ROOT_GEOMETRY_EXCLUSIONS if is_root else ())
        exclude_style = ROOT_STYLE_EXCLUSIONS if is_root else ()
        for finding in compare_pair(pair, tolerances, exclude_geometry, exclude_style=exclude_style, skip_name=skip_name):
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


def verdict_for(findings: dict[str, list[dict[str, Any]]]) -> str:
    if findings["style"] or findings["geometry"]:
        return "DRIFT"
    if findings["missing"]:
        return "MISSING"
    return "MATCH"


def review_lines(result: dict[str, Any]) -> list[str]:
    if result["blocked"]:
        return ["review blocked"]
    lines: list[str] = []
    for pair in result["pairs"]:
        if pair["needsReview"]:
            role_name = pair["signals"]["roleName"] if pair["signals"] else None
            text = pair["signals"]["text"] if pair["signals"] else None
            lines.append(
                f"review {pair['prototype']} <-> {pair['real']} "
                f"score={pair['score']:.2f} roleName={role_name} text={text}"
            )
    for item in result["unappliedPairings"]:
        lines.append(f"pairing unapplied {item['prototype']} -> {item['real']} ({item['reason']})")
    for suggestion in result["suggestions"]:
        lines.append(
            f"suggest {suggestion['side']} {suggestion['path']} -> {suggestion['candidate']} "
            f"score={suggestion['score']:.2f}"
        )
    if not lines:
        lines.append("review none")
    return lines
