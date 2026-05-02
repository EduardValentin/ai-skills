# Compare Spec Format

`compare_spec.json` is the reviewable bridge between inferred PL/SQL signatures and runnable comparison SQL.

Generate it with:

```bash
DB_WORK_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/db-work"

"$DB_WORK_SKILL_DIR/scripts/generate_compare_spec.py" \
  --repo-root /path/to/oracode \
  --manifest util/VA-515/dev_sandbox/shadow_manifest.json
```

After compiling the shadow objects in DEV, prefer DB metadata:

```bash
"$DB_WORK_SKILL_DIR/scripts/generate_metadata_probe.py" \
  --manifest util/VA-515/dev_sandbox/shadow_manifest.json

"$DB_WORK_SKILL_DIR/scripts/run_sqlplus_dev.sh" \
  --script util/VA-515/dev_sandbox/metadata_probe.sql

"$DB_WORK_SKILL_DIR/scripts/generate_compare_spec.py" \
  --repo-root /path/to/oracode \
  --manifest util/VA-515/dev_sandbox/shadow_manifest.json \
  --metadata-tsv util/VA-515/dev_sandbox/logs/db_metadata.tsv
```

DB metadata should be preferred because it reflects the compiled DEV object signatures, including argument modes, overloads, and return types.

Then inspect and edit it before generating SQL:

```bash
"$DB_WORK_SKILL_DIR/scripts/generate_compare_harness.py" --spec util/VA-515/dev_sandbox/compare_spec.json
"$DB_WORK_SKILL_DIR/scripts/generate_stats_harness.py" --spec util/VA-515/dev_sandbox/compare_spec.json
```

By default, `generate_compare_spec.py` generates cases only for public callables whose declaration or package-body implementation lines changed in the ticket diff. It does not generate test SQL for every procedure/function in a cloned package.

If changed lines are inside a private package helper, the source pass should infer public package procedures/functions that call the helper and generate tests for those public callers. If no public callers are inferred, ask for the public entry point and regenerate with `--callable`.

Each generated case contains one or more `runs`. Runs are based on the callable's actual parameters. The generator must not assume every stored procedure/function accepts ISO, market, or date-range arguments.

When matching parameters exist, the generator may propose varied ISO, market, or time-window values. When no safe scenario dimensions are inferred, it emits a single `baseline_review_required` run. Review all runs before execution; add, remove, or edit runs to reflect the business cases that matter for the changed procedure/function.

Use explicit scope controls when needed:

```bash
# Preferred when the affected entry point is known.
"$DB_WORK_SKILL_DIR/scripts/generate_compare_spec.py" \
  --manifest util/VA-515/dev_sandbox/shadow_manifest.json \
  --callable GETCONSTRAINTRATINGSFLOWS

# Broad mode, only when intentionally testing the entire public package surface.
"$DB_WORK_SKILL_DIR/scripts/generate_compare_spec.py" \
  --manifest util/VA-515/dev_sandbox/shadow_manifest.json \
  --all-callables
```

## Agent Review Rules

Always show the inferred calls and arguments to the user before DEV execution.

Ask the user to overwrite arguments when:

- A value is marked `"review_required": true`.
- A string value is `'TODO'`.
- The test case needs business-specific ISO, date window, object id, constraint id, scenario id, or other fixture.
- An `evidence_mode` is uncertain or does not match whether the original code can execute the scenario.
- A `shadow_expected_result` expected query cannot be inferred from dependent DEV tables and code behavior.
- An `expected_delta` cannot be inferred from the code change, ticket intent, source-table inspection, and original-vs-shadow behavior.
- A `procedure_side_effect` observer cannot be inferred from source behavior, called routines, DML targets, output/log/temp tables, package state, and ticket intent.
- A `refcursor_output` materialization plan cannot be inferred from the public wrapper, cursor-opening SQL, called routines, or approved business projection.
- The spec contains no cases because the changed lines could not be mapped; ask for the affected callable name and regenerate with `--callable`.
- The generated run is `baseline_review_required`; ask for procedure/function-specific scenarios before collecting evidence.

Do not execute comparison or stats SQL until the user approves the proposed values or provides replacements.

## Evidence Modes

Every case or run may set `evidence_mode`. Run-level values override case-level values.

| Mode | Use When | Functional Evidence | Performance Evidence |
| --- | --- | --- | --- |
| `regression_compare` | Original can execute the same scenario and should match shadow. | Compare original vs shadow row count and result diff. | Compare original vs shadow means. |
| `shadow_expected_result` | New branch/new market/new ISO/new callable has no meaningful original behavior. | Infer `expected_result_sql` from dependent DEV tables and compare expected vs shadow. | Collect shadow-only stats. |
| `expected_delta` | Behavior intentionally changes and non-zero original-vs-shadow diff is expected. | Infer expected original-minus-shadow and shadow-minus-original SQL, then compare actual diff to expected diff. | Compare original vs shadow means unless original cannot run. |
| `performance_only` | Functional evidence is not meaningful for the run, but runtime evidence is useful. | Skip functional diff. | Collect stats for the configured source, usually shadow. |
| `compile_contract_validation` | The important proof is compile/signature/dependent-caller compatibility. | Use deploy and metadata logs. | Usually none. |

