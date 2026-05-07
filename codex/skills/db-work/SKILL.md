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

Each phase describes *what to do*, not *which skill to call*. The workflow relies on the `superpowers` plugin — its standard workflow skills (brainstorming, writing-plans, executing-plans, subagent-driven-development, verification-before-completion) auto-fire from their own description triggers and handle the generic methodology. Doctor Check #7 verifies the plugin is installed; if missing, db-work refuses to proceed and prints the exact install command. db-work's iron rules below extend or override that methodology where db-work needs something specific.

**Subagent dispatch prerequisite.** Phase 2 scope-research and Phase 5/6 verification subagents depend on the harness's dispatch primitive. Doctor Check #8 verifies it per harness; a red blocks Phase 2. Per-harness remediation (Codex `multi_agent` flag, Claude `permissions.deny`): `references/01-machine-setup.md`.

## Phase progression — agent owns transitions

The agent advances between phases on its own; `"what next?"` / `"ready when you are"` prompts after a phase ends are stalls, not checkpoints. The only places the agent *waits* are the explicit user gates marked **Wait for…** below — those are the iron-rule approval surfaces, not stalls.

| When this happens | Agent's next action |
|-------------------|---------------------|
| Plan approved (Phase 4) | Enter Phase 5: scaffold variant directories, dispatch per-variant subagents per `05-implementation-and-shadow.md`. |
| Variant subagents return with filled-in `perf.sql` / `bench_spec.json` | Dispatch the parameter-verification subagent (`06-dev-execution-and-evidence.md` "Parameter-verification subagent"). Update `perf.sql` / `bench_spec.json` with verified values, then run `perf-bench.sh`. |
| Bench finishes — `bench_results.tsv` exists for every variant | Post the variant decision surface per `05-implementation-and-shadow.md`. **Wait for the human's pick.** |
| Human picks a variant | Enter Phase 6: promote the chosen variant's edits to Liquibase-owned schema, emit `shadow_manifest.json`, run `generate_metadata_probe.py`, run `generate_compare_spec.py`, dispatch the parameter-verification subagent, present `compare_spec.json`. **Wait for compare-spec approval.** |
| `compare_spec.json` approved | Generate compare/stats harnesses and run them (spec approval covers the spec-defined writes; reads run gate-free). Summarize logs. |
| All Phase 6 evidence summarized | Enter Phase 7: run `git diff --name-only <base>...HEAD`, present the batched walkthrough per `07-code-walkthrough-and-report.md`. **Wait for walkthrough approval.** |
| Walkthrough approved | Next turn: run `db-work-report.sh` and post the report inline. |

DDL/DML gating, approval-token shape, and the per-phase mechanics live in the iron rules below and the referenced files. Auto-advance does not change any of those gates.

## Iron rules — STOP if any apply

