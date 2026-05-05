# Performance Debugging

The repository is performance-critical. Picking the right implementation matters more than picking the simplest one.

## Algorithm

```
1. baseline      capture KPIs for the original on N representative scenarios
2. hypothesize   for each variant, predict which KPI moves and why
3. measure       perf-bench.sh --runs M; collect mean, median, p95
4. diagnose      autotrace + dbms_xplan for any KPI that worsened on any variant
5. expand?       if no variant beats baseline by the plan's threshold, propose
                 adjacent-code changes and RE-BRAINSTORM with the user
6. pick winner   apply the plan's "winner-picked-when" rule; otherwise stop and report
```

## KPIs (default set)

| KPI | Source | What it tells you |
|-----|--------|-------------------|
| `elapsed_ms` | `set timing on` / autotrace | end-to-end wall time |
| `consistent_gets` | autotrace statistics | logical IO; the most stable proxy for "how much work" |
| `db_block_gets` | autotrace statistics | physical-touched blocks; usually small |
| `sorts_memory` | autotrace statistics | unexpected sorts often signal a missing index or bad plan |
| `recursive_calls` | autotrace statistics | dictionary churn; spikes hint at hard parses |
| `plan_cost` | `EXPLAIN PLAN` / `dbms_xplan` | optimizer's own estimate; cross-check against measured |

The plan may add or drop KPIs — but never remove `elapsed_ms` and `consistent_gets`.

## Bench harness shape

Each variant ships a SQL harness at `util/<TICKET>/variants/<n>/perf.sql`. Do not write it from scratch — copy the template:

```bash
cp "$DB_WORK_SKILL_DIR/assets/sql/perf_harness_template.sql" \
   util/VA-515/variants/1/perf.sql
```

The template:

1. Resets session state (`alter session set statistics_level = all`).
2. Snapshots `v$mystat` counters (consistent gets, db block gets, sorts memory, recursive calls).
3. Times the variant call with `dbms_utility.get_time`.
4. Looks up `optimizer_cost` from `v$sql` for the SQL annotated with the `/*+ db_work_perf_harness */` hint.
5. Writes ONE trailing TSV line of KPI values in the order declared in `bench_spec.json`.

The template includes four variant-body shapes — pick one and delete the rest:

- **A.** Table function (most common in Oracode).
- **B.** Scalar function.
- **C.** Procedure with side effects (uses setup/cleanup).
- **D.** SYS_REFCURSOR (full fetch, not open-only).

### Required v$ grants (one-time)

The DEV user that runs `perf.sql` needs read on `v$mystat`, `v$statname`, `v$sql`. The skill ships a grants script:

```bash
"$DB_WORK_SKILL_DIR/scripts/run_sqlplus_dev.sh" \
  --connect /@DEVDB_ADMIN_ALIAS \
  --script "$DB_WORK_SKILL_DIR/assets/sql/perf_harness_grants.sql"
```

If grants are missing, the harness raises an Oracle error and the run fails — `perf-bench.sh` will mark the run FAILED and continue.

### bench_spec.json

Copy the template and fill in:

```bash
cp "$DB_WORK_SKILL_DIR/assets/sql/bench_spec_template.json" \
   util/VA-515/variants/bench_spec.json
```

Shape:

```json
{
  "ticket": "VA-515",
  "variants": [
    { "name": "v1_index_hint",  "harness_sql": "util/VA-515/variants/1/perf.sql" },
    { "name": "v2_rewrite",     "harness_sql": "util/VA-515/variants/2/perf.sql" },
    { "name": "v3_materialize", "harness_sql": "util/VA-515/variants/3/perf.sql" }
  ],
  "kpis": ["elapsed_ms","consistent_gets","db_block_gets","sorts_memory","recursive_calls","plan_cost"]
}
```

The KPI list is fixed by default. The plan may add KPIs but never remove `elapsed_ms` or `consistent_gets` — and the harness's TSV output order MUST match the order in `bench_spec.kpis` exactly.

