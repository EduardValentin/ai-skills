---
name: stock-research
description: "Use when researching a US-listed company end-to-end — fundamentals deep dive, building or refreshing an investment thesis, evaluating whether to buy/watch/avoid at the current price. Triggers on phrases like \"research AAPL\", \"deep dive on Microsoft\", \"should I buy NVDA\", \"analyze TSLA's fundamentals\". Long-running session (1–2 hours) producing durable artifacts in a separate git-versioned research repo. Not for: short-term trading, technical analysis, options strategies, or stock-recap (quarterly update of an existing thesis — that's a separate skill)."
---

# Stock Research

End-to-end fundamentals research on a US-listed company, following a long-horizon, business-owner investing philosophy (Buffett/Munger/Dalio, modernized). Produces a durable thesis on disk that the user revisits over years and that the future `stock-recap` skill can mechanically diff against new quarterly results.

## When to use

- The user wants an investment thesis on a specific US-listed ticker
- Phrases like "research X", "deep dive on Y", "should I buy Z", "analyze Q's fundamentals"
- Explicit slash invocation: `/stock-research <TICKER>`

**Do not use for:**
- Quarterly updates of an existing thesis → that's `stock-recap` (separate skill, not yet built)
- Technical analysis, options strategies, day trading
- Non-US listings (the data pipeline is SEC EDGAR + yfinance, both US-focused)

## Prerequisites (one-time setup)

1. **SEC EDGAR User-Agent.** Add to your shell rc:
   ```bash
   export SR_SEC_USER_AGENT="Eduard Trocan eduard.valentin1996@gmail.com"
   ```
   SEC EDGAR rejects requests without a proper User-Agent.

2. **`financial-toolkit` installed in the same agent install dir.** The shared toolkit (12 Python CLIs + 5 utilities for SEC filings, prices, transcripts, financials, valuation math) is *not* part of this skill — it lives under `toolkits/financial-toolkit/` in the source repo and gets installed alongside the skill. Its install path depends on which agent installed it:
   - Claude Code: `~/.claude/toolkits/financial-toolkit/`
   - Codex: `~/.codex/toolkits/financial-toolkit/`

   The toolkit needs a Python venv with all its dependencies. In whichever install dir applies, run:

   ```bash
   cd <toolkit-install-dir>
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

   The `stock-recap` skill (sibling of this one) also depends on the same toolkit.

3. **Research repo exists.** The skill writes artifacts to `/Users/trocaneduard/Documents/Personal/investing-research/`. If this directory doesn't exist, abort with the bootstrap instructions (see "Recovery" below).

## Asking the user for input

**When the workflow needs a decision among a small set of mutually exclusive options, use the runtime's native interactive-input capability rather than printing the choices as plain text and waiting for a typed reply.** Whatever the agent platform provides (Claude Code, Codex, or another runtime) for surfacing structured prompts to the user — a picker, a button row, a multiple-choice modal, an `ask_user`-style tool, etc. — use that mechanism so the user can pick instead of type.

Apply this at every place in the workflow where the choice space is finite and enumerable:

- **Phase 1 — existing-folder gate:** 3 options (Refresh / Archive & restart / Abort)
- **Phase 1 — GVD lens:** 5 options (growth / quality-growth / value / dividend / speculative-growth)
- **Phases 3–7 batch — per-failed-phase recovery:** 3 options (Retry / Skip & continue / Abort)
- **Phase 5 transcript fallback:** 2 options (Paste transcript inline / Skip this quarter)
- **Each checkpoint (Checkpoint 1, 2, 3, 4, and 5):** 2 options (Continue / Push back & revise) — when the user pushes back, the follow-up is free-form, not a picker
- **Phase 10 — push to remote:** 2 options (Push now / Skip)

**Do NOT use a picker for open-ended input.** Conversational dialogue stays as free-form text:
- Phase 1 session-context one-liner
- The projection brainstorm in Phase 8 (locking revenue/margin/share-count/P-E rows is a numeric negotiation, not a multiple-choice)
- Drafting story-specific sell triggers and watch KPIs in Phase 9
- Any "push back" or "discussion" follow-up after a checkpoint

If the runtime doesn't offer a structured-input mechanism (or you're unsure), fall back to clearly enumerated plain text — but try the native mechanism first.

## Output formatting

**Everything you print back to the user — checkpoint summaries, phase status messages, the projection brainstorm, the verdict review, the completion confirmation — must be rendered as well-structured Markdown.** The user sees these in a chat UI that renders Markdown; raw text or ASCII-art separators look ugly and waste cognitive load.

Apply these rules to every chat output:

- **Section headings:** Use `##` for top-level sections (e.g., `## Checkpoint 1 — Business Model & Moat`), `###` for subsections (e.g., `### Explain like I'm in 5th grade`). **Never** use `=== ... ===` ASCII separators.
- **File paths, ticker symbols, code, env vars:** Wrap in backticks (`` `<ticker_dir>/business-and-moat.md` ``, `` `AAPL` ``, `` `SR_SEC_USER_AGENT` ``).
- **Lists:** Use numbered lists for sequenced prompts, bullet lists for enumerations. Indent nested items with 2 spaces.
- **Tables:** Use Markdown tables for any comparison of >2 fields (projection scenarios, verdict summary, ratings distribution). Header row + separator row.
- **Emphasis:** `**bold**` for labels and load-bearing terms (e.g., **Verdict:**, **Buy zone:**). `*italic*` sparingly, for meta-info like "*Drafted at `path`*".
- **Blockquotes:** Use `>` for content quoted verbatim from artifact files (especially the plain-English explanation paragraph pasted into Checkpoint 1) and for any prompt you're posing to the user.
- **Currency & numbers:** Format consistently — `$391.0B`, `$195.50`, `46.2%`, `+5%`. Never raw scientific notation in chat (`391035000000` is unreadable; `$391.0B` is fine).
- **Status indicators:** Use emoji sparingly but meaningfully when status is binary — ✅ for pass, ⚠️ for warning, ❌ for fail, ⬆ / ⬇ / ↔ for trend direction.
- **Code blocks:** Triple-backtick blocks for any shell command shown to the user. Specify the language (` ```bash`, ` ```json`).

