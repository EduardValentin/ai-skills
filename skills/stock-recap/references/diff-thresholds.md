---
artifact: reference
topic: diff-thresholds
schema_version: 1
---

# Actuals-vs-Projection Diff Thresholds

Phase 5 (Quarterly mode) renders a diff table showing, for each thesis-year that has a corresponding filed quarter in the recap window, how the actual lands vs the bull / base / bear projection from `projections.json`. Each row gets a tag.

## Default thresholds

| KPI family | `ahead` if actual is | `behind` if actual is | `on-track` otherwise |
|---|---|---|---|
| Revenue, EPS, FCF (absolute or growth %) | > base + 10% | < base − 10% | |
| Margins (gross / operating / net / FCF / ROIC) | > base + 200 bps | < base − 200 bps | |
| Story-custom KPIs (everything else — restaurants opened, ARPU, NRR, rig count, etc.) | > base + 15% | < base − 15% | |
| Any KPI where the actual is "not reported this quarter" OR the projection is missing for the thesis-year | — | — | `cannot-evaluate` |

## Closest-scenario tag

Independently of `ahead` / `on-track` / `behind` (which compare to base), each row also gets a **closest-scenario** tag — `bull`, `base`, or `bear` — based on which projection the actual is numerically nearest to. This lets the orchestrator say things like "Revenue lands base / EPS lands bear / FCF lands bull" without overcounting the base-only tag.

## Override capture

The user may decide a default threshold is wrong for this thesis (e.g., a high-growth name where ±10% on revenue is too narrow; or a steady-state name where ±5% would be tighter). Phase 5 surfaces the defaults at the start of the diff-table section and uses native interactive-input to let the user override:

- 2 options: **Use defaults** / **Override one or more thresholds**.
- On override: the user names which KPI family and the new tolerance (free-form). The agent confirms back.

**The agreed overrides MUST be written into the recap doc's frontmatter** under a new field `diff_threshold_overrides`, so the next recap session sees the same labeling rules:

```yaml
diff_threshold_overrides:
  revenue_growth_pct: "+/- 5%"
  operating_margin_pct: "+/- 100bps"
```

If a future recap reads a prior recap's overrides, it pre-fills them as the new defaults and asks the user to confirm or change again.

## Cumulative-deviation check

In addition to the per-row tag, Phase 5 computes a **cumulative deviation from base** for each scenario-defining KPI (revenue, EPS, FCF margin) across the quarters in the recap window:

`cumulative_deviation = (Σ(actual_q - base_q) / Σ base_q) * 100`

If `|cumulative_deviation| > 25%` for ANY of those KPIs across ≥ 2 consecutive quarters, that's one of the auto-recommend triggers (see `auto-recommend-rules.md`).
