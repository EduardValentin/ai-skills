---
artifact: reference
purpose: How initial research defines sell triggers and recap mode evaluates them
schema_version: 1
---

# Sell Triggers

The user's methodology has three exit conditions. Initial-research verdict creation persists measurable rules for the first two and either one portfolio-level rule or `null` for the third. Recap mode evaluates the saved rules after each new quarter or material event without rewriting their thresholds or time windows.

## Sell condition 1: Materially overvalued

Pick one or both:

- **Bull-case overshoot:** "Sell if price exceeds bull-case Y5 fair value, i.e., **$X**" (use the bull case's `share_price_high_y5` from `projections.json`).
- **Reverse-DCF overshoot:** "Sell if reverse-DCF-implied growth at current price exceeds **N%**" (a number the agent picks based on what's plausible for the bucket — for a quality-growth name, ~15% might be the line; for a speculative name, ~25%).

## Sell condition 2: Thesis broken

**3–5 named KPI breach conditions**, story-dependent. The list MUST be specific, measurable, and tied to actual financials. Each trigger is a one-sentence rule that recap mode can evaluate against quarterly or event evidence.

### Good triggers (specific, measurable)

- "Revenue growth falls below 10% YoY for two consecutive quarters"
- "Gross margin compresses below 65%"
- "Net dollar retention drops below 110%"
- "Customer concentration exceeds 25% from any single client"
- "FCF/dividend coverage falls below 1.1× for two consecutive quarters" (dividend names)
- "Cash burn extends runway below 18 months without raising capital" (speculative names)
- "Capex intensity exceeds 15% of revenue for two consecutive years" (typical capital-light name turning capital-heavy)

### Bad triggers (vague, unmeasurable)

- "Sell if the moat weakens" — what does that mean numerically?
- "Sell if management makes bad decisions" — define "bad"
- "Sell if growth slows" — by how much, over what period?

## Sell condition 3: Better opportunity

This condition is portfolio-dependent. Persist one concrete comparison rule when the user defines it, for example: "Reallocate if another saved holding offers at least 30% base-case upside while this holding offers less than 10%." Persist `null` when no rule was defined.

## Recap-mode evaluation

Evaluate every populated saved trigger verbatim, including overvaluation, thesis-broken, and portfolio-level rules. Assign exactly one status:

| Status | Meaning |
|---|---|
| `fired` | Current evidence satisfies the complete saved condition, including comparison direction, duration, and consecutive-period requirements. |
| `flashing` | The full condition is not yet met, but an objective leading indicator is near the threshold, deteriorating toward it, or has completed part of a saved multi-period rule. |
| `clear` | Current, comparable evidence is sufficient and shows that the saved condition is not met or near breach. |
| `cannot-evaluate` | Required evidence is missing, stale, incomparable, or outside the available portfolio context. Missing evidence is never `clear`. |

For each rule, report the exact saved wording, status, current and comparison evidence, evidence date, and thesis implication. When `better_opportunity` is `null`, report that no portfolio-level rule is saved and do not invent a trigger or status. A fired trigger prompts a decision; it does not authorize a durable thesis edit or an automatic sale.

## Output format

In `verdict.md`, the Sell Triggers section reads:

```
## 7. Sell triggers

### Materially overvalued
- Bull-case overshoot: $X
- Reverse-DCF overshoot: implied growth > N%

### Thesis broken (any one triggers re-evaluation)
1. Revenue growth < 10% YoY for 2 consecutive quarters
2. Gross margin < 65%
3. ...
4. ...
5. ...

### Better opportunity
- <Saved portfolio-level comparison rule, or "No rule defined">
```

Persist all three conditions under `sell_triggers` in `verdict.json`:

| Field | Type | Contract |
|---|---|---|
| `materially_overvalued` | array of strings | Zero or more saved valuation rules. |
| `thesis_broken` | array of strings | Zero or more saved KPI or event rules. |
| `better_opportunity` | string or `null` | One saved portfolio-level comparison rule, or `null` when none exists. |

```json
{
  "sell_triggers": {
    "materially_overvalued": [
      "Price exceeds bull-case Y5 fair value of $200"
    ],
    "thesis_broken": [
      "Revenue growth falls below 10% YoY for two consecutive quarters"
    ],
    "better_opportunity": null
  }
}
```

In a recap, present one row per saved trigger:

```
| Saved trigger | Status | Evidence | Thesis implication |
|---|---|---|---|
| Revenue growth < 10% YoY for 2 consecutive quarters | fired | 8%, then 7% | Base-case growth assumption is breached |
```
