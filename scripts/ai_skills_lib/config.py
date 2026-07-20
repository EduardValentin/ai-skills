"""Command-line parsing for the AI skills CLI."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and evaluate repository AI skills.")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    validation_targets = validate.add_subparsers(dest="target", required=True)
    for target in ("static", "runtime", "ci-all"):
        validation_targets.add_parser(target)

    triggers = validation_targets.add_parser("triggers")
    _add_model_backed_options(triggers)
    triggers.add_argument("--runs", type=int, choices=(1, 2, 3), default=1)
    triggers.add_argument("--query")

    evals_target = validation_targets.add_parser("evals")
    _add_model_backed_options(evals_target)
    evals_target.add_argument("--case")

    all_target = validation_targets.add_parser("all")
    _add_model_backed_options(all_target)
    all_target.add_argument("--runs", type=int, choices=(1, 2, 3), default=1)

    check_local_installs = commands.add_parser("check-local-installs")
    check_local_installs.add_argument("--harness", choices=("codex",), required=True)

    evals = commands.add_parser("evals")
    evals_commands = evals.add_subparsers(dest="evals_command", required=True)
    aggregate = evals_commands.add_parser("aggregate")
    aggregate.add_argument("--results-dir", type=Path, required=True)
    aggregate.add_argument("--grade-source", choices=("judge", "manual", "both"), required=True)

    return parser


def _add_model_backed_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--harness", choices=("codex", "claude"), required=True)
    parser.add_argument("--skill")
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--max-concurrency", type=int, choices=(1, 2, 3, 4), default=2)


def command_label(args: argparse.Namespace) -> str:
    """Return a readable command label for stubbed handlers."""
    if args.command == "validate":
        return f"validate {args.target}"
    if args.command == "evals":
        return f"evals {args.evals_command}"
    return args.command
