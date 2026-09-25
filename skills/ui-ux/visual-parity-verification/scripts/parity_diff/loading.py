"""Load snapshot JSON, decoding and normalizing it for alignment."""

from __future__ import annotations

import base64
import binascii
import gzip
import json
import zlib
from pathlib import Path
from typing import Any


PATH_SEPARATOR = " > "
IGNORE_KINDS = ("hook", "path")


class InputError(Exception):
    pass


def parse_ignore_entry(entry: str) -> dict[str, str]:
    kind, separator, value = entry.partition(":")
    if kind not in IGNORE_KINDS or not separator or not value:
        raise InputError(f"invalid ignore entry {entry!r}: expected hook:<value> or path:<prefix>")
    return {"kind": kind, "value": value, "entry": entry}


def parse_ignore_entries(entries: list[str]) -> list[dict[str, str]]:
    return [parse_ignore_entry(entry) for entry in entries]


def matches_ignore_entry(node: dict[str, Any], entry: dict[str, str]) -> bool:
    if entry["kind"] == "hook":
        return node["hook"] == entry["value"]
    return node["path"] == entry["value"] or node["path"].startswith(entry["value"] + PATH_SEPARATOR)


def prune_ignored(root: dict[str, Any], entries: list[dict[str, str]], side: str) -> list[dict[str, str]]:
    """Remove every subtree matching an entry from the raw tree, in place, and
    list the removed nodes in document order."""
    for entry in entries:
        if matches_ignore_entry(root, entry):
            raise InputError(f"ignore entry {entry['entry']!r} matches the {side} root {root['path']!r}")
    ignored: list[dict[str, str]] = []

    def walk(node: dict[str, Any]) -> None:
        kept: list[dict[str, Any]] = []
        for child in node["children"]:
            entry = next((candidate for candidate in entries if matches_ignore_entry(child, candidate)), None)
            if entry is None:
                walk(child)
                kept.append(child)
            else:
                ignored.append({"side": side, "path": child["path"], "entry": entry["entry"]})
        node["children"] = kept

    if entries:
        walk(root)
    return ignored


def prune_ignored_snapshots(proto: dict[str, Any], real: dict[str, Any], ignore: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    roots = {"prototype": proto["root"], "real": real["root"]}
    return [item for side, root in roots.items() for item in prune_ignored(root, ignore.get(side, []), side)]


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
