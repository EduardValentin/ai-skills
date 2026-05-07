# Implementation and Shadow Objects

Implementation runs once the plan is approved — use `superpowers:executing-plans` (sequential) or `superpowers:subagent-driven-development` (per-task subagents). For multi-variant work, db-work's per-variant subagent path is described at the end of this file.

## Variant directory layout

```
util/<TICKET>/
├── plan.md
├── variants/
│   ├── 1/
│   │   ├── changes/        editable copies of Liquibase-owned files for this variant
│   │   ├── shadow/         user-suffixed shadow objects compiled to DEV
│   │   ├── perf.sql        bench harness (writes one TSV KPI line)
│   │   └── notes.md        what this variant does and why
│   ├── 2/
│   └── 3/                  optional
│   ├── bench_spec.json
│   ├── bench_results.tsv
│   └── perf_logs/
└── dev_sandbox/            populated only after the winner is picked
```

## Compile each variant's shadow before benchmarking

Each variant's shadow objects are compiled to DEV with the configured suffix (e.g. `_EDI`) so the bench harness calls the variant's shadow, not the original. The original is never touched during measurement.

## Liquibase-owned edits — winner only

Only after the winner is picked from the bench:

- Apply changes to `PROD/`, `YES_SERVICES/`, or sibling schema folders.
- Preserve Oracode SQL rules from `references/oracode-rules.md`.
- One database object per file.
- Trailing `/` on PL/SQL objects.
- No inline comments in Liquibase-owned SQL.
- Unix-style paths in XML.

## Changelog update

```bash
"$DB_WORK_SKILL_DIR/scripts/generate_changelog_entry.py" \
  --team visual-analytics --ticket VA-515 --author "Your Name"
```

Sort changesets by dependency:

```
TYPE_SPEC → TYPE_BODY → SEQUENCE → TABLE → INDEX → SYNONYM →
PACKAGE_SPEC → PACKAGE_BODY → VIEW → FUNCTION → PROCEDURE → TRIGGER → JOB
```

Review the generated XML before writing for non-trivial changes.

## DEV shadow objects (winner)

Generate suffixed copies for DEV compile and comparison:

```bash
"$DB_WORK_SKILL_DIR/scripts/generate_shadow_objects.py" \
  --ticket VA-515 --suffix _EDI

"$DB_WORK_SKILL_DIR/scripts/generate_dev_deploy.py" \
  --ticket VA-515 --grant-execute-to ye_dev
```

- Shadow files go to `util/<TICKET>/dev_sandbox/objects/`.
- The DEV deploy script uses SQLPlus `@@` includes (resolved relative to the deploy script).
- `grant execute on yes_services.<obj>_EDI to ye_dev;` is auto-emitted for executable shadows.
- Shadow files are NEVER added to a Liquibase changelog.

## Lint before handoff

```bash
./dev_utils/lint_changed_files.sh
```

Capture the lint log under `util/<TICKET>/dev_sandbox/logs/lint.log` so the handoff report can summarize it.

## Per-variant implementation via subagents

Subagents in Phase 5 are primarily about **context isolation, not parallelism**. Each variant's exploration of the SQL — testing alternative joins, hint placements, rewrite shapes — re-reads source the parent already digested in Phase 2. Letting that exploration happen in a subagent keeps the parent context stable across all variants.

### Default: dispatch one subagent per variant (sequential is fine)

For any variant whose implementation goes beyond filling in template tokens — i.e. it requires reading more SQL than is already covered by the Phase 2 digest's citation index — dispatch a subagent. Sequential dispatch is fine; the goal is isolation, not speed.

Skip the subagent and let the parent edit directly only when the variant is genuinely a template fill (e.g. swap one identifier, add one hint to one line) and uses zero source beyond the digest.

### Parallel dispatch (optional)

Parallel dispatch is an additional optimization on top, available when:

- The plan has **3 variants**, AND
- Per-variant implementation involves substantial offline work (multi-file edits, non-trivial shadow generation, custom harness setup).

For 2 variants, run the per-variant subagents sequentially — coordination overhead beats wall-clock savings.

### Coordination rules

When fanning out, each subagent edits ONLY its own `util/<TICKET>/variants/<n>/` folder and uses a **distinct sub-suffix** so DEV compiles do not collide:

| Variant | Suffix flag |
|---------|-------------|
| V1 | `--suffix _<INITIALS>_V1` (e.g. `_EDI_V1`) |
| V2 | `--suffix _<INITIALS>_V2` |
| V3 | `--suffix _<INITIALS>_V3` |

Each subagent produces:

- the variant's edited Liquibase-owned files (under its own `changes/` folder, NOT touching `PROD/` or `YES_SERVICES/` yet — the winner edits those after bench);
- the variant's shadow object files via `generate_shadow_objects.py --suffix _<INITIALS>_V<n>`;
- a filled-in `perf.sql` from `assets/sql/perf_harness_template.sql` calling its own shadow;
- a one-page `notes.md` summarizing the approach.

### Serializing steps (parent agent only)

The parent agent — NOT the subagents — handles:

- Writing `bench_spec.json` after all subagents return (it lists all variants).
- Compiling each variant's shadow to DEV via `run_sqlplus_dev.sh` (sequential per variant, never concurrent — even with distinct suffixes, simultaneous compiles can serialize unfavourably and obscure the comparison).
- **Dispatching the parameter-verification subagent** (`references/06-dev-execution-and-evidence.md` "Parameter-verification subagent") to probe DEV with each variant's `perf.sql` arguments. Update each `perf.sql` and `bench_spec.json` with verified values + `verified_against_dev: true` annotations BEFORE running `perf-bench.sh`. Empty result sets discovered now are cheap; discovered after the bench, they invalidate hours of perf evidence.
- Running `perf-bench.sh` (sequential by design — concurrent benches break the warm-cache assumption).
- Posting the variant decision surface (see below) and waiting for the human's pick.
- Promoting the human-chosen variant's edits to the Liquibase-owned schema folders — only after the pick.

