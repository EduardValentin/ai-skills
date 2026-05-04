# Planning with Variants

**REQUIRED SUB-SKILL:** Use `superpowers:writing-plans` to produce the plan. Use `superpowers:executing-plans` to execute it.

## Plan template

Save as `util/<TICKET>/plan.md`.

```markdown
# Plan — <TICKET>

## Problem
<one paragraph from the brainstorm summary>

## Constraints
- Performance budget: <e.g. ≥20% lower mean elapsed_ms; no plan-cost regression on dependent callers>
- Deployment: <e.g. single changeset; runOnChange=true; ordering constraints>
- Out of scope: <list>

## Variants

### V1 — <name>
- Approach:
- Hot-path change:
- Adjacent code touched: none
- Expected KPI direction: <elapsed↓ / consistent_gets↓ / etc.>
- Risk:

### V2 — <name>
- (same fields)

### V3 — <name>            # optional; include when 2 are insufficient
- (same fields)

## Winner-picked-when rule
<concrete rule, e.g. "lowest mean elapsed_ms across 5 runs AND no >10% rise in consistent_gets on PUBLIC_API_X">

## KPI list
elapsed_ms, consistent_gets, db_block_gets, sorts_memory, recursive_calls, plan_cost

## Implementation steps
1. <step>
2. <step>
```

## Variant rules

- The plan MUST list **2–3 variants**. Two is the floor, three is the ceiling. When two genuinely-distinct variants exist, accept without negotiation — do not add a third "for completeness".
- Skip the variant requirement only via the **obvious-variant path**: one approach is unambiguously correct (e.g. fixing a typo in a constant; adding the single index hint the optimizer already failed on). The agent announces `"obvious-variant path: <reason>"` and waits for the user to confirm. Any "no" or hesitation forces 2–3 variants.
- **Do not preemptively offer the obvious-variant path.** Only invoke it when the user explicitly proposes skipping a variant or names an approach as obvious. Volunteering the escape hatch counts as coaching the user toward a skip.
- **Even on obvious-variant path, the single variant still gets benched** against DEV via `perf-bench.sh`. The bench produces `bench_results.tsv`, which is the DEV evidence artifact for Phase 6. "User already tested on dev box" is not bench evidence.
- A user arriving with a pre-written fix is treated as a candidate variant (V1), not as a completed implementation. The variant gate still applies.
- Each variant MUST predict which KPI it improves and why. "Just try it" is not a variant.
- "Adjacent code touched" must be `none` for every variant in the initial plan. Adjacent-code edits require a re-brainstorm — see `references/04-performance-debugging.md`.
- The "winner-picked-when" rule must be measurable from `bench_results.tsv` alone. Vague rules ("V1 should feel faster") are rejected.

## Output of the phase

The plan file at `util/<TICKET>/plan.md`, reviewed and approved by the user before any code is written. The agent posts the plan inline AND saves the file — the user gets both surfaces.
