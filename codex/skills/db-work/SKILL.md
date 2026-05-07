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
| Variant subagents return with filled-in `perf.sql` / `bench_spec.json` (Phase 5 mid-point) | Dispatch the parameter-verification subagent (see `references/06-dev-execution-and-evidence.md` "Parameter-verification subagent") to probe DEV with each variant's bench arguments and confirm > 0 rows. Update `perf.sql` / `bench_spec.json` with verified values + `verified_against_dev: true` annotations. Only then run `perf-bench.sh`. |
| Bench finishes — `bench_results.tsv` exists for every variant (Phase 5 mid-point) | Post the variant decision surface per `references/05-implementation-and-shadow.md`: per-variant bench KPIs, cleanliness assessment, agent recommendation with trade-off reasoning. Wait for the human's explicit pick. Do NOT advance to Phase 6 yet. |
| Human picks a variant (Phase 5 ends) | Enter Phase 6: promote the chosen variant's edits to the Liquibase-owned schema folders, emit `shadow_manifest.json` for the winner, run `generate_metadata_probe.py`, run `generate_compare_spec.py`, **dispatch the parameter-verification subagent** to probe DEV with each run's inferred arguments and update the spec with verified values, then present `compare_spec.json` for user review. The transition is non-negotiable; "the user will say when to start the manual testing" is wrong. |
| `compare_spec.json` reviewed and approved by user (Phase 6 mid-point) | Generate compare/stats harnesses, post the 5-line pre-execution announce for each, await explicit "go", run, summarize. |
| All Phase 6 evidence summarized | Enter Phase 7: run `git diff --name-only <base>...HEAD`, present the batched walkthrough with all seven fields populated per `07-code-walkthrough-and-report.md`. |
| Walkthrough approved (Phase 7 mid-point) | Next turn: run `db-work-report.sh` and post the report inline. |

**Auto-advance covers phase entry; the gate model below covers DEV writes.** Auto-advance forbids the agent stopping at a *phase boundary* waiting for the user to ask for the next phase. It does NOT change the DEV write rules: DDL and DML mutation still require a 5-line announce + explicit "go" unless covered by an explicit prior approval (plan approval covers the bench-defined mutations; spec approval covers the spec-defined mutations). Read-only SQL — including the metadata probe at Phase 6 entry, the spec-defined compare/stats harness invocations after spec approval, and ad-hoc diagnostic SELECTs — runs without a per-action gate. The user-facing approval surfaces (plan approval, variant pick, compare-spec approval, walkthrough approval) are unaffected by auto-advance and unaffected by the DDL/DML gate; they're their own gates.

**Red flag — phase stall.** If the agent's bench finishes (`bench_results.tsv` written) and the agent posts a "what next?" or "ready when you are" message instead of the variant decision surface, that is a stall. If the human picks a variant and the agent posts a hand-off prompt instead of beginning Phase 6 prep, that is a stall. Same at every phase boundary: the agent owns the transition. The Phase 5 mid-point (post-bench) is the one place where the agent *must* wait — for the human's explicit pick — but waiting is not the same as stalling. Stalling = silence after writing the TSV. Waiting = the decision surface is posted and the agent is on hold for the pick.

## Iron rules — STOP if any apply

