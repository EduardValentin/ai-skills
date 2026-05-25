# `stock-recap` skill — design

**Date:** 2026-05-12
**Status:** Brainstorm complete, ready for implementation plan
**Audience:** Future Claude / Codex agent implementing this skill, and the user (Eduard) revisiting how it was designed
**Sibling spec:** `2026-05-11-stock-research-skill-design.md` (this skill consumes its artifacts)

---

## 1. Purpose

A skill that **keeps an existing investment thesis alive**. After `stock-research` produces an initial deep dive on a US-listed name, `stock-recap` is what the user runs to:

- Catch up on every quarter (10-Q / 10-K) that has been filed since the last thesis touched the ticker, in a single guided session — not just the latest quarter in isolation.
- Diff each quarter's reported actuals against the saved Bull / Base / Bear projections to see whether the company is tracking, ahead, or behind.
- Mechanically re-evaluate every saved sell trigger in plain English (English triggers are LLM-evaluated, not regex-matched).
- Analyze the impact of a material event (M&A, CEO change, regulatory ruling, restated guidance, etc.) outside of any earnings cadence.
- Decide, jointly with the user, whether the thesis stands as-is, needs a surgical patch, or warrants a full pivot.

The user's words for the multi-quarter UX: *"I'm usually looking to see the current trajectory now but also how it came to that."* — so the skill is **trajectory-first**, not snapshot-first.

## 2. Scope and non-goals

**In scope:**
- US-listed equities only (same boundary as `stock-research`).
- Two distinct flows that share infrastructure but never run interleaved in a single session:
  - **Quarterly mode** — catch up on all unprocessed 10-Q / 10-K filings since the last recap or initial research.
  - **News mode** — analyze the impact of a single material event the user identifies.
- Mechanical comparison of actuals vs saved Bull / Base / Bear projections.
- LLM-evaluation of the verdict's saved English sell triggers (`🔴 fired` / `🟡 flashing` / `🟢 clear` / `⚪ cannot-evaluate`).
- Optional, agent-recommended thesis updates (surgical or full pivot).
- Durable per-recap artifacts inside the same `tickers/<TICKER>/` folder produced by `stock-research`.

**Out of scope (explicit):**
- Initial deep dive on a new ticker — that is `stock-research`'s job. `stock-recap` errors out if `verdict.json` is missing.
- Portfolio P&L tracking, position sizing math, tax-lot management.
- Technical analysis or timing.
- Multi-ticker batch recaps in one session (one ticker per invocation, single-flow per session).
- Sentiment scoring of news headlines from generic news APIs — the user picks the event(s) worth analyzing in news mode.

## 3. High-level architecture

### 3.1 Skill placement

- One canonical copy at `skills/stock-recap/` per the new `AGENTS.md` rule, dual-synced via `scripts/sync_skill.py` to both `~/.claude/skills/stock-recap/` and `~/.codex/skills/stock-recap/`.
- All financial/SEC tooling is reused via the shared `toolkits/financial-toolkit/` install (already on disk thanks to `stock-research`). `stock-recap` adds **zero new scripts**; if a new capability is needed, it lands in the toolkit, not in the skill.

### 3.2 Repo contract

`stock-recap` reads and writes the same research repo as `stock-research`:

```
/Users/trocaneduard/Documents/Personal/investing-research/
  tickers.json
  tickers/<TICKER>/
    THESIS.md, verdict.{md,json}, projections.{md,json},
    financials.{md,json}, valuation.md, market-expectations.{md,json},
    earnings-calls/, .raw/
```

**Inputs read** (must all exist, schema_version compatible):
- `tickers.json` (root)
- `verdict.json` — classification, conviction, GVD bucket, sell triggers, watch KPIs
- `projections.json` — bull/base/bear yearly KPI projections + scenario probabilities
- `financials.json` — historical annual + last-known-quarterly series
- `market-expectations.json` — last-known analyst consensus

