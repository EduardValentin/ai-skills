---
artifact: reference
purpose: Default quarterly watch-KPI lists per GVD bucket (Phase 9 verdict)
schema_version: 1
---

# Quarterly Watch KPIs

Each verdict carries a watchlist of KPIs the future `stock-recap` skill checks every quarter. The verdict has **two sets**:

- **Generic GVD-default set (5 KPIs)** — taken directly from the table below based on the declared bucket.
- **Story-custom set (3–5 KPIs)** — brainstormed with the user during Phase 9 because every company has unit economics that matter specifically to it ("restaurants opened per year", "average selling price", "rig count", "ARPU", "active customers").

## Generic defaults by bucket

| Bucket | 5 default watch KPIs |
|---|---|
| **Growth** | Revenue YoY, gross margin, FCF margin, NDR (if SaaS) or active users, unit economics (CAC, payback period) |
| **Quality-growth** | Revenue YoY, operating margin, FCF / share, buyback yield, ROIC |
| **Value** | Revenue YoY, operating margin, total shareholder yield, debt paydown, P/E vs historical band |
| **Dividend** | Dividend per share, payout ratio, FCF / dividend coverage, dividend growth %, total return YTD |
| **Speculative growth** | Revenue YoY, gross margin, cash burn rate, runway in months, dilution YoY |

## Story-custom set: dialogue

In Phase 9, after presenting the generic defaults, the orchestrator asks:

> "Beyond the generic GVD watch list, what 3–5 KPIs specific to *this* business should we track each quarter? Think about what would tell you the thesis is on track or breaking down."

Examples by industry:

- **Restaurant chains:** new restaurants opened YoY, same-store sales growth, food cost % of revenue
- **SaaS:** logo count, NDR by cohort, ARR growth, free-to-paid conversion
- **Energy E&P:** average realized price, production growth, F&D cost per BOE, debt/EBITDAX
- **Banks:** net interest margin, efficiency ratio, NCO rate, CET1 ratio
- **Retail/consumer:** comp sales, average selling price, inventory turns, gross margin
- **Auto:** unit volume, ASP, gross margin per vehicle, capex intensity
- **Semiconductors:** revenue mix by end market, gross margin trend, capex/revenue, customer concentration

The story-custom KPIs are written in plain English (same shape as the generic ones) and stored in `verdict.json` under `watch_kpis.story_custom` (array of strings).

## Output format

In `verdict.md`, the Quarterly Watch KPIs section reads:

```
## 8. Quarterly watch KPIs

### Generic (GVD-default for this bucket)
1. Revenue YoY
2. Gross margin
3. ...

### Story-custom
1. <Custom KPI 1>
2. <Custom KPI 2>
...
```

In `verdict.json`, both lists live under `watch_kpis.generic` and `watch_kpis.story_custom`.
