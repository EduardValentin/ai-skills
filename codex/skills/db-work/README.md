# db-work Skill

Human-facing documentation for the `db-work` Codex skill.

The runtime instructions live in `SKILL.md`. This README explains what each bundled piece does, how they fit together, and how the skill reduces manual Oracle/Liquibase work in Oracode.

## Purpose

`db-work` supports the Oracode database workflow:

- inspect changed Oracle SQL and Liquibase changelog files;
- update team changelogs for Liquibase-owned production objects;
- create DEV-only user-suffixed shadow objects such as `PACKAGE_A_ABC`;
- deploy generated DEV scripts through SQLPlus using a wallet alias;
- install SQLPlus automatically on supported Macs from Oracle's official Instant Client DMGs when it is missing;
- create/update the local Oracle wallet configuration after verifying SQLPlus and `mkstore`;
- keep session configuration and scratch files in a temporary db-work session folder instead of the project repo;
- clean marked temporary session folders when the user ends the session;
- avoid ad-hoc binary shims, copied Oracle binaries, and extra wrapper files outside the skill;
- use deprecated `mkstore` for wallet creation because it is the leanest macOS ARM setup path for this workflow;
- grant execute privileges for shadow packages to the configured DEV schema;
- infer affected stored procedures/functions from source diffs and DEV metadata;
- generate reviewed original-vs-shadow comparison scenarios;
- run row-count, result-diff, and SQLPlus autotrace performance checks;
- summarize logs into evidence that can be attached to a ticket or PR.

The skill is intentionally DEV-focused. It should not deploy to TEST, STAGE, or PROD directly.

## Directory Layout

```text
db-work/
├── SKILL.md
├── README.md
├── agents/
│   └── openai.yaml
├── assets/
│   └── sql/
├── references/
└── scripts/
```

## Core Files

### `SKILL.md`

The operational contract for Codex. It defines when the skill should trigger, the default workflow, safety rules, script map, wallet guidance, and how job/Jira ticket context should be gathered.

Important behaviors in `SKILL.md`:

- use `ticket-start` first when a job/Jira ticket drives the work and that skill is available;
- fall back to asking the user for minimum ticket details when `ticket-start` is not available;
- keep personal-project/Linear workflow out of scope;
- prefer generated scripts over one-off SQL pasted into chat;
- execute only against DEV after explicit user approval;
- auto-install only SQLPlus runtime dependencies on supported machines when SQLPlus is missing;
- use `mkstore` to create wallet configuration, with an explicit note that Oracle deprecates it but the team chooses it for lean macOS ARM setup;
- create/update the wallet through `scripts/setup_oracle_wallet.sh`, which checks required CLI tools first;
- install `mkstore` through the skill's Java-based launcher when missing;
- avoid unnecessary wrappers and binaries; use installed CLI tools on `PATH`;
- create `.db-work.yml` in a temporary db-work session folder by default;
- remove marked session temp files when the user says the session is finished;
- never ask for or store database passwords;
- prefer Oracle Secure External Password Store connections such as `/@ORACODE_DEV`;
- infer comparison scenarios from actual callable signatures, not hardcoded ISO/date assumptions;
- infer procedure side-effect observer queries from code behavior before asking the user for corrections;
- classify functions returning `SYS_REFCURSOR` and procedures with `OUT`/`IN OUT SYS_REFCURSOR` as `refcursor_output`;
- materialize `refcursor_output` by testing the public wrapper and fetching the full cursor into comparable DEV rows;
- select a run-level evidence mode: `regression_compare`, `shadow_expected_result`, `expected_delta`, `performance_only`, or `compile_contract_validation`;
- infer expected deltas for intentional behavior changes before asking the user;
- test only affected public stored procedures/functions, including public callers when a private helper changed.

Fallback ticket intake asks only for missing details needed for the current task: ticket id, title or goal, acceptance criteria, affected objects or callables, team/changelog, branch intent, known DEV test scenarios, and open questions. The agent should fill what it can from git diffs, changelogs, SQL files, and sandbox artifacts.

### `README.md`

This file. It is documentation for humans maintaining or auditing the skill. Codex does not need to load it during normal skill execution.

### `agents/openai.yaml`

UI metadata used by Codex skill lists and chips:

- `display_name`: human-readable skill name;
- `short_description`: short UI summary;
- `default_prompt`: a suggested prompt for invoking the skill.

Keep this aligned with the `SKILL.md` frontmatter description when the skill scope changes.

## Assets

### `assets/sql/dev_deploy_template.sql`

