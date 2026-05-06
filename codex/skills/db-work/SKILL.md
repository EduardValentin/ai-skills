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
| 2 | Intake + scope research | Read the ticket; dispatch a subagent to research PL/SQL scope and return a digest; confirm acceptance criteria | `references/02-intake-and-brainstorm.md` |
| 3 | Brainstorm | Explore intent, requirements, design space on the digest, before any plan | `references/02-intake-and-brainstorm.md` |
| 4 | Plan with 2–3 variants | Write a multi-step plan with explicit variants and a chosen winner criterion | `references/03-planning-with-variants.md` |
| 5 | Implement variants + benchmark | Execute the plan one variant at a time; verify with `scripts/perf-bench.sh` | `references/04-performance-debugging.md`, `references/05-implementation-and-shadow.md` |
| 6 | DEV execution & comparison evidence | Run `scripts/run_sqlplus_dev.sh`; capture rows/KPIs/log path | `references/06-dev-execution-and-evidence.md` |
| 7 | Batched walkthrough & handoff report | Pre-merge review of all changed files, then `scripts/db-work-report.sh` | `references/07-code-walkthrough-and-report.md` |

Each phase describes *what to do*, not *which skill to call*. The standard `superpowers` workflow skills auto-fire on their own description-level triggers (brainstorm before creative work, plan before multi-step edits, verify before claiming done). Doctor Check #7 verifies they are installed; if missing, db-work refuses to proceed and prints the exact install command.

**What auto-fires vs what does NOT.** Auto-firing applies to the skills themselves — when a description trigger matches, the skill content loads. It does NOT mean those skills auto-spawn subagents. `superpowers:brainstorming` and `superpowers:writing-plans` both have the **parent agent** read source code, callers, and dependents directly during their research/exploration steps; neither dispatches a subagent for that work. `superpowers:subagent-driven-development` does dispatch subagents, but only per-task during plan *execution*, after the plan is written. There is no upstream auto-trigger that isolates research-time reads from the parent context. That gap is exactly why db-work mandates an explicit scope-research subagent in Phase 2 — see `references/02-intake-and-brainstorm.md` and the iron rule below. If a session blew past the context limit during plan-writing, the cause is parent-side source reads, not a missed auto-trigger.

**Subagent dispatch prerequisite (harness-specific).** Phase 2 scope-research and Phase 5 per-variant subagents both depend on the harness's dispatch primitive. Doctor Check #8 verifies it per harness:

- **Codex:** `multi_agent = true` under `[features]` in `~/.codex/config.toml` (or wherever `CODEX_CONFIG` points). Unset → `spawn_agent` is unavailable → parent silently falls back to reading source itself.
- **Claude Code:** `Task` / `Agent` is available natively; the check fails only if `~/.claude/settings.json` or `settings.local.json` lists `Task` or `Agent(*)` in `permissions.deny`.
- **Unknown harness:** the check warns rather than fails — Phase 2 may silently fall back to parent-side reads, and the operator is responsible for verifying the dispatch primitive themselves.

A red on Check #8 blocks Phase 2. The check is read-only — operators must edit harness config or settings manually, since `--fix` does not modify them.

## Iron rules — STOP if any apply

- **PL/SQL scope reads happen in a subagent, never in the parent context.** The parent agent does NOT read full PL/SQL packages, callers, or dependents directly. Phase 2 dispatches a scope-research subagent that returns a digest with verbatim signatures and file:line citations. Brainstorm and plan-writing operate on that digest. If a later phase needs more detail, the parent re-reads ONLY specific cited line ranges, or re-dispatches the subagent — never whole files. This is the gate against the 250K-context blowup observed during plan-writing. Pressure framings ("just look at the file", "it's only one package", "the subagent is overkill for this one") do not waive the rule. If `superpowers:writing-plans` auto-fires before scope research has run, pause it, run the subagent, then resume. See `references/02-intake-and-brainstorm.md` for the prompt template and digest schema.
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
- **End-of-session cleanup runs in three steps, in order.** When the user signals the end of the session ("let's end the session", "let's conclude the session", "we are finished", "done with db-work", or paraphrase): (1) `scripts/dev_cleanup.sh --ticket <T>` for every ticket the session touched, (2) per-ticket scratch removal (delete `scope_digest.md`, warmup logs, raw spools, `*.draft.*`, `*.tmp` under each `util/<TICKET>/` — full list and dry-run gate in `references/08-session-cleanup.md`), (3) `scripts/cleanup_session.sh` for the temp session dir. DEV cleanup obeys all execution gates (5-line announce, alias check, explicit go). Scratch removal requires a dry-run preview + explicit "go" — never wipe scratch before Phase 7's report is committed, since the report cites the digest. "Ending the session" is end-of-session consent, NOT execution or deletion consent — re-confirm per step. Order matters: if the user aborts step (1), do NOT proceed to (2) or (3); if they abort step (2), do NOT proceed to (3).

## Session lifecycle

At start: `scripts/start_session.sh`. At end: `scripts/dev_cleanup.sh --ticket <T>` (repeat per ticket) THEN `scripts/cleanup_session.sh`. Rules and triggers: `references/08-session-cleanup.md`.

Artifacts: `util/<TICKET>/scope_digest.md` (Phase 2 subagent output), `util/<TICKET>/plan.md`, `util/<TICKET>/dev_sandbox/` (DEV outputs), `util/<TICKET>/variants/<n>/` (variant scratch), `$DB_WORK_TEMP_DIR` (throwaway).

## References (load on demand)

- `oracode-rules.md` — Oracode SQL/Liquibase conventions.
- `compare-spec-format.md` / `compare-spec-examples.md` — evidence-mode taxonomy and JSON examples.
- `sqlplus-dev-execution.md` — DEV execution mechanics (setup lives in `01-machine-setup.md`).
- `08-session-cleanup.md` — end-of-session DEV + local cleanup.
- `script-map.md` — script index.
