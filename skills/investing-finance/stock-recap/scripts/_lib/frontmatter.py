"""YAML frontmatter for .md artifacts.

Frontmatter is a YAML block fenced by `---` lines at the top of the file.
We preserve insertion order so the artifact reads predictably.
"""
from __future__ import annotations

from pathlib import Path

import yaml

FENCE = "---"


def write(path: Path, meta: dict, body: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).rstrip()
    content = f"{FENCE}\n{yaml_text}\n{FENCE}\n{body}"
    path.write_text(content)


def read(path: Path) -> tuple[dict, str]:
    path = Path(path)
    text = path.read_text()
    if not text.startswith(FENCE + "\n") and not text.startswith(FENCE + "\r\n"):
        return {}, text
    end_idx = text.find(f"\n{FENCE}\n", len(FENCE))
    if end_idx == -1:
        return {}, text
    yaml_block = text[len(FENCE) + 1 : end_idx]
    body_start = end_idx + len(FENCE) + 2
    meta = yaml.safe_load(yaml_block) or {}
    return meta, text[body_start:]
