# `stock-research` skill — design

**Date:** 2026-05-11
**Status:** Brainstorm complete, ready for implementation plan
**Audience:** Future Claude / Codex agent implementing this skill, and the user (Eduard) revisiting how it was designed

---

## 1. Purpose

A skill that runs an end-to-end fundamentals-first stock research session on a US-listed company, following a long-horizon business-owner investing philosophy (Buffett / Munger / Dalio, modernized). It outputs a complete, durable thesis on disk in a separate git-versioned research repo, with both human-readable markdown and machine-readable JSON so that:

- The user can revisit any prior thesis years later and understand exactly what they thought and why.
- A sibling `stock-recap` skill (designed separately, not in this spec) can mechanically compare new quarterly results against the saved projections and sell triggers.

This skill covers the **initial deep dive** on a name. Quarterly maintenance is the `stock-recap` skill's job.

## 2. Scope and non-goals

**In scope:**
- US-listed equities only.
- Fundamentals analysis from SEC filings (deterministic) + yfinance for prices and analyst consensus + earnings call transcripts via hybrid fetch.
- Bull/Base/Bear 5-year projection modeling, GVD-tailored (growth / quality-growth / value / dividend / speculative-growth).
- A verdict with concrete buy zones, sell triggers, watch KPIs, and great-investor gate questions.
- Durable artifacts in a separate private git repo at `/Users/trocaneduard/Documents/Personal/investing-research/`.

**Out of scope (explicit):**
- Non-US listings.
- Portfolio management (position tracking, P&L) — kept in the user's broker / spreadsheet.
- Quarterly recap workflow — separate `stock-recap` skill, future design session.
- Technical analysis, options strategies, day trading, or any timing-based decisions.
- Macroeconomic regime detection beyond the user-supplied risk-on/risk-off lens.

## 3. High-level architecture

### 3.1 Skill placement

- Two physical duplicates of the skill, evolving independently to accommodate each agent's quirks:
  - `claude/skills/stock-research/` → mirrored to `~/.claude/skills/stock-research/`
  - `codex/skills/stock-research/` → mirrored to `~/.codex/skills/stock-research/`
- Sibling skill `stock-recap` will be designed and built separately, using the same artifact format on disk.

### 3.2 Two repos, two purposes

- **Skill repo (this one)** holds the skill definition + Python scripts. Versioned with the agent workflows that produced it.
- **Research repo** at `/Users/trocaneduard/Documents/Personal/investing-research/` holds investment artifacts. Separate private repo for: (a) different audience / risk profile, (b) clean diff history of the user's thinking, (c) skill changes don't pollute investment history and vice versa.

The skill **assumes the research repo exists** at the configured path. If missing, it errors with a clear message pointing to the setup procedure. No automatic bootstrap inside the skill itself — the repo will be created manually as the final step of skill creation (see §13).

## 4. Data sources

| Source | Used for | Access |
|---|---|---|
| SEC EDGAR — full-text filings | 10-K, 10-Q, 8-K, DEF 14A, S-1, Form 4 | Free HTTP, no API key |
| SEC EDGAR — XBRL company-facts API | Structured historical financials (revenue, net income, margins, cash flow, etc.) | Free HTTP, no API key |
| Earnings call transcripts | Last 3 quarters per ticker | **Hybrid**: Motley Fool scraper → IR-page fallback → manual paste fallback |
| yfinance | OHLCV + dividends + splits + analyst consensus (price targets, ratings, EPS/revenue estimates, EPS trend) | Free Python lib, no API key |

The hybrid transcript strategy degrades gracefully: scraper covers most large/mid-caps; manual paste handles the rest and is captured to disk in the same format so downstream phases don't care which path produced the transcript.

## 5. Phase topology

