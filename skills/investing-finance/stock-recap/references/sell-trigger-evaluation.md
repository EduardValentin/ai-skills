---
artifact: reference
topic: sell-trigger-evaluation
schema_version: 1
---

# Sell-Trigger Evaluation Rubric

This reference is loaded by Phase 5 (Quarterly mode) and Phase 3 (News mode) to evaluate every English sell trigger saved in `verdict.json.sell_triggers`. That field is a dict with three keys — `materially_overvalued` (list of strings), `thesis_broken` (list of strings), and `better_opportunity` (string or null). The agent flattens these into a single list of trigger strings (preserving category labels so the recap doc can group them), reads each trigger string, the refreshed data, and assigns ONE of four states per trigger. The state plus a 1-2 sentence justification goes into the recap doc.

## The four states

| State | Symbol | Meaning |
|---|---|---|
| **fired** | 🔴 | The condition described by the trigger string is met **right now**. The thesis says to sell (or reduce); the agent surfaces this prominently and recommends entering Phase 6. |
| **flashing** | 🟡 | Within striking distance — one more quarter of the same trend, or one modest worsening, would fire it. Two or more 🟡 triggers auto-recommend a thesis update. |
| **clear** | 🟢 | Comfortably clear. The condition would require a meaningful shift to trigger. |
| **cannot-evaluate** | ⚪ | The data needed to evaluate this trigger is missing, OR the trigger is too ambiguous to evaluate against today's data. The agent proposes a sharper restatement and surfaces it for Phase 6 to either drop, rewrite, or keep as-is. |

## How to evaluate

For each English trigger:

1. **Parse the condition.** What's the metric, what's the threshold, what's the time window? Examples:
   - "Revenue YoY < 5% for two consecutive quarters" → metric: revenue YoY %, threshold: 5%, window: 2 consecutive quarters.
   - "Gross margin < 43%" → metric: gross margin %, threshold: 43%, window: most recent quarter.
   - "Customer concentration crosses 25% from any single client" → metric: any disclosed customer >25% of revenue, window: latest 10-K.

2. **Find the data.** Refreshed `financials.json` covers most quantitative triggers. `earnings-calls/<quarter>-analysis.md` files cover narrative triggers ("management starts hedging on cloud growth"). The 10-K's Item 1 reference to >10% customers covers concentration triggers.

3. **Assign a state.**
   - **🔴 fired** — the most recent data point clearly meets the condition AND any time-window is satisfied.
     - Example: "Revenue YoY < 5% for two consecutive quarters" with 2026-Q1 at +3.2% and 2026-Q2 at +4.1% → 🔴 fired.
   - **🟡 flashing** — the most recent data point is within ~20% of the threshold OR the time-window is partially satisfied (e.g., one of two consecutive quarters has already breached).
     - Example: same trigger, with 2026-Q1 at +4.5% but 2026-Q2 at +6.0% → 🟡 flashing (one of two quarters breached, current at +6% is within 20% relative distance of the 5% threshold). State the math.
     - Example: "Gross margin < 43%" with current at 44.0% → 🟡 flashing (within ~2 percentage points of the threshold).
   - **🟢 clear** — the data point is comfortably away from the threshold AND no part of the time-window is breached.
     - Example: same revenue trigger with 2026-Q1 at +18% and 2026-Q2 at +16% → 🟢 clear.
   - **⚪ cannot-evaluate** — write down WHY:
     - Data missing: "The 10-Q doesn't break out customer concentration; only the 10-K does. We won't know until the next 10-K filing."
     - Ambiguous trigger: "Trigger says 'gross margin trending materially lower' — 'materially' isn't defined. Propose: 'gross margin < 41% (last-known FY 43.5%) on a TTM basis'."

4. **Write the justification.** 1–2 sentences. Include the data point that drove the state. If 🟡 or 🔴, include the dollar/percentage gap so Phase 6 can sharpen the trigger if needed.

## Example output (renders into Phase 5's Checkpoint 2)

```markdown
### Sell triggers — current state

1. **🟢 Revenue YoY < 5% for two consecutive quarters.** 2026-Q1: +14.2%; 2026-Q2: +12.8%. Comfortably above threshold.
2. **🟡 Gross margin < 43%.** Current FY TTM: 43.9%. Within 90bps of the threshold; one of the last three quarters (2026-Q1) dipped to 43.1%. Worth watching closely.
3. **⚪ Customer concentration crosses 25% from any single client.** The 10-Qs in this window don't disclose customer concentration; only the 10-K does. Next disclosure expected ~2027-Q1. Propose sharpening: "On the next 10-K, any single customer >20% of revenue (currently top customer is 14% in FY2025)."
4. **🔴 iPhone unit decline > 10% YoY.** 2026-Q2 iPhone units were down 12.3% YoY (from the segment table in the 10-Q). Trigger fired. Recommend entering Phase 6 to discuss.
```

## Boundary cases

- **A trigger references a number that's reported only annually** (e.g., ROIC, customer concentration). If the recap window contains a 10-K, evaluate using its data; otherwise mark ⚪ cannot-evaluate and propose either a quarterly proxy or marking the trigger "evaluate only at year-end."
- **A trigger references qualitative tone** (e.g., "management starts hedging on cloud growth"). Read the per-quarter analysis files' "Tone" sections and look for the specific phrase or pattern. Quote the verbatim language in the justification.
- **A trigger contradicts the refreshed data in an unexpected way** (e.g., a trigger about dilution where the share count has actually been falling). Mark 🟢 but note that the trigger may be stale — surface as a candidate for Phase 6 surgical sharpening.
