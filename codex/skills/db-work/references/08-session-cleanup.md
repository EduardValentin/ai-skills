# Session Cleanup

When the user signals the end of a db-work session, the agent runs a three-step cleanup BEFORE claiming the session done — see `SKILL.md`'s end-of-session iron rule for the canonical order; this file owns the mechanics.

## Trigger phrases

The agent recognises these (and obvious paraphrases) as end-of-session signals:

- "let's end the session"
- "let's conclude the session"
- "we are finished"
- "we're done"
- "done with db-work"
- "wrap up the session"

If unclear, ask: "End the db-work session and run DEV cleanup?"

## Order of operations

1. **Enumerate.** List every ticket the session touched (every `util/<TICKET>/` directory containing a `dev_sandbox/` or `variants/`). Show the user.
2. **DEV cleanup per ticket** — `scripts/dev_cleanup.sh` (described below).
3. **Per-ticket scratch removal** — delete agent-scratch files under each `util/<TICKET>/` (described in "Per-ticket scratch removal" below).
4. **Local cleanup** — `scripts/cleanup_session.sh` (removes the marked temp session directory + temp `.db-work.yml`).
5. **Report.** Summarize: what was dropped on DEV, which scratch files were removed, which session dir was removed, what durable artifacts (`util/<TICKET>/`) remain.

DEV cleanup runs FIRST. If the user aborts mid-DEV-cleanup, do not proceed to scratch or local cleanup — the local config may still be needed to redo the DEV cleanup later.

## DEV cleanup

```bash
DB_WORK_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/db-work"
"$DB_WORK_SKILL_DIR/scripts/dev_cleanup.sh" --ticket VA-515
# or, dry-run first to see the plan:
"$DB_WORK_SKILL_DIR/scripts/dev_cleanup.sh" --ticket VA-515 --dry-run
```

The script:

1. Aggregates every `shadow_manifest.json` under `util/<TICKET>/` (winner sandbox + per-variant shadows if subagent-driven-development was used).
2. Generates `util/<TICKET>/dev_sandbox/cleanup.sql` with `DROP` statements in reverse-of-deploy order:
   ```
   JOB → TRIGGER → PROCEDURE → FUNCTION → VIEW → PACKAGE → SYNONYM →
   INDEX → TABLE → SEQUENCE → TYPE
   ```
   `PACKAGE BODY` and `TYPE BODY` are skipped — they drop with their parents.
3. Posts the standard 5-line pre-execution announce + the user-facing list of drops.
4. Waits for explicit "go" / "yes" before running.
5. Runs against DEV via `run_sqlplus_dev.sh`.
6. Logs to `util/<TICKET>/dev_sandbox/logs/cleanup.log`.

The cleanup SQL uses `whenever sqlerror continue` so a missing object (e.g. a shadow that failed to compile in the first place) does not abort the run.

## What gets dropped

- Every shadow object listed in any `shadow_manifest.json` under `util/<TICKET>/`. Schema is read from the first segment of the source path (e.g. `PROD/`, `YES_SERVICES/`).

## What is NOT dropped automatically

The agent must surface these before cleanup so the user can decide:

- Helper tables shared across sessions (e.g. `DB_WORK_REFCURSOR_ROWS`). Default: leave intact. If the user wants them gone, write a one-shot cleanup SQL and run it through the same announce-and-confirm flow.
- DML committed by procedure-side-effect harnesses that did not roll back. The procedure observer pattern (see `compare-spec-examples.md`) requires `cleanup_sql: "rollback;"` exactly to avoid this. If a harness committed by mistake, surface the affected tables to the user — do not run blanket `DELETE` statements.
- Anything outside `util/<TICKET>/`. The cleanup is scoped per-ticket; objects compiled directly outside the manifest path are invisible to it.

## Per-ticket scratch removal

Some files written under `util/<TICKET>/` are agent-internal scratch — useful during the work, redundant once the report is committed. These are removed at session end so the durable handoff stays lean.

### Files removed (per ticket)

- `util/<TICKET>/scope_digest.md` — Phase 2 subagent output. Content is reflected in `plan.md` and `dev_sandbox/report.md`, so the digest itself is no longer needed once Phase 7 is done.
- `util/<TICKET>/variants/perf_logs/*.warmup.log` — warmup-run logs (excluded from `bench_results.tsv` by design).
- `util/<TICKET>/dev_sandbox/logs/*.raw.log` — raw spool files that have already been summarized via `summarize_sqlplus_logs.py` into `*.summary.log`.
- Any `*.draft.json`, `*.draft.sql`, or `*.tmp` under `util/<TICKET>/` — intermediate generation artifacts (e.g. unreviewed `compare_spec.draft.json`).

### Files kept (durable handoff — never removed by scratch cleanup)

- `util/<TICKET>/plan.md`
- `util/<TICKET>/variants/<n>/notes.md`, `perf.sql`, `changes/`, `shadow/`
- `util/<TICKET>/variants/bench_spec.json`, `bench_results.tsv`
- `util/<TICKET>/dev_sandbox/shadow_manifest.json` (still required by re-run of `dev_cleanup.sh` later if needed)
- `util/<TICKET>/dev_sandbox/compare_spec.json` (the reviewed-and-approved version)
- `util/<TICKET>/dev_sandbox/compare_harness.sql`, `stats_harness.sql`, `metadata_probe.sql`, `deploy_shadow.sql`
- `util/<TICKET>/dev_sandbox/logs/*.summary.log`, `lint.log`, `cleanup.log`
- `util/<TICKET>/dev_sandbox/report.md`

### Confirmation gate

Scratch removal is local file deletion. The agent must:

1. Run the deletion in `--dry-run` mode first (or the equivalent `find ... -print` shell preview) and post the verbatim file list to the user.
2. Wait for explicit "go" / "yes" before deleting. Silence, "k", or emoji-only ack does not count.
3. Refuse if Phase 7 hasn't run yet — `report.md` must exist before scratch is wiped, since the report cites the digest.
4. Refuse if any file in "Files kept" is missing for the ticket — that indicates incomplete work, not scratch.
5. After deletion, post a one-line summary: `"removed N scratch files from util/<TICKET>/"`.

User assertions ("just delete it", "skip the dry run") do NOT waive the dry-run preview. The preview is the user's last chance to spot a misclassification.

### Pressure resistance

"Just nuke util/<TICKET>/ entirely" is not the same request and must be refused. The durable handoff under `util/<TICKET>/` is the work product; the agent does not delete deliverables on a verbal cue. If the user genuinely wants the whole tree gone (e.g. the work was abandoned), they can `rm -rf` it themselves — db-work does not own that flow.

## Confirmation gate

DEV cleanup IS DEV execution and obeys all the iron rules:

- Pre-execution announce (5 lines: script, alias, expected, evidence_mode=cleanup, log path).
- Wait for explicit "go" / "yes" before running.
- Post-execution summary (drops succeeded, errors, log path).

"User said end the session" is end-of-session consent, NOT execution consent. Re-confirm before each ticket's `dev_cleanup.sh` invocation.

## After cleanup

The `util/<TICKET>/` directory is durable minus the scratch files listed in "Per-ticket scratch removal" — keep what remains. It contains the plan, variants, bench results, evidence, and report. The DEV cleanup removes only database-side shadows; scratch removal removes only redundant intermediates; the durable handoff stays in place.

The handoff report in `util/<TICKET>/dev_sandbox/report.md` MUST exist before scratch removal runs (Phase 7 ran first). The report cites the scope digest and intermediate logs — wiping them before the report is committed orphans the citations. If Phase 7 hasn't run, finish the walkthrough and emit the report before cleaning up.
