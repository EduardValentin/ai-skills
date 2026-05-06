#!/usr/bin/env bash
# dev_cleanup.sh — drop DEV shadow objects compiled during a db-work session.
#
# Usage:
#   dev_cleanup.sh --ticket VA-515 [--connect /@DEV_ALIAS] [--yes] [--dry-run]
#
# Behavior:
#   1. Aggregates shadow objects from every shadow_manifest.json under util/<TICKET>/.
#   2. Generates util/<TICKET>/dev_sandbox/cleanup.sql with DROP statements in
#      reverse-of-deploy order (jobs/triggers first, packages/types last).
#   3. Prints the cleanup plan and requires confirmation (skipped with --yes).
#   4. Runs against DEV via run_sqlplus_dev.sh.
#   5. Writes log to util/<TICKET>/dev_sandbox/logs/cleanup.log.
#
# Trigger: the agent runs this BEFORE cleanup_session.sh whenever the user
# ends the session ("let's end the session", "let's conclude the session",
# "we are finished", "done with db-work", or similar).

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TICKET=""
CONNECT="${DB_WORK_DEV_CONNECT:-}"
YES=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ticket)  TICKET="$2"; shift 2 ;;
    --connect) CONNECT="$2"; shift 2 ;;
    --yes)     YES=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,18p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 64 ;;
  esac
done

[[ -n "$TICKET" ]] || { echo "--ticket required" >&2; exit 64; }
if [[ "$DRY_RUN" != 1 ]]; then
  [[ -n "$CONNECT" ]] || { echo "--connect or DB_WORK_DEV_CONNECT required (or use --dry-run)" >&2; exit 64; }
fi

ticket_dir="util/${TICKET}"
[[ -d "$ticket_dir" ]] || { echo "no $ticket_dir directory found; nothing to clean"; exit 0; }

cleanup_dir="$ticket_dir/dev_sandbox"
log_dir="$cleanup_dir/logs"
mkdir -p "$cleanup_dir" "$log_dir"
cleanup_sql="$cleanup_dir/cleanup.sql"
cleanup_log="$log_dir/cleanup.log"

manifests=()
while IFS= read -r m; do manifests+=("$m"); done < <(find "$ticket_dir" -type f -name "shadow_manifest.json" 2>/dev/null | sort)

if [[ ${#manifests[@]} -eq 0 ]]; then
  echo "no shadow_manifest.json found under $ticket_dir"
  echo "if shadows were compiled manually, write DROP statements yourself in $cleanup_sql and run with --yes"
  exit 0
fi

python3 - "$cleanup_sql" "${manifests[@]}" <<'PY'
import json, sys

cleanup_sql_path = sys.argv[1]
manifests = sys.argv[2:]

# Map manifest object_type (folder-style) -> Oracle DROP type
TYPE_MAP = {
    "PACKAGE_SPEC": "PACKAGE",
    "PACKAGE_BODY": None,        # dropped with PACKAGE
    "TYPE_SPEC":    "TYPE",
    "TYPE_BODY":    None,        # dropped with TYPE
    "FUNCTION":     "FUNCTION",
    "PROCEDURE":    "PROCEDURE",
    "TRIGGER":      "TRIGGER",
    "VIEW":         "VIEW",
    "SYNONYM":      "SYNONYM",
    "TABLE":        "TABLE",
    "INDEX":        "INDEX",
    "SEQUENCE":     "SEQUENCE",
    "JOB":          "JOB",
}

# Reverse-of-deploy order (drop dependents first)
DROP_ORDER = [
    "JOB", "TRIGGER", "PROCEDURE", "FUNCTION", "VIEW",
    "PACKAGE", "SYNONYM", "INDEX", "TABLE", "SEQUENCE", "TYPE",
]

objects = []
for path in manifests:
    try:
        m = json.load(open(path))
    except Exception as e:
        print(f"-- could not parse {path}: {e}", file=sys.stderr)
        continue
    for entry in m.get("entries", []):
        src = entry.get("source_path", "")
        ot  = (entry.get("object_type") or "").upper()
        sn  = (entry.get("shadow_name")  or "").upper()
        if not sn:
            continue
        # Schema = first segment of source_path (e.g. PROD, YES_SERVICES)
        schema = src.split("/")[0].upper() if "/" in src else ""
        drop_type = TYPE_MAP.get(ot)
        if drop_type is None and ot not in ("PACKAGE_BODY", "TYPE_BODY"):
            print(f"-- unknown object_type '{ot}' for {sn}; skipping", file=sys.stderr)
            continue
        objects.append({
            "schema": schema, "name": sn,
            "src_type": ot, "drop_type": drop_type,
            "manifest": path,
        })

# Dedupe (schema, name, drop_type)
seen, deduped = set(), []
for o in objects:
    key = (o["schema"], o["name"], o["drop_type"])
    if key in seen:
        continue
    seen.add(key)
    deduped.append(o)

# Sort: known drop types in DROP_ORDER, body-only entries last (they're skipped)
def sort_key(o):
    if o["drop_type"] is None:
        return (len(DROP_ORDER) + 1, o["name"])
    try:
        return (DROP_ORDER.index(o["drop_type"]), o["name"])
    except ValueError:
        return (len(DROP_ORDER), o["name"])
deduped.sort(key=sort_key)

with open(cleanup_sql_path, "w") as f:
    f.write("-- db-work DEV cleanup\n")
    f.write("-- Drops shadow objects compiled during this session.\n")
    f.write("-- whenever sqlerror continue: a missing object should not abort the run.\n\n")
    f.write("set echo on\n")
    f.write("set feedback on\n")
    f.write("whenever sqlerror continue\n\n")
    drop_count = 0
    for o in deduped:
        qualified = f"{o['schema']}.{o['name']}" if o["schema"] else o["name"]
        if o["drop_type"] is None:
            f.write(f"-- skipping {qualified} ({o['src_type']}) -- dropped with parent object\n")
            continue
        f.write(f"drop {o['drop_type'].lower()} {qualified};\n")
        drop_count += 1
    f.write("\nexit\n")

print(f"wrote {cleanup_sql_path} ({drop_count} drop(s) planned)")
print()
for o in deduped:
    qualified = f"{o['schema']}.{o['name']}" if o["schema"] else o["name"]
    if o["drop_type"] is None:
        print(f"  skip {qualified:<50}  ({o['src_type']}, dropped with parent)")
    else:
        print(f"  drop {o['drop_type'].lower():<10} {qualified:<40}  (from {o['manifest']})")
PY

echo

if [[ "$DRY_RUN" == 1 ]]; then
  echo "dry-run complete. Review $cleanup_sql before running without --dry-run."
  exit 0
fi

# Pre-execution announce
echo "about to run:  $cleanup_sql"
echo "alias:         $CONNECT"
echo "expected:      drop shadow objects listed above"
echo "evidence_mode: cleanup (no comparison evidence)"
echo "log:           $cleanup_log"
echo

if [[ "$YES" != 1 ]]; then
  read -r -p "Proceed with DEV cleanup? [y/N] " ans
  case "$ans" in
    y|Y|yes|YES) : ;;
    *) echo "aborted"; exit 1 ;;
  esac
fi

if "$SKILL_DIR/scripts/run_sqlplus_dev.sh" --connect "$CONNECT" --script "$cleanup_sql" > "$cleanup_log" 2>&1; then
  echo "DEV cleanup OK -- see $cleanup_log"
else
  echo "DEV cleanup had errors -- see $cleanup_log" >&2
  exit 1
fi