Template used by the DEV deploy generator. It provides the SQLPlus script shape for deploying generated shadow objects under `util/<TICKET>/dev_sandbox/`.

The generated deploy script normally includes:

- SQLPlus safety/session setup;
- spool logging;
- ordered `@@` includes for generated object files;
- object validity checks;
- `grant execute` statements for shadow packages/functions/procedures where needed.

### `assets/sql/compare_counts_template.sql`

Template for original-vs-shadow functional comparison SQL. The generated script executes reviewed scenarios from `compare_spec.json` and reports:

- original row count;
- shadow row count;
- `original minus shadow` diff count;
- `shadow minus original` diff count.

For table functions whose original and shadow return types differ, the compare spec should project common columns explicitly.

### `assets/sql/sql_stats_template.sql`

Template for SQLPlus autotrace performance runs. The generated script runs the same reviewed scenarios as the row comparison harness and captures SQLPlus statistics such as:

- elapsed time;
- consistent gets;
- logical reads;
- physical reads;
- redo size;
- sorts;
- rows processed;
- SQL*Net bytes and round trips.

## References

### `references/oracode-rules.md`

Condensed Oracode repository rules. Load this when editing Liquibase-owned SQL or deciding deploy order.

It covers conventions such as:

- schema/object directory layout;
- PL/SQL trailing slash requirements;
- no inline comments;
- Liquibase changeset shape;
- changelog dependency order;
- linter expectations.

### `references/sqlplus-dev-execution.md`

Wallet and SQLPlus execution guidance. Load this when DEV connectivity is unknown, wallet setup is missing, or `sqlplus -L /@ALIAS` fails.

It documents:

- Oracle Instant Client expectations, with Basic + SQL*Plus as the runtime minimum;
- Oracle's official macOS DMG install flow;
- why `mkstore` is used even though Oracle deprecates it;
- `TNS_ADMIN` and `tnsnames.ora`;
- Secure External Password Store setup with `mkstore`;
- agent-assisted wallet setup via `scripts/setup_oracle_wallet.sh`;
- how to validate a DEV alias;
- safe failure handling for credentials.

### `references/compare-spec-format.md`

The editable JSON contract for comparison and performance scenarios.

Use it when reviewing or manually adjusting `compare_spec.json`. It explains:

- case structure;
- run scenario structure;
- argument representation;
- original/shadow SQL fields;
- review-required flags;
- how row-count, result-diff, and performance harnesses consume the spec.

## Scripts

All helper scripts live in the `db-work` skill folder, not in an Oracode project checkout. Run them from the Oracode repo root when they need repo context, but invoke them through the skill directory:

```bash
DB_WORK_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/db-work"
"$DB_WORK_SKILL_DIR/scripts/inspect_changes.sh"
```

### `scripts/start_session.sh`

Creates a marked temporary db-work session directory outside the project repo. It writes:

- `.db-work.yml`: non-secret session defaults;
- `session.env`: shell exports for `DB_WORK_SESSION_DIR`, `DB_WORK_CONFIG`, and `DB_WORK_TEMP_DIR`;
- `tmp/`: scratch directory for temporary files created during the session.

The script also updates a `current` symlink under the session base so helper scripts can find the active temp config even when `DB_WORK_CONFIG` is not explicitly passed.

### `scripts/cleanup_session.sh`

Removes marked db-work temporary session directories. It is intended to run when the user says "let's end the session", "we are finished", or equivalent.

It only removes directories containing the `.db-work-session` marker. It does not remove durable repo artifacts such as `util/<TICKET>/dev_sandbox/` unless the user explicitly asks for that.

### `scripts/inspect_changes.sh`

Prints current branch context and changed files. It is the first-pass inventory helper for Oracode work.

It is meant to identify:

- branch name;
- likely ticket id;
- changed SQL files;
- changed changelog files;
- existing generated sandbox files.

### `scripts/generate_changelog_entry.py`

Builds Liquibase changesets for selected SQL files and a chosen team changelog.

It helps enforce:

- one changeset per object file;
- Jira ticket labels;
- `runWith="sqlplus"`;
- `runOnChange="true"` for redeployable PL/SQL objects;
- Unix-style SQL file paths;
- stable id numbering.

The agent still needs to review generated XML before writing or handing off.

### `scripts/generate_shadow_objects.py`

Creates DEV-only suffixed copies of changed database objects and writes `shadow_manifest.json`.

Typical output location:

```text
util/<TICKET>/dev_sandbox/objects/
```

Typical behavior:

