# Implementation and Shadow Objects

Implementation runs under the harness's plan-execution workflow once the plan is approved (auto-engaged on plan-driven implementation; not invoked by name from db-work). For multi-variant work, the OPTIONAL parallelization path is described at the end of this file.

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

For 2 variants, run the per-variant subagents sequentially — coordination overhead beats wall-clock savings. Codex dispatches subagents directly; db-work does not rely on a harness auto-fire here.

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
- Running `perf-bench.sh` (sequential by design — concurrent benches break the warm-cache assumption).
- Picking the winner.
- Promoting the winner's edits to the Liquibase-owned schema folders.

### When subagents return

Each subagent reports back its variant folder path and a 1-paragraph summary. The parent agent reviews each return for plan compliance (right entry point, KPI prediction stated, no adjacent-code edits) before accepting.

If a subagent proposes adjacent-code changes, the parent agent treats it as scope expansion — re-brainstorm with the user per `references/04-performance-debugging.md`.

## Exit — auto-advance to Phase 6

When the bench picks a winner under the plan's "winner-picked-when" rule and `bench_results.tsv` exists, Phase 5 ends and Phase 6 auto-engages — see `SKILL.md`'s "Phase progression" table for the transition rule. The Phase 6 entry sequence (manifest → metadata probe → compare_spec → review surface) is in `references/06-dev-execution-and-evidence.md` under "Entry".

If no variant clears the plan's threshold, do NOT auto-advance. Follow the adjacent-code expansion path in `references/04-performance-debugging.md` — STOP, propose adjacent edits, re-brainstorm with the user. Phase 6 only auto-engages on a clean winner pick.