For new branches inside existing callables, keep old branches as `regression_compare` runs when applicable and add new branch runs as `shadow_expected_result`.

For added result columns, compare common columns with `regression_compare`. Validate new columns separately with `shadow_expected_result` or `expected_delta`, depending on whether the original can represent the changed behavior.

For completely new stored procedures/functions, use `shadow_expected_result` plus shadow-only performance evidence.

For intentional behavior changes, the agent must infer `expected_delta` first. Use code diff, ticket acceptance criteria, source-table inspection in DEV, and observed original-vs-shadow differences. Ask the user only when the expected delta cannot be inferred safely.

`expected_delta` runs should provide both fields:

```json
{
  "evidence_mode": "expected_delta",
  "expected_delta": {
    "status": "inferred",
    "source": "code and DEV table inspection",
    "notes": [
      "The fix removes inactive facilities that original incorrectly returned."
    ]
  },
  "expected_original_minus_shadow_sql": "select facility_id, status_code\nfrom expected_removed_rows",
  "expected_shadow_minus_original_sql": "select facility_id, status_code\nfrom expected_added_rows"
}
```

Use an empty, column-compatible query when one side of the expected delta should be empty, for example `select facility_id, status_code from expected_removed_rows where 1 = 0`.

For `procedure_side_effect`, the agent must infer observer SQL before asking the user to fill it in. Treat `TODO_RESULT_TABLE`, `TODO_RUN_FILTER`, or `observer_inference.status = "needs_agent_inference"` as blockers. The compare and stats harness generators should fail fast while those placeholders remain.

For `refcursor_output`, the agent must test the affected public wrapper and infer a call-and-fetch materialization plan before asking the user to fill it in. Treat `TODO_REF_CURSOR_*` or `cursor_materialization.status = "needs_agent_inference"` as blockers. The compare and stats harness generators should fail fast while those placeholders remain.

## Procedure Observer Inference

A procedure does not return rows directly, so the agent must define what can be observed after each call. During the code scan, inspect:

- direct DML targets and their key predicates;
- tables populated by called routines;
- output, audit, log, staging, temporary, or package-state tables;
- OUT/IN OUT parameters that can be projected into a result query;
- private-helper changes and the public parent callers selected for testing;
- ticket acceptance criteria and business behavior described by the changed code.

Good observer queries are concrete, column-compatible between original and shadow, and scoped to the run scenario. If original and shadow write to the same table, use setup SQL, run labels, temporary keys, transaction cleanup, or a safe fixture strategy so the two calls can be compared without cross-contamination.

Ask the user only when no defensible observer can be inferred, the observer needs business-specific fixture values, or setup/cleanup would otherwise be unsafe.

Performance testing must use the same reviewed `compare_spec.json` as row-count testing. Do not generate `stats_harness.sql` directly from `shadow_manifest.json` during normal work, because that bypasses affected-callable selection.

Row-count, result-difference, and performance harnesses all iterate the same reviewed run scenarios. After running the stats harness, use the skill-bundled `scripts/summarize_sqlplus_logs.py` to report mean KPI values across runs for each case and source.

## Function Case

```json
{
  "name": "constraint_profile_services_get_ratings",
  "comparison_type": "table_function",
  "object_name": "CONSTRAINT_PROFILE_SERVICES",
  "shadow_name": "CONSTRAINT_PROFILE_SERVICES_EDI",
  "callable_name": "GET_RATINGS",
  "arguments": [
    {
      "name": "p_iso",
      "mode": "in",
      "data_type": "varchar2",
      "value": "'PJMISO'",
      "source": "name heuristic",
      "review_required": true
    }
  ],
  "original_sql": "select *\nfrom table(CONSTRAINT_PROFILE_SERVICES.GET_RATINGS(\n        p_iso => 'PJMISO'\n    ))",
  "shadow_sql": "select *\nfrom table(CONSTRAINT_PROFILE_SERVICES_EDI.GET_RATINGS(\n        p_iso => 'PJMISO'\n    ))",
  "runs": [
    {
      "name": "pjm_recent_day",
      "description": "PJMISO recent one-day window",
      "arguments": [
        {
          "name": "p_iso",
          "mode": "in",
          "data_type": "varchar2",
          "value": "'PJMISO'",
          "source": "scenario pjm_recent_day",
          "review_required": true
        }
      ],
      "original_sql": "select *\nfrom table(CONSTRAINT_PROFILE_SERVICES.GET_RATINGS(\n        p_iso => 'PJMISO'\n    ))",
      "shadow_sql": "select *\nfrom table(CONSTRAINT_PROFILE_SERVICES_EDI.GET_RATINGS(\n        p_iso => 'PJMISO'\n    ))"
    }
  ],
  "compare": {
    "row_count": true,
    "minus": true
  }
}
```