**Outputs written** (per session):
- `tickers/<TICKER>/recaps/recap-<YYYY-MM-DD>-<mode>.md` — primary durable artifact (filename rationale in §7)
- Optionally, on thesis update: refreshed `verdict.{md,json}`, `projections.{md,json}`, and a new `THESIS.md` revision (`projections-archive/projections-vN.json` / `verdict-archive/verdict-vN.json` capture the prior snapshot before overwrite, so historical theses are not lost)
- Updated `tickers.json` row (last_updated, current_status, current_conviction, next_review_trigger, active_sell_triggers, thesis_version)
- A new commit (and tag, if classification changed)

### 3.3 Versioning policy

- **Auto-bump `<TICKER>/v<N+1>` tag only on classification change** (`BUY ↔ WATCH ↔ AVOID`). User confirmed: *"let's auto bump on classification change."*
- Surgical updates within the same classification (e.g., trimming one sell trigger, sliding a buy zone) commit on the existing version. They do not create a new git tag.
- Full pivots — where the user and agent agree the thesis needs to be re-derived from a much-changed business — exit `stock-recap` with a message recommending re-running `stock-research` with the `archive-and-restart` option.

## 4. Two flows

The first thing the skill does after preconditions pass is **ask the user which mode they want**: Quarterly catch-up or News mode. They never run in the same session.

### 4.1 Quarterly mode (the common path)

Catches up on **every** 10-Q / 10-K filed since the last recap (or initial research) for the ticker. If three quarters have passed since the last touch, all three are processed in one session, and the synthesis explains the trajectory across them, not just the latest one in isolation.

Topology:

```
Phase 1: Identify, preconditions, gap detection           [main agent, sync]
   |
Phase 2: Per-quarter fetch batch                          [parallel subagents,
   |                                                       one per unprocessed quarter]
   |   each subagent fetches:
   |     - 10-Q / 10-K filing (extract MD&A + financial statements)
   |     - matching earnings-call transcript
   |     - prepares per-quarter raw bundle in .raw/recap-<YYYY-Qn>/
   |
Phase 3: Refresh trailing financials + valuation          [parallel subagents]
   |   - extend financials.json with the new quarters (TTM rolled forward)
   |   - re-pull yfinance prices, analyst consensus, P/E band
   |   - reverse-DCF recomputed at today's price
   |
Phase 4: Per-quarter analysis fan-out                     [parallel sub-subagents,
   |                                                       one per quarter]
   |   each subagent writes earnings-calls/<YYYY-Qn>-analysis.md and a per-quarter
   |   actuals-vs-projection slice
   |
   --- CHECKPOINT 1 (per-quarter walkthrough) ---
   |
Phase 5: Trajectory synthesis + sell-trigger evaluation   [main agent + user]
   |   - cross-quarter narrative: where the trajectory turned
   |   - mechanical diff: actuals vs projections, by year-of-thesis
   |   - LLM-evaluation of every saved English sell trigger
   |   - GVD bucket fit re-check
   |
   --- CHECKPOINT 2 (sell-trigger and trajectory review) ---
   |
Phase 6: Update thesis (optional, agent-recommended)      [main agent + user]
   |   only entered if the agent recommends or the user requests an update
   |
   --- CHECKPOINT 3 (thesis-update approval, only if Phase 6 ran) ---
   |
Phase 7: Commit & index                                   [main agent, sync]
```

### 4.2 News mode

For a material event between earnings (M&A announcement, CEO change, regulatory ruling, restated guidance, large customer loss, lawsuit verdict, etc.).

Topology:

```
Phase 1: Identify, preconditions, event capture           [main agent, sync]
   |
Phase 2: Optional context fetch                           [subagents, opt-in]
   |   only the subset of refreshes that matter for the event:
   |     - if event affects price/sentiment → fetch_prices + analyst estimates
   |     - if event affects fundamentals     → fetch_sec (latest 8-K, etc.)
   |     - if event references competitor    → diff_risk_factors / competitor pull
   |
Phase 3: Impact analysis                                  [main agent + user]
   |   - what specifically changes in business model / moat / financials / valuation
   |   - which projection-year levers are affected and how
   |   - sell-trigger re-evaluation (only the affected ones)
   |
   --- CHECKPOINT 1 (impact review) ---
   |
Phase 4: Update thesis (optional)                         [main agent + user]
   |
   --- CHECKPOINT 2 (thesis-update approval, only if Phase 4 ran) ---
   |
Phase 5: Commit & index                                   [main agent, sync]
```

The two flows share Phase 1 preconditions, Phase 7/5 commit-and-index logic, and the same artifact format. They differ in fetch fan-out (broad quarterly vs targeted news), in synthesis emphasis (trajectory vs single-event impact), and in how many sell triggers get re-evaluated (all vs affected).

## 5. Phase detail — Quarterly mode

### Phase 1 — Identify, preconditions, gap detection
**Main agent, sync.**

1. Resolve ticker → CIK; load `verdict.json`, `projections.json`, `financials.json` from the research repo.
2. **Hard preconditions** (abort with actionable message if any fail):
   - `tickers/<TICKER>/verdict.json` exists.
   - `verdict.json.schema_version == 1` (or whatever the current shared schema is).
   - `projections.json` exists and has bull/base/bear by-year KPI tables.
3. **Gap detection** — read `financials.json` to find the latest period covered. Query SEC EDGAR for 10-Q / 10-K filings with period-end after that date. List them as `<YYYY-Qn>` and confirm with the user using the runtime's native interactive-input capability.
4. Use the same native interactive-input to pick mode (Quarterly / News). If the user picks News, jump to §6.
5. Echo to the user, in plain Markdown:
   - Current saved verdict (classification, conviction, GVD bucket, position target %)
   - Date of last recap (or initial research)
   - Quarters to be ingested in this session
   - Anything they want to flag *before* the analysis runs (free-form, captured into the recap doc as `session-context`).

### Phase 2 — Per-quarter fetch batch
**Parallel subagents, one per unprocessed quarter.**

Each sub-agent (prompt: `phases/quarterly/02-fetch-sub.md`) does, for one `<YYYY-Qn>`:

- Run `fetch_sec.py <TICKER> --forms 10-Q,10-K --since <period-start> --out tickers/<TICKER>/.raw/recap-<YYYY-Qn>/` (toolkit).
- Run `extract_10q_sections.py` or `extract_10k_sections.py` depending on filing type.
- Run `fetch_transcript.py <TICKER> --quarter <YYYY-Qn> --out tickers/<TICKER>/earnings-calls/` (toolkit). Falls back through scraper → IR → manual paste, identical to `stock-research`'s Phase 5.
- Stage every raw input into the per-quarter `.raw/` folder, write a 1-paragraph fetch-status summary, and return the file paths to the orchestrator.

Output of phase: every quarter has a `.raw/recap-<YYYY-Qn>/` populated with filing extracts + a cleaned `earnings-calls/<YYYY-Qn>.md`.

### Phase 3 — Refresh trailing financials + valuation
**Parallel subagents.**

Two parallel subagents:

- **Financials refresher** (prompt: `phases/quarterly/03-financials-refresh.md`)
  - Run `compute_financials.py <TICKER> --years <since-last-recap>` to extend the existing `financials.json` with the new quarters. The script's candidate-list us-gaap concept resolution (`tag_resolution`, `missing_concepts`) already handles XBRL tag drift across quarters; the subagent inspects them and falls back to direct company-facts JSON inspection only if metrics are missing.
  - Roll TTM forward across the new quarters; check the methodology gate (revenue + net income trending up-and-to-the-right on TTM) and flag inflection points.
  - Overwrite `financials.{md,json}` (prior snapshot kept in git history; no separate archive file).
