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
form_type: <10-Q | 10-K>
ticker_dir: <absolute path>
toolkit_dir: <absolute path to financial-toolkit install for this runtime>
company_slug: <best-guess lowercase-hyphen company name>
```

Issue all dispatches in a single message so the host agent runs them concurrently.

**Failure handling once all sub-agents return:**

| Returned status mix | Action |
|---|---|
| All `DONE` | Proceed to Phase 3 |
| 1 or more `DONE_WITH_CONCERNS` | Proceed; surface which quarters have missing sections in Checkpoint 1 |
| Any `NEEDS_CONTEXT` (transcript) | Surface to the user via native interactive-input — 2 options per affected quarter: **Paste transcript inline** (capture next free-form message as stdin and re-dispatch only that sub-agent with `--manual`) / **Skip this quarter** (drop from the per-quarter analysis fan-out in Phase 4) |
| Any `NEEDS_CONTEXT` (filing missing entirely) | Surface to the user via native interactive-input — 2 options: **Drop this quarter and continue** / **Abort the recap** |

Wait for any required user input and any re-dispatches to complete before moving to Phase 3.
