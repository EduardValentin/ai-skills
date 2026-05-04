# Compare Spec Format

`compare_spec.json` is the reviewable bridge between inferred PL/SQL signatures and runnable comparison SQL. It defines which callables get tested, with which arguments, on which scenarios, and how each scenario's evidence is interpreted.

Generation commands and the full DEV-execution flow live in `references/06-dev-execution-and-evidence.md`. JSON examples (function, procedure, refcursor) and observer/cursor inference rules live in `references/compare-spec-examples.md`. This file covers the format itself plus the agent rules.

## Run scope (defaults)

`generate_compare_spec.py` generates cases only for **public callables whose declaration or package-body implementation lines changed in the ticket diff.** It does not generate test SQL for every procedure/function in a cloned package.

If changed lines are inside a private package helper, the source pass infers public package procedures/functions that call the helper and generates tests for those public callers. If no public callers are inferred, ask for the public entry point and regenerate with `--callable`.

After DEV compile, prefer DB metadata over source regex:

```bash
"$DB_WORK_SKILL_DIR/scripts/generate_compare_spec.py" \
  --manifest util/<TICKET>/dev_sandbox/shadow_manifest.json \
  --metadata-tsv util/<TICKET>/dev_sandbox/logs/db_metadata.tsv
```

DB metadata reflects compiled DEV signatures including argument modes, overloads, and return types.

## Run dimensions

Each generated case contains one or more `runs`. Runs are based on the callable's actual parameters. The generator must NOT assume every stored procedure/function accepts ISO, market, or date-range arguments.

When matching parameters exist, the generator may propose varied ISO, market, or time-window values. When no safe scenario dimensions are inferred, it emits a single `baseline_review_required` run. Review all runs before execution; add, remove, or edit runs to reflect the business cases that matter.

## Scope controls

```bash
# Preferred when the affected entry point is known.
"$DB_WORK_SKILL_DIR/scripts/generate_compare_spec.py" \
  --manifest util/<TICKET>/dev_sandbox/shadow_manifest.json \
  --callable GETCONSTRAINTRATINGSFLOWS

# Broad mode, only when intentionally testing the entire public package surface.
"$DB_WORK_SKILL_DIR/scripts/generate_compare_spec.py" \
  --manifest util/<TICKET>/dev_sandbox/shadow_manifest.json \
  --all-callables
```

## Evidence modes

Every case or run sets `evidence_mode`. Run-level values override case-level values.

| Mode | Use when | Functional evidence | Performance evidence |
|------|----------|---------------------|----------------------|
| `regression_compare` | Original can execute the same scenario and should match shadow. | Compare original vs shadow row count + result diff. | Compare original vs shadow means. |
| `shadow_expected_result` | New branch / new market / new ISO / new callable. Original has no meaningful behavior. | Infer `expected_result_sql` from dependent DEV tables; compare expected vs shadow. | Shadow-only stats. |
| `expected_delta` | Behavior intentionally changes; non-zero diff is expected. | Infer expected `original_minus_shadow` and `shadow_minus_original` SQL; compare actual vs expected delta. | Compare original vs shadow means unless original cannot run. |
| `performance_only` | Functional evidence is not meaningful but runtime evidence is useful. | Skip functional diff. | Stats for the configured source (usually shadow). |
| `compile_contract_validation` | The proof is compile/signature/dependent-caller compatibility. | Use deploy and metadata logs. | Usually none. |

**Mapping rules:**

- New branches inside existing callables: keep old branches as `regression_compare`; add new-branch runs as `shadow_expected_result`.
- Added result columns: `regression_compare` for common columns; validate new columns with `shadow_expected_result` or `expected_delta`.
- Completely new stored procedures/functions: `shadow_expected_result` plus shadow-only performance evidence.
- Intentional behavior fixes: infer `expected_delta` first from code diff, ticket acceptance criteria, source-table inspection, and observed differences. Ask the user only when the expected delta cannot be inferred safely.

## Agent review rules

Always show the inferred calls, arguments, and `evidence_mode` rationale to the user before DEV execution.

Ask the user to overwrite when:

- A value is marked `"review_required": true`.
- A string value is `'TODO'`.
- The case needs business-specific ISO, date window, object id, constraint id, scenario id, or other fixture.
- An `evidence_mode` is uncertain or does not match whether the original can execute the scenario.
- A `shadow_expected_result` expected query cannot be inferred from dependent DEV tables.
- An `expected_delta` cannot be inferred from code change, ticket intent, source-table inspection, and original-vs-shadow behavior.
- A `procedure_side_effect` observer cannot be inferred — see `compare-spec-examples.md`.
- A `refcursor_output` materialization plan cannot be inferred — see `compare-spec-examples.md`.
- The spec is empty because changed lines could not be mapped; ask for the affected callable name and regenerate with `--callable`.
- The generated run is `baseline_review_required`.

**Do not execute comparison or stats SQL until the user approves the proposed values or provides replacements.**

## Harness rules

- Performance testing must use the same reviewed `compare_spec.json` as functional testing. Do not generate `stats_harness.sql` directly from `shadow_manifest.json` during normal work.
- Row-count, result-difference, and performance harnesses iterate the same reviewed run scenarios. After running the stats harness, use `scripts/summarize_sqlplus_logs.py` to report mean KPI values across runs for each case and source.
- The compare and stats harness generators fail fast when placeholders remain — `TODO_REF_CURSOR_*`, `observer_inference.status = "needs_agent_inference"`, `cursor_materialization.status = "needs_agent_inference"`, unresolved expected deltas. Resolve placeholders before generation.
