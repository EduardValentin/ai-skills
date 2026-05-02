#!/usr/bin/env python3
"""Generate DEV-only suffixed copies of changed Oracle object files."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EXCLUDED_PREFIXES = ("util/", "TESTS/", "dev_utils/", "sqlplusbin/")

OBJECT_ORDER = {
    "TYPE_SPEC": 10,
    "TYPE_BODY": 20,
    "SEQUENCE": 30,
    "TABLE": 40,
    "INDEX": 50,
    "SYNONYM": 60,
    "PACKAGE_SPEC": 70,
    "PACKAGE_BODY": 80,
    "VIEW": 90,
    "FUNCTION": 100,
    "PROCEDURE": 110,
    "TRIGGER": 120,
    "JOB": 130,
}


def run_git(repo_root: Path, args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files(repo_root: Path, base_ref: str) -> list[str]:
    files: set[str] = set()
    files.update(run_git(repo_root, ["diff", "--name-only", f"{base_ref}...HEAD"]))
    files.update(run_git(repo_root, ["diff", "--name-only"]))
    files.update(run_git(repo_root, ["diff", "--name-only", "--cached"]))
    return sorted(files)


def is_object_sql(path: str) -> bool:
    if not path.endswith(".sql"):
        return False
    if path.startswith(EXCLUDED_PREFIXES):
        return False
    if "/dev_sandbox/" in path:
        return False
    return len(path.split("/")) >= 3


def sort_key(path: str) -> tuple[int, str]:
    parts = path.split("/")
    return (OBJECT_ORDER.get(parts[1] if len(parts) > 1 else "", 999), path)


def object_name_from_path(path: str) -> str:
    return Path(path).stem


def shadow_name(object_name: str, suffix: str) -> str:
    cleaned = suffix.strip("_").upper()
    if object_name.upper().endswith(f"_{cleaned}"):
        return object_name
    return f"{object_name}_{cleaned}"


def rename_tokens(sql_text: str, object_name: str, replacement: str, mode: str) -> str:
    if mode == "none":
        return sql_text
    pattern = re.compile(rf"\b{re.escape(object_name)}\b", re.IGNORECASE)
    return pattern.sub(replacement, sql_text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Oracode repository root")
    parser.add_argument("--base", default="master", help="Git base ref for changed-file discovery")
    parser.add_argument("--ticket", required=True, help="Ticket id, e.g. VA-515")
    parser.add_argument("--suffix", required=True, help="User suffix, e.g. EDI")
    parser.add_argument("--files", nargs="*", help="Object SQL files. Defaults to changed files.")
    parser.add_argument("--output-dir", help="Defaults to util/<ticket>/dev_sandbox")
    parser.add_argument(
        "--rename-mode",
        choices=["all", "none"],
        default="all",
        help="Token rename mode. 'all' replaces standalone object-name tokens.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    sandbox = Path(args.output_dir).resolve() if args.output_dir else repo_root / "util" / args.ticket / "dev_sandbox"
    objects_dir = sandbox / "objects"
    objects_dir.mkdir(parents=True, exist_ok=True)
    (sandbox / "logs").mkdir(parents=True, exist_ok=True)

    input_files = args.files if args.files is not None else changed_files(repo_root, args.base)
    files = sorted([file for file in input_files if is_object_sql(file)], key=sort_key)

    entries: list[dict] = []
    for relative in files:
        source = repo_root / relative
        object_name = object_name_from_path(relative)
        new_name = shadow_name(object_name, args.suffix)
        target_relative = Path(relative).with_name(f"{new_name}.sql")
        target = objects_dir / target_relative
        target.parent.mkdir(parents=True, exist_ok=True)

        sql_text = source.read_text()
        renamed = rename_tokens(sql_text, object_name, new_name, args.rename_mode)
        header = (
            "-- Generated DEV sandbox copy.\n"
            f"-- Original file: {relative}\n"
            f"-- Original object: {object_name}\n"
            f"-- Shadow object: {new_name}\n\n"
        )
        target.write_text(header + renamed)

        entries.append(
            {
                "source_path": relative,
                "shadow_path": str(target.relative_to(sandbox)),
                "object_type": relative.split("/")[1] if len(relative.split("/")) > 1 else "",
                "object_name": object_name,
                "shadow_name": new_name,
            }
        )

    manifest = {
        "ticket": args.ticket,
        "suffix": args.suffix.strip("_").upper(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sandbox_dir": str(sandbox),
        "entries": entries,
    }
    manifest_path = sandbox / "shadow_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Wrote {manifest_path}")
    for entry in entries:
        print(f"  {entry['source_path']} -> {entry['shadow_path']}")
    if not entries:
        print("No object SQL files found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