- clone the full package/type/function/procedure object, not just one changed routine;
- rename the object with the configured suffix, for example `_ABC`;
- rewrite internal references where safe;
- keep generated shadow files out of production Liquibase paths.

### `scripts/generate_dev_deploy.py`

Creates a SQLPlus deploy script from `shadow_manifest.json`.

The generated script is used for DEV-only compilation of shadow objects and can include execute grants such as:

```sql
grant execute on yes_services.trans_const_overlap_edi to ye_dev;
```

The grantee defaults from skill config or environment, and can be overridden with `--grant-execute-to`.

### `scripts/run_sqlplus_dev.sh`

Safe SQLPlus wrapper for DEV execution.

It expects a wallet-style connect string such as:

```bash
sqlplus -L /@ORACODE_DEV
```

It should be used for running generated deploy, metadata, comparison, and stats scripts.

If `sqlplus` is missing or not on `PATH`, this wrapper calls `scripts/ensure_sqlplus.sh` and also searches common Oracle client install locations.

### `scripts/ensure_sqlplus.sh`

Ensures SQLPlus is available before DEV execution.

Behavior:

- if `sqlplus` is already on `PATH` or in a common Oracle client directory, it exits successfully;
- on macOS, it uses Oracle's official DMG install flow to install only Instant Client Basic and SQL*Plus;
- `DB_WORK_SQLPLUS_INSTALL_MODE=homebrew` can be used when a team intentionally standardizes on the Homebrew tap instead;
- on unsupported platforms, it prints manual install guidance rather than guessing;
- `DB_WORK_AUTO_INSTALL_SQLPLUS=0` disables automatic installation.

With `--wallet-tools`, it also ensures `mkstore` is available. `mkstore` is deprecated by Oracle, but the skill uses it because it avoids a full Oracle Database Client requirement on macOS ARM.

When `mkstore` is missing, the script downloads Oracle's database security jar from Maven Central into `~/.oracle/mkstore/lib` and creates a local launcher under `~/.oracle/mkstore/bin`. Java and curl must be available. Secrets are still collected only by local terminal prompts during wallet setup.

### `scripts/setup_oracle_wallet.sh`

Creates the local Oracle wallet configuration for DEV connections.

It handles:

- checking/installing required Oracle CLI tools before wallet changes;
- creating `~/.oracle/network/admin` and the wallet directory;
- adding a non-secret `tnsnames.ora` alias when a descriptor is provided;
- writing a managed `WALLET_LOCATION` plus `SQLNET.WALLET_OVERRIDE = TRUE` block to `sqlnet.ora`;
- creating the Oracle auto-login wallet with `mkstore -create`;
- creating the `/@DEV_ALIAS` credential with `mkstore -createCredential`;
- optionally testing the resulting `/@DEV_ALIAS` SQLPlus connection.

The agent may ask for non-secret values such as DEV alias or TNS descriptor. Secrets are entered only in local terminal prompts. The script does not create extra shell wrappers, symlinks, or copied Oracle binaries.

### `scripts/generate_metadata_probe.py`

Generates SQL that queries DEV metadata for compiled original and shadow objects.

The output is usually:

```text
util/<TICKET>/dev_sandbox/metadata_probe.sql
util/<TICKET>/dev_sandbox/logs/db_metadata.tsv
```

The metadata probe is important because database metadata is more reliable than source regex for:

- argument order;
- argument modes;
- overloads;
- return types;
- package validity;
- original vs shadow object shape.

### `scripts/generate_compare_spec.py`

Infers affected callable signatures and writes an editable `compare_spec.json`.

Preferred input is DEV metadata from `db_metadata.tsv`. The script can also use source parsing when metadata is unavailable.

Important behavior:

- infer only affected public stored procedures/functions by default;
- support explicit callable selection with `--callable`;
- avoid generating calls for every routine in a cloned package;
- detect private-helper changes and steer testing toward public parent callers;
- propose default arguments based on the actual signature;
- mark uncertain values as review-required instead of pretending they are safe;
- vary ISO/date/market-like dimensions only when matching parameters exist.
- default generated runs to `regression_compare`, then let the agent revise specific runs to `shadow_expected_result`, `expected_delta`, `performance_only`, or `compile_contract_validation` based on code/ticket analysis.
- for procedure side effects, add an observer-inference scaffold that requires the agent to inspect DML targets, called routines, output/log/temp tables, package state, and ticket intent before evidence generation.
- for SYS_REFCURSOR output, add a cursor-materialization scaffold that requires call-and-fetch comparison through the affected public wrapper before evidence generation.

### `scripts/generate_compare_harness.py`

