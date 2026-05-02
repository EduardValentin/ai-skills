#!/usr/bin/env python3
"""Generate or append Oracode Liquibase changesets."""

from __future__ import annotations

import argparse
import html
import os
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_TEAMS = {
    "visual-analytics": {
        "changelog": "visualanalytics_changelog.xml",
        "aliases": ["visual analytics", "va", "visual_analytics", "visualanalytics_changelog.xml"],
    },
    "dataops": {"changelog": "dataops_changelog.xml", "aliases": ["data ops", "dataops"]},
    "dataeng": {"changelog": "dataeng_changelog.xml", "aliases": ["data engineering", "dataeng"]},
    "datadelivery": {
        "changelog": "datadelivery_changelog.xml",
        "aliases": ["data delivery", "datadelivery"],
    },
    "dataplatform": {
        "changelog": "dataplatform_changelog.xml",
        "aliases": ["data platform", "dataplatform"],
    },
    "dataquality": {
        "changelog": "dataquality_changelog.xml",
        "aliases": ["data quality", "dataquality"],
    },
    "codecomplete": {"changelog": "codecomplete_changelog.xml", "aliases": ["code complete"]},
    "platform": {"changelog": "platform_changelog.xml", "aliases": []},
    "pcva": {"changelog": "pcva_changelog.xml", "aliases": []},
    "pi": {"changelog": "pi_changelog.xml", "aliases": ["platform infrastructure"]},
    "root": {"changelog": "root_changelog.xml", "aliases": []},
}

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

EXCLUDED_PREFIXES = ("util/", "TESTS/", "dev_utils/", "sqlplusbin/")


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


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
    files.update(run_git(repo_root, ["ls-files", "--others", "--exclude-standard"]))
    return sorted(files)


def load_config(path: Path) -> dict:
    config: dict = {"teams": {key: value.copy() for key, value in DEFAULT_TEAMS.items()}}
    if not path.exists():
        return config

    current_team: str | None = None
    in_aliases = False
    for raw_line in path.read_text().splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        top = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*?)\s*$", line)
        if top and not raw_line.startswith(" "):
            key, value = top.group(1), top.group(2).strip("'\"")
            if key != "teams":
                config[key] = value
            current_team = None
            in_aliases = False
            continue
        team_match = re.match(r"^\s{2}([^:]+):\s*$", raw_line)
        if team_match:
            current_team = team_match.group(1).strip()
            config["teams"].setdefault(current_team, {"aliases": []})
            in_aliases = False
            continue
        if current_team:
            changelog_match = re.match(r"^\s{4}changelog:\s*(.*?)\s*$", raw_line)
            if changelog_match:
                config["teams"][current_team]["changelog"] = changelog_match.group(1).strip("'\"")
                continue
            aliases_match = re.match(r"^\s{4}aliases:\s*$", raw_line)
            if aliases_match:
                config["teams"][current_team].setdefault("aliases", [])
                in_aliases = True
                continue
            alias_item = re.match(r"^\s{6}-\s*(.*?)\s*$", raw_line)
            if in_aliases and alias_item:
                config["teams"][current_team].setdefault("aliases", []).append(alias_item.group(1).strip("'\""))
    return config


def default_config_path(repo_root: Path) -> Path:
    env_config = os.environ.get("DB_WORK_CONFIG")
    if env_config:
        return Path(env_config).expanduser()

    session_dir = os.environ.get("DB_WORK_SESSION_DIR")
    if session_dir:
        session_config = Path(session_dir).expanduser() / ".db-work.yml"
        if session_config.exists():
            return session_config

    session_base = os.environ.get("DB_WORK_SESSION_BASE") or str(Path(os.environ.get("TMPDIR", "/tmp")) / f"db-work-{os.environ.get('USER', 'user')}")
    current = Path(session_base).expanduser() / "current"
    if current.is_symlink():
        session_config = Path(os.readlink(current)).expanduser() / ".db-work.yml"
        if session_config.exists():
            return session_config

    return repo_root / ".db-work.yml"


