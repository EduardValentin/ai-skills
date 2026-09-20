"""Fixture builders and script runners for the parity pipeline tests."""

from __future__ import annotations

import base64
import copy
import gzip
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "skills" / "ui-ux" / "visual-parity-verification" / "scripts"
DIFF_SCRIPT = SCRIPTS_DIR / "diff_snapshots.py"
LEDGER_SCRIPT = SCRIPTS_DIR / "write_ledger.py"

BASE_STYLE: dict[str, str] = {
    "fontFamily": "Inter, sans-serif",
    "fontSize": "16px",
    "fontWeight": "400",
    "fontStyle": "normal",
    "lineHeight": "24px",
    "letterSpacing": "normal",
    "textTransform": "none",
    "textDecorationLine": "none",
    "color": "rgb(17, 24, 39)",
    "backgroundColor": "rgba(0, 0, 0, 0)",
    "effectiveBackground": "rgb(255, 255, 255)",
    "opacity": "1",
    "paddingTop": "0px",
    "paddingRight": "0px",
    "paddingBottom": "0px",
    "paddingLeft": "0px",
    "marginTop": "0px",
    "marginRight": "0px",
    "marginBottom": "0px",
    "marginLeft": "0px",
    "borderTopWidth": "0px",
    "borderRightWidth": "0px",
    "borderBottomWidth": "0px",
    "borderLeftWidth": "0px",
    "borderTopStyle": "none",
    "borderRightStyle": "none",
    "borderBottomStyle": "none",
    "borderLeftStyle": "none",
    "borderTopColor": "rgb(17, 24, 39)",
    "borderRightColor": "rgb(17, 24, 39)",
    "borderBottomColor": "rgb(17, 24, 39)",
    "borderLeftColor": "rgb(17, 24, 39)",
    "borderTopLeftRadius": "0px",
    "borderTopRightRadius": "0px",
    "borderBottomRightRadius": "0px",
    "borderBottomLeftRadius": "0px",
    "boxShadow": "none",
    "outlineWidth": "0px",
    "outlineStyle": "none",
    "outlineColor": "rgb(17, 24, 39)",
    "outlineOffset": "0px",
    "display": "block",
    "flexDirection": "row",
    "flexWrap": "nowrap",
    "alignItems": "normal",
    "justifyContent": "normal",
    "alignContent": "normal",
    "gridTemplateColumns": "none",
    "gridTemplateRows": "none",
    "gridAutoFlow": "row",
    "rowGap": "normal",
    "columnGap": "normal",
    "position": "static",
    "overflowX": "visible",
    "overflowY": "visible",
    "zIndex": "auto",
    "flexGrow": "0",
    "flexShrink": "1",
    "flexBasis": "auto",
    "alignSelf": "auto",
    "order": "0",
    "gridColumnStart": "auto",
    "gridColumnEnd": "auto",
    "gridRowStart": "auto",
    "gridRowEnd": "auto",
    "textOverflow": "clip",
    "whiteSpace": "normal",
    "transform": "none",
}


def node(
    tag: str = "div",
    *,
    path: str | None = None,
    own_text: str = "",
    role: str = "",
    name: str = "",
    name_from: str = "",
    hook: str | None = None,
    x: float = 0,
    y: float = 0,
    width: float = 100,
    height: float = 20,
    style: dict[str, str] | None = None,
    wrapper: bool = False,
    focusable: bool = False,
    state: dict[str, str] | None = None,
    contrast: dict[str, Any] | None = None,
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    merged_style = dict(BASE_STYLE)
    if style:
        merged_style.update(style)
    return {
        "path": path or tag,
        "tag": tag,
        "hook": hook,
        "ownText": own_text,
        "role": role,
        "name": name,
        "nameFrom": name_from or ("author" if name else ""),
        "focusable": focusable,
        "tabIndex": 0 if focusable else -1,
        "state": state or {},
        "style": merged_style,
        "geometry": {"x": x, "y": y, "width": width, "height": height},
        "contrast": contrast,
        "wrapper": wrapper,
        "children": children or [],
    }


def assign_paths(root: dict[str, Any]) -> dict[str, Any]:
    """Give every node a `tag:nth-of-type(n)` path from the root, like the browser script."""
    root["path"] = root["tag"]

    def walk(parent: dict[str, Any]) -> None:
        counts: dict[str, int] = {}
        for child in parent["children"]:
            counts[child["tag"]] = counts.get(child["tag"], 0) + 1
            child["path"] = f"{parent['path']} > {child['tag']}:nth-of-type({counts[child['tag']]})"
            walk(child)

    walk(root)
    return root


def snapshot(
    root: dict[str, Any],
    *,
    width: int = 1440,
    height: int = 900,
    dpr: float = 1,
    zoom: float = 1,
    color_scheme: str = "light",
    url: str = "http://localhost:5173/orders",
    root_selector: str = "section",
) -> dict[str, Any]:
    assign_paths(root)
    return {
        "url": url,
        "viewport": {"width": width, "height": height},
        "devicePixelRatio": dpr,
        "zoom": zoom,
        "colorScheme": color_scheme,
        "capturedAt": "2026-09-19T10:00:00.000Z",
        "rootSelector": root_selector,
        "rootSummary": {
            "tag": root["tag"],
            "role": root["role"],
            "name": root["name"],
            "width": root["geometry"]["width"],
            "height": root["geometry"]["height"],
        },
        "root": root,
    }


def delta_snapshot(snap: dict[str, Any]) -> dict[str, Any]:
    """Deep copy of `snap` with each non-root node's style stripped to the
    keys whose value differs from its parent's full style, exactly as
    snapshot-subtree.browser.js emits them."""
    result = copy.deepcopy(snap)

    def walk(node: dict[str, Any], parent_full_style: dict[str, str] | None) -> None:
        full_style = dict(node["style"])
        if parent_full_style is not None:
            node["style"] = {key: value for key, value in full_style.items() if parent_full_style.get(key) != value}
        for child in node["children"]:
            walk(child, full_style)

    walk(result["root"], None)
    return result


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def write_compressed_snapshot(path: Path, snapshot: dict[str, Any]) -> Path:
    """Write `snapshot` the way `{ encoding: "gzip-base64" }` returns it: a
    JSON string containing base64 of the gzipped compact JSON."""
    compact = json.dumps(snapshot, separators=(",", ":"))
    compressed = gzip.compress(compact.encode("utf-8"))
    encoded = base64.b64encode(compressed).decode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(encoded), encoding="utf-8")
    return path


def _run(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *arguments],
        cwd=REPO_ROOT,
        env={key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ"}},
        capture_output=True,
        text=True,
        check=False,
    )


def run_diff(*arguments: str) -> subprocess.CompletedProcess[str]:
    return _run(DIFF_SCRIPT, *arguments)


def run_ledger(*arguments: str) -> subprocess.CompletedProcess[str]:
    return _run(LEDGER_SCRIPT, *arguments)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
