---
name: stock-recap
description: "Use when recapping an existing US-listed stock thesis — catching up on every quarter (10-Q/10-K) filed since the last analysis, or analyzing the impact of a material event (M&A, CEO change, regulatory ruling, restated guidance). Triggers on phrases like \"catch me up on NVDA\", \"recap MSFT since last quarter\", \"how does this acquisition affect my AAPL thesis\", \"new earnings just dropped for TSLA\". Mechanically diffs actuals vs saved bull/base/bear projections, LLM-evaluates the saved English sell triggers in 4 states (🔴 fired / 🟡 flashing / 🟢 clear / ⚪ cannot-evaluate), and optionally proposes a surgical or reclassifying thesis update. Not for: initial deep dive on a brand-new ticker (that's stock-research), portfolio P&L tracking, short-term trading, or non-US listings."
---

# Stock Recap

A two-flow skill that keeps an existing investment thesis alive. After `stock-research` produces an initial deep dive, `stock-recap` is what you run to catch up on every 10-Q / 10-K filed since the last touch (Quarterly mode) or to analyze the impact of a material event between earnings (News mode). It mechanically diffs actuals vs the saved bull/base/bear projections, LLM-evaluates every saved English sell trigger in 4 states, and optionally proposes a surgical or reclassifying thesis update.

## When to use

- The user wants to catch up on what's happened with a ticker they already researched. Phrases: "catch me up on NVDA", "recap MSFT since last quarter", "new earnings just dropped on TSLA".
- The user wants to analyze the impact of a material event. Phrases: "how does this acquisition affect my AAPL thesis", "Microsoft just lost their CEO — recap MSFT", "the FTC ruling changes the GOOG thesis, right?".
- Explicit slash invocation: `/stock-recap <TICKER>`.

**Do not use for:**
- Initial deep dive on a brand-new ticker → that's `stock-research`. This skill aborts in Phase 1 if `verdict.json` is missing.
- Portfolio P&L tracking, position sizing math, tax-lot management.
- Technical analysis, options strategies, day trading.
- Non-US listings (the data pipeline is SEC EDGAR + yfinance, both US-focused).

## Prerequisites (one-time setup)

1. **`stock-research` has been run for this ticker.** The skill reads `tickers/<TICKER>/verdict.json`, `projections.json`, `financials.json`, and `market-expectations.json`. If any of those are missing, Phase 1 aborts with instructions to run `stock-research` first.

2. **SEC EDGAR User-Agent.** Same env var as `stock-research`:
   ```bash
   export SR_SEC_USER_AGENT="Eduard Trocan eduard.valentin1996@gmail.com"
   ```

3. **`financial-toolkit` installed in the same agent install dir.** This skill calls into the shared toolkit at:
   - Claude Code: `~/.claude/toolkits/financial-toolkit/`
   - Codex: `~/.codex/toolkits/financial-toolkit/`
   Its `.venv` must already be set up (the `stock-research` skill setup covers this; if `python3 ~/.claude/toolkits/financial-toolkit/.venv/bin/python --version` errors, follow the setup steps from the `stock-research` SKILL.md before continuing).

4. **Research repo exists.** The skill writes per-session artifacts under `/Users/trocaneduard/Documents/Personal/investing-research/tickers/<TICKER>/recaps/`. If the repo root is missing, abort with the same bootstrap instructions as `stock-research`.

## Asking the user for input

**When the workflow needs a decision among a small set of mutually exclusive options, use the runtime's native interactive-input capability rather than printing the choices as plain text and waiting for a typed reply.** Whatever the agent platform provides (Claude Code, Codex, or another runtime) — a picker, a button row, a multiple-choice modal, an `ask_user`-style tool — use that mechanism so the user picks instead of types.

Apply this at every place in the workflow where the choice space is finite and enumerable:

- **Phase 1 — mode picker:** 2 options (Quarterly catch-up / News mode).
- **Phase 1 — gap-detection result with zero new filings:** 3 options (Switch to news mode / Valuation-only recap / Exit).
- **Quarterly Checkpoint 1 — per-quarter walkthrough:** 2 options (Continue / Push back & revise).
- **Quarterly Checkpoint 2 — trajectory and sell-trigger review:** 2 options (Continue without updating / Enter Phase 6 to update).
- **Phase 6 sub-mode picker (both modes):** 3 options (Surgical patch / Reclassification / Recommend full pivot to stock-research).
- **Phase 6 Checkpoint 3 — diff-before-write approval:** 2 options (Apply / Revise further).
- **News mode Phase 2 — context fetch opt-in:** N options (one per proposed fetch, multi-select; or a 2-option Single-select if only one fetch is proposed).
- **News mode Checkpoint 1 — impact review:** 2 options (Continue without updating / Enter Phase 4 to update).
- **Phase 7/5 — push to remote:** 2 options (Push now / Skip).