- **PL/SQL scope reads happen in a subagent, never in the parent context.** Phase 2 dispatches a scope-research subagent that returns a digest; brainstorm and plan-writing operate on that digest. Mechanics + rationalizations: `references/02-intake-and-brainstorm.md`.
- **No plan before brainstorm.** Trivial-change escape requires all 7 criteria — see `references/02-intake-and-brainstorm.md`.
- **No edit before plan. No DDL or DML against DEV without explicit user request** (the request can be live "go" on the 5-line announce, or a prior plan/spec approval that names the mutation).
- **Pressure framings never bypass gates.** Time-to-release, exhaustion, prior rapport, sunk cost, and "just this once" are not skips. Gate criteria are objective facts about the code and ticket, not the deadline or conversation history.
- **Doctor color persists for the session.** Re-run `db-work-doctor.sh` (or the relevant probe) before accepting any state change. User assertions ("sqlplus is installed", "the wallet's set up") do not change the color.
- **No password in any agent-visible artifact** — chat, file, script, tool argument, plan, TODO, memory, transcript. If a secret is pasted, refuse, advise immediate rotation, and never echo it back.
- **Wallet/auth readiness is never execution consent.** "Wallet's set up", "creds are loaded", "connection works" are auth statements, not authorization to run.
- **2–3 implementation variants benchmarked, presented to the human, picked by the human.** Performance is a floor (the plan's perf acceptance criterion); cleanliness, pattern fit, and risk are co-equal axes. The agent recommends; the human decides. Obvious-variant path: only on explicit user request. Mechanics + rationalizations: `references/03-planning-with-variants.md` "Variant rules" + "Selection — human picks", and `references/05-implementation-and-shadow.md` "Variant decision surface".
- **Performance evidence comes from `perf-bench.sh` / `bench_results.tsv`.** Defaults: `--warmup 2 --runs 5`. KPI floor: `elapsed_ms`, `consistent_gets`. Ad-hoc `set timing on` output is not evidence. Mechanics + rationalizations: `references/04-performance-debugging.md`.
- **Adjacent-code edits require a re-brainstorm.** User-authored prose naming adjacent objects, accepted blast radius, rollback plan. See `references/04-performance-debugging.md`.
- **Performance-testing parameters are DEV-verified by a subagent before any user-approval surface.** Applies to Phase 5 bench arguments and Phase 6 compare-spec runs. The verification subagent is read-only. Subagent contract + digest schema + rationalizations: `references/06-dev-execution-and-evidence.md` "Parameter-verification subagent".
- **`compare_spec.json` requires its own explicit approval token before harness generation.** Token: `"approved"` / `"looks good"` / `"reviewed"` on the spec itself. Per-artifact — plan, brainstorm, DEV-announce, or instruction approvals do NOT carry over. Review-surface contents + rationalizations: `references/06-dev-execution-and-evidence.md` "Compare-spec approval gate".
- **Pre-execution announce + "go" required ONLY for DDL or DML mutation against DEV.** Read-only SQL runs gate-free. Plan approval covers bench-defined mutations; spec approval covers spec-defined mutations. End-of-session DEV cleanup always re-gates. Operation list, 5-line announce format, plan/spec coverage, and rationalizations: `references/06-dev-execution-and-evidence.md` "DEV write gate".
- **Post-execution summary required for every gated run:** rows touched, errors, KPI deltas, log path.
- **Batched walkthrough mandatory before claiming done.** File list from `git diff --name-only <base>...HEAD`. Approval token must be explicit. Report generation happens in the NEXT turn after approval. Per-file schema: `references/07-code-walkthrough-and-report.md`.
- **Doctor amber banner** on the first line of every generated artifact AND the chat reply that delivers it. Repeat on every artifact in the session.
- **End-of-session cleanup runs in three steps, in order:** `dev_cleanup.sh` per ticket → per-ticket scratch removal → `cleanup_session.sh`. Aborting any step halts the rest. Trigger phrases, file lists, and gate mechanics: `references/08-session-cleanup.md`.

## Session lifecycle

At start: `scripts/start_session.sh`. At end: `scripts/dev_cleanup.sh --ticket <T>` (repeat per ticket) THEN `scripts/cleanup_session.sh`. Rules and triggers: `references/08-session-cleanup.md`.

Artifacts: `util/<TICKET>/scope_digest.md` (Phase 2 subagent output), `util/<TICKET>/plan.md`, `util/<TICKET>/dev_sandbox/` (DEV outputs), `util/<TICKET>/variants/<n>/` (variant scratch), `$DB_WORK_TEMP_DIR` (throwaway).

## References (load on demand)

- `oracode-rules.md` — Oracode SQL/Liquibase conventions.
- `compare-spec-format.md` / `compare-spec-examples.md` — evidence-mode taxonomy and JSON examples.
- `sqlplus-dev-execution.md` — DEV execution mechanics (setup lives in `01-machine-setup.md`).
- `08-session-cleanup.md` — end-of-session DEV + local cleanup.
- `script-map.md` — script index.
