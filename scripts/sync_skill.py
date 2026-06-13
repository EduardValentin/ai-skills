#!/usr/bin/env python3
"""Sync one canonical skill between this repo and local agent install dirs."""

from __future__ import annotations

import argparse
import os
import subprocess
import shutil
import sys
from pathlib import Path


def repo_root() -> Path:
    if override := os.environ.get("AI_SKILLS_REPO"):
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def validate_skill_name(skill_name: str) -> str:
    if not skill_name or skill_name.startswith(".") or "/" in skill_name or "\\" in skill_name:
        raise ValueError(f"invalid skill name: {skill_name}")
    return skill_name


def ignore_gitkeep(_directory: str, names: list[str]) -> set[str]:
    return {".gitkeep"} if ".gitkeep" in names else set()


def sync_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"missing source: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=ignore_gitkeep)
    print(f"synced: {source} -> {destination}")


def skill_paths(skill_name: str) -> tuple[Path, Path, Path]:
    root = repo_root()
    canonical = root / "skills" / skill_name
    claude = Path.home() / ".claude" / "skills" / skill_name
    codex = Path.home() / ".codex" / "skills" / skill_name
    return canonical, claude, codex


def push(skill_name: str) -> None:
    canonical, claude, codex = skill_paths(skill_name)
    if not canonical.is_dir():
        raise FileNotFoundError(f"missing canonical skill: {canonical}")
    sync_tree(canonical, claude)
    sync_tree(canonical, codex)
    push_native_agents_for_group(skill_name)


def push_native_agents_for_group(skill_name: str) -> None:
    root = repo_root()
    manifest = root / "agents" / "manifest.toml"
    script = root / "scripts" / "sync_native_agents.py"
    if not manifest.is_file():
        return
    if not script.is_file():
        raise FileNotFoundError(f"missing native agent sync script: {script}")

    env = os.environ.copy()
    env["AI_SKILLS_REPO"] = str(root)
    result = subprocess.run(
        [sys.executable, str(script), "push", "--group", skill_name],
        check=False,
        env=env,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"native agent sync failed for group: {skill_name}")


def pull(skill_name: str, agent: str) -> None:
    canonical, claude, codex = skill_paths(skill_name)
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
        description="Sync one canonical skill between this repo and local agent install dirs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    push_parser = subparsers.add_parser(
        "push", help="copy the canonical repo skill to Claude and Codex install dirs"
    )
    push_parser.add_argument("skill_name")

    pull_parser = subparsers.add_parser(
        "pull", help="copy one install dir skill back to the repo and the other install dir"
    )
    pull_parser.add_argument("skill_name")
    pull_parser.add_argument("agent", choices=("claude", "codex"))

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        skill_name = validate_skill_name(args.skill_name)
        if args.command == "push":
            push(skill_name)
        elif args.command == "pull":
            pull(skill_name, args.agent)
        else:
            raise ValueError(f"unknown command: {args.command}")
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
