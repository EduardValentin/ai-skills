#!/usr/bin/env python3
"""Efficient Codex CLI command shim for behavioral skill tests.

The pressure suites accept arbitrary "command reading stdin" values. This
wrapper gives the repo a default Codex command that does not inherit an
expensive user config such as gpt-5.5 with xhigh reasoning.
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
# CODEX_TEST_CWD is the single execution directory for both subprocess cwd and
# Codex's -C flag, so relative paths resolve the same way in the shim and child.
DEFAULT_CODEX_CLI = "/Applications/Codex.app/Contents/Resources/codex"
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_REASONING_EFFORT = "low"
REASONING_CONFIG_KEY = "model_reasoning_effort"
ALLOWED_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Codex exec for skill behavioral tests with efficient defaults."
    )
    parser.add_argument(
        "--role",
        choices=("actor", "judge"),
        default="actor",
        help="Select role-specific CODEX_ACTOR_* or CODEX_JUDGE_* overrides.",
    )
    parser.add_argument(
        "--print-command",
        action="store_true",
        help="Print the Codex exec argv instead of running it.",
    )
    args = parser.parse_args()

    prompt = sys.stdin.read()
    cwd = resolve_test_cwd()
    command = build_command(args.role, cwd=cwd)

    if args.print_command:
        print(shlex.join(command))
        return 0

    with tempfile.NamedTemporaryFile(prefix=f"codex-{args.role}-", suffix=".txt") as output:
        completed = subprocess.run(
            [*command, "--output-last-message", output.name, "-"],
            input=prompt,
            text=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            print(completed.stdout, end="", file=sys.stdout)
            print(completed.stderr, end="", file=sys.stderr)
            return completed.returncode

        output.seek(0)
        sys.stdout.write(output.read().decode("utf-8"))

    return 0


def build_command(role: str, cwd: str | None = None) -> list[str]:
    role_prefix = f"CODEX_{role.upper()}"
    codex_cli = os.environ.get("CODEX_CLI", default_codex_cli())
    cwd = cwd or resolve_test_cwd()
    model = get_setting(role_prefix, "MODEL", DEFAULT_MODEL)
    effort = validate_reasoning_effort(get_setting(role_prefix, "REASONING_EFFORT", DEFAULT_REASONING_EFFORT))

    command = [
        codex_cli,
        "exec",
        "--ephemeral",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C",
        cwd,
    ]
    if model:
        command.extend(["-m", model])
    if effort:
        command.extend(["-c", f'{REASONING_CONFIG_KEY}="{effort}"'])
    return command


def resolve_test_cwd() -> str:
    return os.environ.get("CODEX_TEST_CWD", str(REPO_ROOT))


def validate_reasoning_effort(effort: str) -> str:
    if effort and effort not in ALLOWED_REASONING_EFFORTS:
        allowed = ", ".join(sorted(ALLOWED_REASONING_EFFORTS))
        raise ValueError(f"invalid reasoning effort {effort!r}; expected one of: {allowed}")
    return effort


def default_codex_cli() -> str:
    if Path(DEFAULT_CODEX_CLI).exists():
        return DEFAULT_CODEX_CLI
    return shutil.which("codex") or "codex"


def get_setting(role_prefix: str, suffix: str, default: str) -> str:
    role_value = os.environ.get(f"{role_prefix}_{suffix}")
    if role_value is not None:
        return role_value.strip()

    shared_value = os.environ.get(f"CODEX_TEST_{suffix}")
    if shared_value is not None:
        return shared_value.strip()

    return default


if __name__ == "__main__":
    raise SystemExit(main())
