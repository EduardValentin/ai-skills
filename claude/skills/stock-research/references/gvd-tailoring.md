---
artifact: reference
purpose: GVD-bucket tailoring rules for Phase 7 (projections) and Phase 8 (verdict)
schema_version: 1
---

# GVD Tailoring

When the user declares the GVD lens in Phase 1, that lens shapes how Phase 8 (Bull/Base/Bear projections) and Phase 9 (Verdict) emphasize KPIs and push back on assumptions. Apply the table below at projection time, and challenge the user if the declared lens disagrees with the data the earlier phases produced.

## Bucket emphasis & pushback rules

| Bucket | Primary lever in projections | Secondary lever | Pushback the agent must apply |
|---|---|---|---|
| **Growth** | Revenue growth rate (years 1–5) | Margin expansion | Warn against flat-high exit P/E. Multiples almost always compress as growth slows. A 30%-grower today should NOT be modeled at 40× exit P/E at Y5 without an unusually strong reason. |
| **Quality-growth** | Margin stability + buyback-driven EPS leverage | Modest revenue growth | Challenge "margin expansion forever" — operating margins saturate. ROIC must hold or expand; if it's degrading, the compounder thesis is weakening. |
| **Value** | Exit P/E re-rating (multiple expansion) | Total shareholder yield (buybacks + dividends + debt paydown) | Demand a *catalyst* for the re-rating. "It's cheap" is not a thesis. What changes in the next 5 years that makes the market reassess? |
| **Dividend** | Dividend growth rate + payout safety | Total return (price CAGR + reinvested dividends) | Challenge any drift of payout ratio toward 100%. FCF/dividend coverage below 1.2× = thin. Bond-proxy names usually keep similar exit P/E. |
| **Speculative growth** | Path to profitability — when does FCF turn positive | Burn rate, runway, dilution along the way | Position sizing is capped small regardless of how good projections look (enforced in Phase 9). Model dilution explicitly. |

## When data disagrees with declared GVD

If the user declared, say, "dividend" but the data shows FCF/dividend coverage at 1.05× trending down, the orchestrator at the start of Phase 8 challenges:

> "You said dividend, but FCF/dividend coverage is 1.05× and trending down over the last 3 years. Are we researching this as a dividend anchor or as a turnaround? The lens changes the conversation."

User can confirm dividend (with the risk acknowledged), switch to another bucket, or pause to discuss.

## Position-sizing implications (covered in Phase 9, see sizing-matrix.md)

Position-sizing target % depends on bucket + conviction. The bucket emphasis above ALSO informs which "watch KPIs" we track quarterly (see `watch-kpis-by-gvd.md`).
