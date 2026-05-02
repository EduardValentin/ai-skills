---
name: db-work
description: Oracode Oracle database workflow for Liquibase-owned SQL changes, team changelog updates, DEV-only user-suffixed shadow objects, SQLPlus DEV execution, functional comparison queries, and performance/statistics evidence. Use when working in an Oracode repository checkout or similar Oracode database tasks involving PL/SQL packages, types, functions, procedures, views, Liquibase changelogs, DEV deployments, DataGrip/SQLPlus scripts, original-vs-suffixed comparisons such as PACKAGE_A vs PACKAGE_A_<INITIALS>, or Jira/job-ticket database implementation. When a ticket drives the work, use ticket-start first if available and only follow its job/Jira workflow; if ticket-start is unavailable, ask the user for the minimum job-ticket details directly and proceed from that context. Personal-project/Linear workflow is out of scope for db-work.
---

# DB Work

## Operating Model

Use this skill for Oracode database work. Let `ticket-start` handle job/Jira ticket intake when it is available, then use this skill for SQL, Liquibase, DEV deploy, comparison, and evidence generation. If `ticket-start` is unavailable, blocked, or not installed, gather the job-ticket context directly instead of stopping.

When a ticket is involved:

1. Use `ticket-start` first when it is available.
2. Follow only the `Job workflow` from `ticket-start`.
3. Do not use the personal-project or Linear path.
4. Carry forward the ticket id, ticket title, acceptance criteria, branch intent, and open questions.

If `ticket-start` is unavailable, cannot be read, or is not listed as an available skill:

1. Tell the user briefly that `ticket-start` is unavailable and `db-work` will collect the needed job-ticket context directly.
2. Ask only for missing details needed for the current task:
   - ticket id;
   - ticket title or short business goal;
   - acceptance criteria or intended behavior;
   - affected schema/object/callable names when known;
   - team or changelog, for example `visualanalytics_changelog.xml`;
   - branch intent and implementation scope;
   - known DEV test scenarios, argument values, fixtures, or edge cases;
   - open questions, dependencies, or deployment constraints.
3. Use repo facts from git diffs, changelogs, SQL files, and generated sandbox artifacts to fill any details the user does not know.
4. For implementation work, summarize the gathered context and proposed approach before editing. For testing-only work, summarize assumptions before generating or running DEV SQL.

Before editing or generating artifacts, read the relevant repo instructions and, when needed, `references/oracode-rules.md`.

## Helper Script Location

All `scripts/...` paths in this skill are relative to the `db-work` skill folder, not the Oracode project repository. Run helper scripts from the Oracode repo root as the working directory, but invoke them through the skill path, for example:

```bash
DB_WORK_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/db-work"
"$DB_WORK_SKILL_DIR/scripts/inspect_changes.sh"
```

Do not assume `scripts/inspect_changes.sh`, `scripts/run_sqlplus_dev.sh`, or the other helper scripts exist inside the project checkout.

## Session Temp Files

At the beginning of db-work activity, create or reuse a temporary db-work session:

```bash
DB_WORK_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/db-work"
"$DB_WORK_SKILL_DIR/scripts/start_session.sh"
```

The session script creates a temporary directory outside the project repo, writes the non-secret `.db-work.yml` there, and prints `DB_WORK_SESSION_DIR`, `DB_WORK_CONFIG`, and `DB_WORK_TEMP_DIR` exports. Use that temp `.db-work.yml` for db-work defaults. Do not create a new `.db-work.yml` in the Oracode repo unless the user explicitly asks for a persistent repo config.

Put temporary/scratch files created by the agent under `DB_WORK_TEMP_DIR` or `DB_WORK_SESSION_DIR`. Generated DEV evidence under `util/<TICKET>/dev_sandbox/` is considered a durable work artifact, not a temporary file, unless the user explicitly asks to treat it as temporary.

When the user says they are done, for example "let's end the session", "we are finished", "done with db-work", or similar, run:

```bash
"$DB_WORK_SKILL_DIR/scripts/cleanup_session.sh"
```

Cleanup removes only marked db-work temporary session directories. After cleanup, mention which session directory was removed. Do not remove durable repo artifacts unless the user explicitly asks.

## Default Workflow

0. Start or reuse a temporary session.
   - Use the skill-bundled `scripts/start_session.sh`.
   - Store `.db-work.yml` in the temporary session directory, not in the project repo.
   - Use `DB_WORK_CONFIG` when invoking scripts that need config.

1. Inspect the current repo state.
   - Prefer the skill-bundled `scripts/inspect_changes.sh`.
   - Identify branch, ticket, changed SQL files, changed changelog files, and generated sandbox files.