**Do NOT use a picker for open-ended input.** Conversational dialogue stays as free-form text:
- Phase 1 session-context one-liner ("anything you're already curious or worried about").
- News mode event description.
- Push-back follow-ups at every checkpoint (user explains what they want changed).
- Sell-trigger sharpening dialogue when the LLM marks a trigger ⚪ cannot-evaluate.

## Plain-English voice in every output

Every section the agent prints back to the user must be **pretty-printed Markdown** (headings, tables, fenced code where appropriate — no plaintext walls). The trajectory synthesis (Phase 5) and the sell-trigger justifications must read like a plain-English explanation to a future-self who hasn't touched the thesis in 6 months. No internal abbreviations: write **Checkpoint 1/2/3**, never `CP1`; write **plain-English explanation**, never `ELI5`; write **10-Q / 10-K**, never `Qs`; write **bull case / base case / bear case**, not BBB.

---

## Mode router (Phase 1, Step 1.4)

After Phase 1's preconditions and gap-detection complete, ask the user to pick the mode using the runtime's native interactive-input:

- **Quarterly catch-up** — ingest every unprocessed 10-Q / 10-K since the last recap (or initial research), build trajectory across all of them, evaluate all sell triggers, optionally update thesis.
- **News mode** — analyze a single material event (M&A, leadership, regulatory, guidance, customer/supply, litigation, other) and its impact on the thesis.

The two flows never interleave in a single session. Once the user picks, jump to the appropriate Phase 2.

```
Quarterly mode → Phase 2 (fetch) → Phase 3 (refresh financials + valuation)
                → Phase 4 (per-quarter analysis) → Checkpoint 1
                → Phase 5 (trajectory + trigger eval) → Checkpoint 2
                → Phase 6 (update, optional) → Checkpoint 3
                → Phase 7 (commit + index)

News mode      → Phase 2 (optional context fetch)
                → Phase 3 (impact analysis) → Checkpoint 1
                → Phase 4 (update, optional) → Checkpoint 2
                → Phase 5 (commit + index)
```

## Phase 1: Identify, preconditions, gap detection

This phase runs in the main agent. No subagent dispatch.

### Step 1.1 — Resolve ticker and load saved thesis

1. The user has invoked the skill with a `<TICKER>` argument (via the slash command or by mention). Echo the ticker back in plain Markdown so any typo is caught immediately.
2. Resolve `<ticker_dir>` = `/Users/trocaneduard/Documents/Personal/investing-research/tickers/<TICKER>/` (uppercase).
3. **Hard preconditions** — abort immediately if any fail:
   - `<ticker_dir>/verdict.json` exists.
   - `<ticker_dir>/projections.json` exists.
   - `<ticker_dir>/financials.json` exists.
   - `<ticker_dir>/market-expectations.json` exists.
   - Every file above has `schema_version: 1` at top-level (read the JSON and assert).

   On any failure, abort with:

   ```
   stock-recap requires a prior stock-research session for <TICKER>. Missing: <list>.
   Run /stock-research <TICKER> first to produce the initial thesis.
   ```

4. Load the saved thesis into memory. Note: the data lives in TWO files — `verdict.json` carries the canonical structured thesis, and `tickers.json[<TICKER>]` carries a flat mirror of selected fields for index display. Load:

   **From `verdict.json` (canonical):**
   - `classification` (`BUY` / `WATCH` / `AVOID`)
   - `conviction` (`high` / `medium` / `low`)
   - `gvd_bucket` (one of `growth` / `quality-growth` / `value` / `dividend` / `speculative-growth`)
   - `position_plan` (dict: `target_position_if_buy_zones_hit_pct`, `position_now_pct`, `rationale`)
   - `buy_zones` (list of zone dicts, each with `name`, `price_range` like `"$80-$88"`, `action`)
   - `sell_triggers` (dict with three keys: `materially_overvalued` (list of strings), `thesis_broken` (list of strings), `better_opportunity` (string or null))
   - `watch_kpis` (dict with two keys: `generic` (list of strings), `story_custom` (list of strings))

   **From `tickers.json[<TICKER>]` (flat mirror for at-a-glance use):**
   - `thesis_version` (e.g., `"v1"`)
   - `last_updated` (`YYYY-MM-DD`)
   - `active_sell_triggers` (flat list — this is the user-facing summary; the canonical structured triggers live in `verdict.json.sell_triggers` above)

### Step 1.2 — Echo what's saved

Render a compact Markdown summary directly to the user. The block below is the **content template** — render only its contents, NOT the surrounding fence:

```markdown
## Saved thesis for <TICKER>

| Field | Value |
|---|---|
| Classification | <BUY / WATCH / AVOID> |
| Conviction | <high / medium / low> |
| GVD bucket | <gvd_bucket value> |
| Target position (if all buy zones hit) | <position_plan.target_position_if_buy_zones_hit_pct>% |
| Current position | <position_plan.position_now_pct>% |
| Buy zones | <comma-joined list of "<name> @ <price_range>" from buy_zones> |
| Last touched | <tickers.json[<TICKER>].last_updated> |
| Thesis version | <tickers.json[<TICKER>].thesis_version> |

Active sell triggers (from `verdict.json.sell_triggers`):

- **Materially overvalued:**
  1. <materially_overvalued[0]>
  2. <materially_overvalued[1]>
  3. ...
- **Thesis broken:**
  1. <thesis_broken[0]>
  2. <thesis_broken[1]>
  3. ...
- **Better opportunity:** <better_opportunity or "(no preset trigger)">
```

### Step 1.3 — Gap detection

Use the toolkit's SEC client to list 10-Q and 10-K filings with period-end after `financials.json`'s latest period:

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_sec.py <TICKER> \
  --forms 10-Q,10-K \
  --since <latest-period-in-financials-json> \
  --list-only \
  --out <ticker_dir>/.raw/recap-gap-detection/
```

Where `<toolkit_dir>` is `~/.claude/toolkits/financial-toolkit/` on Claude Code or `~/.codex/toolkits/financial-toolkit/` on Codex (pick by which runtime is executing).

The `--list-only` flag (already supported by `fetch_sec.py`) returns the matching filings as JSON to stdout without downloading the full filings. Parse the JSON, build a list `[("<YYYY-Qn>", "<filing-date>", "<form-type>"), ...]` sorted chronologically.

### Step 1.4 — Mode picker

Render the gap-detection result and ask the user to pick the mode via the runtime's native interactive-input.

**If new filings were detected (1 or more):**

```markdown
### Filings detected since last touch (<date>)

| Period | Filed | Form |
|---|---|---|
| 2026-Q1 | 2026-05-02 | 10-Q |
| 2026-Q2 | 2026-08-01 | 10-Q |
| ... | ... | ... |

What kind of recap do you want?
```

Native interactive-input — 2 options:
1. **Quarterly catch-up** — ingest all <N> filings above, build trajectory, evaluate all sell triggers.
2. **News mode** — ignore filings for now, analyze a specific event instead.

**If NO new filings were detected:**

```markdown
### No new 10-Q or 10-K since the last touch (<date>)

