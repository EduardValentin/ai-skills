"""Load snapshot JSON, decoding and normalizing it for alignment."""

from __future__ import annotations

import base64
import binascii
import gzip
import json
import zlib
from pathlib import Path
from typing import Any


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
    except (OSError, EOFError, zlib.error) as error:
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
