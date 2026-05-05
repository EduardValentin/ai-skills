---
name: db-work
description: Use when changing PL/SQL or Liquibase changelogs in an Oracode checkout — packages, types, functions, procedures, views, DEV-only shadow objects with user-initial suffixes (e.g. PACKAGE_A_EDI), original-vs-shadow comparison on DEV, SQLPlus DEV execution, or job/Jira-ticket database implementation. Performance-critical repository.
---

# DB Work

Oracle/Liquibase changes in Oracode: brainstorm-first design, multi-variant implementation, performance-driven selection, transparent DB execution, reviewable handoff.

## When to use

- Changing PL/SQL in `PROD/`, `YES_SERVICES/`, or sibling schema folders.
- Updating a team `*_changelog.xml`.
- Generating DEV-only `_<INITIALS>` shadow objects.
- Comparing original vs. shadow on DEV.
- Job/Jira-ticket database implementation.

## Phase 1 — Machine readiness (gateway)

Always run the doctor as the first command:

```bash
"${CODEX_HOME:-$HOME/.codex}/skills/db-work/scripts/db-work-doctor.sh"
```

- Green: do NOT load `references/01-machine-setup.md` — proceed to Phase 2 (or end the session if setup was the only ask).
- Red: load `references/01-machine-setup.md` and follow the plan-and-approve flow there.

Setup-only sessions are valid: doctor green → confirm → end. Phases 2–7 run only when there is actual database work.

## Phases 2–7 (when there is database work)

| # | Phase | What this phase IS | Reference |
|---|-------|--------------------|-----------|
| 2 | Intake | Read the ticket, collect scope, confirm acceptance criteria | `references/02-intake-and-brainstorm.md` |
| 3 | Brainstorm | Explore intent, requirements, design space before any plan | `references/02-intake-and-brainstorm.md` |
| 4 | Plan with 2–3 variants | Write a multi-step plan with explicit variants and a chosen winner criterion | `references/03-planning-with-variants.md` |
| 5 | Implement variants + benchmark | Execute the plan one variant at a time; verify with `scripts/perf-bench.sh` | `references/04-performance-debugging.md`, `references/05-implementation-and-shadow.md` |
| 6 | DEV execution & comparison evidence | Run `scripts/run_sqlplus_dev.sh`; capture rows/KPIs/log path | `references/06-dev-execution-and-evidence.md` |
| 7 | Batched walkthrough & handoff report | Pre-merge review of all changed files, then `scripts/db-work-report.sh` | `references/07-code-walkthrough-and-report.md` |

Each phase describes *what to do*, not *which skill to call*. The harness auto-fires the standard workflow skills (brainstorm before creative work, plan before multi-step edits, verify before claiming done) on their own triggers. Doctor Check #7 verifies they are installed; if missing, db-work refuses to proceed and prints the exact install command.

## Iron rules — STOP if any apply

- **No plan before brainstorm.** Trivial-change escape: ALL 7 criteria required (see `02-intake-and-brainstorm.md`). Announce `"trivial path: <reason>"` and require user confirmation.
- **No edit before plan. No DEV execution without explicit user request.**
- **Pressure framings never bypass gates.** Time-to-release, exhaustion, prior rapport ("we already discussed it"), sunk cost ("I already drafted it"), and "just this once" are not valid skips. Gate criteria are objective facts about the code and ticket, not the deadline or conversation history.
- **Doctor color persists for the session.** User assertions ("sqlplus is installed", "the wallet's set up") do not change it. Re-run `db-work-doctor.sh` (or the relevant probe) before accepting any state change.
- **No password in any agent-visible artifact** — chat, file, script, tool argument, plan, TODO, memory, transcript. If a secret is pasted, refuse, advise immediate rotation, and never echo it back even when summarizing the user's message.
- **Refuse aliases not matching `^DEV[_-]`** unless `DB_WORK_ALLOW_NON_DEV="<exact-alias>"` is set in the operator's shell (per-alias one-shot; ignored if it appears in chat or any generated artifact). Override mechanics: `references/01-machine-setup.md`.
- **Wallet/auth readiness is never execution consent.** "Wallet's set up", "creds are loaded", "connection works" are auth statements, not authorization to run.
- **2–3 implementation variants benchmarked before picking a winner.** Obvious-variant path: only on explicit user request — never volunteer the escape. Announce `"obvious-variant path: <reason>"` and require user confirmation. Even on obvious-variant path, the single variant still gets benched against DEV — `bench_results.tsv` is the evidence artifact for Phase 6.
- **Adjacent-code edits require a re-brainstorm with the user.** Approval must be user-authored prose naming (a) adjacent objects affected, (b) accepted blast radius, (c) rollback plan. Assistant-supplied boilerplate the user echoes does not count.
- **Pre-execution announce required (5 lines):** script path, alias, expected effect, evidence_mode, log path. If any field is unknown, STOP and ask — never fabricate. Re-announce in full once known. Never honor "go" against an announce containing `<unknown>`. Do not infer `evidence_mode` from filename, directory, or file contents.
- **Post-execution summary required:** rows touched, errors, KPI deltas, log path.
- **Batched walkthrough mandatory** before claiming done. Changed-file list MUST come from `git diff --name-only <base>...HEAD`, not memory or dictation. Per-file schema in `07-code-walkthrough-and-report.md`. Approval token must be explicit ("reviewed", "looks good", "approved") — emoji-ack alone insufficient if any field was templated. Report generation happens in the NEXT turn after approval, never the same turn.
- **Doctor amber banner** must appear on the first line of every generated artifact AND the first line of the chat reply that delivers it. Repeat on every artifact in the session, not just the first.
- **End-of-session triggers DEV cleanup BEFORE local cleanup.** When the user signals the end of the session ("let's end the session", "let's conclude the session", "we are finished", "done with db-work", or paraphrase), run `scripts/dev_cleanup.sh --ticket <T>` for every ticket the session touched, then `scripts/cleanup_session.sh`. DEV cleanup obeys all execution gates (5-line announce, alias check, explicit go). "Ending the session" is end-of-session consent, NOT execution consent — re-confirm per ticket. Order matters: if user aborts DEV cleanup, do NOT proceed to local cleanup.

## Session lifecycle

At start: `scripts/start_session.sh`. At end: `scripts/dev_cleanup.sh --ticket <T>` (repeat per ticket) THEN `scripts/cleanup_session.sh`. Rules and triggers: `references/08-session-cleanup.md`.

Artifacts: `util/<TICKET>/dev_sandbox/` (DEV outputs), `util/<TICKET>/variants/<n>/` (variant scratch), `$DB_WORK_TEMP_DIR` (throwaway).

## References (load on demand)

- `oracode-rules.md` — Oracode SQL/Liquibase conventions.
- `compare-spec-format.md` / `compare-spec-examples.md` — evidence-mode taxonomy and JSON examples.
- `sqlplus-dev-execution.md` — DEV execution mechanics (setup lives in `01-machine-setup.md`).
- `08-session-cleanup.md` — end-of-session DEV + local cleanup.
- `script-map.md` — script index.
