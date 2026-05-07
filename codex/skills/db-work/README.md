# db-work Skill

A workflow for safe Oracle/Liquibase changes in the Oracode repository: brainstorm-first design, multi-variant implementation, performance evidence on DEV, deliberate winner selection by the human, and a reviewable handoff.

The agent runs the workflow end-to-end. The user makes the decisions that matter (brainstorm, plan, variant pick, evidence spec, walkthrough). The skill exists to make those decisions cheap to make and the agent's work auditable.

For a file-by-file / script-by-script reference, see [`glossary.md`](glossary.md).

## When to use

PL/SQL or Liquibase work in an Oracode checkout — packages, types, functions, procedures, views, team `*_changelog.xml` updates, DEV-only `_<INITIALS>` shadow objects, original-vs-shadow comparison on DEV, or job/Jira-ticket database implementation. See `SKILL.md` for the full trigger description and the iron rules that govern the workflow.

## Workflow

The agent owns the transitions between steps. The user owns the marked **`wait_for_user(...)`** gates.

```python
def db_work_session(ticket):

    # ── Phase 1: Doctor ────────────────────────────────────────────────────
    health = run("scripts/db-work-doctor.sh")            # see [Doctor]
    if not health.green:
        plan = run("scripts/db-work-doctor.sh --plan")
        post_to_user(plan)
        wait_for_user_approval()                          # explicit "go" / "yes"
        run("scripts/db-work-doctor.sh --fix --yes")
        wait_for_user_to_re_run_in_fresh_shell()
    if session_intent == "setup-only":
        return

    # ── Phase 2: Intake + scope research ───────────────────────────────────
    intake = read_ticket(ticket)                          # see [Intake]
    digest = dispatch_subagent(                           # see [Scope research]
        role="scope-research",
        prompt=intake_to_subagent_prompt(intake),
    )
    commit_artifact("util/<TICKET>/scope_digest.md", digest)
    # The parent agent NEVER reads full PL/SQL packages directly — that's
    # exactly what the subagent is for. The parent only re-reads specific
    # line ranges the digest cites if it needs more detail later.

    # ── Phase 3: Brainstorm ────────────────────────────────────────────────
    brainstorm = run_skill("superpowers:brainstorming", input=digest)
    summary = build_brainstorm_summary(brainstorm)        # see [Brainstorm summary]
    post_to_user(summary)
    wait_for_user_approval(summary)

    # ── Phase 4: Plan with 2–3 variants ────────────────────────────────────
    plan = run_skill("superpowers:writing-plans", input=summary)
    # plan contains: 2-3 distinct variants, a performance acceptance
    # criterion (a perf floor — NOT a winner-picker), KPI list, deployment
    # constraints. See [Plan structure].
    commit_artifact("util/<TICKET>/plan.md", plan)
    post_to_user(plan)
    wait_for_user_approval(plan)

    # ── Phase 5: Implement variants + benchmark ────────────────────────────
    for variant in plan.variants:
        impl = dispatch_subagent(                         # see [Variant subagent]
            role="implementer",
            scope=f"util/<TICKET>/variants/{variant.n}/",
            suffix=f"_{INITIALS}_V{variant.n}",
        )
        impl.write_liquibase_edits_under("variants/<n>/changes/")
        impl.run("scripts/generate_shadow_objects.py")
        impl.fill_in("variants/<n>/perf.sql")             # from assets/sql/perf_harness_template.sql
        impl.write("variants/<n>/notes.md")

    write_bench_spec_json(plan.variants, plan.kpis)       # parent serializes

    for variant in plan.variants:                         # sequential, never concurrent
        run("scripts/run_sqlplus_dev.sh",                 # DDL — covered by plan approval
            script=f"variants/{variant.n}/deploy_shadow.sql")

    # Verify the bench arguments produce > 0 rows BEFORE running the bench.
    verification = dispatch_subagent(                     # see [Parameter-verification subagent]
        role="parameter-verification",
        inferred_args=collect_bench_args(plan.variants),
        scope_digest=digest,
    )
    for variant in plan.variants:
        update_with_verified_values(variant.perf_sql, verification[variant])

    run("scripts/perf-bench.sh",                          # warm-cache, --warmup 2 --runs 5
        spec="variants/bench_spec.json")
    # → writes "variants/bench_results.tsv" (one row per measured run)

    # ── Variant decision (human picks) ─────────────────────────────────────
    qualifying = [v for v in plan.variants
                  if meets_perf_acceptance(v, plan.acceptance_criterion)]
    decision_surface = build_decision_surface(            # see [Variant decision surface]
        variants=plan.variants,                           # ALL variants, including disqualified
        bench=read_tsv("variants/bench_results.tsv"),
        cleanliness=score_cleanliness(qualifying),
    )
    recommendation = pick_recommendation(                  # the agent's recommendation
        qualifying,
        reasoning="explicit trade-off between perf and cleanliness",
    )
    post_to_user(decision_surface + recommendation)
    picked = wait_for_user_pick()                         # token names a variant: "V2", "go with V1"
    if picked != recommendation:
        divergence_reason = ask_user_once_for_reason()    # captured for the report

    # ── Phase 6: DEV evidence (manual testing) ─────────────────────────────
    promote_to_liquibase_owned_schema(picked)             # winner's edits → PROD/, YES_SERVICES/
    write_artifact("dev_sandbox/shadow_manifest.json")

    metadata_probe = run("scripts/generate_metadata_probe.py")
    run("scripts/run_sqlplus_dev.sh",                     # read-only — no gate
        script=metadata_probe)

    spec_draft = run("scripts/generate_compare_spec.py",  # see [Compare-spec generation]
                     manifest="dev_sandbox/shadow_manifest.json",
                     metadata="dev_sandbox/logs/db_metadata.tsv")

    # Same verification subagent shape as Phase 5, now over the spec's runs.
    verification = dispatch_subagent(
        role="parameter-verification",
        inferred_args=spec_draft.runs,
        scope_digest=digest,
    )
    spec = update_spec_with_verified_values(spec_draft, verification)
    commit_artifact("util/<TICKET>/dev_sandbox/compare_spec.json", spec)

    post_to_user(spec + verification_banner(spec))        # see [Compare-spec approval]
    wait_for_user_approval_token(spec)                    # "approved" / "looks good" / "reviewed"

    compare_harness = run("scripts/generate_compare_harness.py", spec=spec)
    stats_harness   = run("scripts/generate_stats_harness.py",   spec=spec)
    # Spec approval covers the spec-defined writes (observer inserts, rollbacks,
    # expected_delta materialization). No per-action announce required.
    for harness in [compare_harness, stats_harness]:
        run("scripts/run_sqlplus_dev.sh", script=harness)
    summary = run("scripts/summarize_sqlplus_logs.py",
                  log_dir="dev_sandbox/logs/")

    # ── Phase 7: Walkthrough + handoff ─────────────────────────────────────
    files = sh("git diff --name-only <base>...HEAD")
    walkthrough = build_per_file_walkthrough(             # see [Per-file walkthrough]
        files=files,                                      # all 7 fields per file, no templates
    )
    post_to_user(walkthrough)
    wait_for_user_approval_token(walkthrough)             # "reviewed" / "looks good" / "approved"

    # NEXT TURN — never the same turn as the walkthrough approval:
    run("scripts/db-work-report.sh", ticket=ticket)       # emits dev_sandbox/report.md
    post_to_user(read("util/<TICKET>/dev_sandbox/report.md"))

    # ── End-of-session cleanup (on user trigger) ───────────────────────────
def end_of_session(tickets_touched):
    for ticket in tickets_touched:                        # 1. DEV cleanup (DDL — gated)
        run("scripts/dev_cleanup.sh", ticket=ticket)
    for ticket in tickets_touched:                        # 2. per-ticket scratch removal
        post_dry_run_preview(ticket)
        wait_for_user_approval_token()
        remove_scratch_files(ticket)                      # scope_digest, warmup logs, *.draft.*
    run("scripts/cleanup_session.sh")                     # 3. temp session dir
```

