---
artifact: reference
purpose: Full KPI list + formulas for Phase 8 Bull/Base/Bear projections
schema_version: 1
---

# Projection KPIs

Phase 8 (Bull/Base/Bear projections) produces a five-year table for each scenario. Every cell below must be present in `projections.json`. Markdown view (`projections.md`) renders the same data in human-readable form, plus assumptions and reasoning.

## Per year (Y1–Y5), per scenario (bull / base / bear)

| KPI | Formula / source |
|---|---|
| `revenue` | Locked in dialogue with user — anchored in historical 5-yr trend + peer averages + mgmt guidance + analyst consensus |
| `revenue_growth_pct` | `(revenue_yN - revenue_y(N-1)) / revenue_y(N-1) * 100` |
| `gross_margin_pct` | Locked in dialogue — trajectory matters more than year 1 number |
| `operating_margin_pct` | Locked in dialogue — cleanest read on operating leverage |
| `net_income` | Locked or derived; if derived, `revenue * net_margin_pct` |
| `net_income_growth_pct` | `(net_income_yN - net_income_y(N-1)) / net_income_y(N-1) * 100` |
| `net_margin_pct` | `net_income / revenue * 100` |
| `fcf` | Locked or derived; sanity check vs net income (FCF usually ≈ net income for capital-light, lower for capex-heavy) |
| `fcf_margin_pct` | `fcf / revenue * 100` |
| `shares_diluted` | Locked — must account for SBC dilution and buybacks |
| `eps` | `net_income / shares_diluted` |
| `fcf_per_share` | `fcf / shares_diluted` |
| `dividend_per_share` | Locked (0 for non-payers) |
| `net_debt` | Optional — only model if balance sheet is a live concern |
| `roic_pct` | Optional — recommended for compounders. `nopat / invested_capital * 100` |
| `pe_low` | Locked — exit P/E low estimate at year N |
| `pe_high` | Locked — exit P/E high estimate at year N |
| `share_price_low` | `eps * pe_low` |
| `share_price_high` | `eps * pe_high` |
| `cumulative_dividends` | Running sum of `dividend_per_share` from Y1 |

## Scenario-level summary (computed at Y5)

| KPI | Formula |
|---|---|
| `probability` | Locked in dialogue (bull + base + bear = 1.0) |
| `price_cagr_low_5yr` | `((share_price_low_y5 / current_price) ^ (1/5)) - 1` |
| `price_cagr_high_5yr` | Same with `share_price_high_y5` |
| `total_return_cagr_low_5yr` | Includes reinvested dividends — `((y5_share_price_low + cumulative_dividends_y5) / current_price) ^ (1/5) - 1` |
| `total_return_cagr_high_5yr` | Same with high share price |

## Cross-scenario summary

| KPI | Formula |
|---|---|
| `probability_weighted_total_return_cagr_5yr` | `sum(scenario.probability * scenario.total_return_cagr_low_5yr` for each scenario, then same for high; report a range) |
| `bear_max_drawdown_from_today_pct` | `(bear.share_price_low_y1 / current_price) - 1` if Y1 ≤ today, otherwise the lowest Yn point on the bear curve |
| `implied_margin_of_safety_today_pct` | `(base.share_price_low_y1 / current_price) - 1` |

## Dividend-bucket additions (only for dividend GVD)

| KPI | Formula |
|---|---|
| `payout_ratio_pct` | `dividend_per_share * shares_diluted / net_income * 100` |
| `fcf_dividend_coverage` | `fcf / (dividend_per_share * shares_diluted)` |

## Dialogue flow

The orchestrator locks one row at a time, in this order:

1. Revenue growth path (Y1 → Y5) — base case first, then perturb for bull/bear
2. Gross margin trajectory
3. Operating margin trajectory
4. Net margin trajectory (or derive from above two + reasonable tax assumption)
5. Share count trajectory (SBC dilution + buybacks)
6. Dividend per share trajectory
7. Exit P/E low / high at Y5
8. Compute prices and CAGRs
9. Repeat steps 1–8 for bull (perturbation deltas from base)
10. Repeat for bear
11. Lock probabilities (bull + base + bear = 1.0)
12. Compute probability-weighted return + bear drawdown + implied margin of safety today