- **Valuation refresher** (prompt: `phases/quarterly/03-valuation-refresh.md`)
  - Re-pull yfinance prices, analyst consensus (`fetch_analyst_estimates.py`), P/E historical band (`compute_pe_band.py`), and reverse DCF (`compute_reverse_dcf.py`) at today's price.
  - Update `valuation.md` and `market-expectations.{md,json}`.
  - Surface: where today's price sits in the saved buy zone, how reverse-DCF-implied growth compares to thesis assumptions, how analyst consensus moved since last recap.

These run **in parallel** with Phase 4 *only* once Phase 2's per-quarter `.raw/` bundles are on disk.

### Phase 4 — Per-quarter analysis fan-out
**Parallel sub-subagents, one per quarter.**

Each sub-subagent (prompt: `phases/quarterly/04-quarter-analysis-sub.md`):

- Reads its `.raw/recap-<YYYY-Qn>/` + the cleaned earnings-call transcript.
- Produces:
  1. `earnings-calls/<YYYY-Qn>-analysis.md` — prepared-remarks summary, Q&A themes, forward-looking statements, KPI mentions, tone (confidence / hedging / defensiveness). Identical shape to the `stock-research` Phase 5 sub-subagent output, so the cross-call themes file can be regenerated cleanly.
  2. A **per-quarter actuals slice** (passed back in the return summary, not a separate file): for each KPI tracked in `projections.json` that the filing reports on, the actual number and which scenario (bull / base / bear) it lands in for the corresponding thesis-year.

Output of phase: N new analysis files + N structured return-summaries that Phase 5 consumes.

**Checkpoint 1** — *per-quarter walkthrough.* The main agent walks the user, quarter by quarter in chronological order, through each quarter's headline numbers, tone, and which scenario it lands in. Confirms with the user before moving to synthesis. Uses the runtime's native interactive-input for the confirm step.

### Phase 5 — Trajectory synthesis + sell-trigger evaluation
**Main agent + user, interactive.**

1. **Cross-quarter trajectory** — narrative arc across the ingested quarters. Specifically: where did the trajectory inflect (margin, growth, capital allocation, tone), and what drove it. Updates `earnings-calls/cross-call-themes.md` to span the full window (initial 3 + newly added).
2. **Actuals-vs-projection diff** — single table per scenario showing, for each thesis-year that has a corresponding filed quarter, the projected KPI vs the actual TTM-equivalent. Each row tagged `ahead` / `on-track` / `behind` / `cannot-evaluate`. The diff math itself is mechanical; the labels come from default thresholds (±10% on revenue/EPS rows, ±200bps on margin rows, ±15% on everything else). The user can override any default in this step via native interactive-input; agreed overrides are saved into the recap doc so the next session sees the same labeling rules.
3. **Sell-trigger evaluation** — for each English trigger in `verdict.json.active_sell_triggers`, the LLM evaluates against the refreshed financials/valuation/transcripts and assigns one of four states (user confirmed LLM approach in Q6):
   - 🔴 **fired** — condition is met right now.
   - 🟡 **flashing** — within striking distance (one more quarter of the same trend would fire it).
   - 🟢 **clear** — comfortably clear.
   - ⚪ **cannot-evaluate** — data missing or trigger ambiguous; agent surfaces the gap and proposes a sharper restatement.
   Each trigger gets a 1-2 sentence justification with the data point.
