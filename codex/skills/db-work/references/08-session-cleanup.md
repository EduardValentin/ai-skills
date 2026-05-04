# Session Cleanup

When the user signals the end of a db-work session, the agent runs a two-step cleanup BEFORE claiming the session done.

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
3. **Local cleanup** — `scripts/cleanup_session.sh` (removes the marked temp session directory + temp `.db-work.yml`).
4. **Report.** Summarize: what was dropped on DEV, which session dir was removed, what durable artifacts (`util/<TICKET>/`) remain.

DEV cleanup runs FIRST. If the user aborts mid-DEV-cleanup, do not proceed to local cleanup — the local config may still be needed to redo the DEV cleanup later.

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

## Confirmation gate

DEV cleanup IS DEV execution and obeys all the iron rules:

- Pre-execution announce (5 lines: script, alias, expected, evidence_mode=cleanup, log path).
- Wait for explicit "go" / "yes" before running.
- Refuse non-DEV alias unless `DB_WORK_ALLOW_NON_DEV="<exact-alias>"` is set.
- Post-execution summary (drops succeeded, errors, log path).

"User said end the session" is end-of-session consent, NOT execution consent. Re-confirm before each ticket's `dev_cleanup.sh` invocation.

## After cleanup

The `util/<TICKET>/` directory is durable — keep it. It contains the plan, variants, bench results, evidence, and report. The DEV cleanup leaves these in place; only the database-side shadows are removed.

The handoff report in `util/<TICKET>/dev_sandbox/report.md` should already exist before session cleanup runs (Phase 7 ran first). If it doesn't, the agent has skipped Phase 7 — finish the walkthrough and emit the report before cleaning up.
