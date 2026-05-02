#!/usr/bin/env python3
"""Generate SQLPlus metadata probe SQL for compiled original and shadow objects."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''").upper() + "'"


def object_targets(manifest: dict) -> dict[str, set[str]]:
    targets: dict[str, set[str]] = {}
    for entry in manifest.get("entries", []):
        source_path = entry.get("source_path", "")
        schema = source_path.split("/", 1)[0].upper() if "/" in source_path else ""
        if not schema:
            continue
        targets.setdefault(schema, set()).add(entry.get("object_name", "").upper())
        targets.setdefault(schema, set()).add(entry.get("shadow_name", "").upper())
    return targets


def in_list(values: set[str]) -> str:
    return ", ".join(sql_literal(value) for value in sorted(values) if value)


def procedure_predicate_for_targets(targets: dict[str, set[str]]) -> str:
    clauses: list[str] = []
    for owner, objects in sorted(targets.items()):
        objects_sql = in_list(objects)
        if not objects_sql:
            continue
        clauses.append(
            "("
            f"owner = {sql_literal(owner)} and "
            f"upper(object_name) in ({objects_sql})"
            ")"
        )
    if not clauses:
        return "1 = 0"
    return "\n        or ".join(clauses)


def argument_predicate_for_targets(targets: dict[str, set[str]]) -> str:
    clauses: list[str] = []
    for owner, objects in sorted(targets.items()):
        objects_sql = in_list(objects)
        if not objects_sql:
            continue
        clauses.append(
            "("
            f"owner = {sql_literal(owner)} and "
            f"(upper(object_name) in ({objects_sql}) or upper(package_name) in ({objects_sql}))"
            ")"
        )
    if not clauses:
        return "1 = 0"
    return "\n        or ".join(clauses)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Path to shadow_manifest.json")
    parser.add_argument("--output", help="Defaults to metadata_probe.sql next to the manifest")
    parser.add_argument("--spool", default="logs/db_metadata.tsv", help="SQLPlus spool path for TSV output")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    sandbox = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    output = Path(args.output).resolve() if args.output else sandbox / "metadata_probe.sql"
    targets = object_targets(manifest)
    procedure_predicate = procedure_predicate_for_targets(targets)
    argument_predicate = argument_predicate_for_targets(targets)

    sql = f"""set define off
set echo off
set feedback off
set heading off
set pagesize 0
set linesize 32767
set long 32767
set longchunksize 32767
set trimspool on
set termout off

spool {args.spool}

select 'PROC' || chr(9) ||
       owner || chr(9) ||
       object_name || chr(9) ||
       nvl(procedure_name, '') || chr(9) ||
       nvl(overload, '') || chr(9) ||
       object_type || chr(9) ||
       nvl(pipelined, '')
from all_procedures
where {procedure_predicate}
order by owner, object_name, procedure_name, overload;

select 'ARG' || chr(9) ||
       owner || chr(9) ||
       object_name || chr(9) ||
       nvl(package_name, '') || chr(9) ||
       nvl(overload, '') || chr(9) ||
       nvl(argument_name, '') || chr(9) ||
       position || chr(9) ||
       sequence || chr(9) ||
       data_level || chr(9) ||
       nvl(data_type, '') || chr(9) ||
       nvl(in_out, '') || chr(9) ||
       nvl(type_owner, '') || chr(9) ||
       nvl(type_name, '') ||
       case when defaulted = 'Y' then chr(9) || 'Y' else chr(9) || 'N' end
from all_arguments
where {argument_predicate}
  and data_level = 0
order by owner, nvl(package_name, object_name), object_name, overload, sequence;

spool off
set termout on
exit
"""
    output.write_text(sql)
    print(f"Wrote {output}")
    print(f"Metadata spool path inside SQLPlus: {args.spool}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
