#!/usr/bin/env python3
"""Group the extracted entries of every fragment file into one bucket file per profile target."""
import argparse
import json
import os
import re
import sys

TARGET_LINE = re.compile(r"\[TARGET:\s*<?\s*([A-Za-z0-9_-]+)\s*>?\s*\]")
ITEM_LINE = re.compile(r"ITEM:\s*(.+)")


def parse_entries(text):
    target = None
    for raw_line in text.splitlines():
        line = raw_line.strip().strip("`").strip()
        target_match = TARGET_LINE.search(line)
        if target_match:
            target = target_match.group(1).upper()
            line = line[target_match.end():]
        item_match = ITEM_LINE.search(line)
        if item_match and target:
            yield target, item_match.group(1).strip().strip("`").strip()
            target = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", help="path to profile.json; staging is read beside it")
    args = parser.parse_args()

    with open(args.profile, encoding="utf-8") as handle:
        profile = json.load(handle)
    staging = os.path.join(os.path.dirname(os.path.abspath(args.profile)), ".staging")
    chunks_dir = os.path.join(staging, "chunks")
    fragments_dir = os.path.join(staging, "fragments")
    buckets_dir = os.path.join(staging, "buckets")
    os.makedirs(buckets_dir, exist_ok=True)

    buckets = {target["name"].upper(): [] for target in profile["targets"]}
    seen = set()
    unrouted = 0
    for name in sorted(os.listdir(fragments_dir)):
        with open(os.path.join(fragments_dir, name), encoding="utf-8") as handle:
            text = handle.read()
        source = name.rsplit("__", 1)[0]
        for target, item in parse_entries(text):
            if target not in buckets:
                unrouted += 1
                continue
            key = (target, re.sub(r"\W+", " ", item.lower()).strip())
            if key not in seen:
                seen.add(key)
                buckets[target].append(f"ITEM: {item}  (src: {source})")

    for target, items in buckets.items():
        path = os.path.join(buckets_dir, f"{target}.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("".join(f"{item}\n" for item in items))
        print(f"{target}\titems={len(items)}\t{path}")
    unmapped = sorted(set(os.listdir(chunks_dir)) - set(os.listdir(fragments_dir)))
    print(f"unrouted_entries={unrouted}\tunmapped_chunks={len(unmapped)}")
    for name in unmapped:
        print(f"UNMAPPED\t{name}")
    sys.exit(1 if unmapped else 0)


if __name__ == "__main__":
    main()
