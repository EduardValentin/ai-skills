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

2. **Python venv.** The skill's scripts directory has its own venv with all dependencies. If missing, set up:
   ```bash
   cd ~/.claude/skills/stock-research/scripts
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

3. **Research repo exists.** The skill writes artifacts to `/Users/trocaneduard/Documents/Personal/investing-research/`. If this directory doesn't exist, abort with the bootstrap instructions (see "Recovery" below).

## Asking the user for input

**When the workflow needs a decision among a small set of mutually exclusive options, use the runtime's native interactive-input capability rather than printing the choices as plain text and waiting for a typed reply.** Whatever the agent platform provides (Claude Code, Codex, or another runtime) for surfacing structured prompts to the user — a picker, a button row, a multiple-choice modal, an `ask_user`-style tool, etc. — use that mechanism so the user can pick instead of type.

Apply this at every place in the workflow where the choice space is finite and enumerable:

- **Phase 1 — existing-folder gate:** 3 options (Refresh / Archive & restart / Abort)
- **Phase 1 — GVD lens:** 5 options (growth / quality-growth / value / dividend / speculative-growth)
- **Phases 3–7 batch — per-failed-phase recovery:** 3 options (Retry / Skip & continue / Abort)
- **Phase 5 transcript fallback:** 2 options (Paste transcript inline / Skip this quarter)
- **Each checkpoint (CP1, CP2, CP3, CP4):** 2 options (Continue / Push back & revise) — when the user pushes back, the follow-up is free-form, not a picker
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
- **Blockquotes:** Use `>` for content quoted verbatim from artifact files (especially the ELI5 paragraph pasted into CP1) and for any prompt you're posing to the user.
- **Currency & numbers:** Format consistently — `$391.0B`, `$195.50`, `46.2%`, `+5%`. Never raw scientific notation in chat (`391035000000` is unreadable; `$391.0B` is fine).
- **Status indicators:** Use emoji sparingly but meaningfully when status is binary — ✅ for pass, ⚠️ for warning, ❌ for fail, ⬆ / ⬇ / ↔ for trend direction.
- **Code blocks:** Triple-backtick blocks for any shell command shown to the user. Specify the language (` ```bash`, ` ```json`).

For artifact files (the on-disk `.md` outputs), the same Markdown discipline applies — frontmatter at the top, then well-structured Markdown body. Subagents already follow this in their phase prompts.

## Workflow overview

Ten phases, four user checkpoints:

```
Phase 1: Setup & identity                   [main agent + user]
   |
Phase 2: Business model + moat              [subagent: phases/02-business-model.md]
   |
   --- CHECKPOINT 1: confirm business understanding ---
   |
Phases 3–7: parallel batch
   ├── Phase 3: Financials                  [subagent: phases/03-financials.md]
   ├── Phase 4: Competitors + SWOR          [subagent: phases/04-competitors-swor.md
   │                                                   + sub-subagent per competitor]
   ├── Phase 5: Earnings calls (last 3)     [subagent: phases/05-earnings-calls.md
   │                                                   + sub-subagent per quarter]
   ├── Phase 6: Valuation                   [subagent: phases/06-valuation.md]
   └── Phase 7: Market expectations         [subagent: phases/07-market-expectations.md]
   |
   --- CHECKPOINT 2: discuss tone, direction, recent events ---
   |
Phase 8: Bull/Base/Bear projections          [main agent + user, interactive brainstorm]
   |
   --- CHECKPOINT 3: projection refinement ---
   |
Phase 9: Verdict & price-action plan         [main agent + user]
   |
   --- CHECKPOINT 4: verdict approval ---
   |
