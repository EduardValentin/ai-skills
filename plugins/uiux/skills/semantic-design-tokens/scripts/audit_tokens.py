#!/usr/bin/env python3
"""Scan UI files for common ad-hoc styling values.

This is intentionally conservative: it reports suspicious raw values for a human
to review instead of deciding whether a token definition is legitimate.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

DEFAULT_EXTENSIONS = {
    ".astro",
    ".css",
    ".html",
    ".js",
    ".jsx",
    ".mjs",
    ".scss",
    ".svelte",
    ".ts",
    ".tsx",
    ".vue",
}

SKIP_DIRS = {
    ".git",
    ".next",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "storybook-static",
}

PATTERNS = [
    ("hex-color", re.compile(r"(?<![\w-])#[0-9a-fA-F]{3,8}\b")),
    ("rgb-hsl-color", re.compile(r"\b(?:rgb|rgba|hsl|hsla)\s*\(", re.IGNORECASE)),
    ("tailwind-arbitrary", re.compile(r"\b[a-zA-Z0-9:-]+-\[[^\]]+\]")),
]


def iter_files(paths: list[Path], extensions: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix in extensions:
            files.append(path)
        elif path.is_dir():
            for child in path.rglob("*"):
                if any(part in SKIP_DIRS for part in child.parts):
                    continue
                if child.is_file() and child.suffix in extensions:
                    files.append(child)
    return sorted(set(files))


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return findings

    for line_no, line in enumerate(text.splitlines(), start=1):
        for label, pattern in PATTERNS:
            if pattern.search(line):
                findings.append((line_no, label, line.strip()))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit UI files for ad-hoc style values.")
    parser.add_argument("paths", nargs="+", help="Files or directories to scan")
    parser.add_argument(
        "--extensions",
        default=",".join(sorted(DEFAULT_EXTENSIONS)),
        help="Comma-separated extensions to scan",
    )
    args = parser.parse_args()

    extensions = {ext if ext.startswith(".") else f".{ext}" for ext in args.extensions.split(",") if ext}
    files = iter_files([Path(path) for path in args.paths], extensions)
    total = 0

    for path in files:
        findings = scan_file(path)
        for line_no, label, line in findings:
            total += 1
            print(f"{path}:{line_no}: {label}: {line}")

    if total:
        print(f"\nFound {total} potential ad-hoc style value(s). Review and replace with semantic tokens where appropriate.")
        return 1

    print("No obvious ad-hoc style values found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
