# Code Walkthrough and Handoff Report

## Walkthrough gate (batched, mandatory)

After all evidence is collected and before claiming the work done, the agent walks the user through every changed file in **one batched session**. Per-file approval mid-implementation is not required — the goal is keep flow during work, then surface a single review surface at the end.

### File list source of truth

The changed-file list MUST come from:

```bash
git diff --name-only <base>...HEAD
```

Not from agent memory. Not from user dictation. The agent runs the diff, posts the verbatim file list at the top of the walkthrough, and walks every file on it. If the list is empty, claim "no changes" and stop — do not template placeholders.

### Per-file schema

For each file, the agent presents — all seven fields required, no field may be templated `<...>`:

1. **Path.**
2. **Purpose** (one sentence).
3. **What changed** — concrete diff summary, not "minor edits".
4. **Why this change** — link to plan section + brainstorm decision.
5. **Performance rationale** — which variant the human picked, by how much (concrete number from `bench_results.tsv`), on which KPI. Note the agent's recommendation if different, with the divergence reason. "See evidence" is not acceptable.
6. **Risks and reviewer attention points.**
7. **Pointer to the evidence file** proving the change is safe.

A walkthrough that templates any field (e.g. `<KPI delta>`, `<file_n>`) does not pass the gate.

### Files in scope (walked with all 7 fields)

The walkthrough subjects are the COMMITTED files only — what's about to ship in the PR:

- All Liquibase-owned files in the `git diff` (the team's schema folders).
- The team changelog.
- Ad-hoc data-fix / migration scripts under `util/ADHOC/` that the changelog references via `<sqlFile>` — these ARE committed there, and the walkthrough walks them like any other Liquibase-owned change.

### Files referenced but NOT walked

Evidence artifacts under `util/<TICKET>/` are local-only and never committed. They're cited from each in-scope file's "Pointer to evidence file" field (field 7), but they are NOT walkthrough subjects themselves:

- `util/<TICKET>/variants/<n>/perf.sql` and `util/<TICKET>/variants/bench_results.tsv` — referenced from the per-file performance rationale.
- `util/<TICKET>/dev_sandbox/compare_harness.sql`, `stats_harness.sql`, and `dev_sandbox/logs/*.summary.log` — referenced from the per-file evidence pointer.
- `util/<TICKET>/plan.md`, `scope_digest.md`, `dev_sandbox/report.md` — referenced as session-local audit material.

### Out-of-scope: `util/<TICKET>/...`

If `git diff --name-only <base>...HEAD` shows any path under `util/<TICKET>/`, that's a defect — db-work session artifacts are not part of the deployment surface and must not enter git. STOP, surface the unexpected files, and either gitignore the path or remove it from the index before continuing the walkthrough. (Paths under `util/ADHOC/` are NOT a defect — they're the proper home for committed ad-hoc scripts.)

### User signal to proceed

Approval token must be explicit and affirmative — `"reviewed"`, `"looks good"`, `"approved"`. Anything else (silence, "wait", a question, an emoji-only ack, "k") keeps the walkthrough open. The agent may answer follow-ups inline, but the gate stays open until an explicit affirmative token.

### Same-turn report ban

The handoff report MUST be generated in a separate turn after the approval token. Bundling the walkthrough and the report into the same message bypasses the gate by giving the user nothing to approve — the report is already written. The agent posts the walkthrough, waits for approval, THEN runs `db-work-report.sh`.

### Pressure resistance

"Just write the report, I'll read it in the PR" / "It's late, skip ahead" / "We've been over this" are not waivers. PR review is not a substitute for the walkthrough — the walkthrough is the agent's own artifact-grounded summary, while a PR diff is raw code. The two serve different purposes.

## Handoff report

```bash
"$DB_WORK_SKILL_DIR/scripts/db-work-report.sh" --ticket VA-515
```

Emits `util/VA-515/dev_sandbox/report.md` in this fixed shape:

```markdown
# DB Work Report — VA-515

## Summary
- Branch
- Team changelog
- Variants benchmarked: N
- Performance acceptance criterion (verbatim from plan): <...>
- Qualifying variants: V<a>, V<b>, ...
- Agent's recommendation: V<n> — <one-line reason>
- Human's pick: V<m>
- Divergence reason (if pick != recommendation): <user-supplied reason, captured at the time of the pick>
- Winner KPIs vs baseline: Δ elapsed_ms, Δ consistent_gets

## Files changed (Liquibase-owned)
- list (from git diff)

## Files generated (DEV sandbox)
- list

## Performance evidence
- bench_results.tsv (mean per KPI per variant)
- regressions noted (if any)

## Comparison evidence
- compare/stats log paths
- evidence_mode used per run

## Lint
- ./dev_utils/lint_changed_files.sh result

## Manual steps remaining
- [ ] Reviewer approval of changelog ordering
- [ ] PR opened
- [ ] Liquibase deploy plan confirmed with team
```

The agent posts this report inline (so the user sees it without opening the file) AND writes it to `util/<TICKET>/dev_sandbox/report.md`. The report is local-only audit material — like everything else under `util/<TICKET>/`, it does NOT enter git.

## Done definition

The work is done when ALL of these are true:

- Doctor is green (or amber-with-banner-on-every-artifact for generation-only work).
- Plan with 2–3 variants (or obvious-variant path) was reviewed.
- Bench picked a winner under the plan's rule and `bench_results.tsv` exists.
- DEV evidence is collected and summarized.
- The batched walkthrough ran with all seven fields populated for every file in `git diff`, and the user signaled approval with an explicit affirmative token.
- `db-work-report.sh` emitted the report in a separate turn after approval.
- Lint passes (or remaining issues are listed in the report's manual-steps section).