def resolve_changelog(repo_root: Path, config: dict, team: str | None, changelog: str | None) -> Path:
    if changelog:
        path = repo_root / changelog
        if not path.exists():
            raise SystemExit(f"Changelog does not exist: {path}")
        return path

    team_value = team or config.get("default_team")
    if not team_value:
        raise SystemExit("No team/changelog provided. Pass --team, --changelog, or set default_team in the temp .db-work.yml.")

    if team_value.endswith(".xml"):
        path = repo_root / team_value
        if path.exists():
            return path

    wanted = normalize(team_value)
    for team_name, data in config["teams"].items():
        candidates = [team_name, data.get("changelog", ""), *data.get("aliases", [])]
        if wanted in {normalize(candidate) for candidate in candidates}:
            path = repo_root / data["changelog"]
            if not path.exists():
                raise SystemExit(f"Resolved changelog does not exist: {path}")
            return path

    raise SystemExit(f"Could not resolve team/changelog: {team_value}")


def is_liquibase_sql(path: str) -> bool:
    if not path.endswith(".sql"):
        return False
    if path.startswith(EXCLUDED_PREFIXES):
        return False
    if "/dev_sandbox/" in path:
        return False
    parts = path.split("/")
    return len(parts) >= 3


def sort_key(path: str) -> tuple[int, str]:
    parts = path.split("/")
    object_type = parts[1] if len(parts) > 1 else ""
    return (OBJECT_ORDER.get(object_type, 999), path)


def existing_paths(changelog_text: str) -> set[str]:
    return set(re.findall(r'<sqlFile\s+path="([^"]+)"', changelog_text))


def next_id_number(changelog_text: str, ticket: str) -> int:
    pattern = re.compile(rf'id="{re.escape(ticket)}-(\d+)"')
    numbers = [int(match.group(1)) for match in pattern.finditer(changelog_text)]
    return max(numbers, default=0) + 1


def render_changesets(files: list[str], ticket: str, author: str, start_number: int) -> str:
    blocks: list[str] = []
    number = start_number
    for file in files:
        changeset_id = f"{ticket}-{number:02d}"
        blocks.append(
            f'<changeSet author="{html.escape(author)}"\n'
            f'           id="{html.escape(changeset_id)}"\n'
            f'           runWith="sqlplus"\n'
            f'           runOnChange="true"\n'
            f'           labels="{html.escape(ticket)}">\n'
            f'    <sqlFile path="{html.escape(file)}"\n'
            f'             relativeToChangelogFile="true"/>\n'
            f"</changeSet>"
        )
        number += 1
    return "\n\n".join(blocks)


def append_before_close(changelog_text: str, changesets: str) -> str:
    close_match = re.search(r"\n</databaseChangeLog>\s*$", changelog_text)
    if not close_match:
        return changelog_text.rstrip() + "\n\n" + changesets.rstrip() + "\n"
    return changelog_text[: close_match.start()] + "\n\n" + changesets.rstrip() + changelog_text[close_match.start() :]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Oracode repository root")
    parser.add_argument("--config", help="Non-secret db-work config. Defaults to DB_WORK_CONFIG or the active temp session config.")
    parser.add_argument("--base", default="master", help="Git base ref for changed-file discovery")
    parser.add_argument("--team", help="Team name or alias, e.g. visual-analytics")
    parser.add_argument("--changelog", help="Explicit changelog path")
    parser.add_argument("--ticket", required=True, help="Ticket label, e.g. VA-515")
    parser.add_argument("--author", help="Liquibase changeset author")
    parser.add_argument("--files", nargs="*", help="SQL files to include. Defaults to changed files.")
    parser.add_argument("--write", action="store_true", help="Append changesets to the changelog")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    config_path = Path(args.config).expanduser() if args.config else default_config_path(repo_root)
    if not config_path.is_absolute():
        config_path = repo_root / config_path
    config = load_config(config_path)
    author = args.author or config.get("author")
    if not author:
        raise SystemExit("No author provided. Pass --author or set author in the temp .db-work.yml.")

    changelog_path = resolve_changelog(repo_root, config, args.team, args.changelog)
    input_files = args.files if args.files is not None else changed_files(repo_root, args.base)
    files = sorted([file for file in input_files if is_liquibase_sql(file)], key=sort_key)

    changelog_text = changelog_path.read_text()
    already_present = existing_paths(changelog_text)
    files_to_add = [file for file in files if file not in already_present]

    if not files_to_add:
        print(f"No new SQL files to add to {changelog_path.name}.")
        return 0

    changesets = render_changesets(files_to_add, args.ticket, author, next_id_number(changelog_text, args.ticket))

    if args.write:
        changelog_path.write_text(append_before_close(changelog_text, changesets))
        print(f"Updated {changelog_path}")
        for file in files_to_add:
            print(f"  added: {file}")
    else:
        print(f"Target changelog: {changelog_path}")
        print(changesets)
        print("\nDry run only. Re-run with --write to append these changesets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
