#!/usr/bin/env python3
"""Generate SQLPlus timing/autotrace SQL for reviewed original-vs-shadow call cases."""

from __future__ import annotations

import argparse
import json
import re
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
RESOLVED_OBSERVER_STATUSES = {"inferred", "approved"}


def query_placeholder(object_type: str, object_name: str) -> str:
    if object_type == "VIEW":
        return f"select /* db_work:{object_name} */ *\nfrom {object_name}"
    if object_type in {"FUNCTION", "TYPE_SPEC"}:
        return f"select /* db_work:{object_name} */ *\nfrom table({object_name}())"
    if object_type in {"PACKAGE_SPEC", "PACKAGE_BODY"}:
        return f"select /* db_work:{object_name} */ *\nfrom table({object_name}.TODO_FUNCTION())"
    return f"select /* db_work:{object_name} */ *\nfrom {object_name}"


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


def tagged_sql(sql_text: str, tag: str) -> str:
    stripped = sql_text.strip().rstrip(";")
    if stripped.lower().startswith("select"):
        return re_tag_select(stripped, tag)
    return stripped


def re_tag_select(sql_text: str, tag: str) -> str:
    lower = sql_text.lower()
    select_index = lower.find("select")
    if select_index == -1:
        return sql_text
    return sql_text[: select_index + 6] + f" /* db_work:{tag} */" + sql_text[select_index + 6 :]


def case_runs(case: dict) -> list[dict]:
    if case.get("runs"):
        return case["runs"]
    return [
        {
            "name": "default",
            "original_sql": case.get("original_sql", ""),
            "shadow_sql": case.get("shadow_sql", ""),
            "original_call": case.get("original_call", ""),
            "shadow_call": case.get("shadow_call", ""),
            "original_result_sql": case.get("original_result_sql", ""),
            "shadow_result_sql": case.get("shadow_result_sql", ""),
        }
    ]


def stats_marker(case_name: str, run_name: str, source: str) -> str:
    return f"DB_WORK_STATS_BEGIN case={case_name} run={run_name} source={source}"


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


def emit_shadow_only_stats(lines: list[str], case: dict, run: dict, run_name: str) -> None:
    shadow_call = run.get("shadow_call", case.get("shadow_call", "")).strip()
    shadow_sql = result_sql(case, run, "shadow").strip()
    if shadow_call:
        lines.extend(
            [
                f"prompt {stats_marker(case['name'], run_name, 'SHADOW')}",
                "set autotrace traceonly statistics",
                shadow_call,
                "",
            ]
        )
    if shadow_sql:
        lines.extend(
            [
                f"prompt {stats_marker(case['name'], run_name, 'SHADOW_RESULT')}",
                "set autotrace traceonly statistics",
                tagged_sql(shadow_sql, f"{case['name']}:{run_name}:shadow") + ";",
                "",
            ]
        )


