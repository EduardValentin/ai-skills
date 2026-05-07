# db-work Glossary

File-by-file / script-by-script reference for the skill. The high-level workflow lives in [`README.md`](README.md); the iron rules live in [`SKILL.md`](SKILL.md).

## Top-level files

### `SKILL.md`
Entrypoint. Holds the trigger description (frontmatter), the phase glossary, the phase-progression table (with explicit `Wait for…` user gates), the iron rules (terse `rule + pointer` form), and the session-lifecycle one-liner. SKILL.md is always loaded; it's the orchestration + iron-rule layer, not a methodology document — references hold the mechanics.

### `README.md`
Lean overview for users: what the skill does, when to use it, the workflow as a pseudocode algorithm with see-below explanations, the artifact table, the workflow gates at a glance, dependencies, and the repo sync rule.

### `glossary.md`
This file.

### `agents/openai.yaml`
Codex marketplace metadata: display name + short description shown in the Codex `/plugins` UI. No runtime behavior beyond presentation.

## Assets (`assets/sql/`)

Read-only templates the agent fills in during Phase 5/6. Never edited in place — copied into `util/<TICKET>/` and customized there.

### `assets/sql/perf_harness_template.sql`
Bench harness skeleton for a single variant. Resets session state, snapshots `v$mystat` counters, times the variant call with `dbms_utility.get_time`, looks up `optimizer_cost` from `v$sql` for the SQL annotated with `/*+ db_work_perf_harness */`, writes ONE TSV line of KPI values per measured run. Includes four variant-body shapes (table function, scalar function, procedure with side effects, SYS_REFCURSOR) — pick one and delete the rest when filling in.

### `assets/sql/perf_harness_grants.sql`
One-time grants the DEV user needs for the perf harness to run: read on `v$mystat`, `v$statname`, `v$sql`. Run via `run_sqlplus_dev.sh` once per DEV environment.

### `assets/sql/bench_spec_template.json`
Template for `util/<TICKET>/variants/bench_spec.json`. Lists the variants, their harness paths, and the KPI list (in the order the harness writes them — must match exactly).

## References (`references/`)

Loaded on demand by the agent when the corresponding phase is active. SKILL.md's iron rules point to these for mechanics + rationalizations.

### `references/01-machine-setup.md`
Doctor + auto-fix flow. Eight readiness checks (the eighth is harness-specific: Codex `multi_agent` flag or Claude `permissions.deny`). What's auto-installed (Oracle Instant Client, mkstore, wallet) and what isn't (plugin install, multi_agent flag). Setup-only sessions are valid; the doctor is the gateway. The amber-banner rule for partial-doctor generation-only flows.