```
Phase 1: Identify & setup                       [main agent, sync]
   |
Phase 2: Business model + moat (with ELI5)      [subagent]
   |
   --- CHECKPOINT 1 (confirm business understanding) ---
   |
Phases 3-7: dispatched as a parallel subagent batch
   |- Phase 3: Financials (XBRL + 10-K/10-Q extracts; TTM trend gate)
   |- Phase 4: Competitors + SWOR (incl. risk-factor YoY diff;
   |              fans out one sub-subagent per competitor)
   |- Phase 5: Earnings calls — last 3
   |              (fans out one sub-subagent per quarter,
   |               then aggregator writes cross-call themes)
   |- Phase 6: Valuation (multiples + 5/10-yr P/E band + reverse DCF)
   |_ Phase 7: Market Expectations (analyst consensus — calibration input)
   |
   --- CHECKPOINT 2 (earnings call tone, direction, recent events) ---
   |
Phase 8: Bull / Base / Bear 5-yr projections    [main agent + user, heavy dialogue]
   |
   --- CHECKPOINT 3 (projection refinement) ---
   |
Phase 9: Verdict & price-action plan            [main agent + user]
   |
   --- CHECKPOINT 4 (verdict approval) ---
   |
Phase 10: Commit & index                         [main agent, sync]
```

**Subagent contract:** every subagent (and sub-subagent) writes its full artifact to the ticker folder *before returning*, and returns a tight ~500-word summary to the parent. The parent uses the summary for synthesis; full detail lives in the on-disk file. This pattern preserves context budget while keeping nothing lossy.

## 6. Phase detail

### Phase 1 — Identify & setup
- Resolve ticker → CIK (SEC mapping file), echo name + sector + market cap.
- Check whether `tickers/<TICKER>/` already exists.
  - If yes: prompt **Refresh / Archive-and-restart / Abort** (default behavior, no shortcut flag).
- Confirm with user at session start (4-item gate):
  1. Ticker (echoed with identity)
  2. **GVD lens** declared by user: `growth | quality-growth | value | dividend | speculative-growth`
  3. Session intent (fresh / refresh / archive-restart, only if folder exists)
  4. Free-form "anything you're already curious or worried about" — captured into `THESIS.md` as the session-context line for future-self
- Create skeleton `THESIS.md` and ticker dir if needed.

### Phase 2 — Business model + moat
**Single subagent.** Output: `business-and-moat.md`.

- Opens with an **ELI5 section** (explain like the reader is in 5th grade): plain-language description of every area the company operates in. No jargon.
- Then proceeds to:
  - Revenue segment breakdown (from 10-K segment reporting + 10-Q updates)
  - Geographic revenue mix
  - Recurring vs transactional revenue %
  - Customer concentration disclosure (10-K Item 1 references to >10% customers)
  - Switching costs, network effects, brand, scale evidence
  - Pricing power signals (gross margin trend, retention metrics)
  - ROIC (multi-year)
  - CEO / leadership track record (proxy disclosures, tenure, ownership, capital allocation history)
  - Insider ownership %; net insider transactions (Form 4) trailing 12 months

**Checkpoint 1** after this phase. User confirms the agent has correctly understood the business before any deep analysis fan-out.

### Phase 3 — Financials (parallel batch)
**Subagent.** Output: `financials.md` + `financials.json`.

- Pulls XBRL company-facts for the last 10 years.
- Builds TTM trends for: revenue, gross profit, operating income, net income, FCF, gross/operating/net margins, FCF margin.
- Balance sheet: cash, short-term + long-term debt, net debt, working capital.
- Cash flow: capex intensity, buybacks, dividends paid, FCF / share.
- Stock-based compensation as % of revenue (and growing dilution check).
- Shareholder yield = (buybacks + dividends + debt paydown) / market cap.
- Capital allocation scorecard: 5-yr breakdown of how management deployed FCF, with M&A track record (value created vs destroyed where assessable).
- Explicit pass/fail gate on the user's methodology: "Are revenue and net income trending up and to the right on a TTM basis?" Yes / No / Mixed, with the chart data showing the trend.

### Phase 4 — Competitors + SWOR (parallel batch)
**Orchestrator subagent + N sub-subagents (one per competitor, 3–5 names).**

The orchestrator both dispatches the sub-subagents and acts as the aggregator that writes the final artifacts after they return.