### Step explanations

#### Doctor

Single-shot machine-readiness check (sqlplus, mkstore, alias, wallet, plugin install, subagent dispatch primitive). Modes: `--plan` (read-only, prints what `--fix` would do), `--fix --yes` (runs the installs). On red, the agent presents the plan, gets explicit approval, runs `--fix --yes`, and asks the user to re-run in a fresh shell. Setup-only sessions (doctor green → done) are valid.

#### Intake

Read the ticket; collect: ticket id + title, business goal, acceptance criteria, affected schema/object/callable names if known, team or changelog (e.g. `visualanalytics_changelog.xml`), known DEV scenarios, open questions, dependencies. If `ticket-start` is installed, defer to its job-workflow path. Carry forward into later phases: ticket id, title, acceptance criteria, branch intent, open questions.

#### Scope research

A read-only subagent receives the intake fields, the named in-scope objects, and the repo roots to inspect. It returns a digest with: per-callable verbatim signature + `file:line` source location, hot-path notes (no SQL bodies — just line ranges), side effects (DML target tables only — names), dependent objects (types, sequences, views, packages referenced), public callers, open questions, and a citation index the parent can scan. The parent NEVER falls back to direct source reads — if the digest is incomplete, re-dispatch with a corrective prompt. Digest committed at `util/<TICKET>/scope_digest.md`.