2. Resolve local configuration.
   - Read `.db-work.yml` from `DB_WORK_CONFIG` or `DB_WORK_SESSION_DIR/.db-work.yml`.
   - Treat repo-root `.db-work.yml` only as a legacy/persistent fallback when it already exists.
   - Prefer explicit user input for team/changelog, author, ticket, suffix, and DEV alias.
   - Use config defaults only when the user has not provided a value.

3. Edit Liquibase-owned SQL files.
   - Keep the real objects under schema folders such as `PROD/` and `YES_SERVICES/`.
   - Preserve Oracode SQL rules from `references/oracode-rules.md`.
   - Do not put DEV-only suffixed objects into Liquibase-owned schema folders.

4. Update the team changelog.
   - Use the skill-bundled `scripts/generate_changelog_entry.py`.
   - Require an explicit team/changelog when config cannot resolve it.
   - Review the generated XML before writing when the change is non-trivial.

5. Generate DEV-only shadow objects when requested or useful.
   - Use the skill-bundled `scripts/generate_shadow_objects.py`.
   - Put generated files under `util/<TICKET>/dev_sandbox/objects/`.
   - Use the configured suffix, for example `_EDI`.
   - Treat generated shadow files as DEV-only and reviewable, not production Liquibase artifacts.

6. Generate a DEV deploy script.
   - Use the skill-bundled `scripts/generate_dev_deploy.py`.
   - Prefer SQLPlus `@@` includes so object scripts are resolved relative to the deploy script.
   - Include `grant execute` statements for executable shadow objects so DEV users can query them, for example `grant execute on yes_services.trans_const_overlap_edi to ye_dev;`.
   - Use `--grant-execute-to <user>` or `DB_WORK_GRANT_EXECUTE_TO` when the DEV grantee is not `ye_dev`.
   - Spool logs under `util/<TICKET>/dev_sandbox/logs/`.

7. Execute against DEV only when explicitly requested.
   - Read `references/sqlplus-dev-execution.md` first if the wallet/alias setup is unknown.
   - Use the skill-bundled `scripts/run_sqlplus_dev.sh`.
   - If SQLPlus is missing, `scripts/run_sqlplus_dev.sh` should call `scripts/ensure_sqlplus.sh` to install it when possible.
   - Automatic SQLPlus installation is best-effort and currently supports macOS by following Oracle's official Instant Client DMG flow. It should install only Oracle Instant Client Basic and SQL*Plus.
   - Do not create ad-hoc binary shims, shell wrappers, or copied Oracle binaries outside the skill. Use the installed Oracle CLI tools on `PATH`.
   - If wallet setup is needed, run `scripts/setup_oracle_wallet.sh`; it should invoke `scripts/ensure_sqlplus.sh --wallet-tools` before creating wallet files.
   - Wallet setup uses `mkstore` for Secure External Password Store credentials. `mkstore` is deprecated by Oracle, but this skill uses it deliberately because it is a leaner and more reliable macOS ARM setup path than requiring a full Oracle Database Client.
   - Automatic wallet-tool setup downloads Oracle's Java wallet utility jar from Maven Central and creates a local `mkstore` launcher. The user should not need to manually install a full database client for wallet setup.
   - After the required CLI tools are available, `scripts/setup_oracle_wallet.sh` should create/update `tnsnames.ora`, `sqlnet.ora`, the SEPS wallet, and the wallet credential. Ask the user only for missing non-secret connection details such as DEV alias or TNS descriptor; secrets must be entered only in local terminal prompts.
   - Never accept or store passwords in chat.
   - Prefer Oracle Secure External Password Store with a connect string like `/@DEVDB_ALIAS`.
   - Refuse non-DEV aliases unless the user explicitly overrides the guardrail.

8. Probe DEV metadata after shadow compile.
   - After `deploy_shadow.sql` succeeds, generate `metadata_probe.sql` with the skill-bundled `scripts/generate_metadata_probe.py`.
   - Run the probe against DEV through the same safe SQLPlus path.
   - Prefer the resulting `logs/db_metadata.tsv` as the signature source for comparison spec generation.
   - DB metadata is more reliable than source regex for argument names, argument modes, overloads, and return types.

