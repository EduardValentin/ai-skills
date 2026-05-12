---
artifact: reference
purpose: Position-sizing rules for Phase 9 verdict (target % + scaling-in plan)
schema_version: 1
---

# Position-Sizing Matrix

Used in Phase 9 to recommend target % of portfolio and a scaling-in plan. **The user leans into risk when reward justifies — the agent will not be paternalistic about sizing when bull/base asymmetry is favorable.** Surface the asymmetry; respect the user's call within the matrix.

## Target % of portfolio

| GVD bucket + Conviction | Target % |
|---|---|
| Speculative growth (unprofitable), any conviction | 1–3% (small, period — sizing cap enforced regardless of how good projections look) |
| Quality / value / growth, Low conviction | 2–4% (probe size) |
| Quality / value / growth, Medium conviction | 4–6% (normal) |
| Quality / value / growth, High conviction | 6–9% (anchor) |
| Dividend, Medium-High conviction | 5–8% (dividend anchor) |

When the bull/base asymmetry is favorable (e.g., bear case downside <20% but bull case upside >100%), the agent surfaces this and may recommend the top end of the conviction range rather than the middle. It does not unilaterally exceed the range.

## Scaling-in plan (depends on margin of safety today)

`Margin of safety today` = `(base.share_price_low_y1 / current_price) - 1`, computed in Phase 8.

| Margin of safety today | Scaling-in plan |
|---|---|
| **>25%** | Deploy full target position immediately |
| **10–25%** | 1/3 of target now, 1/3 at -10% drawdown, 1/3 at -20% drawdown |
| **<10%** | 1/4 starter, balance scaled in on -15% to -25% drawdown |
| **negative** (current price > base Y1 fair value low) | Watch only — no position until price corrects into buy zone |

## Buy zone

The verdict records concrete price ranges per tranche, e.g.:

```
buy_zone:
  tranche_1: $160-$175 (1/3 of target)
  tranche_2: $144-$158 (1/3 of target, on -10% from current)
  tranche_3: $128-$140 (1/3 of target, on -20% from current)
```