#### Brainstorm summary

The brainstorming skill's structured output. Required fields: problem statement (concrete, not "the ticket asks for X"), constraints (perf budget, deploy ordering, scope boundaries), candidate directions (≥ 2 distinct directions, 1–2 sentences each), adjacent-code areas flagged (even "none — considered and ruled out"), open questions still pending. The user must explicitly accept this summary before plan-writing begins.

#### Plan structure

Saved at `util/<TICKET>/plan.md`. Contains: problem statement (from brainstorm), constraints (perf budget, deploy ordering, out-of-scope), 2–3 variants (each with name, approach, hot-path change, adjacent code touched = `none`, expected KPI direction, risk), **performance acceptance criterion** (a perf floor variants must clear, e.g. "≥20% lower mean elapsed_ms; no >10% rise in consistent_gets"), KPI list (floor: `elapsed_ms`, `consistent_gets`), implementation steps. The plan does NOT name a winner — selection is the human's at Phase 5 end.

#### Variant subagent

One subagent per variant. Each writes ONLY its own `util/<TICKET>/variants/<n>/` folder, with a distinct sub-suffix on shadow objects (`_<INITIALS>_V1`, `_<INITIALS>_V2`, `_<INITIALS>_V3`) so DEV compiles don't collide. Per variant: edited Liquibase-owned files (under `changes/`, NOT touching `PROD/` / `YES_SERVICES/` yet — only the winner promotes), shadow object files, a filled-in `perf.sql` from `assets/sql/perf_harness_template.sql`, a one-page `notes.md` describing the approach. Parent serializes the bench (concurrent benches break the warm-cache assumption).

#### Parameter-verification subagent

Read-only subagent that probes DEV with the inferred parameter values and counts rows. Used twice — once before `perf-bench.sh` (Phase 5 bench arguments) and once before the compare-spec approval surface (Phase 6 spec runs). For each (case, run, variant) it constructs a representative SELECT against the underlying tables the target callable would query (using the scope digest to find the tables), runs it, and records the row count. If 0, it explores nearby alternatives (widen the date window; swap ISO/market combo; drop one filter) and returns a recommendation. Pass/fail bar varies by `evidence_mode`: `regression_compare` needs both original + shadow > 0; `shadow_expected_result` needs only shadow; `compile_contract_validation` is N/A. The parent updates the artifact with verified values + audit trail (`verified_against_dev`, `verified_row_count`, `original_inferred_values` if changed) BEFORE the user-approval surface is shown.

#### Variant decision surface

Posted after `bench_results.tsv` is written. Per variant — including disqualified ones — the surface lists: identifier, approach (1 sentence from `notes.md`), bench KPIs (mean / median / p95 across the full KPI grid), perf-acceptance verdict, **cleanliness assessment** scored on 6 axes (`pattern fit`, `complexity`, `hidden assumptions`, `reviewability`, `reversibility`, `test surface`) as `+`/`0`/`−` with ≤ 10-word justifications, diff size, side-effect surface, maintenance burden, review/follow-up risk. The agent then posts ONE recommendation in the format `"Recommended: V<n>\nReasoning: <2–4 sentences naming both perf and cleanliness factors>"`. Ends with the explicit ask: `"Which variant should we promote to the Liquibase-owned schema?"`. The human names the variant (`"V2"`, `"go with V1"`, `"the second one"`) — bare assent does NOT pick. If the human picks against the recommendation, the agent asks once for the divergence reason (for the report) and accepts the pick without arguing.

#### Compare-spec generation

`generate_compare_spec.py` produces a draft spec from the shadow manifest + DEV metadata: which callables to test (defaults to public callables whose declaration or implementation lines changed in the diff), with which arguments, on which scenarios, and how each scenario's evidence is interpreted (`regression_compare`, `shadow_expected_result`, `expected_delta`, `performance_only`, `compile_contract_validation`). The parameter-verification subagent then probes DEV and updates the draft with verified values + audit trail before the spec reaches the user.

#### Compare-spec approval

The agent posts the spec verbatim — per-case signature, per-run verified arguments + row count, evidence_mode + rationale, every `review_required` / `TODO` / `baseline_review_required` field, every observer-inference / cursor-materialization / expected-delta SQL block — with a verification banner at the top counting verified / changed / unverifiable runs. UNVERIFIABLE runs are red-flagged. The human must reply with an explicit token (`"approved"` / `"looks good"` / `"reviewed"`) on the spec itself; tokens from any other surface (plan approval, DEV announce go, brainstorm yes, perf-testing instruction) do NOT carry over.

