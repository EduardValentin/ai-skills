# Implementation and Shadow Objects

Implementation runs under `superpowers:executing-plans` after the plan is approved.

## Variant directory layout

```
util/<TICKET>/
├── plan.md
├── variants/
│   ├── 1/
│   │   ├── changes/        editable copies of Liquibase-owned files for this variant
│   │   ├── shadow/         user-suffixed shadow objects compiled to DEV
│   │   ├── perf.sql        bench harness (writes one TSV KPI line)
│   │   └── notes.md        what this variant does and why
│   ├── 2/
│   └── 3/                  optional
│   ├── bench_spec.json
│   ├── bench_results.tsv
│   └── perf_logs/
└── dev_sandbox/            populated only after the winner is picked
```

## Compile each variant's shadow before benchmarking

Each variant's shadow objects are compiled to DEV with the configured suffix (e.g. `_EDI`) so the bench harness calls the variant's shadow, not the original. The original is never touched during measurement.

## Liquibase-owned edits — winner only

Only after the winner is picked from the bench:

- Apply changes to `PROD/`, `YES_SERVICES/`, or sibling schema folders.
- Preserve Oracode SQL rules from `references/oracode-rules.md`.
- One database object per file.
- Trailing `/` on PL/SQL objects.
- No inline comments in Liquibase-owned SQL.
- Unix-style paths in XML.

## Changelog update

```bash
"$DB_WORK_SKILL_DIR/scripts/generate_changelog_entry.py" \
  --team visual-analytics --ticket VA-515 --author "Your Name"
```

Sort changesets by dependency:

```
TYPE_SPEC → TYPE_BODY → SEQUENCE → TABLE → INDEX → SYNONYM →
PACKAGE_SPEC → PACKAGE_BODY → VIEW → FUNCTION → PROCEDURE → TRIGGER → JOB
```

Review the generated XML before writing for non-trivial changes.

## DEV shadow objects (winner)

Generate suffixed copies for DEV compile and comparison:

```bash
"$DB_WORK_SKILL_DIR/scripts/generate_shadow_objects.py" \
  --ticket VA-515 --suffix _EDI

"$DB_WORK_SKILL_DIR/scripts/generate_dev_deploy.py" \
  --ticket VA-515 --grant-execute-to ye_dev
```

- Shadow files go to `util/<TICKET>/dev_sandbox/objects/`.
- The DEV deploy script uses SQLPlus `@@` includes (resolved relative to the deploy script).
- `grant execute on yes_services.<obj>_EDI to ye_dev;` is auto-emitted for executable shadows.
- Shadow files are NEVER added to a Liquibase changelog.

## Lint before handoff

```bash
./dev_utils/lint_changed_files.sh
```

Capture the lint log under `util/<TICKET>/dev_sandbox/logs/lint.log` so the handoff report can summarize it.
