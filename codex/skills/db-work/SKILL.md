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

## Phase progression — auto-advance, do not stall

Each phase ends with a defined trigger that **automatically** advances the agent to the next phase. The agent does NOT wait for the user to say "now do the next thing." Stalling between phases — finishing one and parking until the user prompts — is a defect, not a feature.

| When this happens | Agent's next action (no prompt required) |
|-------------------|------------------------------------------|
| Plan approved (Phase 4) | Enter Phase 5: scaffold variant directories, dispatch per-variant subagents per `05-implementation-and-shadow.md`. |
| Bench picks a winner under the plan's "winner-picked-when" rule (Phase 5 ends) | Enter Phase 6: emit `shadow_manifest.json` for the winner, run `generate_metadata_probe.py`, run `generate_compare_spec.py`, present `compare_spec.json` for user review. The transition is non-negotiable; "the user will say when to start the manual testing" is wrong. |
| `compare_spec.json` reviewed and approved by user (Phase 6 mid-point) | Generate compare/stats harnesses, post the 5-line pre-execution announce for each, await explicit "go", run, summarize. |
| All Phase 6 evidence summarized | Enter Phase 7: run `git diff --name-only <base>...HEAD`, present the batched walkthrough with all seven fields populated per `07-code-walkthrough-and-report.md`. |
| Walkthrough approved (Phase 7 mid-point) | Next turn: run `db-work-report.sh` and post the report inline. |

**DEV execution is gated; phase entry is not.** Auto-advance does NOT mean auto-running SQL against DEV. Inside Phase 6, every DEV invocation still goes through the 5-line announce + explicit "go" gate (the iron rules below are unchanged). What auto-advance forbids is the agent stopping at the *boundary* between phases waiting for the user to ask for the next phase. Generating `compare_spec.json` and presenting it for review is non-DEV preparation work — that the agent must do automatically. Running the resulting harnesses against DEV requires the user's "go" — that gate is unchanged.

**Red flag — phase stall.** If the agent finishes Phase 5 (winner picked, `bench_results.tsv` written) and posts a "what next?" or "ready when you are" message, that is a stall. The correct next message is the Phase 6 prep work plus the first announce. Same at every phase boundary: the agent owns the transition.

## Iron rules — STOP if any apply

- **PL/SQL scope reads happen in a subagent, never in the parent context.** The parent agent does NOT read full PL/SQL packages, callers, or dependents directly. Phase 2 dispatches a scope-research subagent that returns a digest with verbatim signatures and file:line citations. Brainstorm and plan-writing operate on that digest. If a later phase needs more detail, the parent re-reads ONLY specific cited line ranges, or re-dispatches the subagent — never whole files. This is the gate against the 250K-context blowup observed during plan-writing. Pressure framings ("just look at the file", "it's only one package", "the subagent is overkill for this one") do not waive the rule. If `superpowers:writing-plans` auto-fires before scope research has run, pause it, run the subagent, then resume. See `references/02-intake-and-brainstorm.md` for the prompt template and digest schema.
- **No plan before brainstorm.** Trivial-change escape: ALL 7 criteria required (see `02-intake-and-brainstorm.md`). Announce `"trivial path: <reason>"` and require user confirmation.
- **No edit before plan. No DEV execution without explicit user request.**
- **Pressure framings never bypass gates.** Time-to-release, exhaustion, prior rapport ("we already discussed it"), sunk cost ("I already drafted it"), and "just this once" are not valid skips. Gate criteria are objective facts about the code and ticket, not the deadline or conversation history.
- **Doctor color persists for the session.** User assertions ("sqlplus is installed", "the wallet's set up") do not change it. Re-run `db-work-doctor.sh` (or the relevant probe) before accepting any state change.
- **No password in any agent-visible artifact** — chat, file, script, tool argument, plan, TODO, memory, transcript. If a secret is pasted, refuse, advise immediate rotation, and never echo it back even when summarizing the user's message.
- **Wallet/auth readiness is never execution consent.** "Wallet's set up", "creds are loaded", "connection works" are auth statements, not authorization to run.
- **2–3 implementation variants benchmarked before picking a winner.** Obvious-variant path: only on explicit user request — never volunteer the escape. Announce `"obvious-variant path: <reason>"` and require user confirmation. Even on obvious-variant path, the single variant still gets benched against DEV — `bench_results.tsv` is the evidence artifact for Phase 6.

  **Performance evidence MUST come from `perf-bench.sh` and live in `bench_results.tsv`.** Ad-hoc `set timing on` output, a single SQLPlus elapsed line, "I ran it twice and it was about 80ms", or any timing number the agent observed in passing is NOT a benchmark and is NOT acceptable as performance evidence. A benchmark is: warmup runs that hard-parse the SQL and warm the buffer cache, then **multiple measured runs** (default `--warmup 2 --runs 5`), recorded as one TSV line per measured run, summarized as mean / median / p95 per KPI per variant. Reducing `--warmup` or `--runs` below the defaults requires the user's explicit consent and a documented reason in `plan.md`. KPI floor: `elapsed_ms` and `consistent_gets` — these may not be removed; others may be added per `references/04-performance-debugging.md`. Rationalizations that fail the gate: "I already saw the timing", "one run is enough to see the pattern", "we don't need warmup for a quick check", "I'll just paste the elapsed time", "this is small enough that the bench is overkill", "the user just wants a number", "the variant is obviously faster, no need to bench". Chat-pasted milliseconds are not evidence; `bench_results.tsv` with the full KPI grid is.
