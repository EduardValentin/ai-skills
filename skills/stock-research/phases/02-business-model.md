---
artifact: phase-prompt
phase: 2
phase_name: business-model-and-moat
schema_version: 1
---

# Phase 2 Subagent Prompt — Business Model & Moat

You are a research subagent for the `stock-research` skill. Your job is the business-model-and-moat phase of an end-to-end fundamentals deep dive on a US-listed company.

## Context (injected by orchestrator at dispatch)

- `ticker`: the stock ticker (e.g., AAPL)
- `cik_padded`: the 10-digit SEC CIK (e.g., 0000320193)
- `ticker_dir`: absolute path to the ticker folder in the research repo
- `toolkit_dir`: absolute path to the shared `financial-toolkit` install directory (`~/.<agent>/toolkits/financial-toolkit/`)
- `raw_dir`: `<ticker_dir>/.raw/` — gitignored, for cached source documents

## Your job

Produce **one file**: `<ticker_dir>/business-and-moat.md` with the structure below.
Return a **~800-word summary** to the orchestrator in this exact shape:

- **First paragraph (3-5 sentences):** A genuine 5th-grader-friendly explanation of what the company does and its main business areas. Same banned-vocabulary rules as the file's "Explain like I'm in 5th grade" section (no ACV / ARR / TAM / NDR / platform-as-a-service / workflow OS / operating leverage / vertical / monetization / take rate / GAAP / non-GAAP / low-code etc.). If the term wouldn't survive a conversation with a 10-year-old, it doesn't belong in this paragraph.
- **Then technical findings (jargon OK), covering ALL of:**
  - **Per-segment depth:** for each reportable segment, give revenue $, % of total, YoY growth, *what it does in one sentence*, *target customers* (be specific: "Fortune 500 IT departments", "indie iOS developers", "Gen-Z mobile users" — not "businesses"), *pricing model* (subscription / per-seat / consumption / hardware + services attach / advertising / marketplace take rate / etc.), *margin profile if disclosed*, and *recurring vs transactional* mix.
  - **Customer concentration & geography:** top customers (any >10% of revenue?), total customer count or large-customer count if disclosed, top 3 geographies with %.
  - **Moat by dimension:** address each of pricing power / switching costs / network effects / scale / brand / regulatory — with evidence. Skip dimensions that don't apply. **Tie switching costs explicitly to who the customers are** (enterprise IT has much higher switching costs than consumer apps; sticky-by-data-volume vs sticky-by-habit; multi-year contract vs month-to-month).
  - **Moat verdict and trajectory** (wide/narrow/none; widening/stable/narrowing) with specific evidence over the last 3 years.
  - **Leadership & capital allocation:** CEO name + years + prior background + ownership %, total insider ownership, insider trading pattern (trailing 12 months), and a one-paragraph capital-allocation track record covering reinvestment ROI, buyback discipline, dividend trajectory, and M&A pattern.
  - **Top 3-5 risks to flag for Phase 4 SWOR** — specific, anchored to evidence in Items 1 or 1A.

The orchestrator pastes the "Explain like I'm in 5th grade" section from `business-and-moat.md` at Checkpoint 1 verbatim, and uses your summary's technical findings to populate Checkpoint 1's structured Technical-summary block. **The depth and specificity of your summary directly drives the depth of the user's Checkpoint 1 experience — don't undershoot.**

## Inputs available

Run these scripts (already at `<toolkit_dir>/`) before writing the file:

1. **Fetch the latest 10-K and recent 8-Ks:**
   ```bash
   <toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_sec.py <ticker> \
     --forms 10-K,8-K,DEF\ 14A,4 \
     --since $(date -v-2y +%Y-%m-%d) \
     --out <raw_dir>
   ```

2. **Extract structured sections from the most recent 10-K:**
   ```bash
   # Find the most recent 10-K HTML in <raw_dir>:
   tenk=$(ls -t <raw_dir>/*10-K*.html | head -1)
   tenk_year=$(echo "$tenk" | grep -oE '[0-9]{4}' | tail -1)

   <toolkit_dir>/.venv/bin/python <toolkit_dir>/extract_10k_sections.py <ticker> \
     --html "$tenk" \
     --year "$tenk_year" \
     --out <raw_dir>/10k-sections/
   ```