The most recent filing in `financials.json` is <YYYY-Qn>, and SEC EDGAR has no newer 10-Q or 10-K for <TICKER>.
```

Native interactive-input — 3 options:
1. **Switch to news mode** — analyze a specific event (M&A, CEO change, etc.).
2. **Valuation-only recap** — re-pull today's price, analyst consensus, P/E band, and reverse-DCF; re-evaluate sell triggers against the refreshed valuation; do not touch financials.
3. **Exit** — nothing to do right now.

### Step 1.5 — Session-context capture (free-form)

Once the mode is chosen (and is not Exit), ask the user as free-form text:

> Anything you're already curious or worried about for this recap?

Capture the answer verbatim into a session variable `session_context` (used later as the first section of the recap doc). Empty / "no" is acceptable; capture as empty string.

### Step 1.6 — Branch to the chosen mode

- **Quarterly catch-up** → proceed to Quarterly Phase 2.
- **News mode** → proceed to News Phase 1.5 (event capture, since news mode skips per-quarter fetch).
- **Valuation-only recap** → proceed to Quarterly Phase 3 (only the valuation-refresh sub-agent), skip Phases 2 and 4, then jump to Phase 5's sell-trigger evaluation (no trajectory synthesis since no new filings).

---

# Quarterly mode

The following phases apply only when the user picked **Quarterly catch-up** at Phase 1's mode picker.

## Quarterly Phase 2: Per-quarter fetch (parallel batch)

For each filing detected in Phase 1's gap-detection list, dispatch one sub-agent in parallel using `phases/quarterly/02-fetch-sub.md` as the prompt.

Inject the standard context block per sub-agent:

```
ticker: <TICKER>
quarter: <YYYY-Qn>
quarter_end_date: <YYYY-MM-DD>  # the period-end date for this quarter
form_type: <10-Q | 10-K>
ticker_dir: <absolute path>
toolkit_dir: <absolute path to financial-toolkit install for this runtime>
company_slug: <best-guess lowercase-hyphen company name>
# manual_transcript_path: only set on the re-dispatch after a transcript paste — see below
```

`quarter_end_date` comes from Phase 1's gap-detection: each entry in the SEC manifest the orchestrator built includes the `report_date` field which is exactly this date.

Issue all dispatches using the runtime's native parallelism primitive (in Claude Code: multiple Task tool calls in a single message; in Codex: a parallel-task batch). All sub-agents run concurrently.

**Failure handling once all sub-agents return:**

| Returned status | Action |
|---|---|
| All `DONE` | Proceed to Phase 3 |
| Any `DONE_WITH_CONCERNS` | Proceed; surface which quarters have missing sections in Checkpoint 1 |
| `NEEDS_CONTEXT_TRANSCRIPT` | Surface to the user via native interactive-input — 2 options per affected quarter: **Paste transcript inline** / **Skip this quarter**. On **Paste**: capture the next free-form message, write it to a temp file (e.g., via `mktemp`), and re-dispatch only the affected sub-agent with `manual_transcript_path: <temp-file-path>` added to its context block (Step 4b in the sub-agent prompt handles this). On **Skip**: drop the quarter from Phase 4's analysis fan-out; Phase 5's trajectory synthesis will mark this quarter as `data-unavailable` rather than merging it into the trend. |
| `NEEDS_CONTEXT_FILING` | Surface to the user via native interactive-input — 2 options: **Drop this quarter and continue** (Phase 5 marks it `data-unavailable`) / **Abort the recap** (something is wrong upstream — let the user re-check the gap-detection list before re-running). |

Wait for any required user input and any re-dispatches to complete before moving to Phase 3.

## Quarterly Phase 3: Refresh trailing financials + valuation (parallel batch)

Dispatch TWO sub-agents in parallel — issue both dispatches in a single message:

- `phases/quarterly/03-financials-refresh.md` with the standard context block + `new_quarters` (from Phase 2's accepted output) + `latest_period_before_recap` (read from the pre-recap `financials.json`).
- `phases/quarterly/03-valuation-refresh.md` with the standard context block + `saved_buy_zone_overall_low`, `saved_buy_zone_overall_high` (computed by the orchestrator: parse the `price_range` string of each entry in `verdict.json.buy_zones`, take `min(low)` and `max(high)`), and `saved_reverse_dcf_implied_growth` (parsed from `valuation.md` if present, else `null`).

Wait for both to return.

**Failure handling:**

| Returned status mix | Action |
|---|---|
| Both `DONE` | Proceed to Phase 4 |
| financials = `DONE_WITH_CONCERNS` (data-quality gaps) | Proceed; surface the gap list in Checkpoint 1 |
| valuation = `DONE_WITH_CONCERNS` (no analyst coverage) | Proceed; the reverse-DCF-drift auto-recommend rule is skipped in Phase 5 |
| Either `BLOCKED` | Surface to the user via native interactive-input — 2 options: **Retry** / **Abort the recap**. Phase 5 cannot run without refreshed financials and a current price. |

**Valuation-only recap branch:** if Phase 1 routed here directly (no new filings, user picked "Valuation-only recap"), only dispatch the valuation-refresh sub-agent. After it returns, skip Phase 4 and jump to Phase 5's sell-trigger evaluation; the trajectory-synthesis sub-section of Phase 5 becomes "No new filings to synthesize trajectory across — this is a price/consensus-only recap."

## Quarterly Phase 4: Per-quarter analysis fan-out (parallel)

For each quarter Phase 2 accepted (excluding any dropped via `NEEDS_CONTEXT_FILING` or `NEEDS_CONTEXT_TRANSCRIPT`), dispatch one sub-sub-agent in parallel using `phases/quarterly/04-quarter-analysis-sub.md`.

Inject the standard context block plus:

- `quarter_end_date`: from Phase 1's gap-detection list.
- `filing_path`: from Phase 2's return for this quarter.
- `transcript_path`: from Phase 2's return.
- `projection_kpis`: list of KPI keys from `projections.json.scenarios.base.years[0]`, excluding `year` (e.g., `revenue`, `revenue_growth_pct`, `gross_margin_pct`, ..., `cumulative_dividends`).
- `thesis_year_for_quarter`: 1-based integer. Compute `(quarter_end_date - thesis_creation_date) // 365 days + 1`, then clamp to `[1, len(projections.json.scenarios.base.years)]` (typically 5). Read `thesis_creation_date` from `verdict.json.date` (or, as a fallback, `tickers.json.tickers.<TICKER>.research_started`).

Issue all dispatches using the runtime's native parallelism primitive (multiple Task tool calls in one message on Claude Code; parallel-task batch on Codex).

Wait for all sub-sub-agents to return. Collect their `ACTUALS_VS_PROJECTIONS` blocks for use in Phase 5's diff table.

**Failure handling:**

| Returned status | Action |
|---|---|
| All `DONE` | Proceed to Checkpoint 1 |
| Any `DONE_WITH_CONCERNS` | Proceed; surface the affected quarters' data-quality notes in Checkpoint 1 |
| Any `NEEDS_CONTEXT` | Re-check Phase 2's outputs for that quarter (the filing or transcript path must be unreadable). If still failing, drop the quarter from the rest of the flow with a note to the user. |

## Quarterly Checkpoint 1 — Per-quarter walkthrough

