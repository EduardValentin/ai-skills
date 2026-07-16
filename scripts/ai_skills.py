#!/usr/bin/env python3
"""Command-line entry point for repository AI skills tooling."""

from __future__ import annotations

import sys
from pathlib import Path


if sys.version_info < (3, 11):
    print("ai_skills requires Python 3.11 or newer.", file=sys.stderr)
    raise SystemExit(2)


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.ai_skills_lib.config import build_parser, command_label


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"{command_label(args)}: not implemented")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
