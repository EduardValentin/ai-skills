# Compare Spec Examples

JSON case examples for `compare_spec.json` plus inference rules for procedure observers and SYS_REFCURSOR materialization. Load this file when actually editing the spec — the format/rules-only file is `compare-spec-format.md`.

## Function case (table function)

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

## Procedure case (`procedure_side_effect`)

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
    "observed_tables": ["PACKAGE_A_RESULTS"],
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

The generated scaffold starts with `observer_inference.status = "needs_agent_inference"`. The agent must replace it with inferred or user-approved observer SQL before generating row-count, result-diff, or performance evidence.

### Procedure observer inference

A procedure does not return rows directly, so the agent defines what can be observed after each call. During the code scan, inspect:

- direct DML targets and their key predicates;
- tables populated by called routines;
- output, audit, log, staging, temporary, or package-state tables;
- OUT/IN OUT parameters that can be projected into a result query;
- private-helper changes and the public parent callers selected for testing;
- ticket acceptance criteria and business behavior described by the changed code.

Good observer queries are concrete, column-compatible between original and shadow, and scoped to the run scenario. If original and shadow write to the same table, use setup SQL, run labels, temporary keys, transaction cleanup, or a safe fixture strategy so the two calls can be compared without cross-contamination.

Ask the user only when no defensible observer can be inferred, the observer needs business-specific fixture values, or setup/cleanup would be unsafe.

## SYS_REFCURSOR case (`refcursor_output`)

Use `comparison_type = "refcursor_output"` when the affected public callable returns `SYS_REFCURSOR` or exposes an `OUT` / `IN OUT SYS_REFCURSOR` parameter.

Target-selection rule is unchanged: test the affected public wrapper. If a private helper that opens the cursor changed, test the public parent wrappers that call it.

Observation rule is special: call the wrapper, fetch the full cursor, materialize comparable DEV rows, and compare those rows.

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
    "observed_shape": ["FACILITY_ID", "STATUS_CODE", "FLOW_MW"],
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

### Materialization rules

- Prefer a generic helper based on `DBMS_SQL.TO_CURSOR_NUMBER` and `DBMS_SQL.DESCRIBE_COLUMNS2` for scalar-column cursors.
- Store normalized rows or row hashes with `case_name`, `run_name`, `source_name`, and stable row identifiers.
- Default to order-insensitive comparison unless the changed behavior explicitly depends on ordering.
- Performance evidence for `refcursor_output` MUST measure wrapper call plus full cursor fetch/materialization. Measuring only cursor open, or selecting from already-materialized rows, is not sufficient.

## Expected-delta example

`expected_delta` runs require both fields:

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

Use an empty, column-compatible query when one side should be empty:

```sql
select facility_id, status_code from expected_removed_rows where 1 = 0
```