## Procedure Case

```json
{
  "name": "package_a_run_process",
  "comparison_type": "procedure_side_effect",
  "object_name": "PACKAGE_A",
  "shadow_name": "PACKAGE_A_EDI",
  "callable_name": "RUN_PROCESS",
  "observer_inference": {
    "status": "inferred",
    "source": "code scan",
    "observed_tables": [
      "PACKAGE_A_RESULTS"
    ],
    "filter_strategy": "Compare rows written for each run label and business key.",
    "notes": [
      "RUN_PROCESS inserts one row per processed facility into PACKAGE_A_RESULTS."
    ]
  },
  "setup_sql": "delete from PACKAGE_A_RESULTS where run_label in ('pjm_case_original', 'pjm_case_shadow');",
  "original_call": "begin\n    PACKAGE_A.RUN_PROCESS(\n        p_iso => 'PJMISO'\n    );\nend;\n/",
  "shadow_call": "begin\n    PACKAGE_A_EDI.RUN_PROCESS(\n        p_iso => 'PJMISO'\n    );\nend;\n/",
  "original_result_sql": "select facility_id, status_code, processed_value\nfrom PACKAGE_A_RESULTS\nwhere run_label = 'pjm_case_original'",
  "shadow_result_sql": "select facility_id, status_code, processed_value\nfrom PACKAGE_A_RESULTS\nwhere run_label = 'pjm_case_shadow'",
  "cleanup_sql": "rollback;"
}
```

For procedure cases, the generated scaffold starts with `observer_inference.status = "needs_agent_inference"`. The agent must replace that scaffold with inferred or user-approved observer SQL before generating row-count, result-diff, or performance evidence.

## SYS_REFCURSOR Output

Use `comparison_type = "refcursor_output"` when the affected public callable either returns `SYS_REFCURSOR` or exposes an `OUT`/`IN OUT SYS_REFCURSOR` parameter.

The target-selection rule is unchanged: test the affected public wrapper. If a private helper that opens/builds the cursor changed, test the public parent wrappers that call it.

The observation rule is special: call the wrapper, fetch the full cursor, materialize comparable DEV rows, and compare those rows.

```json
{
  "name": "package_a_get_rows",
  "comparison_type": "refcursor_output",
  "object_name": "PACKAGE_A",
  "shadow_name": "PACKAGE_A_EDI",
  "callable_name": "GET_ROWS",
  "cursor_materialization": {
    "status": "inferred",
    "strategy": "call-and-fetch",
    "source": "code scan",
    "observed_shape": [
      "FACILITY_ID",
      "STATUS_CODE",
      "FLOW_MW"
    ],
    "notes": [
      "GET_ROWS opens a SYS_REFCURSOR over the facility flow query."
    ]
  },
  "setup_sql": "delete from DB_WORK_REFCURSOR_ROWS where case_name = 'package_a_get_rows';",
  "original_call": "declare\n    l_rc sys_refcursor;\nbegin\n    l_rc := PACKAGE_A.GET_ROWS(p_market => 'RT');\n    DB_WORK_CAPTURE_REFCURSOR(l_rc, 'package_a_get_rows', 'rt_case', 'ORIGINAL');\nend;\n/",
  "shadow_call": "declare\n    l_rc sys_refcursor;\nbegin\n    l_rc := PACKAGE_A_EDI.GET_ROWS(p_market => 'RT');\n    DB_WORK_CAPTURE_REFCURSOR(l_rc, 'package_a_get_rows', 'rt_case', 'SHADOW');\nend;\n/",
  "original_result_sql": "select row_hash, count(*) row_count\nfrom DB_WORK_REFCURSOR_ROWS\nwhere case_name = 'package_a_get_rows'\n  and run_name = 'rt_case'\n  and source_name = 'ORIGINAL'\ngroup by row_hash",
  "shadow_result_sql": "select row_hash, count(*) row_count\nfrom DB_WORK_REFCURSOR_ROWS\nwhere case_name = 'package_a_get_rows'\n  and run_name = 'rt_case'\n  and source_name = 'SHADOW'\ngroup by row_hash",
  "cleanup_sql": "rollback;"
}
```

Prefer a generic materialization helper based on `DBMS_SQL.TO_CURSOR_NUMBER` and `DBMS_SQL.DESCRIBE_COLUMNS2` for scalar-column cursors. Store normalized rows or row hashes with `case_name`, `run_name`, `source_name`, and stable row identifiers. Default to order-insensitive comparison unless the changed behavior explicitly depends on ordering.

Performance evidence for `refcursor_output` must measure the wrapper call plus full cursor fetch/materialization. Measuring only cursor open, or only a later select from already materialized rows, is not sufficient.
