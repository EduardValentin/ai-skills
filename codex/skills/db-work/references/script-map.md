# Script Map

All scripts live under `${CODEX_HOME:-$HOME/.codex}/skills/db-work/scripts/`. Run from the Oracode repo root using the absolute skill path.

## Lifecycle
- `start_session.sh` — create a marked temp session dir + temp `.db-work.yml` + scratch dir.
- `dev_cleanup.sh` — drop DEV shadow objects compiled during the session (per ticket). Run BEFORE `cleanup_session.sh` at end of session. See `references/08-session-cleanup.md`.
- `cleanup_session.sh` — remove marked temp session dirs at session end.

## Readiness
- `db-work-doctor.sh` — single-shot machine readiness check (`--fix`, `--setup-wallet`).
- `ensure_sqlplus.sh` — auto-install Oracle Instant Client Basic + SQL*Plus on macOS; `--wallet-tools` adds `mkstore` via the Java launcher.
- `setup_oracle_wallet.sh` — create/update `tnsnames.ora`, `sqlnet.ora`, SEPS wallet, `/@DEV_ALIAS` credential.

## Repo inspection
- `inspect_changes.sh` — print branch, inferred ticket, changed SQL files, changelog files, generated sandbox files.

## Implementation
- `generate_changelog_entry.py` — append ordered Liquibase changesets to the resolved team changelog.
- `generate_shadow_objects.py` — create DEV-only suffixed object copies + `shadow_manifest.json`.
- `generate_dev_deploy.py` — ordered SQLPlus deploy script from the manifest, with execute grants.
- `generate_metadata_probe.py` — SQLPlus metadata probe SQL for compiled originals/shadows.

## Performance
- `perf-bench.sh` — run each variant × N runs against DEV, emit `bench_results.tsv`.
- `summarize_sqlplus_logs.py` — summarize SQLPlus logs (errors, KPIs, mean across runs).
- `assets/sql/perf_harness_template.sql` — template for `util/<TICKET>/variants/<n>/perf.sql` (variants A–D for table function / scalar / procedure / refcursor).
- `assets/sql/bench_spec_template.json` — template for `util/<TICKET>/variants/bench_spec.json`.
- `assets/sql/perf_harness_grants.sql` — one-time `v$mystat` / `v$statname` / `v$sql` grants for the DEV user.

## Comparison evidence
- `generate_compare_spec.py` — infer signatures + write reviewable `compare_spec.json` with proposed runs.
- `generate_compare_harness.py` — original-vs-shadow row-count and diff SQL from reviewed runs.
- `generate_stats_harness.py` — autotrace/timing SQL from reviewed runs.

## DEV execution
- `run_sqlplus_dev.sh` — execute a SQL script against DEV via the safe alias path.

## Handoff
- `db-work-report.sh` — emit the fixed-shape handoff markdown.
