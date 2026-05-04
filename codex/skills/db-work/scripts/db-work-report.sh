#!/usr/bin/env bash
# db-work-report.sh — emit a fixed-shape handoff markdown report from session artifacts.
#
# Usage:
#   db-work-report.sh --ticket VA-515 [--out util/VA-515/dev_sandbox/report.md]

set -euo pipefail

TICKET=""
OUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ticket)  TICKET="$2"; shift 2 ;;
    --out)     OUT="$2"; shift 2 ;;
    -h|--help) sed -n '2,6p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 64 ;;
  esac
done

[[ -n "$TICKET" ]] || { echo "--ticket required" >&2; exit 64; }

sandbox="util/${TICKET}/dev_sandbox"
variants_dir="util/${TICKET}/variants"
[[ -n "$OUT" ]] || OUT="${sandbox}/report.md"
mkdir -p "$(dirname "$OUT")"

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "(no git)")
changelog=$(git diff --name-only origin/main...HEAD 2>/dev/null | grep -E '_changelog\.xml$' | head -n1 || echo "(none)")
changed_sql=$(git diff --name-only origin/main...HEAD 2>/dev/null | grep -E '\.sql$' | grep -vE '^util/' || true)
generated_sql=$(find "$sandbox" -maxdepth 3 -name '*.sql' 2>/dev/null | sort || true)
bench_tsv="$variants_dir/bench_results.tsv"
lint_log="$sandbox/logs/lint.log"
plan_file="util/${TICKET}/plan.md"

winner=""
winner_rule=""
variants_run=0
if [[ -f "$bench_tsv" ]]; then
  winner=$(python3 - "$bench_tsv" <<'PY'
import csv, statistics, sys
rows = list(csv.reader(open(sys.argv[1]), delimiter="\t"))
hdr, data = rows[0], rows[1:]
if "elapsed_ms" not in hdr:
    sys.exit(0)
idx = hdr.index("elapsed_ms")
by = {}
for r in data:
    try:
        by.setdefault(r[0], []).append(float(r[idx]))
    except (ValueError, IndexError):
        pass
ranked = sorted(by.items(), key=lambda kv: statistics.mean(kv[1]))
if ranked:
    print(ranked[0][0])
PY
)
  variants_run=$(awk -F'\t' 'NR>1{print $1}' "$bench_tsv" | sort -u | wc -l | tr -d ' ')
fi

if [[ -f "$plan_file" ]]; then
  winner_rule=$(awk '/^## Winner-picked-when rule/{flag=1; next} /^## /{flag=0} flag && NF' "$plan_file" | head -n3 | tr '\n' ' ' | sed 's/  */ /g')
fi

{
  echo "# DB Work Report — $TICKET"
  echo
  echo "## Summary"
  echo "- Branch: \`$branch\`"
  echo "- Team changelog: \`$changelog\`"
  echo "- Variants benchmarked: $variants_run"
  if [[ -n "$winner" ]]; then
    echo "- Winner (lowest mean elapsed_ms): \`$winner\`"
  else
    echo "- Winner: (no bench_results.tsv found)"
  fi
  if [[ -n "$winner_rule" ]]; then
    echo "- Picked under rule: $winner_rule"
  else
    echo "- Picked under rule: (no plan.md found)"
  fi
  echo
  echo "## Files changed (Liquibase-owned)"
  if [[ -n "$changed_sql" ]]; then
    while IFS= read -r f; do echo "- \`$f\`"; done <<< "$changed_sql"
  else
    echo "- (none detected from git diff)"
  fi
  echo
  echo "## Files generated (DEV sandbox)"
  if [[ -n "$generated_sql" ]]; then
    while IFS= read -r f; do echo "- \`$f\`"; done <<< "$generated_sql"
  else
    echo "- (none)"
  fi
  echo
  echo "## Performance evidence"
  if [[ -f "$bench_tsv" ]]; then
    echo
    echo '```'
    cat "$bench_tsv"
    echo '```'
  else
    echo "- (no bench_results.tsv)"
  fi
  echo
  echo "## Comparison evidence"
  found=0
  for f in "$sandbox/logs/"compare*.log "$sandbox/logs/"stats*.log "$sandbox/logs/"summary*.log; do
    [[ -f "$f" ]] && { echo "- \`$f\`"; found=1; }
  done
  [[ "$found" == 0 ]] && echo "- (no comparison logs found under $sandbox/logs/)"
  echo
  echo "## Lint"
  if [[ -f "$lint_log" ]]; then
    issues=$(grep -cE 'ERROR|WARNING' "$lint_log" 2>/dev/null || echo 0)
    echo "- \`$lint_log\` ($issues issue(s))"
  else
    echo "- (lint not run; recommend ./dev_utils/lint_changed_files.sh)"
  fi
  echo
  echo "## Manual steps remaining"
  echo "- [ ] Reviewer approval of changelog ordering"
  echo "- [ ] PR opened"
  echo "- [ ] Liquibase deploy plan confirmed with team"
} > "$OUT"

echo "Wrote $OUT"