- **Adjacent-code edits require a re-brainstorm with the user.** Approval must be user-authored prose naming (a) adjacent objects affected, (b) accepted blast radius, (c) rollback plan. Assistant-supplied boilerplate the user echoes does not count.
- **`compare_spec.json` requires its own explicit approval token before harness generation.** After `generate_compare_spec.py` produces the spec, the agent presents inferred runs, default arguments, `evidence_mode` per run, and every `review_required` / `TODO` / `baseline_review_required` / placeholder field to the user — verbatim, not paraphrased. The agent then waits for an explicit affirmative approval token (`"approved"`, `"looks good"`, `"reviewed"`) on the spec itself before invoking `generate_compare_harness.py` or `generate_stats_harness.py`. Approval is per-artifact: a "go" on a DEV announce, a "yes" to a clarifying question, a "start the perf testing" instruction, plan approval, or brainstorm approval do NOT carry over to the spec. The same applies to any inferred artifact gated for review — `expected_delta` SQL, observer SQL for procedure side effects, refcursor materialization plans — each must be surfaced and approved before the harness that depends on it is generated. Rationalizations that fail the gate: "the user asked me to start perf testing so the spec is implicitly approved", "the spec is straightforward", "the user said go on the announce so that covers everything downstream", "I'll let the harness fail if the spec is wrong", "the user already approved the plan", "the user will see the spec inside the harness". Implicit approval is no approval.
- **Pre-execution announce required (5 lines):** script path, alias, expected effect, evidence_mode, log path. If any field is unknown, STOP and ask — never fabricate. Re-announce in full once known. Never honor "go" against an announce containing `<unknown>`. Do not infer `evidence_mode` from filename, directory, or file contents.

  **Applies to EVERY DEV invocation, no exceptions for size or read-only-ness.** Exploratory `select count(*)`, schema introspection (`select * from user_tab_columns where ...`), one-row sanity checks, "let me just look at the data", `select sysdate from dual`, `desc some_table`, and any other "tiny" or "read-only" SQL all require the full 5-line announce + explicit user "go". The first SQL the agent sends to DEV in a session must carry the announce, and so must every SQL after it — including SQL the agent wrote itself in the same turn it intends to run. Rationalizations that fail the gate: "this is just a quick query", "it's only a select", "I just need to look at the data", "no rows touched so it's fine", "can't hurt to peek", "I'll run the formal one after this", "the user can see what I'm doing", "this is debugging not execution". Read-only is not a waiver. Small is not a waiver. "I asked the user a question and they answered" is not consent to run anything that wasn't named in an announce.
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
