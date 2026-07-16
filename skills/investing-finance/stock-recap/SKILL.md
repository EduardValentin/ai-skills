---
name: stock-recap
description: "Use when recapping an existing US-listed stock thesis — catching up on every quarter (10-Q/10-K) filed since the last analysis, or analyzing the impact of a material event (M&A, CEO change, regulatory ruling, restated guidance). Triggers on phrases like \"catch me up on NVDA\", \"recap MSFT since last quarter\", \"how does this acquisition affect my AAPL thesis\", \"new earnings just dropped for TSLA\". Mechanically diffs actuals vs saved bull/base/bear projections, LLM-evaluates the saved English sell triggers in 4 states (🔴 fired / 🟡 flashing / 🟢 clear / ⚪ cannot-evaluate), and optionally proposes a surgical or reclassifying thesis update. Not for: initial deep dive on a brand-new ticker (that's stock-research), portfolio P&L tracking, short-term trading, or non-US listings."
compatibility: >-
  Requires SR_SEC_USER_AGENT, SR_RESEARCH_REPO, prior stock-research artifacts, market-source network access, and writable Git state. Native agent dispatch and structured-input tools are optional: fall back to sequential prompts and numbered text choices. Missing artifacts route to stock-research; missing bundled scripts or required runtime capabilities block execution.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Stock Recap

A two-flow skill that keeps an existing investment thesis alive. After `stock-research` produces an initial deep dive, `stock-recap` is what you run to catch up on every 10-Q / 10-K filed since the last touch (Quarterly mode) or to analyze the impact of a material event between earnings (News mode). It mechanically diffs actuals vs the saved bull/base/bear projections, LLM-evaluates every saved English sell trigger in 4 states, and optionally proposes a surgical or reclassifying thesis update.

## First response contract

When beginning a recap, the response must preserve these gates before any recap work:

- Prior research preconditions: `verdict.json`, `projections.json`, `financials.json`, `market-expectations.json`, the SEC EDGAR user-agent, the bundled financial runtime, and the investing research repo.
- Gap detection: check for new 10-Q / 10-K filings since the latest saved financial period.
- Mode routing: in the first response, state both routing branches explicitly: if filings exist, offer quarterly catch-up or news mode; if no filings exist, offer switch to news mode, valuation-only recap, or exit.
- Quarterly mechanics: refresh financials and valuation, mechanically diff actuals against saved bull case / base case / bear case projections, and evaluate every saved sell trigger as fired, flashing, clear, or cannot-evaluate. Do not shorten this to "evaluate sell triggers" without naming the four states.
- Checkpoints: explicitly state that the workflow uses the walkthrough and trigger/trajectory checkpoints before any thesis update, asks before any surgical patch or reclassification, and asks again before pushing changes to remote. Do not omit these checkpoint gates from the first response.

## When to use

- The user wants to catch up on what's happened with a ticker they already researched. Phrases: "catch me up on NVDA", "recap MSFT since last quarter", "new earnings just dropped on TSLA".
- The user wants to analyze the impact of a material event. Phrases: "how does this acquisition affect my AAPL thesis", "Microsoft just lost their CEO — recap MSFT", "the FTC ruling changes the GOOG thesis, right?".
- Explicit slash invocation: `stock-recap for <TICKER>`.

**Do not use for:**
- Initial deep dive on a brand-new ticker → that's `stock-research`. This skill aborts in Phase 1 if `verdict.json` is missing.
- Portfolio P&L tracking, position sizing math, tax-lot management.
- Technical analysis, options strategies, day trading.
- Non-US listings (the data pipeline is SEC EDGAR + yfinance, both US-focused).

## Prerequisites (one-time setup)

1. **`stock-research` has been run for this ticker.** The skill reads `tickers/<TICKER>/verdict.json`, `projections.json`, `financials.json`, and `market-expectations.json`. If any of those are missing, Phase 1 aborts with instructions to run `stock-research` first.

2. **SEC EDGAR User-Agent.** Same env var as `stock-research`:
   ```bash
   export SR_SEC_USER_AGENT="Research User contact@example.com"
   ```

3. **Bundled financial runtime is ready.** Resolve scripts from `<skill-root>/scripts/`; do not depend on a repository-level toolkit or another harness install. Its `.venv` must already be set up from the bundled `requirements.txt`. If `<skill-python> --version` fails or a required bundled script is missing, stop and report the setup blocker.

4. **Research repo exists.** The skill writes per-session artifacts under `${SR_RESEARCH_REPO}/tickers/<TICKER>/recaps/`. If the repo root is missing, abort with the same bootstrap instructions as `stock-research`.

## Asking the user for input

**When the workflow needs a decision among a small set of mutually exclusive options, prefer the runtime's native interactive-input capability.** Whatever the agent platform provides — a picker, button row, multiple-choice modal, or `ask_user`-style tool — use it when available. If structured input is unavailable, print the same choices as a numbered plain-text list and wait for the user's typed selection.

Prefer bounded parallel subagents for independent fetch and analysis prompts. If parallel dispatch is unavailable, run the same prompts sequentially in the documented order and preserve the same return contracts.

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

Every section the agent prints back to the user must be **pretty-printed Markdown** (headings, tables, fenced code where appropriate — no plaintext walls). The trajectory synthesis (Phase 5) and the sell-trigger justifications must read like a plain-English explanation to a future-self who hasn't touched the thesis in 6 months. **Spell out every label in full** — write **Checkpoint 1**, **Checkpoint 2**, **Checkpoint 3** rather than any abbreviated form; write **plain-English explanation** rather than any acronym; write **10-Q / 10-K** rather than the short form; write **bull case / base case / bear case** rather than the three-letter shorthand. Any compressed label slips the user's mental model — full forms always.

---

## Mode router (Phase 1, Step 1.4)

After Phase 1's preconditions and gap-detection complete, ask the user to pick the mode using the runtime's native interactive-input:

- **Quarterly catch-up** — ingest every unprocessed 10-Q / 10-K since the last recap (or initial research), build trajectory across all of them, evaluate all sell triggers, optionally update thesis.
- **News mode** — analyze a single material event (M&A, leadership, regulatory, guidance, customer/supply, litigation, other) and its impact on the thesis.

The two flows never interleave in a single session. Quarterly catch-up proceeds to Phase 2; News mode first completes its mandatory Phase 1.5 event capture and then proceeds to Phase 2.

```
Quarterly mode → Phase 2 (fetch) → Phase 3 (refresh financials + valuation)
                → Phase 4 (per-quarter analysis) → Checkpoint 1
                → Phase 5 (trajectory + trigger eval) → Checkpoint 2
                → Phase 6 (update, optional) → Checkpoint 3
                → Phase 7 (commit + index)

News mode      → Phase 1.5 (event capture) → Phase 2 (optional context fetch)
                → Phase 3 (impact analysis) → Checkpoint 1
                → Phase 4 (update, optional) → Checkpoint 2
                → Phase 5 (commit + index)
```

## Detailed workflows

- Always load `references/shared-phase-and-quarterly-workflow.md` first for shared Phase 1 preconditions, gap detection, and mode selection.
- If the user selects **Quarterly catch-up** or **Valuation-only recap**, continue in that reference for the complete quarterly checkpoints, update, commit, and reporting flow.
- If the user selects **News mode**, stop at the shared branch point and load `references/news-workflow.md` for event capture, optional context fetches, impact analysis, checkpoints, update, commit, and reporting.

After mode selection, load only the selected mode's workflow material. Preserve the phase order, return contracts, user gates, and output templates from the applicable reference.