4. **GVD bucket fit re-check** — does the data still support the saved classification (e.g., a saved `growth` name that's posted 4 quarters of <5% revenue growth might be drifting toward `value` or `dividend`)?

**Checkpoint 2** — the user reviews the trajectory narrative, the diff table, and every sell-trigger evaluation. Then, the agent decides per Q9a triggers (below) whether to **recommend** entering Phase 6, and surfaces that recommendation:

**Auto-recommend a thesis update if any of the following:**
- Any sell trigger is 🔴 fired.
- ≥2 sell triggers are 🟡 flashing.
- Cumulative deviation from base case is >25% on any scenario-defining KPI (revenue, EPS, FCF margin) for ≥2 consecutive quarters.
- GVD bucket fit no longer matches the saved classification.
- Reverse-DCF-implied growth at today's price has moved by >50% relative to the saved one (in either direction).
- A capital-allocation event in the window changed the share count, debt level, or dividend policy by >10%.

If none of those fire, the agent says explicitly: *"No automatic update recommended. Do you want to update the thesis anyway? (yes / no)"* using the runtime's native interactive-input. The user can always override and enter Phase 6.

### Phase 6 — Update thesis (optional)
**Main agent + user, interactive. Only runs if Phase 5 recommended it or the user opted in.**

Two sub-modes the user picks at the start of this phase, again via native interactive-input:

- **Surgical patch** (default for recommended updates that don't change classification)
  - Adjust the affected fields only: e.g., trim one sell trigger, slide the buy zone, retire/sharpen a 🟡 flashing trigger, update one projection-year lever, swap one watch KPI.
  - `verdict.{md,json}` and (if any projection lever moved) `projections.{md,json}` are rewritten in place. Prior versions remain in git history.
- **Reclassification** (used when GVD bucket changes or classification flips)
  - Re-derive classification, conviction, position-sizing, buy zone, full sell trigger list, full watch KPI list from the refreshed data.
  - Snapshot the prior `verdict.json` and `projections.json` to `verdict-archive/verdict-vN.json` and `projections-archive/projections-vN.json` before overwriting (cheap belt-and-suspenders on top of git for human browsing).
  - Will be tagged `<TICKER>/v<N+1>` in Phase 7.
- **Full pivot** (used when the business has materially changed — different segment mix, M&A integration, restructuring): not handled inline. The agent recommends running `stock-research` with the `archive-and-restart` flow and exits without rewriting artifacts.

**Checkpoint 3** — the user reviews the proposed surgical/reclassification edit before write. Specifically: the agent shows a unified diff of what `verdict.md` and `verdict.json` (and `projections.{md,json}` if touched) would look like before/after, and waits for confirmation via native interactive-input.

### Phase 7 — Commit & index
**Main agent, sync.** No new artifact files beyond what Phases 4–6 already wrote.

1. Write `tickers/<TICKER>/recaps/recap-<YYYY-MM-DD>-quarterly.md` — the durable session record. Sections: session-context (Phase 1 free-form), quarters processed, trajectory synthesis, actuals-vs-projection diff table, sell-trigger evaluations with states + justifications, GVD re-check, any thesis update applied (with a link to the relevant verdict version), next review trigger.
2. Run `upsert_ticker.py <TICKER> --field ...` to update the `tickers.json` row (last_updated, current_status, current_conviction, thesis_version, active_sell_triggers, next_review_trigger ≈ today + 90 days).
3. Run `update_index.py` to regenerate `INDEX.md`.
4. Stage all new/changed files. Commit with the structured format (§8). Trailers include `session: quarterly-recap`, `trigger: 10-Q-<latest-period>` (or `10-K-<period>` if the window includes one).
5. If Phase 6 ran in `reclassification` mode, tag `<TICKER>/v<N+1>`. Otherwise, no new tag.
6. Push to remote if configured.

## 6. Phase detail — News mode

### Phase 1 — Identify, preconditions, event capture
Same preconditions as Quarterly Phase 1, plus:
- Use native interactive-input to capture the event (free-form: "What's the event?") and event date.
- Classify the event with the agent (informational only — drives Phase 2 fetch fan-out): `M&A` / `leadership` / `regulatory` / `guidance-restated` / `customer-or-supply-chain` / `litigation` / `other`.

### Phase 2 — Optional context fetch
**Subagents, opt-in subset.** The agent proposes which refreshes are warranted and the user confirms via native interactive-input.

Examples:
- M&A target announced → fetch_sec on the latest 8-K, pull the target's XBRL financials if US-listed (one-shot competitor sub-flow, reusing the `stock-research` Phase 4 sub-subagent prompt).
- CEO change → no fetch needed; analysis works from saved proxy data and recent transcripts.
- Regulatory ruling → fetch latest 8-K + the relevant 10-K Item 1A risk-factor section.
- Restated guidance → fetch_prices + fetch_analyst_estimates to see how the market priced it.

### Phase 3 — Impact analysis
**Main agent + user, interactive.**

For each affected thesis layer (business model, moat, financials, projection levers, valuation), the agent walks through what changes and by how much. Specifically:
- **Business model / moat** — does this event widen, narrow, or leave the moat unchanged? Argued with reference to specific evidence.
- **Financials** — which line items will be affected over the next 4 quarters, and by what direction/magnitude.
- **Projection levers** — which of bull/base/bear's yearly KPI rows shift, and by how much. The agent proposes a delta on each affected lever and the user accepts/rejects.
- **Sell triggers** — only the triggers the event plausibly affects are re-evaluated (using the same 4-state model as Quarterly Phase 5). Others stay marked "not re-evaluated this session."

**Checkpoint 1** — user reviews the impact analysis. Then the agent applies the same auto-recommend rule (Q9a in §5) over the recomputed triggers and shifted projection levers, and surfaces whether an update is recommended.

### Phase 4 — Update thesis (optional)
Same sub-mode pattern as Quarterly Phase 6 (surgical / reclassification / pivot-recommendation). **Checkpoint 2** is identical.

### Phase 5 — Commit & index
Identical to Quarterly Phase 7 except the recap artifact is named `recap-<YYYY-MM-DD>-news.md` (filename rationale in §7) and the commit trailer carries `session: news-recap`, `trigger: 8-K-<date>` or `trigger: news` if no SEC filing.

## 7. Artifact and naming conventions

### 7.1 Recap doc filename

`tickers/<TICKER>/recaps/recap-<YYYY-MM-DD>-<mode>.md` where `<mode>` is `quarterly` or `news`. Rationale (user confirmed `Q7b. agreed with the filename recommandations`):
- Sort chronologically by default — `ls` is enough to see the history.
- Mode is in the name so a quick scan separates earnings recaps from event recaps.
- Date is the **session date**, not the latest filed period — multiple recaps in one day for the same ticker (rare but possible) need a tiebreaker, which §7.2 covers.

If a second recap on the same date is needed, append `-2`, `-3`, etc.: `recap-2026-08-15-quarterly-2.md`.

### 7.2 Recap doc structure

Every recap doc opens with YAML frontmatter (extends the `stock-research` convention):

```yaml
---
ticker: <TICKER>
artifact: recap
mode: quarterly | news
session: quarterly-recap | news-recap
session_date: 2026-08-15
window_start: 2026-05-01           # earliest period processed
window_end:   2026-07-31           # latest period processed (or event date in news mode)
periods_processed: ["2026-Q1", "2026-Q2"]   # empty for news mode
event_summary: "..."                         # news mode only
thesis_version_before: v1
thesis_version_after:  v1                    # bumps to v2 on reclassification
schema_version: 1
---
```

Body sections (quarterly):
1. **Session context** — what the user flagged in Phase 1.
2. **Quarters ingested** — table of `<YYYY-Qn>` with filing date and headline numbers.
3. **Refreshed financials snapshot** — last-known TTM revenue / margins / FCF / share count / net debt; delta vs prior recap.
4. **Trajectory synthesis** — cross-quarter narrative with named inflection points.
5. **Actuals vs projections** — diff table per scenario.
6. **Sell-trigger evaluation** — 4-state per trigger + justification.
7. **GVD bucket fit re-check.**
8. **Thesis update applied** — none / surgical / reclassification, with a link to the relevant `verdict.{md,json}` revision.
9. **Next review trigger** — date + condition.

Body sections (news):
1. **Event** — what, when, where it was disclosed.
2. **Event classification** — `M&A` / `leadership` / etc.
3. **Affected thesis layers** — business model / moat / financials / projections / valuation, each with the specific changes.
4. **Affected sell triggers** — only the re-evaluated ones.
5. **Thesis update applied** — same shape as quarterly.
6. **Next review trigger.**

### 7.3 Schema versioning

`schema_version: 1` lives on every JSON artifact and every Markdown frontmatter. The `stock-research` spec sets `1` as the initial value; this skill consumes `schema_version: 1` and writes the same. Any field addition that is backwards-compatible (new optional key) does not bump; any field removal or rename does — but no bump is planned for this design pass.

### 7.4 Commit format

Reuses the `stock-research` Conventional-Commits format with machine-parseable trailers (§8.1 of `2026-05-11-stock-research-skill-design.md`). `stock-recap` sets:

- `type` = `recap` for standard recaps, `pivot` if reclassification ran, `update` for tiny corrections that don't touch the verdict.
- `session` = `quarterly-recap` or `news-recap`.
- `trigger` = `10-Q-<YYYY-Qn>` (latest period in the window), `10-K-<YYYY>`, `8-K-<YYYY-MM-DD>`, `news`, `catalyst-event`.
- `verdict-prior` is set whenever `verdict` differs from the saved one.

## 8. Failure modes and graceful degradation

| Failure | Behavior |
|---|---|
| `verdict.json` missing for the ticker | Abort in Phase 1 with: "Run `stock-research` first to produce an initial thesis." |
| `schema_version` mismatch | Abort in Phase 1 with explicit version expected vs found and instructions to re-run `stock-research` with `archive-and-restart`. |
| Gap detection finds zero new filings (quarterly mode) | Tell the user — *"`stock-research` ran <N> days ago and no new 10-Q or 10-K has been filed since."* — and ask via native interactive-input whether they want to (a) switch to news mode, (b) re-evaluate sell triggers against today's price/valuation only (a "valuation-only recap"), or (c) exit. |
| SEC EDGAR rate-limits / 5xx during fetch | Toolkit retries with backoff (10 req/sec ceiling). On persistent failure, the per-quarter sub-agent returns a `NEEDS_CONTEXT` status; orchestrator surfaces which quarters are missing and asks whether to proceed without them or retry. |
| Transcript scraper fails for a quarter | Same fallback chain as `stock-research`: scraper → IR → manual paste. Manual-paste captures content to the same on-disk format. |
| `compute_financials.py` reports `missing_concepts` for a metric | Phase 3 financials subagent inspects the company-facts JSON directly (per the candidate-list pattern), and if still missing, marks that KPI `cannot-evaluate` in the diff table. The sell-trigger evaluator does the same. |
| yfinance returns empty (delisted / halted) | Phase 3 valuation refresher fails loudly. Phase 5 still runs but reverse-DCF-implied growth is omitted; the auto-recommend rule based on reverse-DCF drift is skipped. |
| User declines to confirm a checkpoint | Skill exits cleanly without committing. Any partial files in `.raw/` remain on disk (gitignored). User can resume later by re-running the skill — the gap-detection in Phase 1 will pick up where they left off. |
| Phase 6 thesis update interrupted (user aborts mid-edit) | Same as above: nothing is written to `verdict.{md,json}` or `projections.{md,json}` until Checkpoint 3 approval. |
| News mode with no pre-existing `verdict.json` | Same as the first row — abort. |

## 9. Inheritance from `stock-research`

This skill follows every convention established by `stock-research`. Concretely:

- **Markdown formatting** — every section the agent prints to the user is pretty-printed Markdown (headings, tables, fenced code where appropriate). No plaintext walls.
- **Native interactive-input** — every user choice uses the runtime's native interactive-input capability (Codex's picker, Claude Code's interactive forms). No "type 1/2/3" plaintext menus.
- **No abbreviations** — `Checkpoint 1/2/3`, not `CP1`; "plain-English explanation," not "ELI5"; "10-Q / 10-K," not "Qs."
- **Plain-English voice in summaries** — the trajectory synthesis and the sell-trigger justifications are written for a future-self who hasn't touched the thesis in 6 months. No internal jargon; if a metric needs context, the agent gives it.
- **Subagent contract** — every subagent writes its full artifact to disk before returning, and returns a tight ~500-word structured summary the parent uses for synthesis.
- **No new scripts in the skill itself** — anything programmatic is in `toolkits/financial-toolkit/`. If a need arises (e.g., a `diff_actuals_vs_projections.py`), it ships into the toolkit and `stock-recap` calls it.
- **Configuration** — same `SR_SEC_USER_AGENT` env var (set permanently in zsh rc to `Eduard Trocan eduard.valentin1996@gmail.com`), same research-repo path default, same SEC retry/backoff posture.
- **Canonical-copy + dual-sync** — `skills/stock-recap/` is the source of truth; `scripts/sync_skill.py push stock-recap` mirrors to both install dirs.

## 10. Open items (intentionally deferred)

- **Multi-ticker batch recap** — running `stock-recap` over every ticker in `tickers.json` whose `next_review_trigger` has passed. Out of scope for this design; would be a thin orchestrator on top.
- **Macro/sector overlay during impact analysis** — Phase 3 (news) currently treats the event in isolation. A macro-aware overlay (e.g., "is this regulatory event sector-wide or ticker-specific?") is a future iteration.
- **Automated next-event watch** — the skill sets `next_review_trigger` but doesn't schedule anything. A cron-driven reminder is a separate project.
- **Hedging recommendation when sell triggers flash** — the user has mentioned learning to hedge. Out of scope here; could be added as an opt-in Phase 5b later.
- **Sector-specific KPI templates** — same deferral as `stock-research`. Story-custom KPIs continue to be brainstormed in dialogue.

## 11. Implementation order (suggested input to `writing-plans`)

The plan will be authored next by `writing-plans`, but for context, a reasonable build order:

1. **Skill skeleton** — `skills/stock-recap/SKILL.md`, `commands/stock-recap.md`, `agents/openai.yaml`, `phases/` subdir scaffolding, frontmatter discipline (description double-quoted because it will contain colons).
2. **Phase 1 (both modes)** — preconditions, gap detection, mode picker, session-context capture. Validate by stubbing the rest and running against a real ticker with an existing `verdict.json`.
3. **Quarterly Phase 2 + 3 + 4** — subagent prompts that wrap toolkit scripts. Each can be unit-tested by mocking the toolkit calls and asserting the subagent's return shape.
4. **Quarterly Phase 5 — trajectory + sell-trigger evaluation** — the LLM-evaluation harness for English triggers. Behavioral tests under `tests/skill-trigger/` for at least one ticker's recap window.
5. **Phase 6 — surgical / reclassification update** — diff-before-write UX, snapshot-on-reclassification.
6. **Phase 7 commit + index** — reuse `upsert_ticker.py` and `update_index.py` from the toolkit; add the auto-tagging-on-classification-change logic.
7. **News mode** — Phases 1/2/3/4/5 reusing the quarterly bits where applicable.
8. **End-to-end dry runs** — at minimum, a quarterly recap against a saved ServiceNow (NOW) thesis covering 1 new quarter, and a news recap simulating a CEO change.
9. **Trigger-test scenarios** — add `stock-recap-quarterly` and `stock-recap-news` rows to `tests/skill-trigger/scenarios.toml` so the static contract test covers both flows.
10. **Dual-sync** — `scripts/sync_skill.py push stock-recap` to mirror to both install dirs.

---

End of design.