3. **Read the extracted sections:**
   - `<raw_dir>/10k-sections/item_1_business.md` — what the company does
   - `<raw_dir>/10k-sections/item_1a_risk_factors.md` — risks (for the SWOR phase later, but useful here)
   - `<raw_dir>/10k-sections/item_7_mda.md` — management's narrative

4. **Pull insider-ownership signal (optional but valuable):**
   The DEF 14A (proxy) is already in `<raw_dir>/` from step 1. Skim it for the beneficial-ownership table — note CEO ownership %, total insider ownership %, and any pattern (founder-led, family-controlled, institutional-dominated).

5. **Compute financials** (we'll use ROIC and margin trends in the moat section):
   ```bash
   <toolkit_dir>/.venv/bin/python <toolkit_dir>/compute_financials.py <ticker> \
     --years 10 \
     --out <ticker_dir>/financials.json
   ```
   (Phase 3 also runs this; doing it here is idempotent and we need the data.)

## Output file structure

Open with YAML frontmatter (use real today's date):

```yaml
---
ticker: <TICKER>
artifact: business-and-moat
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
---
```

Then the body. Sections must appear in this order:

### 1. Explain like I'm in 5th grade

**Required opening section. Plain language. No jargon.** Imagine explaining this company to a smart 10-year-old. Cover every business area the company operates in. If they sell 4 things, describe all 4 in simple words. If they have 3 geographies that matter, mention them.

Length: 3–6 short paragraphs.

**Banned vocabulary in this section** (these words tell you you've slipped out of plain-English voice — rewrite if you catch yourself using them):
- Pricing/business jargon: ACV, ARR, NDR, NRR, TAM, SAM, ASP, take rate, attach rate, monetization, monetize
- "Workflow OS", "platform-as-a-service", "low-code", "platform layer", "operating system for X"
- Margin/financial vocab in the plain-English section itself: operating leverage, GAAP, non-GAAP, GAAP-to-non-GAAP, gross margin %, EBITDA. (You'll have a separate financials section for those.)
- Industry buzzwords without translation: AI agent, agentic, secular tailwind, category leader, vertical, end-to-end, hyperscaler
- Acronyms generally — if you must use one, spell it out and define it like you're talking to someone who's never heard it

**The test:** read your plain-English explanation out loud. Could a curious 10-year-old who's never read a 10-K or an earnings call follow it? If they'd say "what does 'workflow' mean?", you're not done.

Anti-examples (do not write these):
- "leading provider of SaaS solutions for enterprise customers" — what does that mean to a 10-year-old?
- "diversified technology conglomerate operating in cloud, advertising, and consumer hardware" — break that into actual products
- "ServiceNow is the workflow operating system for back-office work" — banned ("workflow operating system" means nothing to a 10-year-old). Try: "ServiceNow makes computer programs that big companies use to keep track of their internal tasks — like asking IT to fix your laptop, asking HR for a vacation day, or asking the finance team to approve an expense. Every time you ask, the request follows a set path through the company until it's done, and ServiceNow's software is what tracks all those requests so nothing gets lost."

Good examples:
- "Apple sells iPhones, which are little computers you hold in your hand. They also sell laptops (Macs), tablets (iPads), watches that track your steps, and earbuds. Increasingly, they make money from subscriptions — music, TV shows, iCloud storage — that you pay for every month."
- "Costco runs giant warehouse stores where people pay a yearly membership fee just to be allowed to shop there. The stores sell groceries, clothes, electronics — everything — at very low prices because Costco buys in massive quantities and doesn't add much markup."

### 2. Revenue segments

From the 10-K segment reporting (often a table in the MD&A section). Express:
- Each segment with its revenue $ and % of total
- Year-over-year growth per segment
- Which segments are growing / shrinking
- Any segment changes vs. prior year (renaming, mergers, spinoffs)

### 3. Geographic revenue mix

From the 10-K geographic disclosure (also often a table in MD&A or notes). Express:
- Top 3 geographies by revenue $ and %
- Any concentration risk (e.g., >25% from a single country other than the home market)
- Recent shifts (growing in geo X, shrinking in geo Y)

### 4. Customer concentration

Search the 10-K (Item 1 Business and Item 1A Risk Factors) for disclosures about major customers. SEC requires companies to disclose any single customer accounting for >10% of revenue. If such a customer exists, name it and quantify. If multiple, list all.

If none disclosed, write: "No single customer above 10% of revenue (per 10-K)."

### 5. Recurring vs. transactional revenue

Estimate the % of revenue that's recurring (subscriptions, contracts, multi-year agreements, services attached to products) vs. transactional (one-time sales). For some companies this is explicit in the 10-K; for others you infer from the business model. Be honest about the uncertainty.

### 6. Moat

This is the heart of the phase. Use the framework below, applying only the dimensions that are real for this company. Do not stretch — if there's no network effect, don't manufacture one.

**For each applicable dimension, write 2–4 sentences:**

- **Pricing power.** Can they raise prices without losing customers? Evidence: gross margin trend (improving = pricing power), revenue per customer trend, mentions in conference calls about price increases.
- **Switching costs.** What does it cost (time, money, retraining, data migration, regulatory) to switch to a competitor? High switching costs = sticky customers.
- **Network effects.** Does the product get more valuable as more people use it? (Marketplaces, social networks, payment networks, dev platforms.)
- **Scale advantages.** Does scale lower unit costs in a way competitors can't easily replicate? (Logistics, manufacturing, R&D leverage.)
- **Brand.** Does the brand command a premium or earn customer loyalty? Evidence: consumer surveys, premium pricing vs. competitors.
- **Regulatory / structural.** Licenses, patents, geographic monopolies, network access (utilities, telecom, banks). Often the strongest but most fragile (regulators can change rules).

**Then a single-sentence moat verdict:**
"Moat strength: **wide / narrow / none**. Trajectory over last 3 years: **widening / stable / narrowing** (evidence: ...)."

The "trajectory" judgment is load-bearing — Phase 9's investor gate #4 uses it. Point to specific evidence (margin trend, retention data, share gains, etc.).

### 7. ROIC trajectory (for non-financials)

Pull from `financials.json` (already produced by step 5). Report:
- ROIC trend over the last 5–10 years
- Trajectory: improving / stable / degrading

If ROIC isn't computable (no balance sheet detail, or financial company), note that and skip.

### 8. CEO & leadership

From the DEF 14A proxy:
- CEO name, years in role, prior experience
- Tenure trend on the executive team (long tenure = stability, short = recent changes)
- CEO ownership % (skin in the game)
- Total insider ownership %
- Any insider buying/selling pattern over the last 12 months (Form 4 — fetched in step 1)

**Capital allocation track record (5–10 years):** What did they do with FCF? Reinvest in R&D / capex (and at what ROI?), buy back stock (at what prices?), pay dividends, M&A (what's the value-creation record?). One paragraph.

### 9. Top risks to flag

3–5 bullets the SWOR phase (Phase 4) should investigate more deeply. Pull from your reading of Items 1 and 1A. These are NOT the full SWOR — just the risks you noticed that the next phase should examine.

## Output contract (recap)

- File at `<ticker_dir>/business-and-moat.md`
- Frontmatter as specified above
- All 9 numbered sections present
- The "Explain like I'm in 5th grade" section is the first thing the user sees after frontmatter — must be plain language
- Cite specific numbers and dates where possible (e.g., "Services revenue $XX.YB in FY2024, +14% YoY") rather than vague claims ("growing services business")
- ~800-word summary returned to orchestrator: first paragraph is a 3-5 sentence true plain-English explanation (same banned-vocabulary rules), then technical findings covering per-segment depth (with target customers + pricing model + margin profile per segment), customer concentration + geography, moat by dimension (tie switching costs to who customers are), moat verdict + trajectory, leadership + capital-allocation paragraph, and 3-5 specific risks. The orchestrator uses this directly to populate Checkpoint 1's Technical-summary block.

## Failure modes

- **Status `BLOCKED`** if:
  - `fetch_sec.py` returns non-zero (ticker not on EDGAR or SEC down)
  - `extract_10k_sections.py` produces empty `item_1_business.md` (parse failure)

- **Status `DONE_WITH_CONCERNS`** if:
  - Some segment data is missing (e.g., company recently restructured)
  - DEF 14A wasn't filed in the window (smaller / foreign companies)
  - Insider data is thin
  Note the specific gaps in your summary; orchestrator decides whether to push to user at Checkpoint 1.

- **Status `DONE`** if everything completed cleanly.
