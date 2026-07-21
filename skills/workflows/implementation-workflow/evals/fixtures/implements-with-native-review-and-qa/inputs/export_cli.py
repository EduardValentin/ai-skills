#!/usr/bin/env python3
"""CLI runtime surface for the fake account-export fixture."""

import argparse
import json
import sys

from account_export import export_account


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requester", required=True)
    parser.add_argument("--owner", required=True)
    args = parser.parse_args()
    records = [
        {
            "email": "owner@example.test",
            "display_name": "Example Owner",
            "internal_note": "fixture support note",
        }
    ]
    try:
        exported = export_account(args.requester, args.owner, records)
    except PermissionError as error:
        print(str(error), file=sys.stderr)
        return 3
    print(json.dumps(exported, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