- **PL/SQL scope reads happen in a subagent, never in the parent context.** The parent agent does NOT read full PL/SQL packages, callers, or dependents directly. Phase 2 dispatches a scope-research subagent that returns a digest with verbatim signatures and file:line citations. Brainstorm and plan-writing operate on that digest. If a later phase needs more detail, the parent re-reads ONLY specific cited line ranges, or re-dispatches the subagent — never whole files. This is the gate against the 250K-context blowup observed during plan-writing. Pressure framings ("just look at the file", "it's only one package", "the subagent is overkill for this one") do not waive the rule. Scope research must complete before plan-writing begins — if plan-writing engaged first, pause it and run the subagent. See `references/02-intake-and-brainstorm.md` for the prompt template and digest schema.
- **No plan before brainstorm.** Trivial-change escape: ALL 7 criteria required (see `02-intake-and-brainstorm.md`). Announce `"trivial path: <reason>"` and require user confirmation.
- **No edit before plan. No DEV execution without explicit user request.**
- **Pressure framings never bypass gates.** Time-to-release, exhaustion, prior rapport ("we already discussed it"), sunk cost ("I already drafted it"), and "just this once" are not valid skips. Gate criteria are objective facts about the code and ticket, not the deadline or conversation history.
- **Doctor color persists for the session.** User assertions ("sqlplus is installed", "the wallet's set up") do not change it. Re-run `db-work-doctor.sh` (or the relevant probe) before accepting any state change.
- **No password in any agent-visible artifact** — chat, file, script, tool argument, plan, TODO, memory, transcript. If a secret is pasted, refuse, advise immediate rotation, and never echo it back even when summarizing the user's message.
- **Wallet/auth readiness is never execution consent.** "Wallet's set up", "creds are loaded", "connection works" are auth statements, not authorization to run.
- **2–3 implementation variants benchmarked, presented to the human, and chosen by the human.** Obvious-variant path: only on explicit user request — never volunteer the escape. Announce `"obvious-variant path: <reason>"` and require user confirmation. Even on obvious-variant path, the single variant still gets benched against DEV — `bench_results.tsv` is the evidence artifact for Phase 6.

  **Performance evidence MUST come from `perf-bench.sh` and live in `bench_results.tsv`.** Ad-hoc `set timing on` output, a single SQLPlus elapsed line, "I ran it twice and it was about 80ms", or any timing number the agent observed in passing is NOT a benchmark and is NOT acceptable as performance evidence. A benchmark is: warmup runs that hard-parse the SQL and warm the buffer cache, then **multiple measured runs** (default `--warmup 2 --runs 5`), recorded as one TSV line per measured run, summarized as mean / median / p95 per KPI per variant. Reducing `--warmup` or `--runs` below the defaults requires the user's explicit consent and a documented reason in `plan.md`. KPI floor: `elapsed_ms` and `consistent_gets` — these may not be removed; others may be added per `references/04-performance-debugging.md`. Rationalizations that fail the gate: "I already saw the timing", "one run is enough to see the pattern", "we don't need warmup for a quick check", "I'll just paste the elapsed time", "this is small enough that the bench is overkill", "the user just wants a number", "the variant is obviously faster, no need to bench". Chat-pasted milliseconds are not evidence; `bench_results.tsv` with the full KPI grid is.

  **Performance is a floor, not the sole selection criterion. The human picks the winner.** The plan's "performance acceptance criterion" is a gate — variants that fail it cannot be the winner. Among variants that pass, the agent does NOT pick mechanically based on raw KPIs. Code cleanliness, fit with existing patterns, complexity, maintenance burden, side-effect surface, and review/follow-up risk are co-equal factors. The agent's job after the bench is to (a) compute and present per-variant bench KPIs, (b) score each variant's cleanliness against the criteria in `references/05-implementation-and-shadow.md` "Variant decision surface", (c) post a recommendation with explicit trade-off reasoning, and (d) **wait for the human's explicit pick**. Approval token: the human names the variant — `"go with V2"`, `"V1"`, `"the second one"`. Until that arrives, no variant is promoted to Liquibase-owned schema folders, no Phase 6 entry happens. Rationalizations that fail the gate: "V2 is 3ms faster, that's the winner", "the bench is unambiguous, I'll just promote V3", "the user said start the perf testing, that covers the pick", "the plan's winner-picked-when rule auto-selects", "agent recommendation is effectively the pick when the human is silent", "fastest variant wins by default". The agent recommends; the human decides.
- **Adjacent-code edits require a re-brainstorm with the user.** Approval must be user-authored prose naming (a) adjacent objects affected, (b) accepted blast radius, (c) rollback plan. Assistant-supplied boilerplate the user echoes does not count.
- **Performance-testing parameters are DEV-verified by a subagent before any approval surface is shown to the user.** Inferred parameter sets (ISO, market, date windows, object IDs, scenario keys) frequently produce zero rows against DEV — making the resulting perf evidence meaningless. Whenever the agent has produced inferred parameters for performance testing — Phase 5's variant `perf.sql` harness arguments AND Phase 6's `compare_spec.json` per-run arguments — the primary agent dispatches a **parameter-verification subagent** before presenting the parameters or the spec to the user. The subagent is read-only: for each (case, run, variant) it probes DEV with the inferred values and counts rows; if the count is 0 it explores nearby alternatives close to the inferred shape; it returns a per-run digest with the recommended values, the row count they produce, and the rationale for any change. The primary agent updates the artifact (`perf.sql` / `bench_spec.json` / `compare_spec.json`) with the verified values, annotates each verified run with `verified_against_dev: true` + the observed row count, and only THEN proceeds to the user-facing approval gate. Subagent contract and digest schema: `references/06-dev-execution-and-evidence.md` "Parameter-verification subagent". Rationalizations that fail the gate: "the inferred values look right", "we'll see if rows come back when the bench runs", "0 rows is still informative", "the spec is short, no need to verify", "the user can spot bad values during approval", "verification adds friction", "the user already approved the plan, parameters are implicit", "the variant subagent already picked good values", "the inference is mechanical, it must be right". The gate exists precisely because inference is mechanical and DEV data is messy. Empty result sets must be discovered before the user approves, not at run time.