#### Per-file walkthrough

The agent runs `git diff --name-only <base>...HEAD` and walks every file in the diff (Liquibase-owned files + the team changelog + the chosen variant's bench harness + bench_results.tsv + the compare/stats harnesses + summarized logs). For each file, all 7 fields required, no templated `<...>` placeholders: path, purpose (1 sentence), what changed (concrete diff summary), why this change (link to plan + brainstorm decision), performance rationale (which variant the human picked, by how much, on which KPI; agent's recommendation if different + divergence reason), risks and reviewer attention points, pointer to the evidence file. Approval token must be explicit (`"reviewed"` / `"looks good"` / `"approved"`); the report runs in a SEPARATE turn after approval.

## Artifacts produced

Per ticket, under `util/<TICKET>/`:

| Artifact | Phase | Durable? | Purpose |
|----------|-------|----------|---------|
| `scope_digest.md` | 2 | scratch | Subagent's digest of in-scope callables, callers, dependents, hot paths. Removed at session end after the report is committed. |
| `plan.md` | 4 | durable | Approved plan with variants, perf acceptance criterion, KPI list. |
| `variants/<n>/` | 5 | durable | Per-variant: edited Liquibase files, shadow objects, `perf.sql`, `notes.md`. |
| `variants/bench_spec.json` | 5 | durable | Bench configuration listing all variants and KPIs. |
| `variants/bench_results.tsv` | 5 | durable | One TSV row per measured run; mean / median / p95 per KPI per variant. |
| `dev_sandbox/objects/` | 6 | durable | Winner's shadow object SQL (suffixed copies for DEV). |
| `dev_sandbox/shadow_manifest.json` | 6 | durable | Required to re-run `dev_cleanup.sh` later. |
| `dev_sandbox/compare_spec.json` | 6 | durable | Approved spec with verified parameter values. |
| `dev_sandbox/compare_harness.sql` / `stats_harness.sql` | 6 | durable | Generated from approved spec; functional + perf evidence. |
| `dev_sandbox/logs/*.summary.log` | 6 | durable | Summarized DEV execution logs. |
| `dev_sandbox/report.md` | 7 | durable | Handoff report (PR-grade summary). |

Reviewable trail = plan → variants → bench → spec → harness logs → report. Everything else (raw spools, draft specs, warmup logs, scope digest) is removed at session end. Full keep/remove list in `references/08-session-cleanup.md`.

## Workflow gates (high level)

`SKILL.md` is the canonical source for the iron rules. Quick scan:

- Scope research is subagent-only — parent never reads full PL/SQL into its context.
- Plan + brainstorm before any edit — no exploratory code between brainstorm and plan approval.
- Performance is a floor, not a winner-picker — the human picks the winner from qualifying variants, with cleanliness as a co-equal axis.
- Compare-spec needs its own approval token — `"approved"` / `"looks good"` / `"reviewed"` on the spec itself.
- Parameter-verification subagent runs before any user-approval surface — empty result sets caught before the user is asked to approve.
- DDL and DML mutation require announce + "go" unless covered by plan or spec approval. Reads run gate-free.
- Batched walkthrough before claiming done — every file from `git diff --name-only`, all 7 fields, explicit approval token before the report.

## Dependencies

- **`superpowers` plugin** — db-work relies on `superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:executing-plans`, `superpowers:subagent-driven-development`, `superpowers:verification-before-completion`. Doctor Check #7 verifies installation.
- **Subagent dispatch primitive** — Codex requires `multi_agent = true` in `~/.codex/config.toml`. Claude Code requires `Task` / `Agent` not denied in `permissions.deny`. Doctor Check #8 verifies per harness.
- **Oracle SQLPlus + SEPS wallet** — `db-work-doctor.sh --fix` provisions everything on macOS automatically; secrets only prompted in the local terminal.

## Layout

```
db-work/
├── SKILL.md                 entrypoint + iron rules
├── README.md                this file
├── glossary.md              file-by-file / script-by-script reference
├── agents/openai.yaml       Codex marketplace metadata
├── assets/sql/              harness templates (perf, compare, stats, deploy)
├── references/              loaded on demand (see glossary.md)
├── scripts/                 see glossary.md
└── tests/pressure-scenarios.md
```

## Repository sync

Per repo-root `AGENTS.md`: every edit under `codex/skills/db-work/` in this repo MUST be mirrored to `/Users/trocaneduard/.codex/skills/db-work/` in the same flow. Verify with `diff -rq <repo-skill> <install-skill>` — the diff must be empty before a change is considered shipped.