This checkpoint walks the user through every newly-ingested quarter in chronological order before the orchestrator synthesizes the cross-quarter trajectory.

**Before rendering: re-read each quarter's `earnings-calls/<quarter>-analysis.md` and pull the headline numbers + tone + guidance from each return summary. Also surface any `DATA_QUALITY_GAPS` from the Phase 3 financials-refresh return.**

Format (rendered Markdown, NOT inside a code block — the fenced block below is the **content template**; render only its contents):

```markdown
## Checkpoint 1 — Quarterly walkthrough

*Per-quarter analysis files written under `<ticker_dir>/earnings-calls/`. Refreshed `financials.{md,json}` and `valuation.md` are also on disk.*

### Data quality

<If Phase 3 reported gaps: surface them here first. Example:
"⚠️ `roic_pct` is null for 2026-Q1 — the company didn't disclose it this quarter (they only report ROIC annually in the 10-K). The diff table will mark ROIC `cannot-evaluate` for this thesis-year." >

<If no gaps: write "No data-quality gaps. All projection KPIs were resolvable from the new filings.">

### Quarter-by-quarter

For each quarter <YYYY-Qn> in chronological order:

#### <YYYY-Qn> (thesis-year <N>)

| Metric | Reported | TTM | YoY |
|---|---|---|---|
| Revenue | $X.XB | $Y.YB | +X.X% |
| Operating income | ... | ... | ... |
| Net income | ... | ... | ... |
| Diluted EPS | $X.XX | $Y.YY | +X.X% |

**Tone:** <one phrase + one sentence>. **Guidance:** <raised / maintained / lowered / no-guidance + one sentence>.

**Lands closest to:** <bull / base / bear> case, because <one-sentence justification from the sub-agent's SCENARIO_LANDING>.

<Pull two or three Q&A theme bullets from the analysis file.>

<Repeat for each quarter.>

### Worth discussing

<3-5 bullets pulled across the new quarters — anything the user should weigh in on before we synthesize the trajectory. Examples:
- "2026-Q1 lands base / 2026-Q2 lands bear — the operating margin compressed 220bps QoQ. Is this a one-off or the start of a trend?"
- "Guidance was raised in Q1 and held in Q2 — management's confidence isn't slipping yet, but the actuals are."
- "Capital allocation: $4B buyback in Q2 vs $1B in Q1 — material shift. Want to discuss the timing?" >
```

**Use the runtime's native interactive-input mechanism for the Continue / Push back & revise choice** at the end of Checkpoint 1.

If the user picks "Continue" → proceed to Phase 5.
If "Push back & revise" → free-form follow-up. Corrections that change the per-quarter analysis files get re-dispatched to the affected sub-sub-agent. Then return to Checkpoint 1.

## Quarterly Phase 5: Trajectory synthesis + sell-trigger evaluation

This phase runs in the main agent (you), not a sub-agent — it's interactive synthesis.

**Read these references before starting:**
- `references/sell-trigger-evaluation.md` — 4-state rubric for evaluating English triggers.
- `references/diff-thresholds.md` — default tolerances + override-capture.
- `references/auto-recommend-rules.md` — the 6 conditions that auto-recommend a thesis update.

### Step 5.1 — Cross-quarter trajectory narrative

