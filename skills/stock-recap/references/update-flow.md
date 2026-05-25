---
artifact: reference
topic: update-flow
schema_version: 1
---

# Thesis Update Flow

When Phase 6 (Quarterly) or Phase 4 (News) runs, the agent first asks the user which sub-mode to use via native interactive-input — 3 options:

1. **Surgical patch** (the most common path)
2. **Reclassification** (used when GVD bucket changes or classification flips)
3. **Recommend full pivot to `stock-research`** (used when the business has materially changed — different segment mix, M&A integration, restructuring)

## Sub-mode 1: Surgical patch

The user keeps the classification (`BUY` / `WATCH` / `AVOID`), conviction, and GVD bucket. They want to adjust specific fields.

Typical edits:
- Trim or sharpen one sell trigger (e.g., a ⚪ cannot-evaluate trigger gets sharpened, or a 🟡 trigger's threshold is moved closer to reality).
- Slide the buy zone up or down based on the refreshed valuation.
- Retire a sell trigger that's no longer relevant; add a new one based on a risk that emerged.
- Update one projection-year lever (e.g., revenue growth in Y2 drops from 14% to 11% given the trajectory).
- Swap one watch KPI for another that better captures the current story.
- Adjust the target position % within the same conviction tier.

Workflow:

1. Show the user the current values of the fields they're allowed to edit, one section at a time (sell triggers, buy zone, projection levers per year, watch KPIs, target position %). Use native interactive-input — 2 options per section: **Edit this section** / **Leave unchanged**.
2. On "Edit this section": engage free-form dialogue. The user describes what changes; the agent proposes specific replacement values. Agent confirms each change.
3. After all sections are walked, write the unified diff (see Checkpoint 3) and ask for final approval.
4. On approval: rewrite `verdict.{md,json}` and (if any projection lever moved) `projections.{md,json}` in place. The prior versions remain in git history; no separate archive file.

Result fields updated in `tickers.json`:
- `last_updated` → today.
- `active_sell_triggers` → new list (if changed).
- `next_review_trigger` → today + 90 days (or earlier if the user specifies).

## Sub-mode 2: Reclassification

The GVD bucket or the classification (`BUY` / `WATCH` / `AVOID`) is changing. This is more invasive.

Workflow:

1. Open the discussion with: "The data points to a different classification or GVD bucket than what's saved. Let me re-derive."
2. Re-walk the user through the affected fields:
   - **Classification** — propose the new one with evidence (e.g., "Saved was BUY at $X buy zone. Today's price is +30% above the bull-case Y5 fair value; one sell trigger has fired; cumulative deviation is -28% on EPS. Recommendation: WATCH or trim. Discuss.").
   - **Conviction** — re-rate (high / medium / low) given the new picture.
   - **GVD bucket** — if drift was detected, propose the new bucket. The user can dispute.
   - **Position sizing** — re-derive from the sizing matrix using new conviction × new bucket.
   - **Buy zone** — re-derive from the refreshed valuation and the new bull/base/bear projections (which may need surgical adjustment in this same phase).
   - **Sell triggers** — full re-walk. Replace the entire list as needed.
   - **Watch KPIs** — full re-walk if the bucket changed (different default 5 per `stock-research` Phase 9's templates).
3. **Snapshot the prior `verdict.json` and `projections.json`** to `verdict-archive/verdict-v<N>.json` and `projections-archive/projections-v<N>.json` BEFORE overwriting:
   ```bash
   mkdir -p <ticker_dir>/verdict-archive <ticker_dir>/projections-archive
   cp <ticker_dir>/verdict.json <ticker_dir>/verdict-archive/verdict-v<N>.json
   cp <ticker_dir>/projections.json <ticker_dir>/projections-archive/projections-v<N>.json
   ```
   Where `<N>` is the saved version (so the archive captures `v1` before the new `v2` is written).
4. Write the new `verdict.{md,json}` and updated `projections.{md,json}`. Set `thesis_version` in `tickers.json` to `v<N+1>`.
5. This sub-mode will be tagged `<TICKER>/v<N+1>` in Phase 7.

## Sub-mode 3: Recommend full pivot to `stock-research`

The business has materially changed. Examples:
- The company completed a transformative acquisition that fundamentally changes the segment mix.
- Spinoff or split — the parent's business is now meaningfully different.
- Major restructuring with new segments / business model.
- The original thesis's circle-of-competence reasoning no longer applies.

Workflow:

1. Explain the recommendation to the user: "The business looks materially different from the original thesis. This is bigger than a surgical patch or even a reclassification — the right move is to archive the existing thesis and run `stock-research` fresh."
2. **Do not rewrite `verdict.{md,json}` or `projections.{md,json}`.** Exit Phase 6.
3. Write the recommendation into the recap doc Phase 7 will write: "Recommendation: archive and re-run `/stock-research <TICKER>` with the 'archive-and-restart' option."
4. Phase 7 commits the recap doc with the recommendation. No tag bump.