- Orchestrator identifies 3–5 direct competitors (10-K "Competition" section + sector lookup).
- Each sub-subagent pulls its competitor's financials (same XBRL pipeline) and returns a comparison-row summary; full per-competitor detail is written to `.raw/competitors/<COMPETITOR>.md`.
- Orchestrator produces the side-by-side table: revenue, growth, gross/operating/net margin, FCF margin, ROIC, P/E (TTM and fwd), market cap, dilution rate.
- Separately (still in this phase), a **risk-factor YoY diff subagent** compares the last two annual 10-K Item 1A sections (`diff_risk_factors.py`). New risks added year-over-year are the single best leading indicator that management sees trouble.
- Orchestrator writes the final `competitors.md` and `swor.md` (Strengths, Weaknesses, Opportunities, **Risks** — risks framed as "what could break the thesis," not abstract external threats).

### Phase 5 — Earnings calls — last 3 quarters (parallel batch)
**Orchestrator subagent + 3 sub-subagents (one per quarter).**

The orchestrator dispatches the per-quarter sub-subagents and, after they return, acts as the aggregator that writes the cross-call synthesis.

- Each sub-subagent runs `fetch_transcript.py` (scraper → IR-page → manual paste fallback), saves cleaned transcript to `earnings-calls/<YYYY-Qn>.md`, then drafts `earnings-calls/<YYYY-Qn>-analysis.md` covering:
  - Prepared remarks summary
  - Q&A themes
  - Forward-looking statements
  - KPI mentions and guidance
  - Tone (confidence, hedging language, defensiveness)
- Orchestrator writes `earnings-calls/cross-call-themes.md`: management's evolving narrative, dropped/added themes, guidance trajectory, tone shift across the three calls.

**Checkpoint 2** after the Phase 3–7 batch finishes. The user discusses tone, direction, and recent events with the agent before projections.

### Phase 6 — Valuation (parallel batch)
**Subagent.** Output: `valuation.md`.

- Current multiples: P/E (TTM and fwd), P/S, P/FCF, EV/EBITDA, P/B (financials only).
- 5- and 10-year P/E historical band: 25th / 50th / 75th percentile, current percentile.
- Reverse DCF (`compute_reverse_dcf.py`): given current price, what 10-year FCF growth rate is the market implying? Result is the single most powerful "is this overpriced?" check.

### Phase 7 — Market Expectations (parallel batch)
**Subagent.** Output: `market-expectations.md` + `market-expectations.json`.

- yfinance analyst consensus:
  - Number of analysts covering
  - Price targets: low / mean / high
  - Ratings distribution (Strong Buy / Buy / Hold / Sell / Strong Sell counts)
  - EPS estimates: current quarter, next quarter, current FY, next FY (consensus, high, low)
  - Revenue estimates: same horizons
  - EPS trend (rising / falling over last 90 days — leading indicator of beats/misses)
  - Recent rating changes (upgrades / downgrades trailing 90 days)
- This phase is **calibration input** for Phase 8. During projections, the agent surfaces the delta between consensus and the user's base case as an explicit prompt ("Consensus base = X; your base = Y; what do you know that they don't?").

### Phase 8 — Bull / Base / Bear 5-year projections (interactive)
**Main agent + user.** Output: `projections.md` + `projections.json`.

**Dialogue structure: base-first, then derive bull and bear by perturbation.**

1. Agent presents starting context (current revenue/margin/share count, 5-yr historical trends, peer averages, mgmt guidance, reverse-DCF implied growth, analyst consensus).
2. Agent proposes a **base-case** revenue growth path year-by-year with reasoning anchored in evidence. User debates, locks.
3. Repeat for: gross margin trajectory, operating margin trajectory, net margin trajectory, share count trajectory, dividends per share trajectory, exit P/E low / high at Y5.
4. Agent computes base-case prices and CAGRs.
5. Agent proposes a **bull case** as perturbations from base — what *credible* upsides would shift these levers? User locks.
6. Same for **bear case** — what *credible* downsides? User locks.
7. Assign **probabilities** to bull / base / bear (must sum to 100%).
8. Agent computes probability-weighted 5-yr total return CAGR.