For artifact files (the on-disk `.md` outputs), the same Markdown discipline applies — frontmatter at the top, then well-structured Markdown body. Subagents already follow this in their phase prompts.

## Workflow overview

Ten phases, five user checkpoints:

```
Phase 1: Setup & identity                   [main agent + user]
   |
Phase 2: Business model + moat              [subagent: phases/02-business-model.md]
   |
   --- CHECKPOINT 1: confirm business understanding ---
   |
Phase 3: Financials                         [subagent: phases/03-financials.md]
   |
   --- CHECKPOINT 2: discuss Income / Balance / Cash Flow + capital allocation ---
   |
Phases 4–7: parallel batch
   ├── Phase 4: Competitors + SWOR          [subagent: phases/04-competitors-swor.md
   │                                                   + sub-subagent per competitor]
   ├── Phase 5: Earnings calls (last 3)     [subagent: phases/05-earnings-calls.md
   │                                                   + sub-subagent per quarter]
   ├── Phase 6: Valuation                   [subagent: phases/06-valuation.md]
   └── Phase 7: Market expectations         [subagent: phases/07-market-expectations.md]
   |
   --- CHECKPOINT 3: discuss tone, direction, recent events from the calls ---
   |
Phase 8: Bull/Base/Bear projections          [main agent + user, interactive brainstorm]
   |
   --- CHECKPOINT 4: projection refinement ---
   |
Phase 9: Verdict & price-action plan         [main agent + user]
   |
   --- CHECKPOINT 5: verdict approval ---
   |
Phase 10: Commit & index                     [main agent, sync]
```

## Phase 1: Setup & identity

When the skill is invoked (slash command or description-triggered), the orchestrator first runs:

1. **Resolve the ticker.** Use `_lib.ticker_resolver.resolve()` via the script `<toolkit>/_lib/ticker_resolver.py` — or just call it inside a one-liner:
   ```bash
   <toolkit>/.venv/bin/python -c "from _lib.ticker_resolver import resolve; r = resolve('AAPL'); print(r.cik_padded, r.name)"
   ```
   If `TickerNotFound`, abort with "Ticker not found on SEC EDGAR. Confirm spelling."