- **`compare_spec.json` requires its own explicit approval token before harness generation.** After `generate_compare_spec.py` produces the spec AND the parameter-verification subagent has updated it with verified values, the agent presents inferred runs, default arguments, `evidence_mode` per run, and every `review_required` / `TODO` / `baseline_review_required` / placeholder field to the user — verbatim, not paraphrased. The agent then waits for an explicit affirmative approval token (`"approved"`, `"looks good"`, `"reviewed"`) on the spec itself before invoking `generate_compare_harness.py` or `generate_stats_harness.py`. Approval is per-artifact: a "go" on a DEV announce, a "yes" to a clarifying question, a "start the perf testing" instruction, plan approval, or brainstorm approval do NOT carry over to the spec. The same applies to any inferred artifact gated for review — `expected_delta` SQL, observer SQL for procedure side effects, refcursor materialization plans — each must be surfaced and approved before the harness that depends on it is generated. Rationalizations that fail the gate: "the user asked me to start perf testing so the spec is implicitly approved", "the spec is straightforward", "the user said go on the announce so that covers everything downstream", "I'll let the harness fail if the spec is wrong", "the user already approved the plan", "the user will see the spec inside the harness". Implicit approval is no approval.
- **Pre-execution announce + "go" required ONLY for DDL or DML mutation against DEV.** Everything else runs without a gate.

  **What requires announce + "go":**
  - **DDL:** `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `GRANT`, `REVOKE`, `RENAME`.
  - **DML mutation:** `INSERT`, `UPDATE`, `DELETE`, `MERGE`.
  - **Anonymous PL/SQL blocks** (`BEGIN ... END;`) that contain any of the above.
  - **Procedure / function calls whose documented side effects include DML or DDL** per `util/<TICKET>/scope_digest.md` or the approved `compare_spec.json`. If side effects are not documented, treat as mutating (lean safe).
  - **Functions with OUT parameters** unless the scope digest documents them as read-only.

  The 5-line announce: script path, alias, expected effect, evidence_mode, log path. If any field is unknown, STOP and ask — never fabricate. Wait for explicit "go" before running. Never honor "go" against an announce containing `<unknown>`.

  **What runs WITHOUT a gate:**
  - **Read-only SQL:** `SELECT`, `WITH ... SELECT`, `DESC`, `EXPLAIN PLAN`, `SHOW`, queries against `v$mystat` / `v$sql` / `user_tab_columns` / any data-dictionary or dynamic-performance view.
  - **Function calls whose side effects are explicitly read-only** per the scope digest or spec.

  The agent posts a one-line "running: <short summary>" before the action and a one-line result summary after, so the user can audit progress, but no "go" is required.

  **Plan and spec approval cover the mutations they authorize.** When the user approves `plan.md`, the bench-defined mutations are covered — variant shadow compiles via `run_sqlplus_dev.sh` against the variant's `deploy_shadow.sql`, bench harness side effects documented in the variant's `notes.md`. When the user approves `compare_spec.json`, the spec-defined mutations are covered — observer pattern inserts into helper tables, the observer's `cleanup_sql: "rollback;"`, expected_delta materialization writes the spec authorizes. Running these covered mutations does NOT need a fresh announce; the prior approval IS the consent. Mutations OUTSIDE what plan or spec authorize ALWAYS re-gate to the full announce + "go".

  **End-of-session DEV cleanup (`scripts/dev_cleanup.sh`) is DDL** (`DROP` of every shadow object) and ALWAYS re-gates with a full announce, even though the shadows themselves were covered by plan approval at compile time. End-of-session is a fresh consent surface.

  **Rationalizations that fail the gate:**
  - "this DML is small";
  - "this DDL is just creating a temp table";
  - "the user is watching, they can interrupt";
  - "the rollback at the end means it's safe";
  - "I'll just run it and revert if needed";
  - "the DELETE is just helper-table cleanup";
  - "this DDL is in the same shape as what the plan approved" (different DDL → different gate);
  - "the user's prior 'go' on the deploy covers this DML too";
  - "this is the same kind of thing as the spec asked for".

  All of these mean: STOP, post the 5-line announce, wait for "go".
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
