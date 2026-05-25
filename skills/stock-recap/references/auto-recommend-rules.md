---
artifact: reference
topic: auto-recommend-rules
schema_version: 1
---

# Auto-Recommend Rules — when to propose a thesis update

After Checkpoint 2 in Quarterly mode (or Checkpoint 1 in News mode), the agent decides whether to recommend entering Phase 6 to update the thesis. The user can always override either way via native interactive-input.

## Trigger conditions (any one is sufficient)

The agent **auto-recommends** a thesis update if any of the following is true after Phase 5 (Quarterly) or Phase 3 (News):

1. **Any sell trigger is 🔴 fired.** See `sell-trigger-evaluation.md` for state definitions.

2. **Two or more sell triggers are 🟡 flashing.** One 🟡 alone doesn't auto-recommend; two does.

3. **Cumulative deviation from base case > 25% on any scenario-defining KPI (revenue, EPS, FCF margin) for ≥ 2 consecutive quarters in the window.** See `diff-thresholds.md` for the cumulative-deviation formula. Quarterly mode only — news mode doesn't compute this.

4. **GVD bucket fit no longer matches the saved classification.** Concretely: the data now scores higher for a different GVD bucket than the saved one (e.g., a saved `growth` name where the last 4 quarters show ≤5% revenue YoY and the company has started raising its dividend would score higher as `dividend` than as `growth`). The agent runs a quick re-score against the 5 GVD buckets using the same scorecard `stock-research` Phase 8 uses; if a different bucket scores higher than the saved one, this rule fires.

5. **Reverse-DCF-implied growth at today's price has moved by > 50% relative to the saved one** (in either direction). If the saved value is `null` (no prior reverse-DCF saved), this rule is skipped.

6. **A capital-allocation event in the window changed the share count, debt level, or dividend policy by > 10%.** Compare share count between `latest_period_before_recap` and the latest new quarter; compare net debt the same way; compare dividend per share annualized. Any one moving >10% (in absolute terms for share count and net debt, in growth rate for dividend) fires this rule.

## Recommendation rendering

If any rule fires:

```markdown
**Recommendation: enter Phase 6 to update the thesis.**

Why:
- <Rule 1 text>: <specific evidence, e.g., "Trigger 'iPhone unit decline > 10% YoY' fired; 2026-Q2 was -12.3%.">
- <Rule 4 text>: <evidence>
```

Then native interactive-input — 2 options:
1. **Enter Phase 6 to update** (the recommended path).
2. **Continue without updating** (the user disagrees with the recommendation — they may want to wait one more quarter for confirmation).

If NO rule fires:

```markdown
**No automatic update recommended.**

All sell triggers are 🟢 clear or 🟡 flashing-but-not-elevated. Cumulative deviation from base is within ±25% on all scenario-defining KPIs. GVD bucket fit unchanged. Reverse-DCF drift within ±50%. No major capital-allocation event.
```

Then native interactive-input — 2 options:
1. **Continue without updating** (the default).
2. **Update anyway** (the user wants to make a surgical edit despite no automatic trigger).