9. Infer and review comparison calls.
   - Use the skill-bundled `scripts/generate_compare_spec.py` to parse package/function/procedure signatures from the changed object specs.
   - Prefer the skill-bundled `scripts/generate_compare_spec.py --metadata-tsv logs/db_metadata.tsv` after DEV compile.
   - By default, infer cases only for public functions/procedures whose declaration or implementation lines changed in the ticket diff.
   - If changed lines are inside a private package helper, infer public package procedures/functions that call that helper and test those public callers instead.
   - Use `--callable NAME` when the affected entry point is known or the diff cannot be mapped safely.
   - Use `--all-callables` only when the user explicitly wants broad package coverage.
   - The script writes `compare_spec.json` with proposed original and suffixed calls.
   - Each affected callable gets proposed runs based only on that callable's actual parameters.
   - Do not assume every callable has ISO, market, or date-range arguments; vary those dimensions only when matching parameters exist.
   - If no safe scenario dimensions are inferred, the script creates a single `baseline_review_required` run and the agent must ask the user for procedure/function-specific scenarios.
   - Assign an `evidence_mode` to each run:
     - `regression_compare`: original can execute the same scenario and should match shadow.
     - `shadow_expected_result`: original cannot execute this scenario, such as a new branch, new market/ISO, or completely new callable. Infer expected rows from dependent DEV tables and compare shadow output to that expected query.
     - `expected_delta`: original and shadow can both execute the scenario, but the behavior intentionally changes. Infer the expected original-vs-shadow delta from code, ticket intent, and dependent DEV tables. Ask the user only if the expected delta cannot be inferred safely.
     - `performance_only`: collect shadow-only or selected-source performance figures when no functional compare is meaningful.
     - `compile_contract_validation`: validate compile/signature/dependent-caller contract when result evidence is not applicable.
   - For new branches in existing callables, include both old-branch `regression_compare` runs when applicable and new-branch `shadow_expected_result` runs.
   - For added result columns, compare common columns with `regression_compare` and validate new columns with `shadow_expected_result` or `expected_delta`.
   - For completely new stored procedures/functions, use `shadow_expected_result` plus shadow-only performance evidence.
   - For intentional behavior fixes, do not treat non-zero diff counts as failures by default. Use `expected_delta` and require the inferred expected delta to be reviewed or corrected before execution.
   - Treat `SYS_REFCURSOR` as an output-observation strategy named `refcursor_output`, not as a separate target-selection strategy.
   - For `refcursor_output`, select the affected public wrapper first: a function returning `SYS_REFCURSOR`, a procedure with `OUT` or `IN OUT SYS_REFCURSOR`, or public parent callers of a changed private cursor helper.
   - Materialize `refcursor_output` by calling the public wrapper and fetching the full cursor output into comparable DEV rows. Prefer `DBMS_SQL.TO_CURSOR_NUMBER` and `DBMS_SQL.DESCRIBE_COLUMNS2` for generic scalar-column cursors.
   - Performance-test `refcursor_output` as wrapper call plus full cursor fetch/materialization, not merely cursor open or a later select from already materialized rows.
   - For `procedure_side_effect` cases, infer the observer query during the code scan before asking the user to supply one.
   - To infer a procedure observer, inspect the affected procedure body, changed private helpers, called routines, DML target tables, output/log/temp tables, package state, and ticket intent. Generate the `original_result_sql` and `shadow_result_sql` that best prove the changed behavior.
   - Ask the user for observer corrections only when no defensible observer can be inferred, the observer depends on business fixtures not present in code, or executing the procedure would be unsafe without setup/cleanup.
   - Review `references/compare-spec-format.md` when editing the spec.
   - Show the inferred calls, proposed default arguments, and proposed run scenarios to the user.
   - Show each run's `evidence_mode` and why it was chosen.
   - Ask the user to add/remove/edit scenarios so they match the changed procedure/function's real business cases.
   - Ask the user to overwrite defaults when a value is business-specific, marked `review_required`, contains `TODO`, the inferred observer query needs business confirmation, or `expected_delta` cannot be inferred with high confidence.
   - Do not execute comparison or stats SQL until the proposed calls are approved or corrected.

10. Generate comparison evidence.
   - Use the skill-bundled `scripts/generate_compare_harness.py --spec compare_spec.json` for original-vs-suffixed row count and result-difference SQL across every reviewed run scenario.
   - Use the skill-bundled `scripts/generate_stats_harness.py --spec compare_spec.json` for timing/autotrace/statistics SQL across the same reviewed run scenarios.
   - Do not generate row-count, diff, or performance SQL directly from `shadow_manifest.json` during normal work.
   - Performance SQL must use the same reviewed `compare_spec.json`; do not generate performance SQL directly from `shadow_manifest.json` during normal work.
   - The stats harness must include only the affected stored procedures/functions represented by `compare_spec.json`.
   - The compare harness must respect run-level `evidence_mode`: original-vs-shadow for `regression_compare`, expected-vs-shadow for `shadow_expected_result`, actual-vs-expected delta for `expected_delta`, and no functional diff for `performance_only` or `compile_contract_validation`.
   - For `procedure_side_effect`, the compare and stats harnesses must refuse unresolved observer placeholders. Replace generated observer placeholders with inferred or user-approved SQL before creating evidence.
   - For `refcursor_output`, the compare and stats harnesses must refuse unresolved cursor materialization placeholders. Replace generated `TODO_REF_CURSOR_*` scaffolds with inferred or user-approved call-and-fetch materialization before creating evidence.
   - For `expected_delta`, the compare harness must refuse unresolved expected-delta placeholders. Replace generated or placeholder delta SQL with inferred or user-approved expected delta SQL before creating evidence.
   - Use the skill-bundled `scripts/summarize_sqlplus_logs.py` to calculate mean KPI values across the run scenarios for each original-vs-shadow source.
   - Run generated scripts against DEV only with the safe DEV execution path.