Phase 10: Commit & index                     [main agent, sync]
```

## Phase 1: Setup & identity

When the skill is invoked (slash command or description-triggered), the orchestrator first runs:

1. **Resolve the ticker.** Use `_lib.ticker_resolver.resolve()` via the script `<scripts>/_lib/ticker_resolver.py` — or just call it inside a one-liner:
   ```bash
   <scripts>/.venv/bin/python -c "from _lib.ticker_resolver import resolve; r = resolve('AAPL'); print(r.cik_padded, r.name)"
   ```
   If `TickerNotFound`, abort with "Ticker not found on SEC EDGAR. Confirm spelling."

2. **Echo identity.** Show the user: ticker, name, sector (sector requires an extra yfinance lookup — `<scripts>/.venv/bin/python -c "import yfinance as yf; print(yf.Ticker('AAPL').info.get('sector'))"` or skip if it's slow). Estimate market cap from yfinance for context.

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
- `ticker`, `cik_padded`, `ticker_dir`, `scripts_dir`, `raw_dir`

Wait for the subagent to write `business-and-moat.md` and return its summary.

After the subagent returns, **mirror artifacts to the install dir** (per the Plan 2 mirror policy):
```bash
cp <ticker_dir>/business-and-moat.md  # (the orchestrator handles install-dir mirror at end-of-phase)
```

(Note: ticker-folder artifacts live in the research repo, not the install dir. The install dir mirrors the SKILL itself, not user artifacts. Only the SKILL tree mirrors to `~/.claude/skills/stock-research/` — that mirror is maintained by per-edit `cp` during skill development, not during runtime.)

## Checkpoint 1

**Before rendering CP1: read the ELI5 section (the first `### 1. ELI5...` block) from `<ticker_dir>/business-and-moat.md` — the file the Phase 2 subagent just wrote. The CP1 message MUST lead with that ELI5 verbatim. Do not paraphrase, shorten, or "compress for the chat." The whole point of ELI5 is that it's the same plain-language voice the user wants to see at the top of the conversation, not just buried in the file. If the ELI5 section in the file is itself jargon-heavy (uses terms like "ACV", "ARR", "platform", "operating leverage", "low-code", "workflow OS"), that's a Phase 2 failure — re-dispatch the subagent with explicit feedback before rendering CP1.**

Format (output exactly this Markdown shape — render it as Markdown in the chat, not inside a code block):

```markdown
## Checkpoint 1 — Business Model & Moat

*Drafted at `<ticker_dir>/business-and-moat.md`.*

### Explain like I'm in 5th grade

> <Paste the ELI5 section from business-and-moat.md verbatim — typically 3-6 short paragraphs of plain language covering every business area the company operates in. Banned vocabulary in this block: ACV, ARR, NDR, NRR, TAM, SAM, platform-as-a-service, workflow OS, low-code, operating leverage, vertical, monetization, take rate, attach rate, GAAP/non-GAAP — and any other jargon. If you can't explain a segment in 10-year-old English, the ELI5 wasn't written right.>

### Technical summary

<3-5 sentences of load-bearing findings: segments + revenue mix with specific dollar/percent numbers, moat verdict + trajectory + key evidence, leadership/insider signal, top 2-3 risks. Jargon allowed here — this is the analyst voice.>

### Quick verification

Before we fan out the data-gathering batch:

1. Does the ELI5 match how YOU think about this business?
2. Any segment, geography, or customer-concentration risk I missed?
3. Moat — am I overrating or underrating any of pricing power / network / scale / brand?
4. Anything you already know that should color the rest of the analysis?
```

**Use the runtime's native interactive-input mechanism for the Continue / Push back & revise choice** — printing the question block above and then surfacing two structured options. If the user picks "Push back & revise," the follow-up reply is free-form text.