def render_from_spec(spec: dict, output: Path) -> None:
    lines = [
        "set define off",
        "set feedback on",
        "set timing on",
        "set pagesize 50000",
        "set linesize 240",
        "set autotrace traceonly statistics",
        "",
        f"spool logs/stats_harness_{spec.get('ticket', 'ticket')}.log",
        "",
        "begin",
        "    dbms_application_info.set_module('db-work', 'original-vs-shadow-stats');",
        "end;",
        "/",
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
            run_name = run.get("name", "default")
            mode = evidence_mode(case, run)
            if mode in {"shadow_expected_result", "performance_only"}:
                if refcursor_output_unresolved(case, run, "shadow") or procedure_observer_unresolved(case, run, "shadow"):
                    raise SystemExit(
                        f"Output observation unresolved for {case['name']} run {run_name}."
                    )
                emit_shadow_only_stats(lines, case, run, run_name)
            elif mode == "compile_contract_validation":
                lines.extend(
                    [
                        f"prompt No SQLPlus stats generated for {case['name']} run {run_name}; compile/metadata validation only.",
                        "",
                    ]
                )
            elif case.get("comparison_type") == "procedure_side_effect":
                if procedure_observer_unresolved(case, run):
                    raise SystemExit(
                        "Procedure observer SQL unresolved for "
                        f"{case['name']} run {run_name}. "
                        "Infer and approve original_result_sql/shadow_result_sql before generating evidence."
                    )
                lines.extend(
                    [
                        f"prompt ORIGINAL_CALL {case['name']} run {run_name}",
                        "set autotrace off",
                        run.get("original_call", case.get("original_call", "")).strip(),
                        "",
                        "set autotrace traceonly statistics",
                        f"prompt {stats_marker(case['name'], run_name, 'ORIGINAL')}",
                        tagged_sql(
                            run.get("original_result_sql", case.get("original_result_sql", "")),
                            f"{case['name']}:{run_name}:original",
                        )
                        + ";",
                        "",
                        "set autotrace off",
                        f"prompt SHADOW_CALL {case['name']} run {run_name}",
                        run.get("shadow_call", case.get("shadow_call", "")).strip(),
                        "",
                        "set autotrace traceonly statistics",
                        f"prompt {stats_marker(case['name'], run_name, 'SHADOW')}",
                        tagged_sql(
                            run.get("shadow_result_sql", case.get("shadow_result_sql", "")),
                            f"{case['name']}:{run_name}:shadow",
                        )
                        + ";",
                        "",
                    ]
                )
            elif case.get("comparison_type") == "refcursor_output":
                if refcursor_output_unresolved(case, run):
                    raise SystemExit(
                        "SYS_REFCURSOR materialization unresolved for "
                        f"{case['name']} run {run_name}. "
                        "Infer and approve call-and-fetch materialization before generating evidence."
                    )
                lines.extend(
                    [
                        f"prompt {stats_marker(case['name'], run_name, 'ORIGINAL')}",
                        "set autotrace traceonly statistics",
                        run.get("original_call", case.get("original_call", "")).strip(),
                        "",
                        "set autotrace off",
                        f"prompt ORIGINAL_RESULT {case['name']} run {run_name}",
                        tagged_sql(
                            run.get("original_result_sql", case.get("original_result_sql", "")),
                            f"{case['name']}:{run_name}:original-result",
                        )
                        + ";",
                        "",
                        f"prompt {stats_marker(case['name'], run_name, 'SHADOW')}",
                        "set autotrace traceonly statistics",
                        run.get("shadow_call", case.get("shadow_call", "")).strip(),
                        "",
                        "set autotrace off",
                        f"prompt SHADOW_RESULT {case['name']} run {run_name}",
                        tagged_sql(
                            run.get("shadow_result_sql", case.get("shadow_result_sql", "")),
                            f"{case['name']}:{run_name}:shadow-result",
                        )
                        + ";",
                        "",
                    ]
                )
            else:
                lines.extend(
                    [
                        f"prompt {stats_marker(case['name'], run_name, 'ORIGINAL')}",
                        tagged_sql(
                            run.get("original_sql", case.get("original_sql", "")),
                            f"{case['name']}:{run_name}:original",
                        )
                        + ";",
                        "",
                        f"prompt {stats_marker(case['name'], run_name, 'SHADOW')}",
                        tagged_sql(
                            run.get("shadow_sql", case.get("shadow_sql", "")),
                            f"{case['name']}:{run_name}:shadow",
                        )
                        + ";",
                        "",
                    ]
                )
    lines.extend(["set autotrace off", "spool off", "exit", ""])
    output.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", help="Path to shadow_manifest.json")
    parser.add_argument("--spec", help="Path to reviewed compare_spec.json")
    parser.add_argument("--output", help="Defaults to stats_harness.sql next to manifest")
    parser.add_argument(
        "--allow-manifest-scaffold",
        action="store_true",
        help="Allow legacy object-level manifest scaffolding. Prefer --spec for affected-callable performance tests.",
    )
    args = parser.parse_args()

    if not args.manifest and not args.spec:
        raise SystemExit("Pass --spec. Use --manifest --allow-manifest-scaffold only for legacy object-level scaffolding.")

    if args.spec:
        spec_path = Path(args.spec).resolve()
        sandbox = spec_path.parent
        spec = json.loads(spec_path.read_text())
        output = Path(args.output).resolve() if args.output else sandbox / "stats_harness.sql"
        render_from_spec(spec, output)
        print(f"Wrote {output}")
        return 0

    if not args.allow_manifest_scaffold:
        raise SystemExit(
            "Performance harness generation requires --spec so only affected callables are tested. "
            "Use generate_compare_spec.py first, or pass --allow-manifest-scaffold for legacy object-level scaffolding."
        )

    manifest_path = Path(args.manifest).resolve()
    sandbox = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    output = Path(args.output).resolve() if args.output else sandbox / "stats_harness.sql"

    lines = [
        "set define off",
        "set feedback on",
        "set timing on",
        "set pagesize 50000",
        "set linesize 240",
        "set autotrace traceonly statistics",
        "",
        f"spool logs/stats_harness_{manifest.get('ticket', 'ticket')}.log",
        "",
        "begin",
        "    dbms_application_info.set_module('db-work', 'original-vs-shadow-stats');",
        "end;",
        "/",
        "",
    ]

    for entry in unique_entries(manifest.get("entries", [])):
        original = entry["object_name"]
        shadow = entry["shadow_name"]
        object_type = entry.get("object_type", "")
        lines.extend(
            [
                f"prompt ORIGINAL {original}",
                query_placeholder(object_type, original) + ";",
                "",
                f"prompt SHADOW {shadow}",
                query_placeholder(object_type, shadow) + ";",
                "",
            ]
        )

    lines.extend(["set autotrace off", "spool off", "exit", ""])
    output.write_text("\n".join(lines))
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
