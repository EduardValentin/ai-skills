#!/usr/bin/env python3
"""Sync one canonical toolkit between this repo and local agent install dirs.

Toolkits are shared infrastructure that one or more skills depend on. Unlike
skills (which live under `skills/<name>/` and install to `~/.<agent>/skills/<name>/`),
toolkits live under `toolkits/<name>/` and install to `~/.<agent>/toolkits/<name>/`.
The mechanics are otherwise identical to `sync_skill.py`.

The `.venv/` inside a toolkit is intentionally NOT synced — each install dir
manages its own venv (locally created, agent-runtime-specific). See the
toolkit's README for setup.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


def repo_root() -> Path:
    if override := os.environ.get("AI_SKILLS_REPO"):
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def validate_toolkit_name(toolkit_name: str) -> str:
    if (
        not toolkit_name
        or toolkit_name.startswith(".")
        or "/" in toolkit_name
        or "\\" in toolkit_name
    ):
        raise ValueError(f"invalid toolkit name: {toolkit_name}")
    return toolkit_name


def ignore_sync_excludes(_directory: str, names: list[str]) -> set[str]:
    """Skip files that are install-dir-specific or developer-local."""
    excluded = {".gitkeep", ".venv", ".pytest_cache", "__pycache__"}
    return excluded.intersection(names)


def sync_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"missing source: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=ignore_sync_excludes)
    print(f"synced: {source} -> {destination}")


def toolkit_paths(toolkit_name: str) -> tuple[Path, Path, Path]:
    root = repo_root()
    canonical = root / "toolkits" / toolkit_name
    claude = Path.home() / ".claude" / "toolkits" / toolkit_name
    codex = Path.home() / ".codex" / "toolkits" / toolkit_name
    return canonical, claude, codex


def push(toolkit_name: str) -> None:
    canonical, claude, codex = toolkit_paths(toolkit_name)
    if not canonical.is_dir():
        raise FileNotFoundError(f"missing canonical toolkit: {canonical}")
    sync_tree(canonical, claude)
    sync_tree(canonical, codex)


def pull(toolkit_name: str, agent: str) -> None:
    canonical, claude, codex = toolkit_paths(toolkit_name)
    if agent == "claude":
        sync_tree(claude, canonical)
        sync_tree(claude, codex)
    elif agent == "codex":
        sync_tree(codex, canonical)
        sync_tree(codex, claude)
    else:
        raise ValueError(f"invalid agent: {agent}")
    print("remember: review, commit, and push the repo changes")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync one canonical toolkit between this repo and local agent install dirs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    push_parser = subparsers.add_parser(
        "push",
        help="copy the canonical repo toolkit to Claude and Codex install dirs",
    )
    push_parser.add_argument("toolkit_name")

    pull_parser = subparsers.add_parser(
        "pull",
        help="copy one install dir toolkit back to the repo and the other install dir",
    )
    pull_parser.add_argument("toolkit_name")
    pull_parser.add_argument("agent", choices=("claude", "codex"))

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        toolkit_name = validate_toolkit_name(args.toolkit_name)
        if args.command == "push":
            push(toolkit_name)
        elif args.command == "pull":
            pull(toolkit_name, args.agent)
        else:
            raise ValueError(f"unknown command: {args.command}")
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