### Run

```bash
"$DB_WORK_SKILL_DIR/scripts/perf-bench.sh" \
  --spec util/VA-515/variants/bench_spec.json \
  --warmup 2 \
  --runs 5
```

Output: `util/<TICKET>/variants/bench_results.tsv` plus per-run logs under `util/<TICKET>/variants/perf_logs/` (warmup logs included for inspection but excluded from the TSV).

### Cache policy: warm-cache only

The bench measures **steady-state, warm-cache behaviour**. For each variant, `perf-bench.sh` runs `--warmup N` invocations before measurement begins. Warmup runs hard-parse the SQL, populate the buffer cache, warm the row cache, and seed any required redo/undo state. They are NOT recorded in `bench_results.tsv`.

After warmup, `--runs M` measured invocations follow and ARE recorded.

Why warm-cache and not cold:
- Cold runs measure first-touch IO and hard-parse cost — both are amortized over the steady-state production workload, so they're noise in a variant comparison.
- Variants that look identical on warm cache but differ wildly cold usually differ because of *plan* differences, which `plan_cost` already surfaces.
- Production traffic is overwhelmingly warm-cache. Optimizing for cold-run performance optimizes for a workload Oracode does not have.

Defaults: `--warmup 2`, `--runs 5`. Bump warmup to 3+ for queries that hit very large segments where 2 passes don't fully populate the cache.

If you genuinely need cold-cache numbers (e.g. you're investigating a startup-warmup hypothesis), add `alter system flush buffer_cache;` (DBA-only) at the top of the harness and set `--warmup 0`. Document the reason in the plan — this is not the default policy.

### Comparable runs across variants

For `bench_results.tsv` to be meaningful:

- All variants must use the same scenario (same arguments, same data window).
- All variants run in the same DEV session class (same user, same wallet, same TNS).
- For Variants A–D the harness body must call the **shadow** of the variant under test (e.g. `MY_PACKAGE_EDI.MY_FN`), not the original. The original is benched only as a baseline variant if the plan calls for one.
- Same `--warmup` and `--runs` for every variant in a single bench (don't change them mid-bench — re-run the whole bench if policy changes).

## Adjacent-code expansion

If the bench shows no variant clears the plan's threshold:

1. STOP the implementation phase.
2. Identify candidate adjacent edits (callers, helpers, indexes, materialized views, hints). **During re-brainstorm, run divergent generation first** — do not pre-enumerate candidates seeded only by the user's suggestion, since that anchors the session.
3. **Run a regression sweep** on adjacent objects touched by any proposed edits (other queries hitting dropped indexes, MV refresh cost, hint side effects). Surface this before asking for approval.
4. RE-BRAINSTORM with the user (the harness's brainstorming workflow re-engages on a fresh creative pass; do not edit adjacent code unilaterally).
5. **Approval must be user-authored prose** explicitly naming:
   - (a) the adjacent objects affected;
   - (b) the accepted blast radius (which other queries / callers may regress);
   - (c) the rollback plan.
   Assistant-supplied boilerplate that the user echoes does NOT count. Bare assent ("yes do it") triggers a re-prompt.
6. If approved, amend the plan (new variants V1.1 / V2.1 with adjacent edits flagged) and re-bench.

## Diagnosing a regression

Even if a variant wins on `elapsed_ms`, refuse to declare it the winner if:

- `consistent_gets` rises >10% on a dependent caller;
- a new sort appears that didn't exist on the original plan;
- `plan_cost` rises and `elapsed_ms` improvement is within run-to-run noise (<5%).

In any of those cases, document the regression in the report and either pick a different variant or escalate to the user.

## Reporting

Bench output and per-run logs are referenced from the handoff report. The report explicitly names the winner plus the rule used to pick it (verbatim from the plan's "winner-picked-when" clause).
