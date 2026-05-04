#!/usr/bin/env bash
# perf-bench.sh — run each variant against DEV and emit a comparable KPI table.
#
# Usage:
#   perf-bench.sh --spec util/<TICKET>/variants/bench_spec.json [--runs 5] [--warmup 2] [--connect /@DEV_ALIAS]
#
# Cache policy: warm-cache only.
#   For each variant, the harness is invoked --warmup times BEFORE measurement
#   begins. Warmup runs hard-parse the SQL, populate the buffer cache, and warm
#   the row cache. They are NOT recorded in bench_results.tsv. After warmup,
#   --runs measured iterations follow and ARE recorded. This keeps the bench
#   focused on steady-state behaviour and removes first-touch IO + parse noise
#   from the comparison.
#
# bench_spec.json shape:
#   {
#     "ticket": "VA-515",
#     "variants": [
#       { "name": "v1_index_hint", "harness_sql": "util/VA-515/variants/1/perf.sql" },
#       ...
#     ],
#     "kpis": ["elapsed_ms","consistent_gets","db_block_gets","sorts_memory","recursive_calls","plan_cost"]
#   }
#
# Each harness_sql is expected to print exactly one trailing TSV line of KPI values
# (in the order declared in spec.kpis). The wrapper picks the last numeric line of the log.
#
# Output: util/<TICKET>/variants/bench_results.tsv with columns variant, run, <kpis...>.
#         Per-run logs under util/<TICKET>/variants/perf_logs/.
#         Warmup logs land in perf_logs/ as ${name}_warmup${n}.log and are kept
#         for inspection but excluded from the TSV.

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPEC=""
RUNS=5
WARMUP=2
CONNECT="${DB_WORK_DEV_CONNECT:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --spec)    SPEC="$2"; shift 2 ;;
    --runs)    RUNS="$2"; shift 2 ;;
    --warmup)  WARMUP="$2"; shift 2 ;;
    --connect) CONNECT="$2"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 64 ;;
  esac
done

[[ -n "$SPEC" ]]    || { echo "--spec required" >&2; exit 64; }
[[ -f "$SPEC" ]]    || { echo "spec not found: $SPEC" >&2; exit 64; }
[[ -n "$CONNECT" ]] || { echo "--connect or DB_WORK_DEV_CONNECT required" >&2; exit 64; }

alias_name_check="${CONNECT#/@}"
if [[ ! "$alias_name_check" =~ ^DEV[_-] ]]; then
  override="${DB_WORK_ALLOW_NON_DEV:-}"
  if [[ -z "$override" || "$override" != "$alias_name_check" ]]; then
    echo "alias '$alias_name_check' does not match ^DEV[_-]; set DB_WORK_ALLOW_NON_DEV='$alias_name_check' to override (per-alias one-shot)" >&2
    exit 1
  fi
fi

ticket=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['ticket'])" "$SPEC")
out_dir="util/${ticket}/variants"
mkdir -p "$out_dir"
out_tsv="$out_dir/bench_results.tsv"
log_dir="$out_dir/perf_logs"
mkdir -p "$log_dir"

# Header
python3 - "$SPEC" > "$out_tsv" <<'PY'
import json, sys
spec = json.load(open(sys.argv[1]))
cols = ["variant", "run"] + spec["kpis"]
print("\t".join(cols))
PY

variants_count=$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1]))['variants']))" "$SPEC")

echo "Running $variants_count variant(s) against $CONNECT"
echo "Per variant: $WARMUP warmup run(s) (discarded) + $RUNS measured run(s)"
echo "Cache policy: warm-cache only — warmup output is kept on disk but NOT in bench_results.tsv"
echo "Spec:    $SPEC"
echo "Output:  $out_tsv"
echo "Logs:    $log_dir"
echo

for ((i=0; i<variants_count; i++)); do
  name=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['variants'][$i]['name'])" "$SPEC")
  harness=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['variants'][$i]['harness_sql'])" "$SPEC")
  echo "[variant] $name -> $harness"

  # Warmup phase: run, log, ignore output
  for ((w=1; w<=WARMUP; w++)); do
    wlog="$log_dir/${name}_warmup${w}.log"
    if ! "$SKILL_DIR/scripts/run_sqlplus_dev.sh" --connect "$CONNECT" --script "$harness" > "$wlog" 2>&1; then
      echo "  warmup $w: FAILED (see $wlog) — continuing to next warmup"
      continue
    fi
    wrow=$(awk '/^[0-9]+([.][0-9]+)?(\t[0-9]+([.][0-9]+)?)+$/ {row=$0} END {print row}' "$wlog")
    echo "  warmup $w: ${wrow:-no KPI row}  (discarded)"
  done

  # Measured phase
  for ((r=1; r<=RUNS; r++)); do
    log="$log_dir/${name}_run${r}.log"
    if ! "$SKILL_DIR/scripts/run_sqlplus_dev.sh" --connect "$CONNECT" --script "$harness" > "$log" 2>&1; then
      echo "  run $r: FAILED (see $log)"
      continue
    fi
    kpi_row=$(awk '/^[0-9]+([.][0-9]+)?(\t[0-9]+([.][0-9]+)?)+$/ {row=$0} END {print row}' "$log")
    if [[ -z "$kpi_row" ]]; then
      echo "  run $r: no KPI row found in log ($log)"
      continue
    fi
    printf "%s\t%d\t%s\n" "$name" "$r" "$kpi_row" >> "$out_tsv"
    echo "  run $r: $kpi_row"
  done
done

echo
echo "Bench complete. Mean per variant:"
python3 - "$out_tsv" <<'PY'
import csv, statistics, sys
rows = list(csv.reader(open(sys.argv[1]), delimiter="\t"))
header = rows[0]
data = rows[1:]
by_variant = {}
for r in data:
    by_variant.setdefault(r[0], []).append(r[2:])
print("\t".join(["variant"] + ["mean_" + k for k in header[2:]]))
for v, runs in by_variant.items():
    means = []
    for col in range(len(header) - 2):
        vals = []
        for run in runs:
            try:
                vals.append(float(run[col]))
            except (ValueError, IndexError):
                pass
        means.append(f"{statistics.mean(vals):.2f}" if vals else "-")
    print("\t".join([v] + means))
PY
