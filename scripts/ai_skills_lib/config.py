"""Command-line parsing for the AI skills CLI."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and evaluate repository AI skills.")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("target", choices=("static", "runtime", "ci-all", "triggers", "evals", "all"))
    validate.add_argument("--harness")
    validate.add_argument("--runs", type=int, choices=(1, 2, 3), default=1)

    check_local_installs = commands.add_parser("check-local-installs")
    check_local_installs.add_argument("--harness", required=True)

    evals = commands.add_parser("evals")
    evals_commands = evals.add_subparsers(dest="evals_command", required=True)
    aggregate = evals_commands.add_parser("aggregate")
    aggregate.add_argument("--results-dir", type=Path, required=True)
    aggregate.add_argument("--grade-source", choices=("judge", "manual", "both"), required=True)

    return parser


def command_label(args: argparse.Namespace) -> str:
    """Return a readable command label for stubbed handlers."""
    if args.command == "validate":
        return f"validate {args.target}"
    if args.command == "evals":
        return f"evals {args.evals_command}"
    return args.command
