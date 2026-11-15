#!/usr/bin/env python3
"""Measure every profile target's output file against its token cap.

Tokens are estimated as characters / 4. Exits 1 when a file is missing or over its cap.
"""
import argparse
import json
import os
import re
import sys

QUANTITY = re.compile(r"\d+(?:\.\d+)?\s?(?:[a-z%]+|:\d+)", re.IGNORECASE)
LIST_ITEM = re.compile(r"\s*(?:[-*]|\d+\.)\s+\S")


def quantities(text):
    return {match.group(0).lower().replace(" ", "") for match in QUANTITY.finditer(text)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", help="path to profile.json; outputs are read beside it")
    args = parser.parse_args()

    with open(args.profile, encoding="utf-8") as handle:
        profile = json.load(handle)
    output_dir = os.path.dirname(os.path.abspath(args.profile))

    texts = {}
    for target in profile["targets"]:
        path = os.path.join(output_dir, target["output"])
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                texts[target["name"]] = handle.read()
    first_pass_quantities = set()
    for target in profile["targets"]:
        if target["pass"] == 1:
            first_pass_quantities |= quantities(texts.get(target["name"], ""))

    failed = False
    for target in profile["targets"]:
        cap = target.get("cap_tokens")
        text = texts.get(target["name"])
        if text is None:
            failed = True
            print(f"{target['output']}\tMISSING")
            continue
        tokens = round(len(text) / 4)
        over = bool(cap) and tokens > cap
        failed = failed or over
        repeated = sorted(quantities(text) & first_pass_quantities) if target["pass"] != 1 else []
        print(
            f"{target['output']}\titems={sum(1 for line in text.splitlines() if LIST_ITEM.match(line))}"
            f"\tchars={len(text)}\ttokens~{tokens}\tcap={cap or '-'}\t{'OVER' if over else 'ok'}"
            f"\trepeats_pass_1={','.join(repeated) or '-'}"
        )
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