Re-read all per-quarter analysis files (`earnings-calls/<quarter>-analysis.md`) and the refreshed `financials.md`. Write a cross-quarter narrative arc and append it to `earnings-calls/cross-call-themes.md` (do NOT overwrite — append a new section dated with today's session date so the prior `stock-research`-written themes remain).

The narrative covers:
- Where the trajectory inflected (revenue, margins, capital allocation, tone) and what drove it.
- How management's narrative evolved across the window (themes dropped, themes added, guidance trajectory).
- One-paragraph "current state" — where the company is now vs where the thesis expected it to be.

### Step 5.2 — Render the actuals-vs-projection diff table

Use the per-quarter `ACTUALS_VS_PROJECTIONS` blocks returned by Phase 4 plus the rules in `references/diff-thresholds.md`.

Surface the defaults first, then use native interactive-input to let the user override (2 options: **Use defaults** / **Override one or more thresholds**). On override, capture into a session variable `diff_threshold_overrides` and re-tag any affected rows.

Then render — one table per scenario, columns: thesis-year, KPI, projected, actual (TTM), tag, closest-scenario:

```markdown
### Actuals vs Bull case (probability <X>%)

| Thesis-year | KPI | Projected | Actual (TTM at <latest-quarter>) | Tag | Closest |
|---|---|---|---|---|---|
| Y1 | Revenue | $X.XB | $Y.YB | on-track | base |
| Y1 | Operating margin | 24.0% | 22.4% | behind | bear |
| ... |

### Actuals vs Base case (probability <X>%)

...

### Actuals vs Bear case (probability <X>%)

...
```

### Step 5.3 — Cumulative deviation check

Compute and surface (per `diff-thresholds.md`):

```markdown
### Cumulative deviation from base (across <N> quarters)

| KPI | Σ(actual − base) | % of Σ(base) | Auto-recommend trigger fires? |
|---|---|---|---|
| Revenue | -$X.XB | -7.2% | No (within 25%) |
| Diluted EPS | -$Y.YY | -28.4% | Yes (> 25%, two consecutive quarters) |
| FCF margin | -120bps | -4.8% | No |
```

### Step 5.4 — Sell-trigger evaluation

For each trigger across all three categories in `verdict.json.sell_triggers` (`materially_overvalued`, `thesis_broken`, `better_opportunity`), apply `references/sell-trigger-evaluation.md` and render (group by category):

```markdown
### Sell triggers — current state

1. **🟢 / 🟡 / 🔴 / ⚪ <verbatim trigger string>.** <1-2 sentence justification with the specific data point and gap to threshold.>
2. ...
```

### Step 5.5 — GVD bucket fit re-check

Compare the refreshed financials against the 5 GVD bucket profiles (the same scorecard `stock-research` Phase 8 uses). Report the top 2 buckets by score:

```markdown
### GVD bucket fit

- Saved: **<saved-bucket>**
- Best fit now: **<best-bucket>** (score <X>) — <one-sentence why>
- Runner-up: **<runner-up>** (score <Y>) — <one-sentence why>
- <If best != saved>: **Drift detected** — this fires auto-recommend rule 4.
```

## Quarterly Checkpoint 2 — Trajectory & sell-trigger review

**Before rendering: assemble the full Checkpoint 2 block from §5.1–§5.5, then evaluate the auto-recommend rules (see `references/auto-recommend-rules.md`) and append the recommendation block.**

Format (rendered Markdown, NOT inside a code block):

```markdown
## Checkpoint 2 — Trajectory, diff, and triggers

### Cross-quarter trajectory

<Pull §5.1's narrative arc, 2-4 paragraphs. Use blockquotes for any verbatim management citation.>

### Actuals vs projections

<§5.2 — three diff tables (bull / base / bear).>

### Cumulative deviation

<§5.3 — the cumulative-deviation table.>

### Sell triggers

<§5.4 — one row per trigger with state + justification.>

### GVD bucket fit

<§5.5 — saved vs best-fit-now.>

---

### Auto-recommend evaluation

<Pull the recommendation block from `auto-recommend-rules.md`. Either "Recommendation: enter Phase 6 to update the thesis" with the firing rules and evidence, OR "No automatic update recommended" with the rule-by-rule clearance summary.>
```

**Use the runtime's native interactive-input mechanism** for the user's response. Options depend on the recommendation:

| Recommendation | Options |
|---|---|
| Update recommended | 1. **Enter Phase 6 to update** / 2. **Continue without updating** |
| No update recommended | 1. **Continue without updating** / 2. **Update anyway** |

If the user picks "Continue without updating" — skip Phase 6 and jump to Phase 7 with no thesis changes.
If the user picks "Enter Phase 6" or "Update anyway" — proceed to Phase 6.

## Quarterly Phase 6: Update thesis (optional)

This phase runs only if Checkpoint 2 routed here.

**Read this reference before starting:**
- `references/update-flow.md` — the three sub-modes (surgical / reclassification / pivot-to-restart) and their workflows.

### Step 6.1 — Pick sub-mode

Use native interactive-input — 3 options (per `update-flow.md`):
1. **Surgical patch**
2. **Reclassification**
3. **Recommend full pivot to `stock-research`**

If sub-mode 3 → render the recommendation, set a session variable `update_applied = "pivot-recommended"`, and jump directly to Phase 7. Skip Checkpoint 3.

### Step 6.2 — Walk the sub-mode

Follow the workflow in `update-flow.md` for the chosen sub-mode. Capture every change into staging variables; do NOT write to disk yet.

For surgical: walk each section (sell triggers, buy zone, projection levers, watch KPIs, position size) with native interactive-input (**Edit this section** / **Leave unchanged**). On "Edit," engage free-form.

For reclassification: re-walk classification, conviction, GVD bucket (if drifted), position sizing, buy zone, full sell-trigger list, full watch-KPI list. Free-form dialogue.

### Step 6.3 — Render the diff

Compose the diff-before-write block:

```markdown
## Checkpoint 3 — Diff before write

The proposed update is:

### `verdict.md` changes

```diff
- <old line>
+ <new line>
```

### `verdict.json` changes

```diff
  "sell_triggers": {
    "materially_overvalued": [...],
-   "thesis_broken": [
-     "<old trigger 1>",
-     "<old trigger 2>"
-   ],
+   "thesis_broken": [
+     "<new trigger 1>",
+     "<new trigger 2>",
+     "<new trigger 3>"
+   ],
    "better_opportunity": null
  },
```

(Note: `thesis_version` lives in `tickers.json`, not `verdict.json`. If the version bumps on reclassification, surface the tickers.json change in a separate `### tickers.json changes` block — see Phase 7 step 7.2 for the `upsert_ticker.py` invocation.)

### `projections.json` changes (if any)

<Either a unified diff of the affected projection-year cells, or "No changes to projections.json this update.">

### Summary

- Classification: <unchanged | OLD → NEW>
- Conviction: <unchanged | OLD → NEW>
- GVD bucket: <unchanged | OLD → NEW>
- Buy zone: <unchanged | $A-$B → $C-$D>
- Sell triggers: <X retained, Y replaced, Z added, W dropped>
- Watch KPIs: <unchanged | X swapped>
- Position target %: <unchanged | OLD → NEW>
- Tag bump: <yes (vN → vN+1) | no — surgical within same classification>
```

Use native interactive-input — 2 options:
1. **Apply** — write to disk, proceed to Phase 7.
2. **Revise further** — re-engage free-form dialogue on the disputed sections, then re-render Checkpoint 3.

### Step 6.4 — On Apply: write to disk

For **reclassification**:
1. Snapshot prior files to `verdict-archive/verdict-v<N>.json` and `projections-archive/projections-v<N>.json` (per `update-flow.md`).
2. Write new `verdict.{md,json}` and updated `projections.{md,json}`.
3. Set session variable `update_applied = "reclassification"` and `thesis_version_after = "v<N+1>"`.

For **surgical**:
1. Write the surgical edits in place. No archive files (git history covers it).
2. Set session variable `update_applied = "surgical"` and `thesis_version_after = "v<N>"` (unchanged).

After Step 6.4 completes, proceed to Phase 7.

## Quarterly Phase 7: Commit & index

This phase runs in the main agent, sync. It writes the recap doc, updates `tickers.json`, regenerates `INDEX.md`, commits, and optionally tags.

### Step 7.1 — Compose the recap doc

Write `<ticker_dir>/recaps/recap-<YYYY-MM-DD>-quarterly.md` (create the `recaps/` directory if it doesn't exist). Use the frontmatter + sections defined in spec §7.2:

```yaml
---
ticker: <TICKER>
artifact: recap
mode: quarterly
session: quarterly-recap
session_date: <YYYY-MM-DD>
window_start: <earliest-period-end-date-from-Phase2>
window_end: <latest-period-end-date-from-Phase2>
periods_processed: ["<YYYY-Qn>", ...]
thesis_version_before: <vN>
thesis_version_after: <vN | vN+1 if reclassification | vN if surgical>
schema_version: 1
diff_threshold_overrides: <from session if any, else omit>
---

# <TICKER> — Quarterly recap, <YYYY-MM-DD>

## Session context

<Phase 1's free-form session_context, or "(none)" if empty.>

## Quarters ingested

| Period | Filed | Form | Landed | Tone |
|---|---|---|---|---|
| <YYYY-Qn> | <filing-date> | 10-Q | base | confident |
| ... |

## Refreshed financials snapshot

<Pull the §5.1 "current state" paragraph + a compact 1-table summary of TTM revenue / margins / FCF / share count / net debt at window_end vs at the prior-recap period.>

## Trajectory synthesis

<§5.1 cross-quarter narrative arc, 2-4 paragraphs.>

## Actuals vs projections

<§5.2 — three diff tables (bull / base / bear) condensed.>

## Sell trigger evaluation

<§5.4 — one row per trigger with state + justification.>

## GVD bucket fit re-check

<§5.5.>

## Thesis update applied

<One of:
- "**None.** No thesis changes this session." (Checkpoint 2 → continue-without-updating)
- "**Surgical patch.** <list of changed fields in 3-5 bullets>. Prior verdict at git ref `<prev-commit>`." (sub-mode 1)
- "**Reclassification → <vN+1>.** <one paragraph why>. Prior thesis archived at `verdict-archive/verdict-v<N>.json` and `projections-archive/projections-v<N>.json`." (sub-mode 2)
- "**Full pivot recommended.** Business has materially changed. Recommendation: run `/stock-research <TICKER>` with the archive-and-restart option. No thesis files were modified." (sub-mode 3)
>

## Next review trigger

<today + 90 days, or earlier if the user specified during Phase 6, in the form "earnings:~<YYYY-MM-DD>" or "event:<description>">
```

### Step 7.2 — Update `tickers.json`

Run from anywhere (the `--repo` flag points at the research repo root):

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/upsert_ticker.py <TICKER> \
  --repo /Users/trocaneduard/Documents/Personal/investing-research \
  --field last_updated=<YYYY-MM-DD> \
  --field status=<verdict.classification> \
  --field classification=<verdict.classification> \
  --field conviction=<verdict.conviction> \
  --field thesis_version=<thesis_version_after> \
  --field next_review_trigger=earnings:~<YYYY-MM-DD> \
  --list-field active_sell_triggers="<flat trigger 1>" \
  --list-field active_sell_triggers="<flat trigger 2>"
  # (one --list-field per trigger; the script appends to the list,
  #  but the script's CLI accepts only "key=value" — for replace
  #  semantics, manually rewrite tickers.json[<TICKER>].active_sell_triggers
  #  before calling upsert_ticker.py, OR use --list-field for adds only.)
```

`upsert_ticker.py` requires `--repo`. Scalar fields use `--field key=value`. List fields use `--list-field key=value` (one invocation per list element). The `active_sell_triggers` flat-list mirror in `tickers.json` is built from the canonical `verdict.json.sell_triggers` dict by concatenating the strings under `materially_overvalued`, `thesis_broken`, and (if non-null) `better_opportunity` — that's what the user sees in the INDEX.md dashboard.

### Step 7.3 — Regenerate `INDEX.md`

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/update_index.py \
  --repo /Users/trocaneduard/Documents/Personal/investing-research
```

### Step 7.4 — Stage and commit

In the research repo:

```bash
cd /Users/trocaneduard/Documents/Personal/investing-research
git add tickers/<TICKER>/ tickers.json INDEX.md
```

Compose the commit message using the structured trailer format from `stock-research` Phase 10. The fields:

- `type`:
  - `recap` if `update_applied ∈ {"none", "surgical"}`.
  - `pivot` if `update_applied == "reclassification"`.
  - `update` if the only change was administrative (unlikely in this flow).
- `session`: `quarterly-recap`.
- `trigger`: `10-Q-<latest-period>` (or `10-K-<year>` if the window includes a 10-K).
- `verdict`: the (possibly updated) classification, or `UNCHANGED` if unchanged.
- `verdict-prior`: prior classification, included only if changed.
- `conviction`: current.
- `gvd`: current.
- `price-target-low` / `-base` / `-high`: from the refreshed valuation.
- `position-target-pct`: current.
- `files-changed`: comma-list.

Example commit:

```bash
git commit -m "$(cat <<'EOF'
recap(NOW): 2026-Q1+Q2 catch-up; one trigger sharpened

Two quarters since last touch. Revenue growth held above the trend
gate (+15% TTM); operating margin compressed 120bps from the buyback-
funded SBC offset narrative; one sell trigger sharpened from "Subs
NRR < 100%" to "Customer cRPO growth < 18% YoY" given mgmt no longer
discloses NRR. Verdict and classification unchanged.

ticker: NOW
session: quarterly-recap
date: 2026-08-15
trigger: 10-Q-2026-Q2
verdict: BUY
conviction: high
gvd: quality-growth
price-target-low: 850
price-target-base: 920
price-target-high: 1050
position-target-pct: 7
files-changed: tickers/NOW/financials.md, tickers/NOW/financials.json, tickers/NOW/valuation.md, tickers/NOW/market-expectations.md, tickers/NOW/market-expectations.json, tickers/NOW/earnings-calls/2026-Q1.md, tickers/NOW/earnings-calls/2026-Q1-analysis.md, tickers/NOW/earnings-calls/2026-Q2.md, tickers/NOW/earnings-calls/2026-Q2-analysis.md, tickers/NOW/earnings-calls/cross-call-themes.md, tickers/NOW/verdict.md, tickers/NOW/verdict.json, tickers/NOW/recaps/recap-2026-08-15-quarterly.md, tickers.json, INDEX.md
EOF
)"
```

### Step 7.5 — Tag on reclassification only

If `update_applied == "reclassification"`:

```bash
git tag <TICKER>/v<N+1> -m "Reclassification: <one-line reason>"
```

Otherwise: no tag.

### Step 7.6 — Push (optional)

Use native interactive-input — 2 options:
1. **Push now** (`git push --follow-tags`).
2. **Skip** (user pushes later or doesn't push at all).

### Step 7.7 — Final summary to the user

Render a closing summary in the main agent's chat:

```markdown
## Recap committed

**<TICKER> — <YYYY-MM-DD> quarterly recap**

- <N> quarter(s) integrated: <YYYY-Qn>, ...
- Verdict: <UNCHANGED at <classification> | <OLD> → <NEW>>
- Thesis version: <vN | vN → vN+1>
- Sell triggers: <X clear, Y flashing, Z fired, W cannot-evaluate>
- Next review: <next_review_trigger>

Recap doc: `tickers/<TICKER>/recaps/recap-<YYYY-MM-DD>-quarterly.md`
Commit: `<short-sha>`
Tag: <`<TICKER>/v<N+1>` | no tag this session>
```