2. **Echo identity.** Show the user: ticker, name, sector (sector requires an extra yfinance lookup — `<toolkit>/.venv/bin/python -c "import yfinance as yf; print(yf.Ticker('AAPL').info.get('sector'))"` or skip if it's slow). Estimate market cap from yfinance for context.

3. **Check existing ticker folder.** If `/Users/trocaneduard/Documents/Personal/investing-research/tickers/<TICKER>/` exists, prompt the user (**use the runtime's native interactive-input mechanism — see "Asking the user for input"**):
   - **Refresh** — re-run all phases, overwrite (commits as `update(TICKER)`)
   - **Archive & restart** — move existing to `archive/<TICKER>-<old-date>/`, start fresh (commits as `archive(TICKER)` then `research(TICKER)` v2)
   - **Abort** — leave it, suggest `stock-recap` for quarterly update

4. **GVD lens declaration.** Ask the user (**use the runtime's native interactive-input mechanism — this is a 5-option enum, perfect picker territory**):
   > "What GVD lens are we researching this through? Pick: **growth | quality-growth | value | dividend | speculative-growth**. This shapes Phase 8 (projections) and Phase 9 (verdict). The agent will challenge later if the data disagrees."

5. **Session context** (optional, captured in THESIS.md). Ask:
   > "Anything you're already curious or worried about going into this? (Free-form one-liner. Captured in THESIS.md so future-you remembers what prompted this analysis.)"

6. **Initialize ticker folder.** Create:
   ```bash
   mkdir -p /Users/trocaneduard/Documents/Personal/investing-research/tickers/<TICKER>/{.raw,earnings-calls}
   ```
   And write a skeleton `THESIS.md` with the identity, GVD lens, and session-context line. Full thesis builds out across the phases.

## Phase 2: Business model + moat

Dispatch a subagent with `phases/02-business-model.md` as the prompt, injecting context:
- `ticker`, `cik_padded`, `ticker_dir`, `toolkit_dir`, `raw_dir`

Wait for the subagent to write `business-and-moat.md` and return its summary. The artifact is written directly into the research repo's ticker folder — no install-dir mirroring is needed at runtime. (The skill itself is mirrored from this repo into the agent install dirs by the repo-level `scripts/sync_skill.py push stock-research` during skill development, not during a research session.)

## Checkpoint 1

**Before rendering Checkpoint 1: read the "Explain like I'm in 5th grade" section (the first `### 1. Explain like I'm in 5th grade` block) from `<ticker_dir>/business-and-moat.md` — the file the Phase 2 subagent just wrote. The Checkpoint 1 message MUST lead with that section verbatim. Do not paraphrase, shorten, or "compress for the chat." The whole point of the plain-English explanation is that it's the same plain-language voice the user wants to see at the top of the conversation, not just buried in the file. If the section in the file is itself jargon-heavy (uses terms like "ACV", "ARR", "platform", "operating leverage", "low-code", "workflow OS"), that's a Phase 2 failure — re-dispatch the subagent with explicit feedback before rendering Checkpoint 1.**

Format (output exactly this Markdown shape — render it as Markdown in the chat, not inside a code block):

```markdown
## Checkpoint 1 — Business Model & Moat

*Drafted at `<ticker_dir>/business-and-moat.md`.*

### Explain like I'm in 5th grade

> <Paste the "Explain like I'm in 5th grade" section from business-and-moat.md verbatim — typically 3-6 short paragraphs of plain language covering every business area the company operates in. Banned vocabulary in this block: ACV, ARR, NDR, NRR, TAM, SAM, platform-as-a-service, workflow OS, low-code, operating leverage, vertical, monetization, take rate, attach rate, GAAP/non-GAAP — and any other jargon. If you can't explain a segment in 10-year-old English, the section wasn't written right.>

### Technical summary

The analyst-voice synthesis. Pull from `business-and-moat.md` — go deeper than 3-5 sentences. Jargon is allowed here; precision over plainness.

#### Segments

For each reportable segment (or product line if the company doesn't break out segments):

- **<Segment name>** — $X.XB (Y% of revenue), growing Z% YoY.
  - *What it does:* <1-2 sentences, specific.>
  - *Target customers:* <enterprise / mid-market / SMB / consumer / government / developers / etc. Be specific — "Fortune 500 IT departments" not "businesses".>
  - *Pricing model:* <subscription / per-seat / consumption / hardware + services attach / advertising / marketplace take rate / freemium-to-paid / etc.>
  - *Margin profile if disclosed:* <gross margin, contribution margin, or qualitative read like "lower-margin than the company average" — pull from the 10-K MD&A if it breaks segment economics down.>
  - *Recurring vs transactional:* <% recurring if disclosed, or qualitative read.>

(Repeat for every segment. Don't skip one to keep the message short — the user wants the full picture.)

#### Customer concentration & geography

- **Top customers:** <Any single customer >10% of revenue per 10-K disclosure? Name them and quantify. If none, write "No single customer above 10%.">
- **Customer count / scale:** <If disclosed: total customers, $1M+ ACV customers, enterprise vs mid-market split.>
- **Geographic mix:** <Top 3 geographies by revenue % and any concentration risk (e.g., ">25% from a single country other than the home market" or "diversified — no geography above 30%").>

#### Pricing power & moat — by dimension

Address each dimension that's real for this business. Skip dimensions that don't apply — don't fabricate a network effect that doesn't exist.

- **Pricing power:** <evidence — gross margin trend (improving = pricing power), price increases mentioned in earnings calls, renewal economics, retention rates, comparison to peer pricing.>
- **Switching costs:** <how customers actually use this — data migration, retraining, integration depth, multi-year contracts, regulatory lock-in. Tie to who the customers are: enterprise IT has much higher switching costs than consumer apps. Quantify if possible.>
- **Network effects:** <how value scales with users — marketplace liquidity, dev ecosystem, payment network reach. Or: "None.">
- **Scale advantages:** <unit economics that improve with size — logistics density, R&D leverage, manufacturing scale. Or: "None.">
- **Brand:** <premium pricing supported by brand, consumer surveys, NPS. Or: "Not a brand-driven moat.">
- **Regulatory / structural:** <licenses, patents, geographic monopolies, network access. Or: "Not applicable.">

**Moat verdict:** **wide** / **narrow** / **none**  
**Trajectory over last 3 years:** **widening** / **stable** / **narrowing** — <specific evidence: margin trend, retention number, market share gain, R&D as % of revenue, etc.>

#### Leadership & capital allocation

- **CEO:** <name, years in role, prior background, what they're known for.>
- **CEO ownership / skin in the game:** <% ownership, founder-led vs hired-gun, total insider ownership.>
- **Insider trading pattern (trailing 12 months):** <net buying / selling, any large transactions worth flagging — or "no significant insider activity".>
- **Capital allocation track record (5–10 years):** <one paragraph. What did they do with cumulative FCF? Reinvestment ROI, buyback discipline (did they buy back at reasonable prices?), dividend trajectory, M&A pattern. Note any deals that look value-destructive or value-creative.>

#### Top risks to investigate downstream

3–5 specific risks Phase 4's SWOR should investigate. Anchor each to evidence in the 10-K or earnings calls, not abstractions.

1. <specific risk>
2. <...>
3. <...>

### Quick verification

Before we move to financials:

1. Does the plain-English explanation match how YOU think about this business?
2. Any segment, geography, or customer-concentration risk I missed?
3. Moat — am I overrating or underrating any of pricing power / switching costs / network / scale / brand?
4. Anything you already know about leadership or capital-allocation history that should color the rest of the analysis?
```

**Use the runtime's native interactive-input mechanism for the Continue / Push back & revise choice** — printing the question block above and then surfacing two structured options. If the user picks "Push back & revise," the follow-up reply is free-form text.

Wait for user input. Possible responses:
- "Continue" → proceed to Phases 3–7 batch
- "Push back & revise" → engage free-form. Corrections get relayed to a fresh Phase 2 subagent (re-dispatch with the user's corrections in the context) → return to Checkpoint 1.

## Phase 3: Financials

Dispatch a subagent with `phases/03-financials.md` as the prompt, injecting the standard context block. The subagent runs `compute_financials.py` (multi-candidate XBRL extraction), inspects the result for `missing_concepts` and `tag_resolution`, applies critical thinking to fill gaps from the company-facts JSON where possible, and writes `financials.{md,json}` structured around the three classic statements (Income Statement, Balance Sheet, Cash Flow Statement) plus the trend gate, capital allocation, and quality metrics.

Wait for the subagent to return its ~500-word summary.

## Checkpoint 2

The financials are load-bearing for everything downstream (valuation, projections, verdict). The user discusses the three statements here before the parallel batch fans out, so they can correct any misreads, flag concerns, and lock the financial picture before competitors / earnings calls / valuation start.

**Before rendering Checkpoint 2: open `<ticker_dir>/financials.{md,json}`. If `financials.json` has a non-empty `missing_concepts` array OR `tag_resolution` resolved any metric to an unexpected candidate (e.g., `SalesRevenueNet` instead of `Revenues` or `RevenueFromContractWithCustomerExcludingAssessedTax`), surface that as the very first thing in this checkpoint — the user needs to know which numbers came from where before discussing them.**

Format (rendered Markdown, not inside a code block):

```markdown
## Checkpoint 2 — Financials: Income, Balance Sheet, Cash Flow

*Written to `<ticker_dir>/financials.md` and `<ticker_dir>/financials.json`.*

### Data-quality notes (only if there are any)

<If financials.json has missing_concepts or a non-default tag_resolution: spell it out here. Example:
"⚠️ The XBRL script's default candidate list didn't find revenue for FY2018+ under `Revenues`. The script's fallback resolved it to `RevenueFromContractWithCustomerExcludingAssessedTax` (the post-ASC-606 tag this company uses). All FY2018+ revenue numbers come from that tag."
"⚠️ `sbc` (stock-based compensation) is missing — the company doesn't report it under any of the standard candidates. I left those rows null." >

### Income Statement at a glance

<2-3 sentence verbal summary, then the income-statement table from financials.md (revenue, gross/op/net, EPS year-by-year). Format $ in $B, EPS in $.>

### Balance Sheet snapshot

<1-2 sentence verbal summary, then a compact table: latest-FY cash, long-term debt, net debt, and the 5-year trend direction for each.>

### Cash Flow Statement at a glance

<2-3 sentence verbal summary, then the cash-flow table from financials.md (CFO, capex, FCF, SBC %, buybacks, dividends year-by-year).>

### Trend gate verdict

> <Pass / Pass-with-caveats / Fail with the specific metric that's mixed or down>

### Worth discussing

1. <3-5 bullets — specific things the user should weigh in on. Examples:
   - "Operating margin compressed from 24% to 18% between FY22 and FY24 — driven by what?"
   - "SBC % of revenue is 11% and growing. Real dilution offsetting buyback yield."
   - "Net cash position has shrunk from $58B (FY20) to $12B (FY24) — where did the cash go?"
   - "Revenue tag mismatch noted above — comfortable with the substitute?" >
```

**Use the runtime's native interactive-input mechanism for the Continue / Push back choice** at the end of Checkpoint 2. If the user pushes back, the follow-up is free-form (they may have private knowledge of an M&A deal, an accounting change, or a one-time charge that explains a number). After the discussion, proceed to the parallel batch.

## Phases 4–7: parallel batch

Dispatch FOUR subagents in parallel — issue all four subagent dispatches in a single message so the host agent can run them concurrently. Each subagent gets its phase prompt file's contents as the prompt, plus the standard context block:

- Phase 4 — `phases/04-competitors-swor.md` (which itself fans out to per-competitor sub-subagents)
- Phase 5 — `phases/05-earnings-calls.md` (which fans out to per-quarter sub-subagents) — also inject `company_slug` (your best guess from the company name, lowercase, hyphens for spaces)
- Phase 6 — `phases/06-valuation.md`
- Phase 7 — `phases/07-market-expectations.md`

Wait for all 4 to return.

**Failure handling in the batch:**

| Returned status | Action |
|---|---|
| All 4 `DONE` | Proceed to Checkpoint 3 |
| 1–2 `DONE_WITH_CONCERNS` | Proceed; flag concerns in Checkpoint 3 summary |
| Any `BLOCKED` | Surface to user via **the runtime's native interactive-input mechanism**: "Phase X failed because <reason>." with 3 options — Retry / Skip & continue / Abort |
| Any `NEEDS_CONTEXT` (almost always from Phase 5's transcript scrapers) | Surface to user via **native interactive input** with 2 options — Paste transcript inline / Skip this quarter. If "paste", read the transcript content as the next free-form message and re-dispatch only that single sub-subagent with `--manual`. |

## Checkpoint 3

This checkpoint synthesizes the entire Phase 4–7 batch into a single picture: competitors, earnings calls, valuation, and market expectations. The user should leave this checkpoint with a clear read on **how the company stacks up against peers, what management is signaling, where the stock sits valuation-wise, and what the market expects** — before they start building their own projections in Phase 8.

**Before rendering Checkpoint 3: read the four artifact files written by the batch:**
- `<ticker_dir>/competitors.md` and `<ticker_dir>/swor.md` (Phase 4)
- `<ticker_dir>/earnings-calls/cross-call-themes.md` (Phase 5)
- `<ticker_dir>/valuation.md` (Phase 6)
- `<ticker_dir>/market-expectations.md` (Phase 7)

Also pull the ~500-word summaries returned by each batch subagent. The checkpoint's job is to compress the load-bearing parts of each into a single readable synthesis.

Format (rendered Markdown, not inside a code block):

```markdown
## Checkpoint 3 — Batch Synthesis: Competitors, Calls, Valuation, Market Expectations

*Four artifacts written under `<ticker_dir>/`: `competitors.md`, `swor.md`, `earnings-calls/cross-call-themes.md`, `valuation.md`, `market-expectations.md`. The summary below is the load-bearing distillation; open the files for the full detail.*

### 🏟️ Competitive positioning

<2-3 sentence positioning verdict from Phase 4's summary: where the company sits, who's pulling ahead, the moat-vs-competitor read.>

<Compact competitor table — pull the top 3-4 rows from competitors.md, NOT all the metrics, just the ones that tell the story (market cap, revenue, growth, op margin, P/E):>

| Ticker | Market cap | Revenue (TTM) | Rev growth (3-yr) | Op margin | P/E (TTM) |
|---|---|---|---|---|---|
| **<TICKER>** | $X.XB | $Y.YB | XX% | XX.X% | XX.X× |
| ... | ... | ... | ... | ... | ... |

<Top 2-3 SWOR risks the user should know about, taken from `swor.md`'s Risks section — specifically the ones flagged by the year-over-year risk-factor diff (NEW risks mgmt added). One sentence each.>

### 📞 Earnings calls — tone & direction

<Paste Phase 5's tone-trajectory + cross-call themes, 2-4 paragraphs. Use blockquotes for any verbatim mgmt quote you cite. Note any guidance trajectory (raising / holding / lowering across the 3 calls) and emerging themes.>

### 💰 Valuation snapshot

| Metric | Value | Note |
|---|---|---|
| **Current price** | $XXX.XX | as of <today> |
| **P/E (TTM)** | XX.X× | <position vs historical 10-yr band: above median / below 25th / etc.> |
| **Current P/E percentile** (10-yr) | XX% | |
| **P/S (TTM)** | X.X× | |
| **P/FCF (TTM)** | XX.X× | |
| **Reverse-DCF implied growth** | XX% / yr | <plausible / aggressive / conservative for this bucket> |

<1-2 sentence verdict from valuation.md: expensive / fair / cheap, and why.>

### 📊 Market expectations (calibration for Phase 8)

| Field | Value |
|---|---|
| **Analyst coverage** | N analysts |
| **Consensus price target** | low $XXX / mean $XXX / high $XXX |
| **Implied upside (mean)** | +XX% |
| **Ratings** | XX% Buy / XX% Hold / XX% Sell |
| **EPS estimate trend (90 days)** | ⬆ rising / ⬇ falling / ↔ flat |
| **Consensus 5-yr growth** | XX% / yr |

> <Paste Phase 7's calibration prompt verbatim — the one that frames "consensus expects X / Y / Z, what do you know that they don't?" This anchors the Phase 8 brainstorm.>

### 🎯 Worth discussing before projections

<3-7 bullets pulled across the four phases — anything the user should weigh in on before we move to the projection brainstorm. Examples:
- "Competitive: Microsoft's Copilot pricing undercuts the company's services tier — Phase 5 calls mentioned this twice. Real moat compression risk."
- "Earnings tone: mgmt's services growth guidance dropped from 'high-teens' (Q1) to 'low-teens' (Q3). Worth pressing on what changed."
- "Valuation: current P/E at 76th percentile of 10-yr band, but reverse-DCF implies 14%/yr growth — slightly above the 11% historical CAGR. Modestly expensive but not heroic."
- "Market expectations: consensus expects +12% revenue next year vs the company's own guide of +10%. Either consensus is too high or the company is sandbagging."

Pull from each phase's summary — these are the items each phase flagged as 'worth discussing'.>
```

**Use the runtime's native interactive-input mechanism for the Continue / Discuss further choice** at the end of Checkpoint 3. If the user picks "Discuss further," the follow-up dialogue is free-form text — this is the most conversation-heavy checkpoint, and the user often has a take on recent events, peer dynamics, or valuation context that should color the projections. Engage substantively before continuing.

## Phase 8: Bull/Base/Bear projections

This phase runs in the main agent (you), not a subagent — it's an interactive brainstorm.

**Read these references before starting:**
- `references/gvd-tailoring.md` — how to push back on assumptions for this GVD bucket
- `references/projection-kpis.md` — the full KPI list + formulas + dialogue flow

Open the brainstorm (rendered Markdown):

```markdown
## Phase 8 — Bull / Base / Bear 5-Year Projections

I'll walk us through the **base case** row-by-row, anchored in everything we've gathered:

- Historical 5-yr trends → `financials.json`
- Peer averages → `competitors.md`
- Mgmt forward guidance → `earnings-calls/cross-call-themes.md`
- Reverse-DCF implied growth → `valuation.md`
- **Consensus expectations** → `market-expectations.md`:

> <Paste Phase 7's calibration prompt verbatim, as a blockquote so it visually anchors the brainstorm.>

Base case first. Then bull and bear as perturbations from base. Then probabilities.

### Row 1 — Revenue growth (Y1 → Y5)

| Anchor | Value |
|---|---|
| Historical 3-yr CAGR | X% |
| Peers (avg) | Y% |
| Mgmt guidance | Z% |
| Consensus | W% |

**My base-case proposal:** Y1 = a%, Y2 = b%, Y3 = c%, Y4 = d%, Y5 = e%.

Push back, adjust, or accept.
```

Continue this row-by-row pattern (each row = a Markdown subsection with an anchor table and your base-case proposal) for the remaining rows.

Walk through the locking sequence from `references/projection-kpis.md`:

1. Revenue growth → user locks
2. Gross margin → user locks
3. Operating margin → user locks
4. Net margin → user locks (or derive from above + tax assumption)
5. Share count (SBC + buybacks) → user locks
6. Dividend per share → user locks
7. Exit P/E low/high at Y5 → user locks
8. Compute base-case prices and CAGRs, show to user
9. Bull case: ask "what credible upsides shift these levers?" → user proposes deltas → re-lock each row
10. Bear case: same for downsides
11. Probabilities: bull + base + bear = 1.0 → user locks
12. Compute probability-weighted return + bear drawdown + implied margin of safety

Apply `references/gvd-tailoring.md` rules — if the user proposes a 35× exit P/E for a 30%-grower at Y5, challenge it.

When all rows are locked and computations done, write:
- `projections.json` — full machine-readable schema per `references/projection-kpis.md`
- `projections.md` — narrative version: assumptions per scenario, the table, headline numbers

## Checkpoint 4

Format (rendered Markdown, not inside a code block):

```markdown
## Checkpoint 4 — Projection Refinement

*`projections.md` and `projections.json` written to `<ticker_dir>`.*

### Scenario summary

| Scenario | Probability | 5-yr Total Return CAGR (low → high) |
|---|---|---|
| 🐂 Bull | XX% | **+XX% → +XX%** |
| ⚖️ Base | XX% | **+XX% → +XX%** |
| 🐻 Bear | XX% | **−XX% → −XX%** |
| **Probability-weighted** | — | **+XX% → +XX%** |

- **Margin of safety today:** XX%
- **Bear-case max drawdown from current:** −XX%

### Quick sanity check

1. Does the asymmetry feel right? (Bull upside vs bear downside.)
2. Any assumption locked above you want to revisit?
3. Probabilities — does the bull scenario require what you'd call "everything going right"? Should we push the base case probability up?
```

**Use the runtime's native interactive-input mechanism for the Continue / Revise projections choice** at the end of Checkpoint 4.

## Phase 9: Verdict & price-action plan

Read these references:
- `references/sizing-matrix.md`
- `references/investor-gates.md`
- `references/sell-trigger-templates.md`
- `references/watch-kpis-by-gvd.md`

Construct `verdict.md` (and `verdict.json`) with 10 sections (per overall-spec §6 Phase 9):

1. **Classification** — BUY / WATCH / AVOID. Logic:
   - BUY: positive probability-weighted return, margin of safety >10%, bull/base asymmetry favorable, all 6 investor gates answered
   - WATCH: positive probability-weighted return but margin of safety thin OR thesis not yet earnings-proven
   - AVOID: negative or marginal probability-weighted return, OR moat trajectory narrowing, OR investor gates can't be answered substantively
2. **Conviction** — High / Medium / Low with one-sentence why
3. **GVD bucket** — final (may differ from declared at Phase 1)
4. **Time horizon** — Minimum 5-year hold
5. **Position sizing** — From `references/sizing-matrix.md`. Surface bull/base asymmetry; **do not be paternalistic** about sizing when asymmetry is favorable.
6. **Buy zone** — Concrete price ranges per tranche from `references/sizing-matrix.md`'s scaling-in plan
7. **Sell triggers** — Apply `references/sell-trigger-templates.md`:
   - Materially overvalued threshold (bull-case Y5 fair value + reverse-DCF threshold)
   - 3–5 thesis-broken KPI breaches (story-specific — brainstorm with user)
   - Better-opportunity note
8. **Quarterly watch KPIs** — Two sets:
   - Generic GVD defaults (5 KPIs from `references/watch-kpis-by-gvd.md`)
   - Story-custom (3–5 KPIs — brainstorm with user)
9. **Great-investor gates** — All 6 questions from `references/investor-gates.md`, each with a 1–3 paragraph answer in prose
10. **One-page thesis** — Can you defend this position in 60 seconds? Write the 60-second pitch.

Use the interactive brainstorm pattern for steps 5–8 (don't unilaterally pick the watch KPIs; ask the user what's load-bearing for THIS story).

## Checkpoint 5

Format (rendered Markdown, not inside a code block):

```markdown
## Checkpoint 5 — Verdict Approval

*`verdict.md` and `verdict.json` drafted at `<ticker_dir>`.*

### Verdict at a glance

| Field | Value |
|---|---|
| **Classification** | 🟢 BUY / 🟡 WATCH / 🔴 AVOID |
| **Conviction** | High / Medium / Low |
| **GVD bucket** | `<category>` |
| **Target position** | XX% of portfolio |
| **Buy zone (first tranche)** | $XXX – $XXX |
| **Active sell triggers** | <count> |
| **Watch KPIs** | 5 generic + N story-custom |

### Final review before commit

1. **Classification** — does the BUY / WATCH / AVOID match your gut after all this analysis?
2. **Sizing** — too small, too big, right?
3. **Sell triggers** — any too strict (would fire on noise) or too loose (would never fire)?
4. Anything missing from `verdict.md`?
```

**Use the runtime's native interactive-input mechanism for the Approve & commit / Push back choice** at the end of Checkpoint 5.

## Phase 10: Commit & index

After Checkpoint 5 approval:

1. **Update `tickers.json`** atomically:
   ```bash
   <toolkit>/.venv/bin/python <toolkit>/upsert_ticker.py <TICKER> \
     --repo /Users/trocaneduard/Documents/Personal/investing-research \
     --field name="<NAME>" \
     --field sector="<SECTOR>" \
     --field gvd_category=<gvd> \
     --field current_status=<BUY|WATCH|AVOID> \
     --field current_conviction=<high|medium|low> \
     --field thesis_version=v1 \
     --field price_at_last_analysis=<price> \
     --field buy_zone_low=<low> \
     --field buy_zone_high=<high> \
     --field current_target_position_pct=<pct> \
     --list-field active_sell_triggers="<trigger 1>" \
     --list-field active_sell_triggers="<trigger 2>" \
     # ... etc
   ```

2. **Regenerate `INDEX.md`**:
   ```bash
   <toolkit>/.venv/bin/python <toolkit>/update_index.py \
     --repo /Users/trocaneduard/Documents/Personal/investing-research
   ```

3. **Commit in the research repo** using the structured format from overall-spec §8.1:
   ```bash
   cd /Users/trocaneduard/Documents/Personal/investing-research
   git add tickers/<TICKER>/ INDEX.md tickers.json
   git commit -m "$(cat <<'EOF'
   research(<TICKER>): initial deep dive — verdict <BUY|WATCH|AVOID> @ $<price>

   <Brief 2-3 sentence body summary of the thesis>

   ticker: <TICKER>
   session: initial-research
   date: <YYYY-MM-DD>
   trigger: manual
   verdict: <BUY|WATCH|AVOID>
   conviction: <high|medium|low>
   gvd: <category>
   price-target-low: <number>
   price-target-base: <number>
   price-target-high: <number>
   position-target-pct: <number>
   files-changed: tickers/<TICKER>/(all artifact files), INDEX.md, tickers.json
   EOF
   )"
   ```

4. **Tag** the thesis version:
   ```bash
   git tag <TICKER>/v1
   ```

5. **Optional remote push** (if a remote is configured): ask the user via **the runtime's native interactive-input mechanism** — 2 options: Push now / Skip. Default: skip — let the user push when they want.

6. **Confirm completion** to the user (rendered Markdown):

   ```markdown
   ## ✅ Research complete — `<TICKER>` (`<NAME>`)

   | Field | Value |
   |---|---|
   | **Verdict** | 🟢/🟡/🔴 `<BUY/WATCH/AVOID>` — conviction `<level>` — GVD `<category>` |
   | **Target position** | XX% of portfolio |
   | **Buy zone (first tranche)** | $XXX – $XXX |
   | **Artifacts** | `<ticker_dir>` |
   | **Commit** | `<SHA>` |
   | **Tag** | `<TICKER>/v1` |
   ```

## Recovery / setup errors

All setup-error messages render as Markdown (header + code block), not plain text.

If Phase 1 finds:

- **`SR_SEC_USER_AGENT` unset** → print:
  ````markdown
  ### ❌ Setup needed: SEC User-Agent

  Set this in your shell rc and reload:

  ```bash
  export SR_SEC_USER_AGENT="<Your Name> <your@email>"
  source ~/.zshrc
  ```
  ````

- **Research repo missing** → print:
  ````markdown
  ### ❌ Setup needed: research repo

  Research repo not found at `/Users/trocaneduard/Documents/Personal/investing-research`.

  Bootstrap (one-time):

  ```bash
  mkdir -p /Users/trocaneduard/Documents/Personal/investing-research
  cd $_ && git init -b main
  # Then create README.md, INDEX.md, tickers.json, .gitignore per
  # docs/superpowers/specs/2026-05-11-stock-research-plan-2-design.md §10
  ```
  ````

- **Python venv missing** → print:
  ````markdown
  ### ❌ Setup needed: financial-toolkit venv

  Set up the shared toolkit's venv. The `financial-toolkit` lives at `~/.claude/toolkits/financial-toolkit` (Claude Code) or `~/.codex/toolkits/financial-toolkit` (Codex), separate from this skill's install dir.

  ```bash
  cd <toolkit-install-dir>
  python -m venv .venv
  .venv/bin/pip install -r requirements.txt
  ```
  ````

## File references

- `phases/02-business-model.md` through `phases/07-market-expectations.md` — subagent prompts
- `references/gvd-tailoring.md`, `references/projection-kpis.md`, `references/sizing-matrix.md`, `references/investor-gates.md`, `references/sell-trigger-templates.md`, `references/watch-kpis-by-gvd.md` — Phase 8/9 reference data
- Shared toolkit at `~/.<agent>/toolkits/financial-toolkit/` — 12 Python CLIs + 5 utilities the subagents invoke (call via `<toolkit_dir>/.venv/bin/python <toolkit_dir>/<script>.py`). Source lives at `toolkits/financial-toolkit/` in the repo. To sync canonical → both install dirs during development: `python3 scripts/sync_skill.py push stock-research` for this skill, `python3 scripts/sync_toolkit.py push financial-toolkit` for the shared toolkit.

## Iron rule: never write to user code

This skill only writes to the research repo at `/Users/trocaneduard/Documents/Personal/investing-research/`, the skill's own `.raw/` cache, and stdout. It does NOT touch the user's code projects, git config, or anything outside the research-repo path. The Python scripts are read-only (no edits) — they're already shipped by Plan 1.
