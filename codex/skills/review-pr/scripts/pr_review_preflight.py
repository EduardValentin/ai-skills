#!/usr/bin/env python3
"""Summarize branch, base branch, diff, and test context for PR review."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


COMMON_BASE_BRANCHES = (
    "origin/master",
    "origin/main",
    "master",
    "main",
    "origin/develop",
    "develop",
    "origin/development",
    "development",
    "origin/trunk",
    "trunk",
)

INSTRUCTION_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    ".github/pull_request_template.md",
)

TEST_MARKERS = (
    "/__tests__/",
    "/cypress/",
    "/e2e/",
    "/integration/",
    "/tests/",
    ".spec.",
    ".test.",
)


class GitCommandError(RuntimeError):
    """Raised when a git command fails."""


def git(args: list[str], cwd: Path, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise GitCommandError(result.stderr.strip() or result.stdout.strip() or "git command failed")
    return result.stdout.strip()


def find_repo_root(cwd: Path) -> Path:
    output = git(["rev-parse", "--show-toplevel"], cwd=cwd)
    return Path(output)


def get_current_branch(repo_root: Path) -> str:
    branch = git(["branch", "--show-current"], cwd=repo_root)
    if branch:
        return branch
    return git(["rev-parse", "--short", "HEAD"], cwd=repo_root)


def list_branches(repo_root: Path) -> list[str]:
    output = git(
        ["for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes"],
        cwd=repo_root,
    )
    branches = []
    seen = set()
    for raw_line in output.splitlines():
        branch = raw_line.strip()
        if not branch or branch.endswith("/HEAD"):
            continue
        if branch not in seen:
            seen.add(branch)
            branches.append(branch)
    return branches


def discover_instruction_files(repo_root: Path, cwd: Path) -> list[str]:
    paths = []
    seen = set()
    current = cwd.resolve()
    repo_root_resolved = repo_root.resolve()

    while True:
        for relative_name in INSTRUCTION_FILES:
            candidate = current / relative_name
            if candidate.exists():
                path_text = str(candidate)
                if path_text not in seen:
                    seen.add(path_text)
                    paths.append(path_text)
        if current == repo_root_resolved:
            break
        current = current.parent

    for relative_name in INSTRUCTION_FILES:
        candidate = repo_root_resolved / relative_name
        if candidate.exists():
            path_text = str(candidate)
            if path_text not in seen:
                seen.add(path_text)
                paths.append(path_text)

    return paths


def resolve_base_branch(repo_root: Path, branches: list[str], requested_base: str | None) -> tuple[str | None, str]:
    branch_set = set(branches)

    if requested_base:
        if requested_base in branch_set:
            return requested_base, "user"
        origin_requested = f"origin/{requested_base}"
        if origin_requested in branch_set:
            return origin_requested, "user"
        return None, "user-missing"

    try:
        symbolic = git(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo_root)
    except GitCommandError:
        symbolic = ""

    if symbolic:
        candidate = symbolic.removeprefix("refs/remotes/")
        if candidate in branch_set:
            return candidate, "origin-head"

    for candidate in COMMON_BASE_BRANCHES:
        if candidate in branch_set:
            return candidate, "heuristic"

    return None, "unresolved"


def branch_matches_ticket(branch: str, ticket_id: str | None) -> bool | None:
    if not ticket_id:
        return None
    return ticket_id.lower() in branch.lower()


def candidate_branches_for_ticket(branches: list[str], ticket_id: str | None) -> list[str]:
    if not ticket_id:
        return []
    ticket_lower = ticket_id.lower()

    def sort_key(branch: str) -> tuple[int, int, str]:
        is_remote = 1 if branch.startswith("origin/") else 0
        return (is_remote, len(branch), branch.lower())

    return sorted([branch for branch in branches if ticket_lower in branch.lower()], key=sort_key)


def suggested_checkout(branches: list[str], candidates: list[str]) -> str | None:
    if not candidates:
        return None

    branch_set = set(branches)
    chosen = candidates[0]
    if chosen.startswith("origin/"):
        local_name = chosen.removeprefix("origin/")
        if local_name in branch_set:
            return f"git checkout {local_name}"
        return f"git checkout -t {chosen}"
    return f"git checkout {chosen}"


def changed_files_against_base(repo_root: Path, base_branch: str | None) -> tuple[str | None, list[str]]:
    if not base_branch:
        return None, []

    merge_base = git(["merge-base", "HEAD", base_branch], cwd=repo_root)
    output = git(["diff", "--name-only", "--diff-filter=ACMR", f"{merge_base}..HEAD"], cwd=repo_root)
    files = [line.strip() for line in output.splitlines() if line.strip()]
    return merge_base, files


def is_test_path(path: str) -> bool:
    normalized = f"/{path.lower()}"
    return any(marker in normalized for marker in TEST_MARKERS)


def impacted_areas(changed_files: list[str]) -> list[str]:
    areas = []
    seen = set()
    for path in changed_files:
        top_level = path.split("/", 1)[0]
        if top_level and top_level not in seen:
            seen.add(top_level)
            areas.append(top_level)
    return areas


def summarize(data: dict) -> str:
    lines = []
    lines.append(f"Repository root: {data['repo_root']}")
    lines.append(f"Current branch: {data['current_branch']}")
    if data["ticket_id"]:
        lines.append(f"Ticket ID: {data['ticket_id']}")
        lines.append(f"Branch matches ticket: {'yes' if data['branch_matches_ticket'] else 'no'}")
    else:
        lines.append("Ticket ID: not provided")

    if data["instruction_files"]:
        lines.append("Instruction files to inspect:")
        lines.extend(f"  - {path}" for path in data["instruction_files"])
    else:
        lines.append("Instruction files to inspect: none found by preflight")

    base_branch = data["base_branch"] or "unresolved"
    lines.append(f"Base branch: {base_branch} ({data['base_branch_source']})")
    if data["merge_base"]:
        lines.append(f"Merge base: {data['merge_base']}")

    if data["candidate_branches"]:
        lines.append("Candidate branches for ticket:")
        lines.extend(f"  - {branch}" for branch in data["candidate_branches"][:10])
        remaining = len(data["candidate_branches"]) - 10
        if remaining > 0:
            lines.append(f"  - ... and {remaining} more")

    if data["suggested_checkout"]:
        lines.append(f"Suggested checkout: {data['suggested_checkout']}")

    lines.append(f"Changed files: {len(data['changed_files'])}")
    lines.extend(f"  - {path}" for path in data["changed_files"][:25])
    remaining_files = len(data["changed_files"]) - 25
    if remaining_files > 0:
        lines.append(f"  - ... and {remaining_files} more")

    lines.append(f"Changed test files: {len(data['changed_test_files'])}")
    lines.extend(f"  - {path}" for path in data["changed_test_files"][:10])
    remaining_tests = len(data["changed_test_files"]) - 10
    if remaining_tests > 0:
        lines.append(f"  - ... and {remaining_tests} more")

    if data["impacted_areas"]:
        lines.append("Impacted top-level areas:")
        lines.extend(f"  - {area}" for area in data["impacted_areas"])

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket-id", help="Ticket identifier expected in the current branch name")
    parser.add_argument("--base-branch", help="Base branch to diff against")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cwd = Path(os.getcwd())

    try:
        repo_root = find_repo_root(cwd)
        current_branch = get_current_branch(repo_root)
        branches = list_branches(repo_root)
        instruction_files = discover_instruction_files(repo_root, cwd)
        base_branch, base_branch_source = resolve_base_branch(repo_root, branches, args.base_branch)
        merge_base, changed_files = changed_files_against_base(repo_root, base_branch)
    except GitCommandError as exc:
        print(f"Preflight failed: {exc}", file=sys.stderr)
        return 2

    branch_match = branch_matches_ticket(current_branch, args.ticket_id)
    candidates = candidate_branches_for_ticket(branches, args.ticket_id)
    changed_test_files = [path for path in changed_files if is_test_path(path)]

    data = {
        "repo_root": str(repo_root),
        "ticket_id": args.ticket_id,
        "current_branch": current_branch,
        "branch_matches_ticket": branch_match,
        "instruction_files": instruction_files,
        "base_branch": base_branch,
        "base_branch_source": base_branch_source,
        "merge_base": merge_base,
        "candidate_branches": candidates,
        "suggested_checkout": suggested_checkout(branches, candidates) if branch_match is False else None,
        "changed_files": changed_files,
        "changed_test_files": changed_test_files,
        "impacted_areas": impacted_areas(changed_files),
    }

    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(summarize(data))

    if branch_match is False:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
