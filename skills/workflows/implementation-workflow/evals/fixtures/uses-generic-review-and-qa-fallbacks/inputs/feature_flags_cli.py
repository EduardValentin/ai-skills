#!/usr/bin/env python3
"""CLI runtime surface for the fake feature-flag fixture."""

import argparse
import json

from feature_flags import visible_flag_names


FLAGS = [
    {"name": "search-v2", "audience": "public", "enabled": True},
    {"name": "staged-import", "audience": "public", "enabled": False},
    {"name": "billing-console", "audience": "private", "enabled": True},
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("operator", "admin"), required=True)
    args = parser.parse_args()
    print(json.dumps(visible_flag_names(args.role, FLAGS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