**Full KPI set per year per scenario** (years 1-5 from session date):
- Revenue
- Revenue Growth %
- Gross Margin %
- Operating Margin %
- Net Income
- Net Income Growth %
- Net Income Margin %
- FCF
- FCF Margin %
- Shares Diluted
- EPS
- FCF per share
- Dividend per share
- Net debt
- ROIC (non-financials)
- P/E Low Estimate
- P/E High Estimate
- Share Price Low (P/E Low × EPS at year N)
- Share Price High (P/E High × EPS at year N)
- Cumulative dividends collected (running total from Y1)
- Price CAGR Low (from today's price to Y5 low)
- Price CAGR High (from today's price to Y5 high)
- Total Return CAGR Low and High (price CAGR + reinvested dividends)
- **For dividend names additionally:** payout ratio %, FCF / dividends paid coverage ratio

**Scenario-level summary KPIs:**
- Probability
- 5-yr total return CAGR low / base / high
- 5-yr cumulative dividend yield

**Cross-scenario KPIs:**
- Probability-weighted 5-yr total return CAGR
- Bear case max drawdown from today %
- Implied margin of safety today (current price vs. base-case Y1 fair-value low)

**GVD tailoring (lens applied throughout the dialogue):**

| GVD bucket | Phase 8 emphasis | Agent pushes back on |
|---|---|---|
| Growth | Revenue growth path is primary lever; margin expansion secondary | Flat-high exit P/E assumption — multiples compress as growth slows |
| Quality-growth | Margin stability + buyback-driven EPS leverage; ROIC must hold | "Margin expansion forever" — eventually saturates |
| Value | Exit P/E re-rating thesis; total shareholder yield explicit | "Re-rating happens because reasons" — must name a *catalyst* |
| Dividend | Dividend growth rate + payout safety; total return > price CAGR | Payout drifting toward 100%, FCF/dividend coverage <1.2× |
| Speculative growth | Path to profitability; burn rate; runway; dilution | None on the model side; sizing capped in Phase 9 regardless |

The agent challenges the declared GVD if data disagrees (e.g., "you said dividend, but FCF/dividend coverage is 1.05× — should we research this as a turnaround instead?").

### Phase 9 — Verdict & price-action plan (interactive)
**Main agent + user.** Output: `verdict.md` + `verdict.json`.

Structure of `verdict.md`:

1. **Classification** — `BUY | WATCH | AVOID`
2. **Conviction** — `High | Medium | Low` + 1-sentence why
3. **GVD bucket** — final (may differ from declared if Phase 8 reclassified)
4. **Time horizon** — minimum 5-year hold (per methodology)
5. **Position sizing** — target % of portfolio + scaling-in plan. Sizing framework:

   | GVD bucket + Conviction | Target % of portfolio |
   |---|---|
   | Speculative growth (unprofitable), any conviction | 1-3% (small, period) |
   | Quality / value / growth, Low conviction | 2-4% (probe size) |
   | Quality / value / growth, Medium conviction | 4-6% (normal) |
   | Quality / value / growth, High conviction | 6-9% (anchor) |
   | Dividend, Medium-High conviction | 5-8% (dividend anchor) |

   **User-specific note baked into the agent prompt: the user leans into risk when reward justifies. The agent will not be paternalistic about sizing when bull/base asymmetry is favorable — it surfaces the asymmetry and respects the user's call.**

   Scaling-in plan based on margin of safety today:
   - **MoS >25%** → full position immediately
   - **MoS 10-25%** → 1/3 now, 1/3 at -10%, 1/3 at -20%
   - **MoS <10%** → 1/4 starter, balance scaled in on -15% to -25% drawdown

6. **Buy zone** — concrete price ranges per tranche
7. **Sell triggers** — concrete, measurable, KPI-tied:
   - **Materially overvalued:** "price exceeds bull-case Y5 fair value" OR "reverse-DCF-implied growth at current price exceeds X%"
   - **Thesis broken:** 3–5 named KPI breach conditions, story-dependent. Examples: "Revenue growth <X% YoY for two consecutive quarters", "Gross margin <Y%", "NRR <Z%", "Customer concentration crosses W% from any single client". Number depends on the story.
   - **Better opportunity:** not pre-definable; framework leaves room.

   These are mechanically checked by `stock-recap` each quarter.

8. **Quarterly watch KPIs** — split into two sets:
   - **Generic GVD-default (5 KPIs)** — same set as the templates below.
   - **Story-custom (3–5 KPIs)** — brainstormed in dialogue between agent and user. Specific to the company's actual unit economics (e.g., "restaurants opened per year", "average selling price", "ARPU", "active customers", "rig count").

   Generic GVD-default templates:

   | GVD bucket | Default 5 watch KPIs |
   |---|---|
   | Growth | Revenue YoY, gross margin, FCF margin, NDR (if SaaS) / users / unit economics |
   | Quality-growth | Revenue YoY, operating margin, FCF / share, buyback yield, ROIC |
   | Value | Revenue YoY, operating margin, total shareholder yield, debt paydown, P/E vs band |
   | Dividend | Dividend per share, payout ratio, FCF / dividend coverage, dividend growth %, total return YTD |
   | Speculative | Revenue YoY, gross margin, cash burn rate, runway in months, dilution YoY |

9. **Great-investor gates** — 6 required questions, answered in prose in `verdict.md` before BUY can issue (WATCH and AVOID still answer them; only BUY blocks on completeness):
   1. **Munger inversion** — "What's the most likely way this company is worth materially less in 10 years than today?"
   2. **Buffett 10-year market closure** — "Would you be comfortable owning this if the market closed for 10 years and you couldn't trade?"
   3. **Steelmanned short case** — "What would the smartest bear argue, and why are they wrong (or right)?"
   4. **Moat trajectory** — "Is the moat widening or narrowing based on the last 3 years of evidence? Point to specific data."
   5. **Dalio regime fit** — "Risk-on or risk-off today? How does this name fit current GVD allocation and correlate with existing positions?"
   6. **Circle of competence** — "Explain in 5 sentences using first-principle business mechanics (no jargon) why this company makes more money in 10 years than today."

10. **One-page thesis** — could you defend this position in 60 seconds?

`verdict.json` carries the same data in structured form so `stock-recap` can mechanically read classification, sell triggers, watch KPIs, and projection-link IDs.

### Phase 10 — Commit & index
**Main agent, sync.** No new artifact files; updates `INDEX.md` and `tickers.json` at the repo root, then commits.

- Run `upsert_ticker.py <TICKER> --field ...` to update `tickers.json` atomically.
- Run `update_index.py` to regenerate `INDEX.md` from `tickers.json`.
- Stage all new/changed files, commit with the structured format (see §8), tag `<TICKER>/v1` for first thesis or `<TICKER>/v<N>-<reason>` for thesis pivots.
- Push to remote (if configured).

## 7. Artifact and repo structure

### 7.1 Research repo layout (`/Users/trocaneduard/Documents/Personal/investing-research/`)

```
investing-research/
  README.md                          purpose, methodology summary, how to use
  INDEX.md                           human dashboard of every ticker (auto-regen)
  tickers.json                       machine-readable mirror, source of truth
  .gitignore                         ignores **/.raw/ and OS files
  tickers/
    AAPL/
    MSFT/
    ...
  notes/                             user's cross-cutting notes (agent-readonly)
  archive/                           sold positions and abandoned theses
    README.md
```

### 7.2 Per-ticker folder layout (`tickers/<TICKER>/`)

```
tickers/AAPL/
  THESIS.md                          front-door: 1-page summary + links to deep dives
  business-and-moat.md               opens with ELI5 section
  financials.md
  financials.json
  competitors.md
  swor.md
  valuation.md
  market-expectations.md
  market-expectations.json
  projections.md
  projections.json
  verdict.md
  verdict.json
  earnings-calls/
    <YYYY-Qn>.md                     cleaned transcript per quarter
    <YYYY-Qn>-analysis.md            our notes
    cross-call-themes.md             narrative shifts across the 3 calls
  .raw/                              gitignored: raw SEC HTML, transcript HTML/PDF
```

`stock-recap` (future) will append: `recap-<YYYY-Qn>.md` per quarterly cycle, update `verdict.{md,json}`, add new earnings-call pairs.

## 8. Durability conventions (agent-retrievable formats)

### 8.1 Git commit format

Conventional-Commits-style with machine-parseable trailers:

```
<type>(<TICKER>): <subject under 70 chars>

<body — what changed and why, 1-3 short paragraphs>

ticker: <TICKER>
session: <initial-research|quarterly-recap|thesis-pivot|update|archive>
date: <YYYY-MM-DD>
trigger: <manual|10-K-<period>|10-Q-<period>|8-K-<date>|news|catalyst-event>
verdict: <BUY|WATCH|AVOID|UNCHANGED>
verdict-prior: <previous verdict, on recap/pivot only>
conviction: <high|medium|low>
gvd: <growth|quality-growth|value|dividend|speculative-growth>
price-target-low: <number>
price-target-base: <number>
price-target-high: <number>
position-target-pct: <number>
files-changed: <comma-list>
```

**Commit types:** `research` (initial deep dive), `recap` (quarterly), `pivot` (material thesis change), `update` (minor correction), `archive` (moving to archive/).

**Tags (sparingly):**
- `<TICKER>/v<N>` for major thesis versions: `AAPL/v1`, `AAPL/v2-china-decline`
- `<TICKER>/exit-<YYYY-MM-DD>` when closing position

### 8.2 File frontmatter

Every `.md` artifact opens with YAML frontmatter:

```yaml
---
ticker: AAPL
artifact: verdict
session: initial-research
date: 2026-05-11
schema_version: 1
---
```

`artifact` value is one of: `thesis | business-and-moat | financials | competitors | swor | valuation | market-expectations | projections | verdict | earnings-call | earnings-call-analysis | cross-call-themes | recap`.

JSON artifacts (`financials.json`, `market-expectations.json`, `projections.json`, `verdict.json`) carry the same metadata as top-level keys.

### 8.3 `tickers.json` schema

```json
{
  "schema_version": 1,
  "tickers": {
    "AAPL": {
      "name": "Apple Inc.",
      "sector": "Technology",
      "gvd_category": "quality-growth",
      "first_analyzed": "2026-05-11",
      "last_updated": "2026-05-11",
      "current_status": "WATCH",
      "current_conviction": "medium",
      "thesis_version": "v1",
      "price_at_last_analysis": 195.50,
      "buy_zone_low": 160,
      "buy_zone_high": 175,
      "current_target_position_pct": 5,
      "current_actual_position_pct": 0,
      "next_review_trigger": "earnings:~2026-07-31",
      "active_sell_triggers": [
        "Revenue YoY < 5% for 2 consecutive quarters",
        "Gross margin < 43%",
        "iPhone unit decline > 10% YoY"
      ]
    }
  }
}
```

`INDEX.md` is regenerated from this on every commit by `update_index.py`. Columns: Ticker | Sector | GVD | Status | Conviction | Buy Zone | Target % | Last Updated | Triggers Firing.

## 9. Scripts

All scripts live in `<skill>/scripts/`, are Python CLI tools using `argparse`, exit non-zero on failure, log to stderr, emit JSON to stdout or files to disk.

| Script | Purpose | CLI shape (approximate) |
|---|---|---|
| `fetch_sec.py` | Download raw SEC filings to `.raw/` | `fetch_sec.py <TICKER> --forms 10-K,10-Q,8-K --since 2020 --out <dir>` |
| `extract_10k_sections.py` | Parse Items 1, 1A, 7, 7A, segment, geographic from most recent 10-K | `extract_10k_sections.py <TICKER> --year <YYYY> --out <dir>` |
| `extract_10q_sections.py` | Parse MD&A + financial summary from latest 10-Q | `extract_10q_sections.py <TICKER> --quarter <YYYY-Qn> --out <dir>` |
| `fetch_transcript.py` | Earnings call transcript: scraper → IR fallback → manual paste | `fetch_transcript.py <TICKER> --quarter <YYYY-Qn> --out <dir>` |
| `fetch_prices.py` | OHLCV + dividends + splits via yfinance | `fetch_prices.py <TICKER> --years 10 --out <dir>` |
| `fetch_analyst_estimates.py` | Consensus PE/EPS/price-targets/ratings/trends via yfinance | `fetch_analyst_estimates.py <TICKER> --out <dir>` |
| `compute_financials.py` | XBRL company-facts → `financials.json` | `compute_financials.py <TICKER> --years 10 --out <dir>` |
| `compute_pe_band.py` | P/E history → 5/10-yr percentile bands | `compute_pe_band.py <TICKER> --out <dir>` |
| `compute_reverse_dcf.py` | Implied growth at current price | `compute_reverse_dcf.py <TICKER> --price <p> --discount-rate 0.10 --terminal-growth 0.025` |
| `diff_risk_factors.py` | YoY diff of 10-K Item 1A | `diff_risk_factors.py <TICKER> --year-a 2023 --year-b 2024` |
| `update_index.py` | Regenerate `INDEX.md` from `tickers.json` | `update_index.py --repo <path>` |
| `upsert_ticker.py` | Atomically update one ticker entry in `tickers.json` | `upsert_ticker.py <TICKER> --field key=value ...` |

Scripts are duplicated across both `claude/skills/stock-research/scripts/` and `codex/skills/stock-research/scripts/` as physical copies (per §3.1).

## 10. Configuration

A single config file (e.g., `<skill>/config.yaml` or env-based, decided at implementation time):

- `research_repo_path` — default `/Users/trocaneduard/Documents/Personal/investing-research`
- `transcript_source_priority` — `[motley_fool, ir_page, manual]`
- `sec_user_agent` — SEC requires a User-Agent header for EDGAR; configured here (e.g., `Eduard Trocan eduard.trocan@yesenergy.com`)
- `discount_rate` — default 0.10 for reverse DCF
- `terminal_growth_rate` — default 0.025 for reverse DCF
- `years_of_history` — default 10

The implementation plan will decide whether config is YAML, env vars, or both.

## 11. Failure modes and graceful degradation

| Failure | Behavior |
|---|---|
| SEC EDGAR rate-limits / 5xx | Retry with backoff (SEC asks 10 req/sec max); fail loudly on persistent error |
| Transcript scraper finds no match | Fall back to IR page; if that fails, prompt user to paste transcript content |
| yfinance returns empty (delisted, halted) | Phase 7 outputs "no analyst coverage available"; Phase 6 fails loudly (price history is required) |
| Ticker not found in CIK map | Phase 1 aborts with "ticker not found on EDGAR — confirm spelling" |
| Research repo missing | Skill aborts in Phase 1 with setup instructions |
| Partial subagent failure in parallel batch | Other subagents continue; main agent surfaces which artifacts are missing and asks user whether to retry the failed one or proceed without |

## 12. Open items (intentionally deferred)

- **`stock-recap` skill** — designed in a separate brainstorming session, but must read this skill's `projections.json`, `verdict.json`, and `tickers.json` as inputs. Schema versioning (`schema_version: 1` everywhere) is the contract.
- **Sector-specific KPI templates** — generic GVD templates are enough for now; sector overlays (SaaS, REIT, bank, energy E&P) can be added later as `templates/<sector>.yaml` without changing the skill structure.
- **Macro regime input** — for now the user declares risk-on / risk-off as part of the Dalio gate; automating this is a separate project.
- **Hedging assistant** — user mentioned learning to hedge as wealth grows; explicitly out of scope here.

## 13. Skill creation closing step (one-time)

After the skill files and scripts are written and tested, the final implementation step is to create the research repo manually:

1. `mkdir -p /Users/trocaneduard/Documents/Personal/investing-research`
2. `cd` in and `git init`
3. Write `README.md` (methodology summary + how to use), empty `INDEX.md` template, `tickers.json` (`{"schema_version": 1, "tickers": {}}`), `.gitignore` (ignores `**/.raw/`, OS files).
4. Initial commit: `chore: bootstrap research repo`
5. Optionally add a private GitHub remote and push.

This is done **once**, by us, at the end of skill creation — not on every skill invocation.

## 14. Implementation order (suggested input to writing-plans)

The implementation plan will be written by the `writing-plans` skill next, but for context, a reasonable build order is:

1. **Scripts first** (deterministic, testable independently): `fetch_sec.py` and `compute_financials.py` are the foundation; the rest layer on top.
2. **Per-phase prompts** (Phase 2, then 3-7 batch, then 8, then 9, then 10) — each phase has its own subagent prompt that lives in the skill.
3. **Orchestrator SKILL.md** — wires phases, checkpoints, and parallel dispatch.
4. **Frontmatter + commit-format enforcement** — utility helpers all phases share.
5. **End-to-end dry run** against a known good ticker (e.g., AAPL or MSFT) before declaring done.
6. **Bootstrap research repo** (§13).
7. **Mirror to `~/.claude/skills/` and `~/.codex/skills/`** per sync rule.

---

End of design.