11. Summarize logs and validate.
   - Use the skill-bundled `scripts/summarize_sqlplus_logs.py` for SQLPlus output.
   - Run `./dev_utils/lint_changed_files.sh` in Oracode before handoff whenever possible.
   - Report changed files, generated files, deploy order, validation, and remaining manual steps.

## Repo Config

Use this optional repo-local file for non-secret defaults:

```yaml
# Temporary .db-work.yml created by scripts/start_session.sh
author: Your Name
user_suffix: ABC
default_team: visual-analytics
dev_connect: /@DEVDB_ALIAS
grant_execute_to: ye_dev

teams:
  visual-analytics:
    changelog: visualanalytics_changelog.xml
    aliases:
      - visual analytics
      - va
      - visual_analytics
      - visualanalytics_changelog.xml
  dataops:
    changelog: dataops_changelog.xml
    aliases:
      - data ops
      - dataops
```

Do not store secrets in `.db-work.yml`. Create this file in the temporary db-work session directory by default, not in the project repo.

## Script Map

These scripts are bundled with the skill under the `db-work/scripts/` directory. They are not expected to exist in the project repo.

- `scripts/start_session.sh`: Create a marked temporary db-work session directory, temp `.db-work.yml`, and temp scratch directory.
- `scripts/cleanup_session.sh`: Remove marked temporary db-work session directories when the user ends the session.
- `scripts/inspect_changes.sh`: Print branch, inferred ticket, changed SQL files, changelog files, and generated sandbox files.
- `scripts/generate_changelog_entry.py`: Generate or append ordered Liquibase changesets to the resolved team changelog.
- `scripts/generate_shadow_objects.py`: Create DEV-only suffixed object copies and a `shadow_manifest.json`.
- `scripts/generate_dev_deploy.py`: Create an ordered SQLPlus deploy script from the shadow manifest, including execute grants for DEV shadow objects.
- `scripts/ensure_sqlplus.sh`: Ensure SQLPlus is available; auto-install only Oracle Instant Client Basic and SQL*Plus on macOS from Oracle's official DMG packages when missing. With `--wallet-tools`, also ensure `mkstore` is available by installing the lean Java-based launcher when needed.
- `scripts/setup_oracle_wallet.sh`: Create/update local Oracle network config, SEPS wallet, and `/@DEV_ALIAS` credential with `mkstore`; it runs the required CLI check first and user secrets are entered only in local terminal prompts.
- `scripts/run_sqlplus_dev.sh`: Execute a SQL script against DEV using a safe SQLPlus connect alias.
- `scripts/generate_metadata_probe.py`: Create SQLPlus metadata probe SQL for compiled original/shadow objects.
- `scripts/generate_compare_spec.py`: Infer affected callable signatures and write an editable `compare_spec.json` with proposed multi-run arguments.
- `scripts/generate_compare_harness.py`: Create original-vs-shadow row count and difference-check SQL from reviewed run scenarios.
- `scripts/generate_stats_harness.py`: Create affected-callable original-vs-shadow SQLPlus timing/autotrace SQL from reviewed run scenarios.
- `scripts/summarize_sqlplus_logs.py`: Summarize SQLPlus logs for errors, common statistics, and mean performance KPIs across runs.

## Safety Rules

- Default to generating scripts, not executing database changes.
- Execute only after the user explicitly asks for DEV execution.
- Never request, echo, write, or commit database passwords.
- Prefer `/@DEV_ALIAS` wallet connections.
- Reject aliases that do not look like DEV unless the user explicitly overrides and the task still fits the safe workflow.
- Keep generated DEV artifacts under `util/<TICKET>/dev_sandbox/`.
- Keep temporary/scratch files under `DB_WORK_TEMP_DIR` or `DB_WORK_SESSION_DIR` so they can be cleaned up at session end.
- Exclude generated DEV sandbox files from Liquibase changelog generation.
- Surface uncertainty about team changelog, deploy order, or object renaming before writing risky changes.

## Oracle Wallet Setup

If the DEV wallet does not exist, use `scripts/setup_oracle_wallet.sh`. The script should install/check SQLPlus, require `mkstore`, create the local folders/config files, and invoke `mkstore`; the user's manual work should be limited to typing secrets into local terminal prompts. Never ask the user to reveal a database password in chat. Be explicit that `mkstore` is deprecated by Oracle, but db-work uses it because it gives the team a lean macOS ARM wallet setup without a full Oracle Database Client.
