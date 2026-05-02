#!/usr/bin/env python3
"""Generate an ordered SQLPlus deploy script from a shadow manifest."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

OBJECT_ORDER = {
    "TYPE_SPEC": 10,
    "TYPE_BODY": 20,
    "SEQUENCE": 30,
    "TABLE": 40,
    "INDEX": 50,
    "SYNONYM": 60,
    "PACKAGE_SPEC": 70,
    "PACKAGE_BODY": 80,
    "VIEW": 90,
    "FUNCTION": 100,
    "PROCEDURE": 110,
    "TRIGGER": 120,
    "JOB": 130,
}

EXECUTE_GRANT_OBJECT_TYPES = {
    "TYPE_SPEC",
    "TYPE_BODY",
    "PACKAGE_SPEC",
    "PACKAGE_BODY",
    "FUNCTION",
    "PROCEDURE",
}


def default_config_path() -> Path | None:
    env_config = os.environ.get("DB_WORK_CONFIG")
    if env_config and Path(env_config).expanduser().exists():
        return Path(env_config).expanduser()

    session_dir = os.environ.get("DB_WORK_SESSION_DIR")
    if session_dir:
        session_config = Path(session_dir).expanduser() / ".db-work.yml"
        if session_config.exists():
            return session_config

    session_base = os.environ.get("DB_WORK_SESSION_BASE") or str(Path(os.environ.get("TMPDIR", "/tmp")) / f"db-work-{os.environ.get('USER', 'user')}")
    current = Path(session_base).expanduser() / "current"
    if current.is_symlink():
        session_config = Path(os.readlink(current)).expanduser() / ".db-work.yml"
        if session_config.exists():
            return session_config

    repo_config = Path(".db-work.yml")
    if repo_config.exists():
        return repo_config
    return None


def config_scalar(key: str) -> str | None:
    config_path = default_config_path()
    if not config_path:
        return None
    for raw_line in config_path.read_text().splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        found_key, value = line.split(":", 1)
        if found_key.strip() == key:
            return value.strip().strip("'\"") or None
    return None


def grant_targets(entries: list[dict], grantee: str) -> list[tuple[str, str, str]]:
    targets: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        if entry.get("object_type") not in EXECUTE_GRANT_OBJECT_TYPES:
            continue
        source_path = entry.get("source_path", "")
        schema = source_path.split("/", 1)[0] if "/" in source_path else ""
        shadow_name = entry.get("shadow_name", "")
        if not schema or not shadow_name:
            continue
        key = (schema.upper(), shadow_name.upper())
        if key in seen:
            continue
        seen.add(key)
        targets.append((schema.lower(), shadow_name.lower(), grantee.lower()))
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Path to shadow_manifest.json")
    parser.add_argument("--output", help="Defaults to deploy_shadow.sql next to the manifest")
    parser.add_argument(
        "--grant-execute-to",
        default=os.environ.get("DB_WORK_GRANT_EXECUTE_TO") or config_scalar("grant_execute_to") or "ye_dev",
        help="User/schema to receive execute grants on generated executable shadow objects. Defaults to ye_dev.",
    )
    parser.add_argument("--no-grants", action="store_true", help="Do not generate grant execute statements")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    sandbox = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    entries = sorted(
        manifest.get("entries", []),
        key=lambda entry: (OBJECT_ORDER.get(entry.get("object_type", ""), 999), entry.get("shadow_path", "")),
    )
    output = Path(args.output).resolve() if args.output else sandbox / "deploy_shadow.sql"
    log_name = f"logs/deploy_shadow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    lines = [
        "set define off",
        "set echo on",
        "set feedback on",
        "set timing on",
        "set serveroutput on size unlimited",
        "whenever sqlerror exit sql.sqlcode rollback",
        "",
        f"spool {log_name}",
        "",
        f"prompt Deploying DEV shadow objects for {manifest.get('ticket', 'unknown ticket')}",
        "",
    ]

    for entry in entries:
        shadow_path = entry["shadow_path"].replace("\\", "/")
        lines.extend(
            [
                f"prompt Deploying {entry.get('shadow_name', shadow_path)}",
                f"@@{shadow_path}",
                "show errors",
                "",
            ]
        )

    if not args.no_grants:
        grants = grant_targets(entries, args.grant_execute_to)
        if grants:
            lines.extend(["prompt Granting execute on DEV shadow objects", ""])
            for schema, shadow_name, grantee in grants:
                lines.extend(
                    [
                        f"prompt Granting execute on {schema}.{shadow_name} to {grantee}",
                        f"grant execute on {schema}.{shadow_name} to {grantee};",
                        "",
                    ]
                )

    lines.extend(["spool off", "exit", ""])
    output.write_text("\n".join(lines))
    print(f"Wrote {output}")
    print(f"Log spool path inside SQLPlus: {log_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
