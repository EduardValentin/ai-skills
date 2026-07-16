---
artifact: reference
topic: investment-classification-contracts
schema_version: 1
---

# Investment Classification Contracts

These local contracts make recap classification and KPI selection independent of another skill's workflow text.

## GVD bucket scorecard

Score every bucket from 0 to 2 on each applicable dimension: `0` contradicts the profile, `1` is mixed or inconclusive, and `2` strongly fits. Use current filings and refreshed financials, cite at least one concrete fact for every nonzero score, sum to a maximum of 10, and report the top two. Do not change the saved bucket on a tie; present the tie for user judgment.

| Bucket | Business stage and growth | Quality and cash generation | Valuation or income | Capital allocation and risk | Distinguishing evidence |
| --- | --- | --- | --- | --- | --- |
| `growth` | Sustained above-market revenue and EPS growth | Improving operating leverage or a credible path to it | Valuation supported by continued growth | Reinvestment has attractive incremental returns | Growth is broad, durable, and not mainly acquisition-funded |
| `quality-growth` | Durable moderate-to-high organic growth | Strong margins, return on invested capital, and free-cash-flow conversion | Premium supported by consistency | Conservative balance sheet and disciplined reinvestment | Resilience and repeatability matter as much as headline growth |
| `value` | Stable or recoverable earnings rather than required high growth | Positive normalized free cash flow | Discount to normalized earnings, assets, or conservative DCF | Credible catalyst, deleveraging, or accretive repurchases | The discount survives normalized rather than peak assumptions |
| `dividend` | Stable earnings and cash flow | Dividend covered by free cash flow | Sustainable current income plus plausible dividend growth | Manageable leverage and no recurring dilution funding the payout | Payout safety and growth are supported through a down cycle |
| `speculative-growth` | Early-stage or unusually rapid growth | Weak, volatile, or not-yet-proven cash generation | Valuation depends on distant outcomes | Runway, dilution, execution, and financing risk are material | Milestone delivery and unit economics dominate current earnings |

Use five scored dimensions per bucket: growth profile, profitability/cash conversion, balance-sheet resilience, valuation/income support, and capital-allocation/execution quality. When a table cell spans multiple concepts, explain which concept determined the score.

## Watch KPI defaults

Select five company-specific KPIs, starting from the saved list when it remains relevant. When the bucket changes, use the matching defaults below and replace generic items with disclosed story-specific measures where possible.

| Bucket | Five defaults |
| --- | --- |
| `growth` | Organic revenue growth; customer or recurring-revenue growth; gross margin; operating leverage; free-cash-flow conversion |
| `quality-growth` | Organic revenue growth; retention or recurring-revenue durability; operating margin; return on invested capital; free-cash-flow margin |
| `value` | Normalized EPS or free cash flow; net debt; catalyst milestones; share-count change; normalized valuation multiple |
| `dividend` | Dividend per share; free-cash-flow payout ratio; interest coverage; net leverage; earnings stability |
| `speculative-growth` | Cash runway; dilution; unit economics; bookings or pipeline; product/regulatory milestone delivery |

Every selected KPI must state its source, direction that supports the thesis, and threshold or trend that would challenge it. If the company does not disclose a default KPI, substitute a measurable proxy and record the limitation.