### When subagents return

Each subagent reports back its variant folder path and a 1-paragraph summary. The parent agent reviews each return for plan compliance (right entry point, KPI prediction stated, no adjacent-code edits) before accepting.

If a subagent proposes adjacent-code changes, the parent agent treats it as scope expansion — re-brainstorm with the user per `references/04-performance-debugging.md`.

## Variant decision surface (mandatory before Phase 6)

After `bench_results.tsv` is written, the agent does NOT pick a winner. The agent posts a decision surface to the human and waits for an explicit pick. This surface is the input the human uses to decide; it is also the artifact the handoff report cites.

### Per-variant entries

For every variant — including disqualified ones (so the human sees why) — post:

1. **Identifier** — `V1`, `V2`, `V3`.
2. **Approach (1 sentence)** — what this variant does, copy-paste from `notes.md`.
3. **Bench KPIs** — mean / median / p95 for the full KPI grid from `bench_results.tsv` (at minimum `elapsed_ms`, `consistent_gets`; whatever else the plan added).
4. **Performance acceptance** — `qualifies` or `disqualified — <reason from "Diagnosing a regression" in 04-performance-debugging.md>`.
5. **Cleanliness assessment** — score against each criterion in the next section.
6. **Diff size** — files touched + lines changed (`git diff --stat` against the baseline for the variant's `changes/` set).
7. **Side-effect surface** — DML targets, autonomous transactions, sequence reads, new dependencies. Names only.
8. **Maintenance burden** — anything the team will have to keep maintaining (refresh job, hint dependent on stats, pinned plan, custom index).
9. **Review/follow-up risk** — one of: `low` (one-shot review), `medium` (needs a reviewer who knows the package), `high` (broad blast radius or non-idiomatic structure).

### Cleanliness criteria

The agent scores each variant on each axis as `+` (clearly good), `0` (neutral), or `−` (concern), with a short justification (≤ 10 words):

- **Pattern fit** — does it reuse an existing pattern in the team's schema folder, or invent a new one?
- **Complexity** — single SELECT vs multi-step procedure vs cross-package coordination.
- **Hidden assumptions** — does correctness depend on stats, an existing index, an optimizer hint, or a particular plan being chosen?
- **Reviewability** — can a reviewer who knows Oracode but not this ticket understand it from the diff alone, or do they need the brainstorm context?
- **Reversibility** — if a regression surfaces post-merge, how hard is the rollback? (drop one object: `+`; rewrite a caller: `0`; un-pick a materialized view that other queries now depend on: `−`.)
- **Test surface** — does it widen the comparison/stats spec scope (more callables affected, more scenarios needed)?

The cleanliness assessment is the agent's judgement, not measured. Ties are fine; explicit `0` is fine. Do not pad with `+` to favour a recommendation.

### Agent recommendation

Below the per-variant entries, the agent posts ONE recommendation, in this exact shape:

```
Recommended: V<n>
Reasoning: <2–4 sentences spelling out the trade-off explicitly — e.g. "V2 is 3% slower than V3 on elapsed_ms but reuses the existing TRANS_CONST_OVERLAP cursor pattern, has zero side effects, and a one-shot review surface. V3 introduces a materialized view requiring a refresh job; the perf gain does not justify the maintenance burden.">
```

The recommendation MUST be a qualifying variant. If only one variant qualifies, the agent recommends it but still posts the decision surface — the human's pick is still required.

### The ask

End the surface with an explicit, short question:

> Which variant should we promote to the Liquibase-owned schema?

Wait for the human to name a variant (`"V2"`, `"go with V1"`, `"the second one"`). Bare assent — `"go"`, `"yes"`, `"approved"`, `"ok"`, emoji-only ack — does NOT pick a variant; it is ambiguous in this context. Re-prompt by name if the response is ambiguous.

### What the gate prevents

Until the human names a variant:

- the agent does NOT promote any variant's edits to `PROD/`, `YES_SERVICES/`, or sibling schema folders;
- the agent does NOT emit `shadow_manifest.json` for a winner;
- the agent does NOT enter Phase 6.

The human is allowed to override the recommendation. If they pick a variant the agent did not recommend, the agent accepts the pick without arguing — but asks (once) for the divergence reason so the report can record it. The agent does NOT re-debate the trade-off after the pick.

### Rationalizations that fail the gate

- "V2 is 3ms faster than V3 — that's the winner";
- "the bench is unambiguous, no need to wait";
- "the user said start the perf testing, that covers the pick";
- "the plan said pick the lowest mean, so I picked the lowest mean";
- "agent recommendation is effectively the pick when the human is silent";
- "fastest variant wins by default";
- "user already approved the plan with this winner-picked-when rule";
- "going to Phase 6 with V<n>, can switch later if user objects".

All of these mean: STOP, post the decision surface (or the missing parts of it), and wait for the human to name a variant.

## Exit — auto-advance to Phase 6 once the human has picked

Phase 5 ends when the human names a variant on the decision surface. At that point, Phase 6 auto-engages — see `SKILL.md`'s "Phase progression" table. The Phase 6 entry sequence (promote-to-schema → manifest → metadata probe → compare_spec → review surface) is in `references/06-dev-execution-and-evidence.md` under "Entry".

If no variant clears the plan's performance acceptance criterion, do NOT post the decision surface yet, and do NOT auto-advance. Follow the adjacent-code expansion path in `references/04-performance-debugging.md` — STOP, propose adjacent edits, re-brainstorm with the user. Phase 6 only engages after a human pick on a qualifying variant.
