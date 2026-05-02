#!/usr/bin/env python3
"""Generate original-vs-shadow comparison SQL from reviewed call scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


UNRESOLVED_OBSERVER_TOKENS = (
    "TODO_RESULT_TABLE",
    "TODO_RUN_FILTER",
    "TODO_OBSERVER",
    "DB_WORK_OBSERVER_REQUIRED",
)
UNRESOLVED_REFCURSOR_TOKENS = (
    "TODO_REF_CURSOR_RESULT_FOR",
    "TODO_REF_CURSOR_MATERIALIZE",
    "DB_WORK_REFCURSOR_REQUIRED",
)
UNRESOLVED_EXPECTED_TOKENS = (
    "TODO_EXPECTED_RESULT",
    "TODO_EXPECTED_DELTA",
    "DB_WORK_EXPECTED_REQUIRED",
)
RESOLVED_OBSERVER_STATUSES = {"inferred", "approved"}


def query_placeholder(object_type: str, object_name: str) -> str:
    if object_type == "VIEW":
        return f"select *\n    from {object_name}"
    if object_type in {"FUNCTION", "TYPE_SPEC"}:
        return f"select *\n    from table({object_name}())"
    if object_type in {"PACKAGE_SPEC", "PACKAGE_BODY"}:
        return f"select *\n    from table({object_name}.TODO_FUNCTION())"
    return f"select *\n    from {object_name}"


def unique_entries(entries: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    output: list[dict] = []
    for entry in entries:
        key = (entry.get("object_name", ""), entry.get("shadow_name", ""))
        if key in seen:
            continue
        seen.add(key)
        output.append(entry)
    return output


def indent_sql(sql_text: str, spaces: int = 4) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line.strip() else line for line in sql_text.strip().splitlines())


def case_runs(case: dict) -> list[dict]:
    if case.get("runs"):
        return case["runs"]
    return [
        {
            "name": "default",
            "original_sql": case.get("original_sql", ""),
            "shadow_sql": case.get("shadow_sql", ""),
            "setup_sql": case.get("setup_sql", ""),
            "original_call": case.get("original_call", ""),
            "shadow_call": case.get("shadow_call", ""),
            "original_result_sql": case.get("original_result_sql", ""),
            "shadow_result_sql": case.get("shadow_result_sql", ""),
            "cleanup_sql": case.get("cleanup_sql", ""),
        }
    ]


def procedure_observer_unresolved(case: dict, run: dict, source_scope: str = "both") -> bool:
    if case.get("comparison_type") != "procedure_side_effect":
        return False
    observer = run.get("observer_inference") or case.get("observer_inference") or {}
    status = str(observer.get("status", "")).strip().lower() if isinstance(observer, dict) else ""
    if status and status not in RESOLVED_OBSERVER_STATUSES:
        return True
    fields = []
    if source_scope != "shadow":
        fields.append(run.get("original_result_sql", case.get("original_result_sql", "")))
    if source_scope != "original":
        fields.append(run.get("shadow_result_sql", case.get("shadow_result_sql", "")))
    if any(not field.strip() for field in fields):
        return True
    observer_sql = "\n".join(fields)
    return any(token in observer_sql for token in UNRESOLVED_OBSERVER_TOKENS)


def refcursor_output_unresolved(case: dict, run: dict, source_scope: str = "both") -> bool:
    if case.get("comparison_type") != "refcursor_output":
        return False
    materialization = run.get("cursor_materialization") or case.get("cursor_materialization") or {}
    status = str(materialization.get("status", "")).strip().lower() if isinstance(materialization, dict) else ""
    if status and status not in RESOLVED_OBSERVER_STATUSES:
        return True
    fields = []
    if source_scope != "shadow":
        fields.extend(
            [
                run.get("original_call", case.get("original_call", "")),
                run.get("original_result_sql", case.get("original_result_sql", "")),
            ]
        )
    if source_scope != "original":
        fields.extend(
            [
                run.get("shadow_call", case.get("shadow_call", "")),
                run.get("shadow_result_sql", case.get("shadow_result_sql", "")),
            ]
        )
    if any(not field.strip() for field in fields):
        return True
    refcursor_sql = "\n".join(fields)
    return any(token in refcursor_sql for token in UNRESOLVED_REFCURSOR_TOKENS)


def evidence_mode(case: dict, run: dict) -> str:
    return run.get("evidence_mode", case.get("evidence_mode", "regression_compare"))


def result_sql(case: dict, run: dict, source: str) -> str:
    if source == "original":
        return run.get("original_result_sql", case.get("original_result_sql", "")) or run.get(
            "original_sql", case.get("original_sql", "")
        )
    return run.get("shadow_result_sql", case.get("shadow_result_sql", "")) or run.get(
        "shadow_sql", case.get("shadow_sql", "")
    )


def has_unresolved_expected(sql_text: str) -> bool:
    return any(token in sql_text for token in UNRESOLVED_EXPECTED_TOKENS)


def expected_result_unresolved(case: dict, run: dict) -> bool:
    expected_sql = run.get("expected_result_sql", case.get("expected_result_sql", ""))
    shadow_sql = result_sql(case, run, "shadow")
    if not expected_sql.strip() or not shadow_sql.strip():
        return True
    return has_unresolved_expected(expected_sql) or has_unresolved_expected(shadow_sql)


def expected_delta_unresolved(case: dict, run: dict) -> bool:
    delta = run.get("expected_delta", case.get("expected_delta", {}))
    status = str(delta.get("status", "")).strip().lower() if isinstance(delta, dict) else ""
    if status and status not in RESOLVED_OBSERVER_STATUSES:
        return True
    expected_original_minus_shadow = run.get(
        "expected_original_minus_shadow_sql",
        case.get("expected_original_minus_shadow_sql", ""),
    )
    expected_shadow_minus_original = run.get(
        "expected_shadow_minus_original_sql",
        case.get("expected_shadow_minus_original_sql", ""),
    )
    fields = [
        result_sql(case, run, "original"),
        result_sql(case, run, "shadow"),
        expected_original_minus_shadow,
        expected_shadow_minus_original,
    ]
    if any(not field.strip() for field in fields):
        return True
    return any(has_unresolved_expected(field) for field in fields)


def emit_query_run(lines: list[str], case: dict, run: dict) -> None:
    original_sql = run.get("original_sql", case.get("original_sql", "")).strip().rstrip(";")
    shadow_sql = run.get("shadow_sql", case.get("shadow_sql", "")).strip().rstrip(";")
    lines.extend(
        [
            f"prompt Comparing {case['name']} run {run.get('name', 'default')}",
            "with original_result as (",
            indent_sql(original_sql),
            "),",
            "shadow_result as (",
            indent_sql(shadow_sql),
            ")",
            "select 'ORIGINAL' as source_name, count(*) as row_count from original_result",
            "union all",
            "select 'SHADOW' as source_name, count(*) as row_count from shadow_result;",
            "",
        ]
    )
    if case.get("compare", {}).get("minus", True):
        lines.extend(
            [
                "with original_result as (",
                indent_sql(original_sql),
                "),",
                "shadow_result as (",
                indent_sql(shadow_sql),
                ")",
                "select 'ORIGINAL_MINUS_SHADOW' as diff_name, count(*) as diff_count",
                "from (",
                "    select * from original_result",
                "    minus",
                "    select * from shadow_result",
                ")",
                "union all",
                "select 'SHADOW_MINUS_ORIGINAL' as diff_name, count(*) as diff_count",
                "from (",
                "    select * from shadow_result",
                "    minus",
                "    select * from original_result",
                ");",
                "",
            ]
        )


def emit_procedure_run(lines: list[str], case: dict, run: dict) -> None:
    setup_sql = run.get("setup_sql", case.get("setup_sql", "")).strip()
    cleanup_sql = run.get("cleanup_sql", case.get("cleanup_sql", "")).strip()
    original_call = run.get("original_call", case.get("original_call", "")).strip()
    shadow_call = run.get("shadow_call", case.get("shadow_call", "")).strip()
    original_result_sql = run.get("original_result_sql", case.get("original_result_sql", "")).strip().rstrip(";")
    shadow_result_sql = run.get("shadow_result_sql", case.get("shadow_result_sql", "")).strip().rstrip(";")

    lines.append(f"prompt Comparing {case['name']} run {run.get('name', 'default')}")
    if setup_sql:
        lines.extend([setup_sql, ""])
    lines.extend([original_call, "", shadow_call, ""])
    lines.extend(
        [
            "with original_result as (",
            indent_sql(original_result_sql),
            "),",
            "shadow_result as (",
            indent_sql(shadow_result_sql),
            ")",
            "select 'ORIGINAL' as source_name, count(*) as row_count from original_result",
            "union all",
            "select 'SHADOW' as source_name, count(*) as row_count from shadow_result;",
            "",
            "with original_result as (",
            indent_sql(original_result_sql),
            "),",
            "shadow_result as (",
            indent_sql(shadow_result_sql),
            ")",
            "select 'ORIGINAL_MINUS_SHADOW' as diff_name, count(*) as diff_count",
            "from (",
            "    select * from original_result",
            "    minus",
            "    select * from shadow_result",
            ")",
            "union all",
            "select 'SHADOW_MINUS_ORIGINAL' as diff_name, count(*) as diff_count",
            "from (",
            "    select * from shadow_result",
            "    minus",
            "    select * from original_result",
            ");",
            "",
        ]
    )
    if cleanup_sql:
        lines.extend([cleanup_sql, ""])


def emit_shadow_expected_run(lines: list[str], case: dict, run: dict) -> None:
    setup_sql = run.get("setup_sql", case.get("setup_sql", "")).strip()
    cleanup_sql = run.get("cleanup_sql", case.get("cleanup_sql", "")).strip()
    shadow_call = run.get("shadow_call", case.get("shadow_call", "")).strip()
    expected_sql = run.get("expected_result_sql", case.get("expected_result_sql", "")).strip().rstrip(";")
    shadow_sql = result_sql(case, run, "shadow").strip().rstrip(";")

    lines.append(f"prompt Shadow expected-result validation {case['name']} run {run.get('name', 'default')}")
    if setup_sql:
        lines.extend([setup_sql, ""])
    if shadow_call:
        lines.extend([shadow_call, ""])
    lines.extend(
        [
            "with expected_result as (",
            indent_sql(expected_sql),
            "),",
            "shadow_result as (",
            indent_sql(shadow_sql),
            ")",
            "select 'EXPECTED' as source_name, count(*) as row_count from expected_result",
            "union all",
            "select 'SHADOW' as source_name, count(*) as row_count from shadow_result;",
            "",
            "with expected_result as (",
            indent_sql(expected_sql),
            "),",
            "shadow_result as (",
            indent_sql(shadow_sql),
            ")",
            "select 'EXPECTED_MINUS_SHADOW' as diff_name, count(*) as diff_count",
            "from (",
            "    select * from expected_result",
            "    minus",
            "    select * from shadow_result",
            ")",
            "union all",
            "select 'SHADOW_MINUS_EXPECTED' as diff_name, count(*) as diff_count",
            "from (",
            "    select * from shadow_result",
            "    minus",
            "    select * from expected_result",
            ");",
            "",
        ]
    )
    if cleanup_sql:
        lines.extend([cleanup_sql, ""])


def emit_expected_delta_run(lines: list[str], case: dict, run: dict) -> None:
    setup_sql = run.get("setup_sql", case.get("setup_sql", "")).strip()
    cleanup_sql = run.get("cleanup_sql", case.get("cleanup_sql", "")).strip()
    original_call = run.get("original_call", case.get("original_call", "")).strip()
    shadow_call = run.get("shadow_call", case.get("shadow_call", "")).strip()
    original_sql = result_sql(case, run, "original").strip().rstrip(";")
    shadow_sql = result_sql(case, run, "shadow").strip().rstrip(";")
    expected_original_minus_shadow = run.get(
        "expected_original_minus_shadow_sql",
        case.get("expected_original_minus_shadow_sql", ""),
    ).strip().rstrip(";")
    expected_shadow_minus_original = run.get(
        "expected_shadow_minus_original_sql",
        case.get("expected_shadow_minus_original_sql", ""),
    ).strip().rstrip(";")

    lines.append(f"prompt Expected-delta validation {case['name']} run {run.get('name', 'default')}")
    if setup_sql:
        lines.extend([setup_sql, ""])
    if original_call:
        lines.extend([original_call, ""])
    if shadow_call:
        lines.extend([shadow_call, ""])
    lines.extend(
        [
            "with original_result as (",
            indent_sql(original_sql),
            "),",
            "shadow_result as (",
            indent_sql(shadow_sql),
            "),",
            "actual_original_minus_shadow as (",
            "    select * from original_result",
            "    minus",
            "    select * from shadow_result",
            "),",
            "actual_shadow_minus_original as (",
            "    select * from shadow_result",
            "    minus",
            "    select * from original_result",
            "),",
            "expected_original_minus_shadow as (",
            indent_sql(expected_original_minus_shadow),
            "),",
            "expected_shadow_minus_original as (",
            indent_sql(expected_shadow_minus_original),
            ")",
            "select 'ACTUAL_ORIGINAL_MINUS_SHADOW' as diff_name, count(*) as diff_count from actual_original_minus_shadow",
            "union all",
            "select 'EXPECTED_ORIGINAL_MINUS_SHADOW' as diff_name, count(*) as diff_count from expected_original_minus_shadow",
            "union all",
            "select 'ACTUAL_SHADOW_MINUS_ORIGINAL' as diff_name, count(*) as diff_count from actual_shadow_minus_original",
            "union all",
            "select 'EXPECTED_SHADOW_MINUS_ORIGINAL' as diff_name, count(*) as diff_count from expected_shadow_minus_original;",
            "",
            "with original_result as (",
            indent_sql(original_sql),
            "),",
            "shadow_result as (",
            indent_sql(shadow_sql),
            "),",
            "actual_original_minus_shadow as (",
            "    select * from original_result",
            "    minus",
            "    select * from shadow_result",
            "),",
            "actual_shadow_minus_original as (",
            "    select * from shadow_result",
            "    minus",
            "    select * from original_result",
            "),",
            "expected_original_minus_shadow as (",
            indent_sql(expected_original_minus_shadow),
            "),",
            "expected_shadow_minus_original as (",
            indent_sql(expected_shadow_minus_original),
            ")",
            "select 'OMS_ACTUAL_MINUS_EXPECTED' as mismatch_name, count(*) as mismatch_count",
            "from (select * from actual_original_minus_shadow minus select * from expected_original_minus_shadow)",
            "union all",
            "select 'OMS_EXPECTED_MINUS_ACTUAL' as mismatch_name, count(*) as mismatch_count",
            "from (select * from expected_original_minus_shadow minus select * from actual_original_minus_shadow)",
            "union all",
            "select 'SMO_ACTUAL_MINUS_EXPECTED' as mismatch_name, count(*) as mismatch_count",
            "from (select * from actual_shadow_minus_original minus select * from expected_shadow_minus_original)",
            "union all",
            "select 'SMO_EXPECTED_MINUS_ACTUAL' as mismatch_name, count(*) as mismatch_count",
            "from (select * from expected_shadow_minus_original minus select * from actual_shadow_minus_original);",
            "",
        ]
    )
    if cleanup_sql:
        lines.extend([cleanup_sql, ""])


def render_from_spec(spec: dict, output: Path) -> None:
    lines = [
        "set define off",
        "set feedback on",
        "set timing on",
        "set pagesize 50000",
        "set linesize 240",
        "",
        f"spool logs/compare_counts_{spec.get('ticket', 'ticket')}.log",
        "",
    ]
    if spec.get("review_required"):
        lines.extend(
            [
                "prompt WARNING: compare_spec.json was marked review_required.",
                "prompt Confirm proposed arguments were reviewed before trusting these results.",
                "",
            ]
        )
    for case in spec.get("cases", []):
        for run in case_runs(case):
            mode = evidence_mode(case, run)
            if mode == "shadow_expected_result":
                if expected_result_unresolved(case, run):
                    raise SystemExit(
                        "Expected-result SQL unresolved for "
                        f"{case['name']} run {run.get('name', 'default')}. "
                        "Infer expected_result_sql from dependent DEV tables before generating evidence."
                    )
                if refcursor_output_unresolved(case, run, "shadow") or procedure_observer_unresolved(case, run, "shadow"):
                    raise SystemExit(
                        f"Output observation unresolved for {case['name']} run {run.get('name', 'default')}."
                    )
                emit_shadow_expected_run(lines, case, run)
            elif mode == "expected_delta":
                if expected_delta_unresolved(case, run):
                    raise SystemExit(
                        "Expected-delta SQL unresolved for "
                        f"{case['name']} run {run.get('name', 'default')}. "
                        "Infer expected delta from code/ticket/source tables or ask the user before generating evidence."
                    )
                if refcursor_output_unresolved(case, run) or procedure_observer_unresolved(case, run):
                    raise SystemExit(
                        f"Output observation unresolved for {case['name']} run {run.get('name', 'default')}."
                    )
                emit_expected_delta_run(lines, case, run)
            elif mode in {"performance_only", "compile_contract_validation"}:
                lines.extend(
                    [
                        f"prompt Skipping functional compare for {case['name']} run {run.get('name', 'default')} evidence_mode={mode}",
                        "",
                    ]
                )
            elif case.get("comparison_type") == "procedure_side_effect":
                if procedure_observer_unresolved(case, run):
                    raise SystemExit(
                        "Procedure observer SQL unresolved for "
                        f"{case['name']} run {run.get('name', 'default')}. "
                        "Infer and approve original_result_sql/shadow_result_sql before generating evidence."
                    )
                emit_procedure_run(lines, case, run)
            elif case.get("comparison_type") == "refcursor_output":
                if refcursor_output_unresolved(case, run):
                    raise SystemExit(
                        "SYS_REFCURSOR materialization unresolved for "
                        f"{case['name']} run {run.get('name', 'default')}. "
                        "Infer and approve call-and-fetch materialization before generating evidence."
                    )
                emit_procedure_run(lines, case, run)
            else:
                emit_query_run(lines, case, run)
    lines.extend(["spool off", "exit", ""])
    output.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", help="Path to shadow_manifest.json")
    parser.add_argument("--spec", help="Path to reviewed compare_spec.json")
    parser.add_argument("--output", help="Defaults to compare_counts.sql next to manifest")
    parser.add_argument(
        "--allow-manifest-scaffold",
        action="store_true",
        help="Allow legacy object-level manifest scaffolding. Prefer --spec for affected-callable scenario tests.",
    )
    args = parser.parse_args()

    if not args.manifest and not args.spec:
        raise SystemExit("Pass --spec. Use --manifest --allow-manifest-scaffold only for legacy object-level scaffolding.")

    if args.spec:
        spec_path = Path(args.spec).resolve()
        sandbox = spec_path.parent
        spec = json.loads(spec_path.read_text())
        output = Path(args.output).resolve() if args.output else sandbox / "compare_counts.sql"
        render_from_spec(spec, output)
        print(f"Wrote {output}")
        return 0

    if not args.allow_manifest_scaffold:
        raise SystemExit(
            "Comparison harness generation requires --spec so only affected callables and reviewed scenarios are tested. "
            "Use generate_compare_spec.py first, or pass --allow-manifest-scaffold for legacy object-level scaffolding."
        )

    manifest_path = Path(args.manifest).resolve()
    sandbox = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    output = Path(args.output).resolve() if args.output else sandbox / "compare_counts.sql"

    lines = [
        "set define off",
        "set feedback on",
        "set timing on",
        "set pagesize 50000",
        "set linesize 240",
        "",
        f"spool logs/compare_counts_{manifest.get('ticket', 'ticket')}.log",
        "",
    ]

    for entry in unique_entries(manifest.get("entries", [])):
        original = entry["object_name"]
        shadow = entry["shadow_name"]
        object_type = entry.get("object_type", "")
        lines.extend(
            [
                f"prompt Comparing {original} to {shadow}",
                "/*",
                "Replace TODO placeholders with the exact call and filters for this entry point.",
                "Keep original_result and shadow_result column-compatible if using MINUS checks.",
                "*/",
                "with original_result as (",
                "    " + query_placeholder(object_type, original).replace("\n", "\n    "),
                "),",
                "shadow_result as (",
                "    " + query_placeholder(object_type, shadow).replace("\n", "\n    "),
                ")",
                "select 'ORIGINAL' as source_name, count(*) as row_count from original_result",
                "union all",
                "select 'SHADOW' as source_name, count(*) as row_count from shadow_result;",
                "",
                "with original_result as (",
                "    " + query_placeholder(object_type, original).replace("\n", "\n    "),
                "),",
                "shadow_result as (",
                "    " + query_placeholder(object_type, shadow).replace("\n", "\n    "),
                ")",
                "select 'ORIGINAL_MINUS_SHADOW' as diff_name, count(*) as diff_count",
                "from (",
                "    select * from original_result",
                "    minus",
                "    select * from shadow_result",
                ")",
                "union all",
                "select 'SHADOW_MINUS_ORIGINAL' as diff_name, count(*) as diff_count",
                "from (",
                "    select * from shadow_result",
                "    minus",
                "    select * from original_result",
                ");",
                "",
            ]
        )

    lines.extend(["spool off", "exit", ""])
    output.write_text("\n".join(lines))
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
