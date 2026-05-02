# Oracode Rules

## Changelog Selection

Prefer this order:

1. Explicit user-provided team or changelog.
2. Temp `.db-work.yml` `default_team` from the active db-work session.
3. Changed changelog file already present in the worktree.
4. Ask for the team changelog.

Common mappings:

- `visual-analytics`, `visual analytics`, `va`: `visualanalytics_changelog.xml`
- `dataops`, `data ops`: `dataops_changelog.xml`
- `dataeng`, `data engineering`: `dataeng_changelog.xml`
- `datadelivery`, `data delivery`: `datadelivery_changelog.xml`
- `dataplatform`, `data platform`: `dataplatform_changelog.xml`
- `dataquality`, `data quality`: `dataquality_changelog.xml`
- `codecomplete`: `codecomplete_changelog.xml`
- `platform`: `platform_changelog.xml`
- `pcva`: `pcva_changelog.xml`
- `pi`: `pi_changelog.xml`
- `root`: `root_changelog.xml`

## SQL Rules

- Keep one database object per SQL file.
- Use trailing `/` for PL/SQL objects: packages, package bodies, functions, procedures, types, type bodies, and triggers.
- Do not use inline comments in Liquibase-owned SQL files.
- Use Unix-style paths in XML.
- Avoid `DROP TYPE`; create a new type version when needed.
- Treat `ALTER TABLE` as high-risk and use approved local patterns.

## Liquibase Changeset Shape

Use one changeset per object file:

```xml
<changeSet author="Your Name"
           id="VA-515-01"
           runWith="sqlplus"
           runOnChange="true"
           labels="VA-515">
    <sqlFile path="YES_SERVICES/PACKAGE_SPEC/CONSTRAINT_PROFILE_SERVICES.sql"
             relativeToChangelogFile="true"/>
</changeSet>
```

Sort changesets by dependency:

1. `TYPE_SPEC`
2. `TYPE_BODY`
3. `SEQUENCE`
4. `TABLE`
5. `INDEX`
6. `SYNONYM`
7. `PACKAGE_SPEC`
8. `PACKAGE_BODY`
9. `VIEW`
10. `FUNCTION`
11. `PROCEDURE`
12. `TRIGGER`
13. `JOB`

## Generated DEV Artifacts

Generated DEV-only files belong under:

```text
util/<TICKET>/dev_sandbox/
```

Do not include those files in production changelogs.

DEV shadow packages, functions, procedures, and types usually need execute grants so the DEV user can call them:

```sql
grant execute on yes_services.trans_const_overlap_edi to ye_dev;
```

The skill-bundled `scripts/generate_dev_deploy.py` should generate these grants after compiling shadow objects. The default grantee is `ye_dev`; override it with `--grant-execute-to` or `DB_WORK_GRANT_EXECUTE_TO` when needed.

Recommended generated files:

```text
util/<TICKET>/dev_sandbox/
├── deploy_shadow.sql
├── metadata_probe.sql
├── compare_counts.sql
├── stats_harness.sql
├── shadow_manifest.json
├── logs/
└── objects/
```