### `references/02-intake-and-brainstorm.md`
Phase 2 intake (ticket fields the agent collects) + the **scope-research subagent** (when to dispatch, prompt template, required digest schema, parent rules after the digest returns, what's out of scope, rationalizations that fail the rule). Phase 3 brainstorm gate, the trivial-change escape hatch (all 7 criteria), the brainstorm summary's required fields.

### `references/03-planning-with-variants.md`
Plan template (saved at `util/<TICKET>/plan.md`), variant rules (2–3 floor, obvious-variant escape only on user request, even on obvious-variant the single variant still gets benched), the **performance acceptance criterion** (a perf floor — NOT a winner-picker), the KPI list, the "Selection — human picks" section (the plan does NOT name a winner; the human picks from qualifying variants on Phase 5's decision surface).

### `references/04-performance-debugging.md`
Performance methodology — the 8-step algorithm (baseline → hypothesize → measure → diagnose → expand? → qualify → recommend → wait for pick), KPI taxonomy with sources, bench harness shape (template variants A–D, required v$ grants, `bench_spec.json`), warm-cache policy and rationale (`--warmup 2 --runs 5` defaults), comparable-runs rules, adjacent-code expansion path (re-brainstorm + user-authored prose), regression diagnosis (variant lead on `elapsed_ms` is not the winner if `consistent_gets` rises >10% on a dependent caller, etc.), reporting fields, perf-evidence rationalizations.

### `references/05-implementation-and-shadow.md`
Variant directory layout, shadow-object compilation, Liquibase-owned edits (winner only — promoted at Phase 6 entry), changelog ordering, DEV shadow generation, lint, **per-variant subagent dispatch** (default for non-template-fill variants; parallel optional for 3-variant heavy work), parent serializing steps (bench, parameter-verification dispatch, decision-surface posting, winner promotion), the **variant decision surface** (per-variant entries with bench KPIs + cleanliness scoring on 6 axes, agent recommendation format, the explicit ask, what the gate prevents, divergence handling, rationalizations that fail).

### `references/06-dev-execution-and-evidence.md`
Phase 6 entry sequence (promote → manifest → metadata probe → compare-spec generation → parameter verification → review surface), the **DEV write gate** (DDL/DML operation list, what runs without a gate, plan/spec coverage rules, 5-line announce format, hard rules, rationalizations), execution + non-DEV alias handling, post-execution summary, comparison evidence flow, the **parameter-verification subagent** (when to dispatch in Phase 5 and Phase 6, prompt template, required digest schema, pass/fail bar by `evidence_mode`, parent rules, what's out of scope, rationalizations), the **compare-spec approval gate** (what the agent posts verbatim, approval token, what the gate prevents, rationalizations), harness execution (post-spec-approval), quick rules.

### `references/07-code-walkthrough-and-report.md`
Phase 7 batched walkthrough gate (file list source = `git diff --name-only`, per-file 7-field schema, files in scope, user signal to proceed, same-turn report ban, pressure resistance), the handoff report template emitted by `db-work-report.sh`, the done-definition checklist.

### `references/08-session-cleanup.md`
End-of-session three-step order (DEV cleanup → per-ticket scratch removal → local session-dir cleanup), trigger phrases, DEV cleanup mechanics (`dev_cleanup.sh` aggregates manifests, generates DROPs in reverse-of-deploy order, gates with announce + "go"), per-ticket scratch removal (full files-removed and files-kept lists, dry-run preview gate, pressure resistance), confirmation gate, after-cleanup state.

### `references/compare-spec-format.md`
`compare_spec.json` format reference — run scope (default = public callables whose declaration or implementation lines changed in the diff), run dimensions, scope controls (`--callable`, `--all-callables`), evidence-mode taxonomy (`regression_compare`, `shadow_expected_result`, `expected_delta`, `performance_only`, `compile_contract_validation`) with mapping rules, agent review rules, harness rules, parameter-verification metadata fields (`verified_against_dev`, `verified_row_count`, `original_inferred_values`, `verification_change_reason`, `unverifiable_reason`).

### `references/compare-spec-examples.md`
Worked JSON examples (function case, procedure with side effects + observer pattern, SYS_REFCURSOR materialization), observer-inference rules, cursor-materialization rules, `expected_delta` examples.

### `references/oracode-rules.md`
Oracode SQL/Liquibase conventions: file naming, one database object per file, trailing `/` on PL/SQL objects, no inline comments in Liquibase-owned SQL, Unix-style paths in XML, dependency ordering for changesets.

### `references/sqlplus-dev-execution.md`
SQLPlus mechanics: SEPS connect string format, `mkstore` rationale (chosen over a full Database Client for macOS ARM ergonomics), troubleshooting (TNS resolution, wallet override, env conflicts), Oracle docs sources.

### `references/script-map.md`
Quick-scan table indexing every script by its phase and purpose. Useful for finding the right script when you know what you want to do but not what it's called.

## Scripts (`scripts/`)

Grouped by where they fit in the workflow.

### Setup and lifecycle

#### `scripts/db-work-doctor.sh`
Single-shot machine-readiness check + plan-and-approve auto-fix. Modes: default (read-only checks, exit 0 green / 1 otherwise), `--plan` (read-only + concise plan), `--fix` (runs installs after approval), `--yes` (skip the approval prompt — use after `--plan` was shown). Eight checks: `DB_WORK_SKILL_DIR`, `sqlplus` on PATH, `mkstore` available, `DB_WORK_DEV_CONNECT` set, `tnsnames.ora` has the alias, live SQLPlus connect, required workflow plugins resolvable, subagent dispatch primitive (Codex `multi_agent = true` or Claude `Task`/`Agent` not denied).

#### `scripts/ensure_sqlplus.sh`
Installs Oracle Instant Client Basic + SQL*Plus on macOS via Oracle's official DMG. Optional `--wallet-tools` adds a tiny `mkstore` Java launcher. Idempotent. Used by the doctor's `--fix` flow.

#### `scripts/setup_oracle_wallet.sh`
Creates the SEPS wallet and writes `tnsnames.ora` / `sqlnet.ora`. Prompts the local terminal only — never asks for secrets in chat. Inputs: DEV username, DEV password, wallet password (all entered locally via `read -s`).

#### `scripts/start_session.sh`
Sets up the temporary session directory under `$DB_WORK_SESSION_BASE` (default `/tmp/db-work-$USER/session-<id>/`) with a `.db-work-session` marker file. Writes a `current` symlink to the latest session.

#### `scripts/cleanup_session.sh`
Removes the temporary session directory at end of session. Skips unmarked directories (safety: only removes paths with the `.db-work-session` marker). Cleans up the stale `current` symlink. Modes: `--session-dir DIR`, `--all`, `--session-base DIR`.

### Phase 5 — variant scaffolding and bench

#### `scripts/generate_shadow_objects.py`
Emits `_<INITIALS>` (or `_<INITIALS>_V<n>` for parallel variant work) shadow copies of the winner's PL/SQL objects under `util/<TICKET>/dev_sandbox/objects/`. Copies are renamed in source + grants are inserted so the shadow is callable from the configured DEV user.

#### `scripts/generate_dev_deploy.py`
Emits `deploy_shadow.sql` that compiles all shadow objects in dependency order (TYPE_SPEC → TYPE_BODY → SEQUENCE → TABLE → INDEX → SYNONYM → PACKAGE_SPEC → PACKAGE_BODY → VIEW → FUNCTION → PROCEDURE → TRIGGER → JOB). Uses SQLPlus `@@` includes resolved relative to the deploy script. Auto-emits `grant execute ... to ye_dev` for executable shadows.

#### `scripts/generate_changelog_entry.py`
Appends a Liquibase changeset to the team's `*_changelog.xml` for the winner's edits. Inputs: `--team`, `--ticket`, `--author`. Generates the XML with the right ordering and Oracode conventions; review before writing for non-trivial changes.

#### `scripts/perf-bench.sh`
Runs `perf.sql` per variant against DEV, sequential (concurrent benches break the warm-cache assumption), warm-cache by default (`--warmup 2 --runs 5`). Reads `bench_spec.json`, executes each variant's harness, records ONE TSV row per measured run to `util/<TICKET>/variants/bench_results.tsv`. Per-run logs go to `util/<TICKET>/variants/perf_logs/`. Warmup runs are NOT recorded.

#### `scripts/inspect_changes.sh`
Quick diff helper for browsing what's changed in the working tree. Filters down to the schema folders db-work cares about. Read-only.

### Phase 6 — DEV execution and evidence

#### `scripts/run_sqlplus_dev.sh`
Wallet-only SQLPlus wrapper. Refuses non-`/@ALIAS` connect strings (no inline username/password). Auto-installs SQLPlus via `ensure_sqlplus.sh` if missing. Used for every DEV invocation in the workflow (deploy, probe, harness runs, cleanup). Inputs: `--connect /@ALIAS`, `--script <path>`, optional `--spool <path>`.

#### `scripts/generate_metadata_probe.py`
Emits a read-only data-dictionary probe (`metadata_probe.sql`) that captures compiled DEV signatures: argument modes, overloads, return types, dependent objects. Used in Phase 6 entry to seed `compare_spec.json` with DB-truth signatures (preferred over source regex). Output written to `util/<TICKET>/dev_sandbox/logs/db_metadata.tsv`.

#### `scripts/generate_compare_spec.py`
Generates `compare_spec.json` from the shadow manifest + DB metadata. Decides which callables to test (defaults to public callables whose declaration or implementation lines changed in the diff), which arguments to use (inferred from parameter shape — ISO/market/window etc. when applicable), and which `evidence_mode` per run (`regression_compare`, `shadow_expected_result`, `expected_delta`, `performance_only`, `compile_contract_validation`). Inputs: `--manifest`, `--metadata-tsv`, optional `--callable` or `--all-callables`. The draft is then verified by the parameter-verification subagent BEFORE the user-approval surface is shown.

#### `scripts/generate_compare_harness.py`
Emits the functional comparison harness (`compare_harness.sql`) from an APPROVED `compare_spec.json`. Refuses to emit if placeholders remain (`TODO_REF_CURSOR_*`, unresolved observers, unresolved expected deltas). Per run: original-vs-shadow row count + result diff according to `evidence_mode`.

#### `scripts/generate_stats_harness.py`
Emits the perf/stats harness (`stats_harness.sql`) from the same approved `compare_spec.json`. Same placeholder refusal. Per run: KPI capture for original and shadow across `--runs N` measured invocations.

#### `scripts/summarize_sqlplus_logs.py`
Reduces raw spool logs into per-case summaries (means per KPI, row counts, errors). Output: `*.summary.log` files alongside the raw logs. The handoff report cites the summaries; raw spools become scratch and are removed at session end.

### Phase 7 — handoff

#### `scripts/db-work-report.sh`
Emits `util/<TICKET>/dev_sandbox/report.md` after the walkthrough is approved (separate turn — never the same turn as approval). Fields: branch, team changelog, variants benchmarked, performance acceptance criterion (verbatim), qualifying variants, agent's recommendation, human's pick, divergence reason if any, winner KPI deltas, files changed, files generated, performance evidence pointers, comparison evidence with `evidence_mode` per run, lint result, manual steps remaining.

### End-of-session

#### `scripts/dev_cleanup.sh`
Drops every shadow object listed in any `shadow_manifest.json` under `util/<TICKET>/`. Generates `cleanup.sql` with `DROP` statements in reverse-of-deploy order; runs against DEV via `run_sqlplus_dev.sh`. DDL — gated by the 5-line announce + "go". Modes: per-ticket, dry-run. Logs to `util/<TICKET>/dev_sandbox/logs/cleanup.log`.

## Tests (`tests/`)

### `tests/pressure-scenarios.md`
Subagent baseline + bulletproofing tests, organized by gate. Each scenario specifies a setup, pass criteria, fail signals, and rationalizations the agent might use to slip the gate. Run a fresh subagent against each scenario WITHOUT the skill (record baseline rationalizations), then again WITH the skill (verify compliance). New rationalizations discovered during testing get added to the iron-rule rationalization lists in the corresponding reference (not in SKILL.md, which stays terse).