Wait for user input. Possible responses:
- "Continue" → proceed to Phases 3–7 batch
- "Push back & revise" → engage free-form. Corrections get relayed to a fresh Phase 2 subagent (re-dispatch with the user's corrections in the context) → return to Checkpoint 1.

## Phases 3–7: parallel batch

Dispatch FIVE subagents in parallel (single message with five Agent tool calls). Each gets its phase prompt file as content, plus the standard context block:

- Phase 3 — `phases/03-financials.md`
- Phase 4 — `phases/04-competitors-swor.md` (which itself fans out to per-competitor sub-subagents)
- Phase 5 — `phases/05-earnings-calls.md` (which fans out to per-quarter sub-subagents) — also inject `company_slug` (your best guess from the company name, lowercase, hyphens for spaces)
- Phase 6 — `phases/06-valuation.md`
- Phase 7 — `phases/07-market-expectations.md`

Wait for all 5 to return.

**Failure handling in the batch:**

| Returned status | Action |
|---|---|
| All 5 `DONE` | Proceed to Checkpoint 2 |
| 1–2 `DONE_WITH_CONCERNS` | Proceed; flag concerns in Checkpoint 2 summary |
| Any `BLOCKED` | Surface to user via **the runtime's native interactive-input mechanism**: "Phase X failed because <reason>." with 3 options — Retry / Skip & continue / Abort |
| Any `NEEDS_CONTEXT` (almost always from Phase 5's transcript scrapers) | Surface to user via **native interactive input** with 2 options — Paste transcript inline / Skip this quarter. If "paste", read the transcript content as the next free-form message and re-dispatch only that single sub-subagent with `--manual`. |

## Checkpoint 2

Format (rendered Markdown, not inside a code block):

```markdown
## Checkpoint 2 — Earnings Calls: Tone, Direction, Recent Events

*Last 3 calls analyzed at `<ticker_dir>/earnings-calls/`. Cross-call themes at `<ticker_dir>/earnings-calls/cross-call-themes.md`.*

### Tone & cross-call summary

<Paste Phase 5's tone-trajectory + cross-call summary — 2-4 paragraphs. Use blockquotes for any verbatim mgmt quotes you cite.>

### Worth discussing before projections

1. <Phase 5's "CP2 prep" items, 3–5 bullets — specific events / guidance / KPI shifts the user should weigh in on>
2. ...
```

**Use the runtime's native interactive-input mechanism for the Continue / Discuss further choice** at the end of CP2. If the user picks "Discuss further," the follow-up dialogue is free-form text — this is the most conversation-heavy checkpoint, and the user often has a take on recent events that should color the projections. Engage substantively before continuing.

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

## Checkpoint 3

Format (rendered Markdown, not inside a code block):

```markdown
## Checkpoint 3 — Projection Refinement

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

**Use the runtime's native interactive-input mechanism for the Continue / Revise projections choice** at the end of CP3.

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

## Checkpoint 4

Format (rendered Markdown, not inside a code block):

```markdown
## Checkpoint 4 — Verdict Approval

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

**Use the runtime's native interactive-input mechanism for the Approve & commit / Push back choice** at the end of CP4.

## Phase 10: Commit & index

After Checkpoint 4 approval:

1. **Update `tickers.json`** atomically:
   ```bash
   <scripts>/.venv/bin/python <scripts>/upsert_ticker.py <TICKER> \
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
   <scripts>/.venv/bin/python <scripts>/update_index.py \
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
  ### ❌ Setup needed: scripts venv

  Set up the skill venv:

  ```bash
  cd ~/.claude/skills/stock-research/scripts
  python -m venv .venv
  .venv/bin/pip install -r requirements.txt
  ```
  ````

## File references

- `phases/02-business-model.md` through `phases/07-market-expectations.md` — subagent prompts
- `references/gvd-tailoring.md`, `references/projection-kpis.md`, `references/sizing-matrix.md`, `references/investor-gates.md`, `references/sell-trigger-templates.md`, `references/watch-kpis-by-gvd.md` — Phase 8/9 reference data
- `scripts/mirror.sh` — refresh install-dir from worktree
- `scripts/` — Plan 1 Python scripts (call via `<scripts>/.venv/bin/python <script>.py`)

## Iron rule: never write to user code

This skill only writes to the research repo at `/Users/trocaneduard/Documents/Personal/investing-research/`, the skill's own `.raw/` cache, and stdout. It does NOT touch the user's code projects, git config, or anything outside the research-repo path. The Python scripts are read-only (no edits) — they're already shipped by Plan 1.