Reads reviewed `compare_spec.json` and writes original-vs-shadow row-count and result-diff SQL.

The generated harness should be run only after scenarios are reviewed or corrected. It validates functional equivalence for the affected callable scenarios. It respects `evidence_mode`: original-vs-shadow for `regression_compare`, expected-vs-shadow for `shadow_expected_result`, actual-vs-expected deltas for `expected_delta`, and skip prompts for `performance_only` / `compile_contract_validation`. For `procedure_side_effect`, it fails fast if observer SQL still contains unresolved placeholders or `observer_inference.status` has not been changed to `inferred` or `approved`. For `refcursor_output`, it fails fast until the cursor call-and-fetch materialization is inferred or approved.

### `scripts/generate_stats_harness.py`

Reads reviewed `compare_spec.json` and writes SQLPlus autotrace performance SQL for the same affected callable scenarios.

This keeps performance testing aligned with functional testing and prevents broad, noisy package-wide benchmarking. It uses both original and shadow for `regression_compare` / `expected_delta`, and shadow-only stats for `shadow_expected_result` / `performance_only`. For `procedure_side_effect`, it uses the same approved observer SQL as the comparison harness and refuses unresolved observer scaffolds. For `refcursor_output`, it measures the wrapper call plus full cursor fetch/materialization and refuses unresolved cursor scaffolds.

### `scripts/summarize_sqlplus_logs.py`

Parses SQLPlus logs and produces a Markdown evidence summary.

It reports:

- detected Oracle/SQLPlus errors;
- elapsed values;
- autotrace statistics;
- mean KPI values across scenarios;
- original vs shadow deltas and percent deltas where possible.

## Typical Workflow

1. Start a temporary db-work session:

   ```bash
   DB_WORK_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/db-work"
   "$DB_WORK_SKILL_DIR/scripts/start_session.sh"
   ```

2. Inspect the branch:

   ```bash
   "$DB_WORK_SKILL_DIR/scripts/inspect_changes.sh"
   ```

3. Update Liquibase-owned SQL and the correct team changelog.

4. Generate DEV-only shadow objects:

   ```bash
   "$DB_WORK_SKILL_DIR/scripts/generate_shadow_objects.py" ...
   ```

5. Generate and run DEV deploy:

   ```bash
   "$DB_WORK_SKILL_DIR/scripts/generate_dev_deploy.py" ...
   "$DB_WORK_SKILL_DIR/scripts/run_sqlplus_dev.sh" --connect /@ORACODE_DEV --script util/<TICKET>/dev_sandbox/deploy_shadow.sql
   ```

6. Probe DEV metadata:

   ```bash
   "$DB_WORK_SKILL_DIR/scripts/generate_metadata_probe.py" ...
   "$DB_WORK_SKILL_DIR/scripts/run_sqlplus_dev.sh" --connect /@ORACODE_DEV --script util/<TICKET>/dev_sandbox/metadata_probe.sql
   ```

7. Generate and review comparison scenarios:

   ```bash
   "$DB_WORK_SKILL_DIR/scripts/generate_compare_spec.py" --metadata-tsv util/<TICKET>/dev_sandbox/logs/db_metadata.tsv ...
   ```

8. Generate row-diff and performance harnesses:

   ```bash
   "$DB_WORK_SKILL_DIR/scripts/generate_compare_harness.py" --spec util/<TICKET>/dev_sandbox/compare_spec.json
   "$DB_WORK_SKILL_DIR/scripts/generate_stats_harness.py" --spec util/<TICKET>/dev_sandbox/compare_spec.json
   ```

9. Run both harnesses through the DEV wrapper.

10. Summarize logs:

   ```bash
   "$DB_WORK_SKILL_DIR/scripts/summarize_sqlplus_logs.py" util/<TICKET>/dev_sandbox/logs/*.log --output util/<TICKET>/dev_sandbox/logs/summary_<TICKET>.md
   ```

11. End the session and clean temporary config/scratch files:

   ```bash
   "$DB_WORK_SKILL_DIR/scripts/cleanup_session.sh"
   ```

## Sync Rule

When maintaining the skill in a source repository and an installed Codex skill directory, keep those copies as a one-to-one mirror.

```text
<ai-skills-repo>/codex/skills/db-work
${CODEX_HOME:-$HOME/.codex}/skills/db-work
```

After changing either copy, verify sync with:

```bash
diff -qr <ai-skills-repo>/codex/skills/db-work "${CODEX_HOME:-$HOME/.codex}/skills/db-work"
```

No output means the two copies match.
