# `stock-research` Skill — Plan 2: Orchestration & Deployment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the SKILL.md + per-phase prompts + references for both Claude Code and Codex variants of the `stock-research` skill, mirror them to install dirs, duplicate Plan 1's scripts into the Codex tree, bootstrap the research repo, and validate end-to-end on AAPL.

**Architecture:** Two physically duplicated skill trees (`claude/skills/stock-research/` and `codex/skills/stock-research/`) built around a small SKILL.md that orchestrates and lazy-loads per-phase subagent prompts (`phases/`) and reference data (`references/`) on demand. Per-edit `cp` keeps install dirs continuously synced; `mirror.sh` provides a full-refresh backstop. Plan 1's scripts are physically duplicated into the Codex variant so each skill is self-contained.

**Tech Stack:** Markdown (SKILL.md, phase prompts, references), YAML (frontmatter, Codex `agents/openai.yaml`), Bash (`mirror.sh`), Python (Plan 1 scripts — used, not modified). The skill files themselves carry no test suite; validation happens via the end-to-end AAPL dry run in Task 22.

**Spec references:**
- Plan 2 spec: `docs/superpowers/specs/2026-05-11-stock-research-plan-2-design.md` (commit `f92fee5`)
- Overall skill spec: `docs/superpowers/specs/2026-05-11-stock-research-skill-design.md` (commit `c8fdc67`)
- Plan 1: `docs/superpowers/plans/2026-05-11-stock-research-plan-1-scripts.md` — already complete, current HEAD `5214db1`

**Setup gate before starting:**
- `SR_SEC_USER_AGENT="Eduard Trocan eduard.valentin1996@gmail.com"` must be exported (matches Plan 1).
- All Plan 1 scripts must be present at `claude/skills/stock-research/scripts/`. Confirm: `ls claude/skills/stock-research/scripts/_lib/ | wc -l` ≥ 5.

---

## File Structure (what this plan creates)

```
claude/skills/stock-research/
├── SKILL.md                              ~250 lines — orchestrator
├── commands/
│   └── stock-research.md                 slash command wrapper
├── phases/
│   ├── 02-business-model.md
│   ├── 03-financials.md
│   ├── 04-competitors-swor.md
│   ├── 04-competitor-sub.md
│   ├── 05-earnings-calls.md
│   ├── 05-earnings-call-sub.md
│   ├── 06-valuation.md
│   └── 07-market-expectations.md
├── references/
│   ├── gvd-tailoring.md
│   ├── projection-kpis.md
│   ├── sizing-matrix.md
│   ├── investor-gates.md
│   ├── sell-trigger-templates.md
│   └── watch-kpis-by-gvd.md
└── scripts/                              from Plan 1
    ├── mirror.sh                         NEW in Plan 2
    └── (existing _lib, top-level scripts, tests, fixtures, requirements.txt, pytest.ini, README.md)

codex/skills/stock-research/
├── (same tree as Claude variant)
├── agents/openai.yaml                    Codex agent metadata
└── scripts/                              duplicate of Plan 1 scripts (physical copy)

~/.claude/skills/stock-research/          mirrored from claude/skills/stock-research/
~/.codex/skills/stock-research/           mirrored from codex/skills/stock-research/

/Users/trocaneduard/Documents/Personal/investing-research/   research repo (bootstrap)
├── README.md
├── INDEX.md
├── tickers.json
├── .gitignore
├── tickers/                              empty for now
├── notes/
└── archive/
```

---

## Task 1: Claude variant directory scaffold + `mirror.sh`

**Files:**
- Create: `claude/skills/stock-research/SKILL.md` (skeleton; full body comes in Task 16)
- Create: `claude/skills/stock-research/commands/stock-research.md`
- Create: `claude/skills/stock-research/scripts/mirror.sh`
- Create: `claude/skills/stock-research/phases/.gitkeep`
- Create: `claude/skills/stock-research/references/.gitkeep`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p claude/skills/stock-research/commands
mkdir -p claude/skills/stock-research/phases
mkdir -p claude/skills/stock-research/references
touch claude/skills/stock-research/phases/.gitkeep
touch claude/skills/stock-research/references/.gitkeep
```

- [ ] **Step 2: Write `SKILL.md` skeleton**

File: `claude/skills/stock-research/SKILL.md`

```markdown
---
name: stock-research
description: Use when researching a US-listed company end-to-end — fundamentals deep dive, building or refreshing an investment thesis, evaluating whether to buy/watch/avoid at the current price. Triggers on phrases like "research AAPL", "deep dive on Microsoft", "should I buy NVDA", "analyze TSLA's fundamentals". Long-running session (1–2 hours) producing durable artifacts in a separate git-versioned research repo. Not for: short-term trading, technical analysis, options strategies, or stock-recap (quarterly update of an existing thesis — that's a separate skill).
---

# Stock Research

End-to-end fundamentals research on a US-listed company, following a long-horizon, business-owner investing philosophy (Buffett/Munger/Dalio, modernized). Produces a durable thesis on disk that the user revisits over years and that the future `stock-recap` skill can mechanically diff against new quarterly results.

**Body to be filled in by Task 16.**
```

- [ ] **Step 3: Write `commands/stock-research.md` slash-command wrapper**

File: `claude/skills/stock-research/commands/stock-research.md`

```markdown
---
description: Start a stock-research session on a US-listed ticker. Usage: /stock-research <TICKER>
argument-hint: <TICKER>
---

Start a `stock-research` session on the ticker {{args}}.

Invoke the `stock-research` skill and pass the ticker symbol as the initial input. The skill's Phase 1 will resolve the ticker, confirm the GVD lens with the user, and proceed through all 10 phases.
```

- [ ] **Step 4: Write `scripts/mirror.sh`**

File: `claude/skills/stock-research/scripts/mirror.sh`

```bash
#!/usr/bin/env bash
# Mirror this skill tree to the corresponding install directory.
# Auto-detects target based on script location:
#   <repo>/claude/skills/stock-research/scripts/mirror.sh  -> ~/.claude/skills/stock-research/
#   <repo>/codex/skills/stock-research/scripts/mirror.sh   -> ~/.codex/skills/stock-research/
#
# Usage:
#   ./mirror.sh           refresh install dir from worktree
#   ./mirror.sh --dry     show what would be copied
#
# Excluded from sync: .venv/, .pytest_cache/, __pycache__/, .git
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
SKILL_NAME="$(basename "$SKILL_DIR")"
PLATFORM_DIR="$(basename "$(dirname "$(dirname "$SKILL_DIR")")")"

case "$PLATFORM_DIR" in
  claude) TARGET="$HOME/.claude/skills/$SKILL_NAME" ;;
  codex)  TARGET="$HOME/.codex/skills/$SKILL_NAME"  ;;
  *)
    echo "error: cannot determine target install dir from path $SKILL_DIR" >&2
    echo "       expected to live under .../{claude,codex}/skills/$SKILL_NAME/" >&2
    exit 2
    ;;
esac

DRY=""
[[ "${1:-}" == "--dry" ]] && DRY="--dry-run"

echo "Mirroring $SKILL_DIR -> $TARGET"
mkdir -p "$TARGET"
rsync -av --delete $DRY \
  --exclude='.venv/' \
  --exclude='.pytest_cache/' \
  --exclude='__pycache__/' \
  --exclude='.git' \
  --exclude='.DS_Store' \
  "$SKILL_DIR/" "$TARGET/"

echo "Done."
```

- [ ] **Step 5: Make `mirror.sh` executable**

```bash
chmod +x claude/skills/stock-research/scripts/mirror.sh
```

- [ ] **Step 6: Verify the scaffold**

```bash
ls claude/skills/stock-research/
# Expected: SKILL.md  commands/  phases/  references/  scripts/

ls claude/skills/stock-research/scripts/
# Expected: includes mirror.sh + the Plan 1 files (_lib, scripts, tests, etc.)

claude/skills/stock-research/scripts/mirror.sh --dry 2>&1 | head -5
# Expected: prints "Mirroring ... -> /Users/trocaneduard/.claude/skills/stock-research"
```

- [ ] **Step 7: Commit**

```bash
git add claude/skills/stock-research/SKILL.md \
        claude/skills/stock-research/commands/ \
        claude/skills/stock-research/phases/.gitkeep \
        claude/skills/stock-research/references/.gitkeep \
        claude/skills/stock-research/scripts/mirror.sh
git commit -m "stock-research(claude): scaffold skill tree + slash command + mirror.sh"
```

---

## Task 2: `references/gvd-tailoring.md`

**Files:**
- Create: `claude/skills/stock-research/references/gvd-tailoring.md`

- [ ] **Step 1: Write the file**

File: `claude/skills/stock-research/references/gvd-tailoring.md`

```markdown
---
artifact: reference
purpose: GVD-bucket tailoring rules for Phase 7 (projections) and Phase 8 (verdict)
schema_version: 1
---

# GVD Tailoring

When the user declares the GVD lens in Phase 1, that lens shapes how Phase 8 (Bull/Base/Bear projections) and Phase 9 (Verdict) emphasize KPIs and push back on assumptions. Apply the table below at projection time, and challenge the user if the declared lens disagrees with the data the earlier phases produced.

## Bucket emphasis & pushback rules

| Bucket | Primary lever in projections | Secondary lever | Pushback the agent must apply |
|---|---|---|---|
| **Growth** | Revenue growth rate (years 1–5) | Margin expansion | Warn against flat-high exit P/E. Multiples almost always compress as growth slows. A 30%-grower today should NOT be modeled at 40× exit P/E at Y5 without an unusually strong reason. |
| **Quality-growth** | Margin stability + buyback-driven EPS leverage | Modest revenue growth | Challenge "margin expansion forever" — operating margins saturate. ROIC must hold or expand; if it's degrading, the compounder thesis is weakening. |
| **Value** | Exit P/E re-rating (multiple expansion) | Total shareholder yield (buybacks + dividends + debt paydown) | Demand a *catalyst* for the re-rating. "It's cheap" is not a thesis. What changes in the next 5 years that makes the market reassess? |
| **Dividend** | Dividend growth rate + payout safety | Total return (price CAGR + reinvested dividends) | Challenge any drift of payout ratio toward 100%. FCF/dividend coverage below 1.2× = thin. Bond-proxy names usually keep similar exit P/E. |
| **Speculative growth** | Path to profitability — when does FCF turn positive | Burn rate, runway, dilution along the way | Position sizing is capped small regardless of how good projections look (enforced in Phase 9). Model dilution explicitly. |

## When data disagrees with declared GVD

If the user declared, say, "dividend" but the data shows FCF/dividend coverage at 1.05× trending down, the orchestrator at the start of Phase 8 challenges:

> "You said dividend, but FCF/dividend coverage is 1.05× and trending down over the last 3 years. Are we researching this as a dividend anchor or as a turnaround? The lens changes the conversation."

User can confirm dividend (with the risk acknowledged), switch to another bucket, or pause to discuss.

## Position-sizing implications (covered in Phase 9, see sizing-matrix.md)

Position-sizing target % depends on bucket + conviction. The bucket emphasis above ALSO informs which "watch KPIs" we track quarterly (see `watch-kpis-by-gvd.md`).
```

- [ ] **Step 2: Commit**

```bash
git add claude/skills/stock-research/references/gvd-tailoring.md
git commit -m "stock-research(claude): add references/gvd-tailoring.md"
```

---

## Task 3: `references/projection-kpis.md`

**Files:**
- Create: `claude/skills/stock-research/references/projection-kpis.md`

- [ ] **Step 1: Write the file**

File: `claude/skills/stock-research/references/projection-kpis.md`

```markdown
---
artifact: reference
purpose: Full KPI list + formulas for Phase 8 Bull/Base/Bear projections
schema_version: 1
---

# Projection KPIs

Phase 8 (Bull/Base/Bear projections) produces a five-year table for each scenario. Every cell below must be present in `projections.json`. Markdown view (`projections.md`) renders the same data in human-readable form, plus assumptions and reasoning.

## Per year (Y1–Y5), per scenario (bull / base / bear)

| KPI | Formula / source |
|---|---|
| `revenue` | Locked in dialogue with user — anchored in historical 5-yr trend + peer averages + mgmt guidance + analyst consensus |
| `revenue_growth_pct` | `(revenue_yN - revenue_y(N-1)) / revenue_y(N-1) * 100` |
| `gross_margin_pct` | Locked in dialogue — trajectory matters more than year 1 number |
| `operating_margin_pct` | Locked in dialogue — cleanest read on operating leverage |
| `net_income` | Locked or derived; if derived, `revenue * net_margin_pct` |
| `net_income_growth_pct` | `(net_income_yN - net_income_y(N-1)) / net_income_y(N-1) * 100` |
| `net_margin_pct` | `net_income / revenue * 100` |
| `fcf` | Locked or derived; sanity check vs net income (FCF usually ≈ net income for capital-light, lower for capex-heavy) |
| `fcf_margin_pct` | `fcf / revenue * 100` |
| `shares_diluted` | Locked — must account for SBC dilution and buybacks |
| `eps` | `net_income / shares_diluted` |
| `fcf_per_share` | `fcf / shares_diluted` |
| `dividend_per_share` | Locked (0 for non-payers) |
| `net_debt` | Optional — only model if balance sheet is a live concern |
| `roic_pct` | Optional — recommended for compounders. `nopat / invested_capital * 100` |
| `pe_low` | Locked — exit P/E low estimate at year N |
| `pe_high` | Locked — exit P/E high estimate at year N |
| `share_price_low` | `eps * pe_low` |
| `share_price_high` | `eps * pe_high` |
| `cumulative_dividends` | Running sum of `dividend_per_share` from Y1 |

## Scenario-level summary (computed at Y5)

| KPI | Formula |
|---|---|
| `probability` | Locked in dialogue (bull + base + bear = 1.0) |
| `price_cagr_low_5yr` | `((share_price_low_y5 / current_price) ^ (1/5)) - 1` |
| `price_cagr_high_5yr` | Same with `share_price_high_y5` |
| `total_return_cagr_low_5yr` | Includes reinvested dividends — `((y5_share_price_low + cumulative_dividends_y5) / current_price) ^ (1/5) - 1` |
| `total_return_cagr_high_5yr` | Same with high share price |

## Cross-scenario summary

| KPI | Formula |
|---|---|
| `probability_weighted_total_return_cagr_5yr` | `sum(scenario.probability * scenario.total_return_cagr_low_5yr` for each scenario, then same for high; report a range) |
| `bear_max_drawdown_from_today_pct` | `(bear.share_price_low_y1 / current_price) - 1` if Y1 ≤ today, otherwise the lowest Yn point on the bear curve |
| `implied_margin_of_safety_today_pct` | `(base.share_price_low_y1 / current_price) - 1` |

## Dividend-bucket additions (only for dividend GVD)

| KPI | Formula |
|---|---|
| `payout_ratio_pct` | `dividend_per_share * shares_diluted / net_income * 100` |
| `fcf_dividend_coverage` | `fcf / (dividend_per_share * shares_diluted)` |

## Dialogue flow

The orchestrator locks one row at a time, in this order:

1. Revenue growth path (Y1 → Y5) — base case first, then perturb for bull/bear
2. Gross margin trajectory
3. Operating margin trajectory
4. Net margin trajectory (or derive from above two + reasonable tax assumption)
5. Share count trajectory (SBC dilution + buybacks)
6. Dividend per share trajectory
7. Exit P/E low / high at Y5
8. Compute prices and CAGRs
9. Repeat steps 1–8 for bull (perturbation deltas from base)
10. Repeat for bear
11. Lock probabilities (bull + base + bear = 1.0)
12. Compute probability-weighted return + bear drawdown + implied margin of safety today
```

- [ ] **Step 2: Commit**

```bash
git add claude/skills/stock-research/references/projection-kpis.md
git commit -m "stock-research(claude): add references/projection-kpis.md"
```

---

## Task 4: `references/sizing-matrix.md`

**Files:**
- Create: `claude/skills/stock-research/references/sizing-matrix.md`

- [ ] **Step 1: Write the file**

File: `claude/skills/stock-research/references/sizing-matrix.md`

```markdown
---
artifact: reference
purpose: Position-sizing rules for Phase 9 verdict (target % + scaling-in plan)
schema_version: 1
---

# Position-Sizing Matrix

Used in Phase 9 to recommend target % of portfolio and a scaling-in plan. **The user leans into risk when reward justifies — the agent will not be paternalistic about sizing when bull/base asymmetry is favorable.** Surface the asymmetry; respect the user's call within the matrix.

## Target % of portfolio

| GVD bucket + Conviction | Target % |
|---|---|
| Speculative growth (unprofitable), any conviction | 1–3% (small, period — sizing cap enforced regardless of how good projections look) |
| Quality / value / growth, Low conviction | 2–4% (probe size) |
| Quality / value / growth, Medium conviction | 4–6% (normal) |
| Quality / value / growth, High conviction | 6–9% (anchor) |
| Dividend, Medium-High conviction | 5–8% (dividend anchor) |

When the bull/base asymmetry is favorable (e.g., bear case downside <20% but bull case upside >100%), the agent surfaces this and may recommend the top end of the conviction range rather than the middle. It does not unilaterally exceed the range.

## Scaling-in plan (depends on margin of safety today)

`Margin of safety today` = `(base.share_price_low_y1 / current_price) - 1`, computed in Phase 8.

| Margin of safety today | Scaling-in plan |
|---|---|
| **>25%** | Deploy full target position immediately |
| **10–25%** | 1/3 of target now, 1/3 at -10% drawdown, 1/3 at -20% drawdown |
| **<10%** | 1/4 starter, balance scaled in on -15% to -25% drawdown |
| **negative** (current price > base Y1 fair value low) | Watch only — no position until price corrects into buy zone |

## Buy zone

The verdict records concrete price ranges per tranche, e.g.:

```
buy_zone:
  tranche_1: $160-$175 (1/3 of target)
  tranche_2: $144-$158 (1/3 of target, on -10% from current)
  tranche_3: $128-$140 (1/3 of target, on -20% from current)
```
```

- [ ] **Step 2: Commit**

```bash
git add claude/skills/stock-research/references/sizing-matrix.md
git commit -m "stock-research(claude): add references/sizing-matrix.md"
```

---

## Task 5: `references/investor-gates.md`

**Files:**
- Create: `claude/skills/stock-research/references/investor-gates.md`

- [ ] **Step 1: Write the file**

File: `claude/skills/stock-research/references/investor-gates.md`

```markdown
---
artifact: reference
purpose: The 6 Munger/Buffett/Dalio gate questions for Phase 9 verdict
schema_version: 1
---

# Great-Investor Gates

Phase 9 must answer all 6 of these questions in prose in `verdict.md` before a BUY classification can issue. WATCH and AVOID classifications still answer them (the answers explain why we're not buying), but only BUY blocks on completeness.

## The questions

### 1. Munger inversion
**"What's the most likely way this company is worth materially less in 10 years than today?"**

Forces explicit bear thesis. If you can't articulate the path to value destruction, you don't understand the risk. Common answers: disruption (new technology), commoditization (loss of pricing power), capital-allocation failure (overpaying for M&A), regulatory shock, balance-sheet stress in recession.

### 2. Buffett 10-year market closure
**"Would you be comfortable owning this if the market closed for 10 years and you couldn't trade?"**

Tests business confidence vs. trading confidence. If the answer is "I'd want to sell out," the position size is wrong — or the business isn't durable enough for the time horizon.

### 3. Steelmanned short case
**"What would the smartest bear argue, and why are they wrong (or right)?"**

Munger: "Tell me where I'm wrong." Forces engagement with the strongest opposing view, not the strawman. If the steelman is uncomfortable, the thesis needs more work.

### 4. Moat trajectory
**"Is the moat widening or narrowing based on the last 3 years of evidence? Point to specific data."**

Abstract "they have a moat" is not enough. Specific evidence: gross margin trend, retention metrics, share gains, switching cost disclosures, R&D vs revenue, etc. A narrowing moat at a flat price is a sell signal.

### 5. Dalio regime fit
**"Risk-on or risk-off today? How does this name fit current GVD allocation and correlate with existing positions?"**

The methodology calls for a GVD mix that's always partially in/out of favor. New positions should improve diversification, not concentrate exposure. In risk-on markets, tilt buying toward value/dividend; in risk-off, toward growth.

### 6. Circle of competence
**"Explain in 5 sentences using first-principle business mechanics (no jargon) why this company makes more money in 10 years than today."**

Self-check. If you can't explain it simply, you're outside your circle. "AI tailwinds" / "secular growth" / "category leader" is jargon, not mechanics. Mechanics looks like: "they sell X to Y customers who keep buying because Z, the customer base is growing at A%, and each customer spends B% more each year because of C."

## Output format in `verdict.md`

Each gate gets a `### N. Title` section with a 1–3 paragraph answer. No bullet-only answers. Show your thinking.

For BUY classifications, the orchestrator checks that all 6 sections are present and non-trivial before issuing the verdict. If any gate is missing or evasive (e.g., "TBD" or one-line dismissals), the verdict cannot be BUY — it falls back to WATCH with a note about which gate needs more work.
```

- [ ] **Step 2: Commit**

```bash
git add claude/skills/stock-research/references/investor-gates.md
git commit -m "stock-research(claude): add references/investor-gates.md"
```

---

## Task 6: `references/sell-trigger-templates.md`

**Files:**
- Create: `claude/skills/stock-research/references/sell-trigger-templates.md`

- [ ] **Step 1: Write the file**

File: `claude/skills/stock-research/references/sell-trigger-templates.md`

```markdown
---
artifact: reference
purpose: How to write thesis-broken sell triggers in Phase 9 verdict
schema_version: 1
---

# Sell Triggers

The user's methodology has three exit conditions. Phase 9 encodes the first two as concrete, measurable, KPI-tied thresholds at verdict time. These get auto-checked by the future `stock-recap` skill each quarter.

## Sell condition 1: Materially overvalued

Pick one or both:

- **Bull-case overshoot:** "Sell if price exceeds bull-case Y5 fair value, i.e., **$X**" (use the bull case's `share_price_high_y5` from `projections.json`).
- **Reverse-DCF overshoot:** "Sell if reverse-DCF-implied growth at current price exceeds **N%**" (a number the agent picks based on what's plausible for the bucket — for a quality-growth name, ~15% might be the line; for a speculative name, ~25%).

## Sell condition 2: Thesis broken

**3–5 named KPI breach conditions**, story-dependent. The list MUST be specific, measurable, and tied to actual financials. Each trigger is a one-sentence rule that can be auto-evaluated against quarterly data by `stock-recap`.

### Good triggers (specific, measurable)

- "Revenue growth falls below 10% YoY for two consecutive quarters"
- "Gross margin compresses below 65%"
- "Net dollar retention drops below 110%"
- "Customer concentration exceeds 25% from any single client"
- "FCF/dividend coverage falls below 1.1× for two consecutive quarters" (dividend names)
- "Cash burn extends runway below 18 months without raising capital" (speculative names)
- "Capex intensity exceeds 15% of revenue for two consecutive years" (typical capital-light name turning capital-heavy)

### Bad triggers (vague, unmeasurable)

- "Sell if the moat weakens" — what does that mean numerically?
- "Sell if management makes bad decisions" — define "bad"
- "Sell if growth slows" — by how much, over what period?

## Sell condition 3: Better opportunity

Not pre-definable; the framework leaves room. The verdict notes this as: "Sell if a clearly better opportunity emerges (higher conviction, more favorable bull/base asymmetry, better margin of safety) — judged at portfolio level."

## Output format

In `verdict.md`, the Sell Triggers section reads:

```
## 7. Sell triggers

### Materially overvalued
- Bull-case overshoot: $X
- Reverse-DCF overshoot: implied growth > N%

### Thesis broken (any one triggers re-evaluation)
1. Revenue growth < 10% YoY for 2 consecutive quarters
2. Gross margin < 65%
3. ...
4. ...
5. ...

### Better opportunity
- Re-evaluated quarterly against the rest of the portfolio.
```

In `verdict.json`, the same data lives under `sell_triggers.materially_overvalued` (array) and `sell_triggers.thesis_broken` (array of strings).
```

- [ ] **Step 2: Commit**

```bash
git add claude/skills/stock-research/references/sell-trigger-templates.md
git commit -m "stock-research(claude): add references/sell-trigger-templates.md"
```

---

## Task 7: `references/watch-kpis-by-gvd.md`

**Files:**
- Create: `claude/skills/stock-research/references/watch-kpis-by-gvd.md`

- [ ] **Step 1: Write the file**

File: `claude/skills/stock-research/references/watch-kpis-by-gvd.md`

```markdown
---
artifact: reference
purpose: Default quarterly watch-KPI lists per GVD bucket (Phase 9 verdict)
schema_version: 1
---

# Quarterly Watch KPIs

Each verdict carries a watchlist of KPIs the future `stock-recap` skill checks every quarter. The verdict has **two sets**:

- **Generic GVD-default set (5 KPIs)** — taken directly from the table below based on the declared bucket.
- **Story-custom set (3–5 KPIs)** — brainstormed with the user during Phase 9 because every company has unit economics that matter specifically to it ("restaurants opened per year", "average selling price", "rig count", "ARPU", "active customers").

## Generic defaults by bucket

| Bucket | 5 default watch KPIs |
|---|---|
| **Growth** | Revenue YoY, gross margin, FCF margin, NDR (if SaaS) or active users, unit economics (CAC, payback period) |
| **Quality-growth** | Revenue YoY, operating margin, FCF / share, buyback yield, ROIC |
| **Value** | Revenue YoY, operating margin, total shareholder yield, debt paydown, P/E vs historical band |
| **Dividend** | Dividend per share, payout ratio, FCF / dividend coverage, dividend growth %, total return YTD |
| **Speculative growth** | Revenue YoY, gross margin, cash burn rate, runway in months, dilution YoY |

## Story-custom set: dialogue

In Phase 9, after presenting the generic defaults, the orchestrator asks:

> "Beyond the generic GVD watch list, what 3–5 KPIs specific to *this* business should we track each quarter? Think about what would tell you the thesis is on track or breaking down."

Examples by industry:

- **Restaurant chains:** new restaurants opened YoY, same-store sales growth, food cost % of revenue
- **SaaS:** logo count, NDR by cohort, ARR growth, free-to-paid conversion
- **Energy E&P:** average realized price, production growth, F&D cost per BOE, debt/EBITDAX
- **Banks:** net interest margin, efficiency ratio, NCO rate, CET1 ratio
- **Retail/consumer:** comp sales, average selling price, inventory turns, gross margin
- **Auto:** unit volume, ASP, gross margin per vehicle, capex intensity
- **Semiconductors:** revenue mix by end market, gross margin trend, capex/revenue, customer concentration

The story-custom KPIs are written in plain English (same shape as the generic ones) and stored in `verdict.json` under `watch_kpis.story_custom` (array of strings).

## Output format

In `verdict.md`, the Quarterly Watch KPIs section reads:

```
## 8. Quarterly watch KPIs

### Generic (GVD-default for this bucket)
1. Revenue YoY
2. Gross margin
3. ...

### Story-custom
1. <Custom KPI 1>
2. <Custom KPI 2>
...
```

In `verdict.json`, both lists live under `watch_kpis.generic` and `watch_kpis.story_custom`.
```

- [ ] **Step 2: Commit**

```bash
git add claude/skills/stock-research/references/watch-kpis-by-gvd.md
git commit -m "stock-research(claude): add references/watch-kpis-by-gvd.md"
```

---

## Task 8: `phases/02-business-model.md`

**Files:**
- Create: `claude/skills/stock-research/phases/02-business-model.md`

- [ ] **Step 1: Write the file**

File: `claude/skills/stock-research/phases/02-business-model.md`

````markdown
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
- `scripts_dir`: absolute path to the skill's scripts directory
- `raw_dir`: `<ticker_dir>/.raw/` — gitignored, for cached source documents

## Your job

Produce **one file**: `<ticker_dir>/business-and-moat.md` with the structure below.
Return a **~500-word summary** to the orchestrator covering: ELI5 in 2–3 sentences, key segments + geographic mix, moat verdict, CEO/leadership signal, top 2–3 risks worth flagging in later phases.

## Inputs available

Run these scripts (already at `<scripts_dir>/`) before writing the file:

1. **Fetch the latest 10-K and recent 8-Ks:**
   ```bash
   <scripts_dir>/.venv/bin/python <scripts_dir>/fetch_sec.py <ticker> \
     --forms 10-K,8-K,DEF\ 14A,4 \
     --since $(date -v-2y +%Y-%m-%d) \
     --out <raw_dir>
   ```

2. **Extract structured sections from the most recent 10-K:**
   ```bash
   # Find the most recent 10-K HTML in <raw_dir>:
   tenk=$(ls -t <raw_dir>/*10-K*.html | head -1)
   tenk_year=$(echo "$tenk" | grep -oE '[0-9]{4}' | tail -1)

   <scripts_dir>/.venv/bin/python <scripts_dir>/extract_10k_sections.py <ticker> \
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
   <scripts_dir>/.venv/bin/python <scripts_dir>/compute_financials.py <ticker> \
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

### 1. ELI5 — Explain Like I'm in 5th Grade

**Required opening section. Plain language. No jargon.** Imagine explaining this company to a smart 10-year-old. Cover every business area the company operates in. If they sell 4 things, describe all 4 in simple words. If they have 3 geographies that matter, mention them.

Length: 3–6 short paragraphs.

Anti-examples (do not write these):
- "leading provider of SaaS solutions for enterprise customers" — what does that mean to a 10-year-old?
- "diversified technology conglomerate operating in cloud, advertising, and consumer hardware" — break that into actual products

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
- ELI5 section is the first thing the user sees after frontmatter — must be plain language
- Cite specific numbers and dates where possible (e.g., "Services revenue $XX.YB in FY2024, +14% YoY") rather than vague claims ("growing services business")
- ~500-word summary returned to orchestrator with: ELI5 in 2–3 sentences, segments + geo mix snapshot, moat verdict, leadership signal, top 2–3 risks

## Failure modes

- **Status `BLOCKED`** if:
  - `fetch_sec.py` returns non-zero (ticker not on EDGAR or SEC down)
  - `extract_10k_sections.py` produces empty `item_1_business.md` (parse failure)

- **Status `DONE_WITH_CONCERNS`** if:
  - Some segment data is missing (e.g., company recently restructured)
  - DEF 14A wasn't filed in the window (smaller / foreign companies)
  - Insider data is thin
  Note the specific gaps in your summary; orchestrator decides whether to push to user at CP1.

- **Status `DONE`** if everything completed cleanly.
````

- [ ] **Step 2: Commit**

```bash
git add claude/skills/stock-research/phases/02-business-model.md
git commit -m "stock-research(claude): add phases/02-business-model.md"
```

---

## Task 9: `phases/03-financials.md`

**Files:**
- Create: `claude/skills/stock-research/phases/03-financials.md`

- [ ] **Step 1: Write the file**

File: `claude/skills/stock-research/phases/03-financials.md`

````markdown
---
artifact: phase-prompt
phase: 3
phase_name: financials
schema_version: 1
---

# Phase 3 Subagent Prompt — Financials

You are a research subagent for `stock-research`. Your job is Phase 3: financial trends + pass/fail gate.

## Context (injected by orchestrator)

- `ticker`, `cik_padded`, `ticker_dir`, `scripts_dir`, `raw_dir` (same as Phase 2)

## Your job

Produce **two files**:
- `<ticker_dir>/financials.json` — machine-readable, full schema
- `<ticker_dir>/financials.md` — human-readable companion with charts described in prose + the pass/fail gate verdict

Return a **~500-word summary** covering: revenue/net-income trend verdict (up-and-right, down-and-left, mixed), margin trajectory, FCF + SBC concerns, balance-sheet snapshot, capital-allocation scorecard.

## Inputs available

If Phase 2 already ran `compute_financials.py`, `financials.json` exists. Otherwise run:

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/compute_financials.py <ticker> \
  --years 10 \
  --out <ticker_dir>/financials.json
```

Re-read it. Use the data for the markdown companion.

## `financials.json` schema (already produced by the script)

Per `compute_financials.py` output:

```json
{
  "ticker": "AAPL",
  "cik": "0000320193",
  "name": "Apple Inc.",
  "schema_version": 1,
  "generated_at": "2026-05-11",
  "years": [
    {
      "fiscal_year": 2024,
      "revenue": 391035000000,
      "gross_profit": ...,
      "operating_income": ...,
      "net_income": ...,
      "cfo": ...,
      "capex": ...,
      "fcf": ...,
      "gross_margin_pct": ...,
      "operating_margin_pct": ...,
      "net_margin_pct": ...,
      "fcf_margin_pct": ...,
      "diluted_shares": ...,
      "eps": ...,
      "fcf_per_share": ...,
      "sbc": ...,
      "sbc_pct_of_revenue": ...,
      "buybacks": ...,
      "dividends_paid": ...,
      "cash": ...,
      "long_term_debt": ...,
      "net_debt": ...
    },
    ...
  ],
  "trend_gate": {
    "revenue_up_and_right": true | false | "mixed" | "insufficient_data",
    "net_income_up_and_right": ...,
    "fcf_up_and_right": ...
  }
}
```

Your job is NOT to regenerate this — the script did it. Your job is to write the human-readable `financials.md` companion AND verify the trend gate is correct.

## `financials.md` structure

Open with frontmatter:

```yaml
---
ticker: <TICKER>
artifact: financials
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
---
```

Then sections:

### 1. Trend verdict (the gate)

Lead with the trend gate result for the user's methodology check ("up and to the right TTM?"):

- **Revenue trend (5–10 yr):** ⬆ UP / ⬇ DOWN / ↔ MIXED — with the year-by-year numbers in a small table
- **Net income trend:** same
- **FCF trend:** same

Then a one-sentence overall verdict: **"Passes the up-and-to-the-right gate"** or **"Fails the up-and-to-the-right gate (mixed FCF)"** etc.

### 2. Margins over time

| Year | Gross % | Op % | Net % | FCF % |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

A paragraph on the margin story: are they expanding, stable, compressing? Note any inflection points (M&A, restructuring, COVID, AI capex cycle, etc.).

### 3. Stock-based compensation

| Year | SBC ($) | SBC % of revenue |
|---|---|---|

Note any concerning trend (SBC growing faster than revenue = hidden dilution). For tech companies, SBC % of revenue >5% is worth flagging; >10% is a red flag.

### 4. Capital allocation scorecard (5–10 yr)

| Year | FCF | Buybacks | Dividends | Net debt paydown / (incurred) | M&A spend |
|---|---|---|---|---|---|

A paragraph on capital-allocation track record:
- How much FCF was generated over the period?
- How much was returned to shareholders (buybacks + dividends)?
- What was the M&A pattern? Quick sanity check on value creation — do you remember any of these deals (refresh from the 10-K M&A footnotes if needed)?

### 5. Shareholder yield

Compute and report:
- **Buyback yield (TTM)** = `buybacks / market_cap` × 100. Market cap = `latest_price × diluted_shares`. (Use Phase 6's price if available; otherwise note "current price TBD.")
- **Dividend yield (TTM)** = `dividends_paid / market_cap` × 100.
- **Total shareholder yield** = buyback yield + dividend yield + debt-paydown yield.

If this can't be computed (current price not available yet because Phase 6 runs in parallel), note: "Shareholder yield to be computed in Phase 6 once current price is fetched."

### 6. Balance sheet snapshot (latest fiscal year)

- Cash: $X B
- Long-term debt: $Y B
- Net debt: $Z B (positive = net debtor, negative = net cash)
- Net debt / EBITDA: ratio (compute EBITDA approx as `operating_income + depreciation`; if depreciation isn't in the JSON, use operating income as a rough proxy and note the approximation)

A one-paragraph balance-sheet read: cash-heavy / leveraged / balanced. Mention any debt maturity walls or covenant concerns if you can find them in the 10-K.

### 7. ROIC trajectory

If `financials.json` includes ROIC per year, build a small chart-in-prose. If not, compute approximate ROIC year-by-year using: `roic = net_income / (long_term_debt + book_equity)`. Book equity isn't in our schema — note this and skip ROIC if you can't get it from another source.

## Trend-gate verification

Open `financials.json`. The `trend_gate.revenue_up_and_right` field has one of: `true`, `false`, `"mixed"`, `"insufficient_data"`.

Independent check: look at the year-by-year revenue values. Does the gate value match what you see? If not, it's a script bug — note it in your summary so the orchestrator can flag it. (Likely you'll find: gate is correct.)

## Output contract (recap)

- `financials.json` — emitted by `compute_financials.py`, untouched by you
- `financials.md` — human-readable companion you produce
- `~500-word summary` covering trend gate, margins, SBC, capital-allocation, balance sheet

## Failure modes

- **`BLOCKED`** if `compute_financials.py` returns non-zero (ticker resolution or XBRL API failure)
- **`DONE_WITH_CONCERNS`** if balance-sheet fields are sparsely populated (some companies don't report cash/LTD on the XBRL endpoint — the JSON will show `null` for those fields), or if ROIC can't be computed
- **`DONE`** otherwise
````

- [ ] **Step 2: Commit**

```bash
git add claude/skills/stock-research/phases/03-financials.md
git commit -m "stock-research(claude): add phases/03-financials.md"
```

---

## Task 10: `phases/04-competitors-swor.md`

**Files:**
- Create: `claude/skills/stock-research/phases/04-competitors-swor.md`

- [ ] **Step 1: Write the file**

File: `claude/skills/stock-research/phases/04-competitors-swor.md`

````markdown
---
artifact: phase-prompt
phase: 4
phase_name: competitors-and-swor
schema_version: 1
---

# Phase 4 Subagent Prompt — Competitors + SWOR (orchestrator)

You are the orchestrator subagent for Phase 4. You fan out to per-competitor sub-subagents, then aggregate their results into `competitors.md` and `swor.md`. You also dispatch a separate risk-factor YoY diff sub-subagent.

## Context (injected by orchestrator)

Same as Phase 2 + 3: `ticker`, `cik_padded`, `ticker_dir`, `scripts_dir`, `raw_dir`, `gvd_category`. Plus:
- `business_and_moat_summary`: the summary returned by Phase 2 (so you know what segments/moat the parent already identified)

## Your job

Produce **three files**:
- `<ticker_dir>/competitors.md` — side-by-side table + per-competitor notes
- `<ticker_dir>/swor.md` — Strengths / Weaknesses / Opportunities / Risks for the company
- `<ticker_dir>/.raw/risk-factor-diff.json` (and `.md`) — YoY diff of the last two 10-K Item 1A sections

Return a **~500-word summary** covering: who the top competitors are, how the company stacks up on key metrics, the SWOR verdict, and what changed in risk factors year-over-year.

## Step 1: Identify 3–5 direct competitors

Read `<raw_dir>/10k-sections/item_1_business.md` from Phase 2. The 10-K Item 1 often names competitors directly (especially in the "Competition" subsection). Pull 3–5 names.

If the 10-K doesn't name competitors (common for diversified companies), use the segments + sector to identify the most obvious competitors. For example:
- Apple → Samsung (smartphones), Microsoft + Google (services), Dell + HP (Macs)
- Costco → Walmart (Sam's Club), BJ's, Amazon (membership programs)

Aim for diversity: include both direct competitors and substitution threats where they matter. **Keep the list to 3–5 names.**

## Step 2: Dispatch per-competitor sub-subagents in parallel

For each competitor ticker, dispatch a sub-subagent using `phases/04-competitor-sub.md` as the prompt. Inject:
- `competitor_ticker`: the competitor's ticker
- `scripts_dir`: same path
- `raw_dir`: `<ticker_dir>/.raw/competitors/<competitor_ticker>/`

Each sub-subagent fetches its competitor's financials and returns a comparison row. You wait for all sub-subagents to finish before proceeding.

If a competitor isn't on EDGAR (foreign, private, ETF, etc.), the sub-subagent reports `NEEDS_CONTEXT`. Drop that competitor from the comparison and note it in `competitors.md` ("no public filings available").

## Step 3: Dispatch the risk-factor YoY diff sub-subagent

If `<raw_dir>/10k-sections/` has Item 1A from the most recent 10-K, also find the prior-year 10-K (it should be in `<raw_dir>` from Phase 2's `fetch_sec.py --since 2y`). Extract its Item 1A:

```bash
prior_tenk=$(ls -t <raw_dir>/*10-K*.html | sed -n '2p')
prior_year=$(echo "$prior_tenk" | grep -oE '[0-9]{4}' | tail -1)
<scripts_dir>/.venv/bin/python <scripts_dir>/extract_10k_sections.py <ticker> \
  --html "$prior_tenk" --year "$prior_year" \
  --out <raw_dir>/10k-sections-prior/
```

Then run the diff:

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/diff_risk_factors.py \
  --file-a <raw_dir>/10k-sections-prior/item_1a_risk_factors.md \
  --file-b <raw_dir>/10k-sections/item_1a_risk_factors.md \
  --ticker <TICKER> \
  --out <raw_dir>/risk-factor-diff.json \
  --out-md <raw_dir>/risk-factor-diff.md
```

This produces JSON with `added`, `removed`, `modified` paragraphs. You'll use it in Step 5.

## Step 4: Write `competitors.md`

Frontmatter:

```yaml
---
ticker: <TICKER>
artifact: competitors
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
---
```

Then:

### Side-by-side table

| Ticker | Name | Market cap | Revenue (TTM) | Rev growth (3-yr CAGR) | Gross margin | Op margin | Net margin | FCF margin | ROIC | P/E (TTM) | Diluted-share growth (3-yr) |
|---|---|---|---|---|---|---|---|---|---|---|---|

Each row is the company we're analyzing (first row, highlight it) and each competitor (returned by the sub-subagents). Use the data from each sub-subagent's returned summary.

### Per-competitor notes

For each competitor (3–5), write 3–5 sentences:
- How they overlap with the company's business
- Where they're better / worse on the key metrics
- Any strategic concerns (e.g., "Walmart's e-commerce growth is accelerating into Costco's grocery footprint")

### Competitive positioning summary

Two paragraphs:
1. Where does the company sit in this comparison? Best on which metrics? Worst on which?
2. What's the moat-vs-competitor read? Are they pulling ahead, falling behind, or holding steady?

## Step 5: Write `swor.md`

Frontmatter:

```yaml
---
ticker: <TICKER>
artifact: swor
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
---
```

Then four sections:

### Strengths

4–7 bullets. What the company does well. Anchor each to evidence — a margin number, a market-share fact, a moat dimension, a balance-sheet line. **No vague platitudes.**

### Weaknesses

4–7 bullets. What's structurally weak. Same evidence anchoring. Examples: "Single-product concentration: iPhone is 52% of revenue (FY2024)"; "Capital intensity rising — capex grew from 3% of revenue in FY20 to 4.8% in FY24."

### Opportunities

3–5 bullets. Credible growth vectors the company is positioned to capture. Examples: services attach rate; geographic expansion; adjacencies; pricing power runway. Each bullet should be specific enough that you can imagine it in the bull case (Phase 8).

### Risks

5–8 bullets. **Risks framed as "what could break the thesis"**, not abstract external threats. Pull heavily from:
- Item 1A risk factors (from Phase 2's extraction)
- The risk-factor diff (Step 3) — specifically NEW risks added year-over-year (these are the leading-edge signals)
- Competitor moves
- Macro/regulatory exposures

Each bullet should be specific and testable. Examples:
- "China revenue (17% of total) is exposed to trade-policy shocks; the FY24 10-K added a new risk factor about export controls on advanced semis."
- "Services growth depends on App Store economics, which face active antitrust scrutiny (DMA in EU, Epic lawsuit aftermath)."

### Risk-factor YoY diff highlight

A small section (3–5 sentences) calling out what NEW risks the company added in its latest 10-K vs. the prior year. This is the single-best leading indicator that management sees something the market hasn't fully priced. Use `<raw_dir>/risk-factor-diff.md` as source.

## Output contract (recap)

- `competitors.md`, `swor.md`, `.raw/risk-factor-diff.{json,md}`
- ~500-word summary covering: top competitors named, positioning verdict, SWOR essence, what's new in risk factors

## Failure modes

- **`BLOCKED`** if >50% of competitor sub-subagents fail (you can't build a comparison from 1 of 5)
- **`DONE_WITH_CONCERNS`** if:
  - Prior-year 10-K isn't in `<raw_dir>` (some companies are newly public, or fetch failed) — skip the risk diff and note it
  - Some competitor financials are incomplete (e.g., private peer with limited filings)
- **`DONE`** otherwise
````

- [ ] **Step 2: Commit**

```bash
git add claude/skills/stock-research/phases/04-competitors-swor.md
git commit -m "stock-research(claude): add phases/04-competitors-swor.md"
```

---

## Task 11: `phases/04-competitor-sub.md`

**Files:**
- Create: `claude/skills/stock-research/phases/04-competitor-sub.md`

- [ ] **Step 1: Write the file**

File: `claude/skills/stock-research/phases/04-competitor-sub.md`

````markdown
---
artifact: phase-prompt
phase: 4-sub
phase_name: per-competitor-analysis
schema_version: 1
---

# Phase 4 Sub-subagent Prompt — Per-Competitor Analysis

You are a sub-subagent dispatched by the Phase 4 orchestrator. Your job is to pull one competitor's financials and return a comparison row.

## Context (injected by Phase 4 orchestrator)

- `competitor_ticker`: the competitor's ticker (e.g., "MSFT")
- `scripts_dir`: skill scripts directory
- `raw_dir`: `<parent_ticker_dir>/.raw/competitors/<competitor_ticker>/` — your scratch space

## Your job

1. Pull the competitor's XBRL financials.
2. Compute key metrics (TTM revenue, margins, growth, P/E, etc.).
3. Write a short comparison row + per-competitor notes to `<raw_dir>/summary.md`.
4. Return a structured one-paragraph summary that the orchestrator uses to build the side-by-side table.

## Step 1: Pull financials

```bash
mkdir -p <raw_dir>
<scripts_dir>/.venv/bin/python <scripts_dir>/compute_financials.py <competitor_ticker> \
  --years 5 \
  --out <raw_dir>/financials.json
```

If `compute_financials.py` exits non-zero (e.g., the competitor isn't on EDGAR — foreign listing, private company, ETF), return status `NEEDS_CONTEXT` with the error message. The Phase 4 orchestrator will drop you from the comparison.

## Step 2: Pull price + market cap

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/fetch_prices.py <competitor_ticker> \
  --years 2 \
  --out <raw_dir>/prices/
```

If exit code 2 (yfinance returned no data), return `NEEDS_CONTEXT`.

The latest close (last bar in `prices.json`) × diluted shares (from financials.json) = market cap.

## Step 3: Compute the row

From `<raw_dir>/financials.json` and `<raw_dir>/prices/prices.json`:

- `market_cap_b` = latest close × latest diluted shares / 1e9, formatted as "$X.XB"
- `revenue_ttm_b` = latest year's revenue / 1e9
- `revenue_growth_3yr_cagr_pct` = `((revenue_y[-1] / revenue_y[-4]) ^ (1/3) - 1) * 100`
- `gross_margin_pct`, `operating_margin_pct`, `net_margin_pct`, `fcf_margin_pct` = latest year
- `roic_pct` = latest year (from financials.json if available)
- `pe_ttm` = latest close / latest year's EPS
- `diluted_share_growth_3yr_pct` = `((diluted_shares_y[-1] / diluted_shares_y[-4]) - 1) * 100` (positive = dilution, negative = buyback)

## Step 4: Write `<raw_dir>/summary.md`

```yaml
---
competitor_ticker: <COMPETITOR>
parent_ticker: <PARENT>
artifact: competitor-summary
schema_version: 1
---

# <COMPETITOR> vs <PARENT> — comparison row

| Metric | Value |
|---|---|
| Market cap | $X.XB |
| Revenue TTM | $X.XB |
| Revenue 3-yr CAGR | X.X% |
| Gross margin | XX.X% |
| Operating margin | XX.X% |
| Net margin | XX.X% |
| FCF margin | XX.X% |
| ROIC | XX.X% |
| P/E (TTM) | XX.X |
| Diluted-share growth (3-yr) | +X.X% (dilution) / -X.X% (buyback) |

## Strategic note

<2-3 sentences on how this competitor overlaps with PARENT and where they're stronger/weaker on the metrics. Use the financials.json data; don't speculate beyond what the numbers show.>
```

## Output contract (recap)

- File: `<raw_dir>/summary.md`
- Returned summary (one structured paragraph + the metrics in inline form, e.g., "MSFT — market cap $3.1T, revenue $245B TTM, +12% 3-yr CAGR, op margin 44.6%, net margin 36.4%, P/E 35.2× — pulling ahead on cloud (Azure 30%+ growth), gross margin advantage of 200bps vs Apple Services").

## Failure modes

- **`NEEDS_CONTEXT`** if EDGAR or yfinance returns no data for this ticker (foreign, ETF, etc.)
- **`DONE_WITH_CONCERNS`** if some metrics are missing (e.g., financial company without standard income-statement concepts)
- **`DONE`** otherwise
````

- [ ] **Step 2: Commit**

```bash
git add claude/skills/stock-research/phases/04-competitor-sub.md
git commit -m "stock-research(claude): add phases/04-competitor-sub.md"
```

---

## Task 12: `phases/05-earnings-calls.md`

**Files:**
- Create: `claude/skills/stock-research/phases/05-earnings-calls.md`

- [ ] **Step 1: Write the file**

File: `claude/skills/stock-research/phases/05-earnings-calls.md`

````markdown
---
artifact: phase-prompt
phase: 5
phase_name: earnings-calls
schema_version: 1
---

# Phase 5 Subagent Prompt — Earnings Calls (orchestrator)

You orchestrate Phase 5: fetch the last 3 quarterly earnings call transcripts, dispatch a sub-subagent per quarter for analysis, then aggregate cross-call themes.

## Context (injected by orchestrator)

Standard: `ticker`, `cik_padded`, `ticker_dir`, `scripts_dir`, `raw_dir`. Plus:
- `company_slug`: lowercase company name used for Motley Fool URLs (e.g., "apple", "microsoft"). The orchestrator passes its best guess; you can override via inspection of the IR page if the scraper fails.

## Your job

Produce these files in `<ticker_dir>/earnings-calls/`:
- `<YYYY-Qn>.md` per quarter (cleaned transcript) — 3 files
- `<YYYY-Qn>-analysis.md` per quarter (your analysis) — 3 files (produced by sub-subagents)
- `cross-call-themes.md` (you write this, aggregating across the 3)

Return a **~500-word summary**: tone trajectory across the calls, dropped/added themes, key forward-looking guidance, anything CP2 should surface to the user.

## Step 1: Determine the 3 quarters to fetch

Today's date - 9 months back, rounded to the most recent reporting quarter, gives the oldest of the 3. Then the 2 most recent quarters.

Reporting calendars vary by company. A safe default:
- Pull the company's filing history: `<raw_dir>/_filings_index.json` (from Phase 2's `fetch_sec.py`)
- Find the 3 most recent 10-Qs (or 10-K + 2 10-Qs if the most recent reporting period was the fiscal year)
- Each 10-Q's `report_date` tells you which quarter it is

Convert to `YYYY-Qn` labels (e.g., a 10-Q with report_date `2024-06-29` for Apple = `2024-Q3` because Apple's fiscal year ends in September).

**Be careful with fiscal-year offsets.** Most US companies use calendar quarters (Q1 = Jan-Mar, Q4 = Oct-Dec). Some don't — Apple's FY ends in September, so its Q3 reports cover April-June. Walmart's FY ends Jan 31, so its Q4 reports cover Nov-Jan. Pick the convention the company itself uses (you can usually see it in their press releases).

## Step 2: Dispatch sub-subagents in parallel (one per quarter)

For each of the 3 quarters, dispatch a sub-subagent using `phases/05-earnings-call-sub.md`. Inject:
- `quarter_label`: `YYYY-Qn`
- `ticker`, `company_slug`, `scripts_dir`
- `out_dir`: `<ticker_dir>/earnings-calls/`

Wait for all 3 to complete. Each writes its own `<quarter_label>.md` (transcript) and `<quarter_label>-analysis.md`, and returns a summary covering: tone, prepared-remarks highlights, Q&A themes, guidance.

If a sub-subagent returns `NEEDS_CONTEXT` (transcript not findable), the orchestrator pauses and asks the user to paste it inline — see Failure Modes.

## Step 3: Write `cross-call-themes.md`

Read all 3 analysis files (or the returned summaries). Frontmatter:

```yaml
---
ticker: <TICKER>
artifact: cross-call-themes
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
quarters_covered: [<Q1>, <Q2>, <Q3>]
---
```

Then sections:

### 1. Tone trajectory

Across the 3 calls, has management's tone shifted? Categories:
- Confidence (e.g., "we're very bullish on..." → "we're cautiously optimistic about...")
- Hedging language (rare → frequent = bad sign)
- Defensiveness in Q&A (more deflecting / fewer specifics = bad sign)
- Specificity (more granular guidance = good; vague aspirations = bad)

Write 2–3 paragraphs describing the trajectory with quotes / paraphrases from specific calls.

### 2. Themes that emerged or dropped

What did management start talking about? What stopped being mentioned?

Examples:
- **Emerged:** "AI" was mentioned 12× in the most recent call vs 2× three calls ago.
- **Dropped:** "Foldable phones" disappeared after Q1 — strategy change?

A short list of 4–8 bullets, each with a quick "good / bad / neutral" tag.

### 3. Guidance trajectory

Find each call's forward guidance (revenue, margin, capex, etc.) and tabulate:

| Quarter | Revenue guide (next quarter) | Margin guide | Capex guide |
|---|---|---|---|
| ... | ... | ... | ... |

Are they raising / lowering / holding guidance? Note any "we don't give guidance" patterns or any one-time changes.

### 4. KPI mentions

If management mentions specific operational KPIs (customer count, ARPU, store count, capacity utilization, take rate, etc.), list them across the 3 calls in a small table — same KPI mentioned each time with its values. This becomes a candidate watchlist for Phase 9.

### 5. CP2 prep (what to surface to the user)

A short "things worth discussing at Checkpoint 2" list — 3–5 items that you think the user should weigh in on before projections. Examples:
- "Mgmt is suddenly cautious about Q1 next year — they didn't explain why. Worth pressing."
- "AI capex is doubling but they haven't shown the revenue contribution. Bull case has to assume this pays off."

## Output contract (recap)

- 3 transcript files + 3 analysis files + 1 cross-call-themes file
- ~500-word summary

## Failure modes

- **`NEEDS_CONTEXT`** if any sub-subagent returns `NEEDS_CONTEXT` (transcript not found by scraper and no manual paste yet). The orchestrator handles this by pausing to ask the user to paste the missing transcript before re-dispatching that single sub-subagent. You report this status to the main orchestrator so it can drive the user interaction.
- **`DONE_WITH_CONCERNS`** if guidance comparison is incomplete (e.g., company doesn't give forward guidance — many don't)
- **`DONE`** otherwise
````

- [ ] **Step 2: Commit**

```bash
git add claude/skills/stock-research/phases/05-earnings-calls.md
git commit -m "stock-research(claude): add phases/05-earnings-calls.md"
```

---

## Task 13: `phases/05-earnings-call-sub.md`

**Files:**
- Create: `claude/skills/stock-research/phases/05-earnings-call-sub.md`

- [ ] **Step 1: Write the file**

File: `claude/skills/stock-research/phases/05-earnings-call-sub.md`

````markdown
---
artifact: phase-prompt
phase: 5-sub
phase_name: per-quarter-call-analysis
schema_version: 1
---

# Phase 5 Sub-subagent Prompt — Per-Quarter Earnings Call Analysis

You handle one quarter's earnings call. Fetch the transcript, clean it, write an analysis.

## Context (injected by Phase 5 orchestrator)

- `quarter_label`: `YYYY-Qn` (e.g., `2024-Q3`)
- `ticker`: parent ticker (e.g., `AAPL`)
- `company_slug`: best-guess slug for Motley Fool URLs
- `scripts_dir`, `out_dir` (= `<ticker_dir>/earnings-calls/`)

## Your job

Produce two files in `<out_dir>/`:
- `<quarter_label>.md` — cleaned transcript with frontmatter
- `<quarter_label>-analysis.md` — your structured analysis

Return a **~500-word summary**: tone read, key prepared-remarks points, top 2–3 Q&A themes, forward guidance.

## Step 1: Fetch the transcript

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/fetch_transcript.py <ticker> \
  --quarter <quarter_label> \
  --company-slug <company_slug> \
  --out <out_dir>
```

This produces `<out_dir>/<quarter_label>.md` with the cleaned transcript (Motley Fool scrape).

If the script exits 3 (no source available), return status `NEEDS_CONTEXT` with this message:
```
Transcript not found via scraper for <ticker> <quarter_label>. Please paste the transcript inline. Orchestrator will re-dispatch with the pasted content.
```

The Phase 5 orchestrator handles user paste and re-dispatches with `--manual` mode. Your re-dispatch will receive the transcript via stdin; pass `--manual` to `fetch_transcript.py` and pipe stdin through:

```bash
echo "$pasted_transcript" | <scripts_dir>/.venv/bin/python <scripts_dir>/fetch_transcript.py <ticker> \
  --quarter <quarter_label> \
  --manual \
  --out <out_dir>
```

## Step 2: Read the transcript

Read `<out_dir>/<quarter_label>.md`. The frontmatter is already there; the body is the cleaned transcript with section headers like:
- Prepared Remarks (CEO, CFO, etc. each have their part)
- Q&A (analyst-by-analyst exchanges)

## Step 3: Write `<out_dir>/<quarter_label>-analysis.md`

Frontmatter:

```yaml
---
ticker: <TICKER>
artifact: earnings-call-analysis
quarter: <quarter_label>
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
---
```

Then sections:

### 1. Prepared remarks summary

3–6 paragraphs covering:
- Topline numbers cited (revenue, EPS, segment performance)
- Strategic announcements (new products, acquisitions, capital returns, leadership changes)
- Reasons given for outperformance / underperformance vs expectations
- Forward-looking commentary

### 2. Q&A themes

3–5 themes that came up in Q&A. For each:
- The question (paraphrased)
- The answer (paraphrased — specificity vs evasion matters)
- Your read: does the answer satisfy the question? Does it dodge?

### 3. Forward-looking statements

A bullet list of every concrete forward statement: guidance numbers, capex plans, hiring plans, geographic expansion plans, product launches, etc. Be specific — "we expect H2 to be strong" is not concrete; "we expect operating margin to expand 100bps in H2" is.

### 4. KPI mentions

Operational KPIs management cited (customer count, units sold, ARPU, etc.). List them with their values. These feed the Phase 5 orchestrator's cross-call KPI table.

### 5. Tone

A 1-paragraph qualitative read:
- Confidence (high / medium / low / declining)
- Hedging (use of "uncertainty", "challenges", "headwinds")
- Q&A defensiveness (deflecting questions, repeating talking points)
- Use of specific language (numbers, dates) vs vague aspirations

### 6. Net read

1 paragraph: what did THIS call tell you that you didn't know before? Worth flagging to the parent orchestrator for CP2?

## Output contract (recap)

- 2 files (`<quarter_label>.md` transcript + `<quarter_label>-analysis.md`)
- ~500-word summary

## Failure modes

- **`NEEDS_CONTEXT`** if `fetch_transcript.py` exit code 3 (covered above)
- **`DONE_WITH_CONCERNS`** if transcript is heavily truncated or has obvious parse errors (e.g., paragraphs cut mid-sentence) — note it
- **`DONE`** otherwise
````

- [ ] **Step 2: Commit**

```bash
git add claude/skills/stock-research/phases/05-earnings-call-sub.md
git commit -m "stock-research(claude): add phases/05-earnings-call-sub.md"
```

---

## Task 14: `phases/06-valuation.md`

**Files:**
- Create: `claude/skills/stock-research/phases/06-valuation.md`

- [ ] **Step 1: Write the file**

File: `claude/skills/stock-research/phases/06-valuation.md`

````markdown
---
artifact: phase-prompt
phase: 6
phase_name: valuation
schema_version: 1
---

# Phase 6 Subagent Prompt — Valuation

Pull current multiples, build the 5/10-year P/E percentile band, and run reverse DCF.

## Context (injected by orchestrator)

Standard. Plus:
- `financials_path`: `<ticker_dir>/financials.json` — Phase 3 produced this
- `prices_dir`: `<ticker_dir>/.raw/prices/` — you'll produce this

## Your job

Produce **one file**: `<ticker_dir>/valuation.md`. Plus supporting JSON in `.raw/`: `prices.json`, `dividends.json`, `splits.json`, `pe_band.json`, `reverse_dcf.json`.

Return a **~500-word summary**: current multiples, where we sit in the historical P/E band, reverse-DCF implied growth — and the headline "expensive / fair / cheap" verdict for this name.

## Step 1: Fetch prices and analyst data

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/fetch_prices.py <ticker> \
  --years 10 \
  --out <ticker_dir>/.raw/prices/
```

If exit code 2 (no data — delisted, halted), the entire Phase 6 fails. Report `BLOCKED` to the orchestrator with the message. Phase 6 is load-bearing — without prices we can't do valuation.

## Step 2: Compute P/E band

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/compute_pe_band.py \
  --prices <ticker_dir>/.raw/prices/prices.json \
  --financials <ticker_dir>/financials.json \
  --out <ticker_dir>/.raw/pe_band.json
```

This produces `pe_band.json` with the percentile breakdown.

## Step 3: Compute reverse DCF

Get the current price from `prices.json` (last bar's close):

```bash
current_price=$(jq '.bars[-1].close' <ticker_dir>/.raw/prices/prices.json)
```

Then:

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/compute_reverse_dcf.py \
  --financials <ticker_dir>/financials.json \
  --price "$current_price" \
  --discount-rate 0.10 \
  --terminal-growth 0.025 \
  --years 10 \
  --out <ticker_dir>/.raw/reverse_dcf.json
```

If the latest fiscal year has negative FCF (speculative-growth name), the reverse DCF will produce nonsense (the model assumes positive FCF). In that case, note "Reverse DCF not applicable — latest year FCF is negative; relevant valuation lens is path-to-profitability rather than DCF" and skip this step.

## Step 4: Write `valuation.md`

Frontmatter:

```yaml
---
ticker: <TICKER>
artifact: valuation
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
current_price: <number>
---
```

Then sections:

### 1. Current multiples

Compute and report (use `financials.json` latest year + current price):

| Metric | Value | Note |
|---|---|---|
| Current price | $XXX.XX | as of <today> |
| Diluted shares | X.XB | latest FY |
| Market cap | $X.XB | price × shares |
| P/E (TTM) | XX.X | price / EPS_TTM |
| Forward P/E | XX.X | price / consensus next-year EPS (see Phase 7 market expectations) |
| P/S (TTM) | XX.X | market cap / revenue_TTM |
| P/FCF (TTM) | XX.X | market cap / fcf_TTM |
| EV/EBITDA | XX.X | (market cap + net debt) / EBITDA. EBITDA approx = operating income + depreciation; if depreciation not in JSON, use operating income and note approximation |
| P/B (financials only) | XX.X | only meaningful for banks / insurers / asset-heavy financials |

### 2. Historical P/E band (5- and 10-year)

From `pe_band.json`:

| Metric | 10-year |
|---|---|
| 25th percentile | XX.X |
| Median (50th) | XX.X |
| 75th percentile | XX.X |
| Min | XX.X |
| Max | XX.X |
| **Current** | XX.X |
| **Current percentile** | XX.X% |

A paragraph: where is the current P/E in the historical distribution? Above median, below, near a historical high/low? Note any structural reasons the multiple might have shifted (e.g., business mix changed, balance sheet de-risked).

### 3. Reverse DCF — implied growth

From `reverse_dcf.json`:

- **Implied 10-year FCF growth at current price: X.X% / year** (assuming 10% discount rate, 2.5% terminal growth)

A paragraph interpreting this:
- Is this growth rate plausible? Compare with the company's historical FCF growth (from financials.json).
- For the GVD bucket, is this rate aggressive or conservative? (Quality-growth >15% = aggressive; value <8% = conservative.)
- What's the **margin of error**: at 8% discount rate the implied is X.X%; at 12% it's Y.Y%. (Re-run `compute_reverse_dcf.py` with different rates if you want this.)

### 4. Valuation verdict

One-sentence headline: **"Expensive / Fair / Cheap"** at current price, based on:
- P/E vs historical band
- Reverse-DCF implied growth vs plausible
- Multiple comparison vs peers (use the competitors.md row data)

This is a *snapshot* verdict for orchestrator synthesis. The full BUY/WATCH/AVOID call comes in Phase 9 after projections.

## Output contract (recap)

- `valuation.md` + raw JSONs in `.raw/`
- ~500-word summary

## Failure modes

- **`BLOCKED`** if `fetch_prices.py` returns exit 2 (no price data)
- **`DONE_WITH_CONCERNS`** if reverse DCF is not applicable (negative FCF) — fine, note it
- **`DONE`** otherwise
````

- [ ] **Step 2: Commit**

```bash
git add claude/skills/stock-research/phases/06-valuation.md
git commit -m "stock-research(claude): add phases/06-valuation.md"
```

---

## Task 15: `phases/07-market-expectations.md`

**Files:**
- Create: `claude/skills/stock-research/phases/07-market-expectations.md`

- [ ] **Step 1: Write the file**

File: `claude/skills/stock-research/phases/07-market-expectations.md`

````markdown
---
artifact: phase-prompt
phase: 7
phase_name: market-expectations
schema_version: 1
---

# Phase 7 Subagent Prompt — Market Expectations

Pull analyst consensus from yfinance into a calibration input for the Phase 8 projection brainstorm.

## Context (injected by orchestrator)

Standard. Phase 7 has no dependencies on prior phases beyond ticker resolution.

## Your job

Produce **two files**:
- `<ticker_dir>/market-expectations.json` — produced directly by `fetch_analyst_estimates.py`
- `<ticker_dir>/market-expectations.md` — human-readable companion you write

Return a **~500-word summary**: consensus price target vs current price, ratings distribution, key EPS/revenue estimates, EPS-trend direction (rising/falling = beat/miss signal). Most importantly: **what consensus expects for growth — this becomes the calibration prompt during Phase 8.**

## Step 1: Fetch analyst estimates

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/fetch_analyst_estimates.py <ticker> \
  --out <ticker_dir>/
```

This produces `market-expectations.json` containing: price target (low/mean/high/num_analysts), ratings (strong_buy/buy/hold/sell/strong_sell counts), earnings_estimate, revenue_estimate, eps_trend, growth_estimates.

If yfinance returns empty across the board (uncommon — even no-coverage names usually have *some* fields), note "No analyst coverage available" and produce a stub `market-expectations.md` saying so. Return `DONE_WITH_CONCERNS`.

## Step 2: Write `market-expectations.md`

Frontmatter:

```yaml
---
ticker: <TICKER>
artifact: market-expectations
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
---
```

Then sections:

### 1. Coverage

- **Number of analysts:** N (from `price_target.num_analysts`)
- Categorize: thin (<5), normal (5–25), heavily covered (>25)

### 2. Price target

| Tier | Value |
|---|---|
| Low | $XXX |
| Mean | $XXX |
| High | $XXX |
| **Current price** | $XXX |
| **Implied upside (mean)** | +XX% |
| **Implied upside (high)** | +XX% |

### 3. Ratings distribution

| Rating | Count | % |
|---|---|---|
| Strong Buy | N | XX% |
| Buy | N | XX% |
| Hold | N | XX% |
| Sell | N | XX% |
| Strong Sell | N | XX% |

A one-sentence read: "Consensus is bullish (75% Buy/Strong Buy)" or "Mixed (40% Hold)" or "Bearish minority is large enough to notice".

### 4. EPS estimates (next 4 quarters + current/next FY)

| Period | Consensus EPS | Low | High | # estimates |
|---|---|---|---|---|

A one-sentence read: are estimates clustered (high conviction) or wide (uncertainty)?

### 5. Revenue estimates

Same shape as EPS — period, consensus, range.

### 6. EPS trend (leading indicator)

`eps_trend` shows how the consensus EPS estimate has evolved over the last 90 days. The four columns are typically: `current_estimate`, `7d_ago`, `30d_ago`, `60d_ago`, `90d_ago`.

- Rising estimates = analysts ratcheting expectations up (often a "beat" signal)
- Falling estimates = analysts ratcheting down (often a "miss" signal)
- Flat = market expects what they expect

Report the trend direction for the current quarter and the current FY.

### 7. Growth estimates

`growth_estimates` typically has next-quarter, next-FY, and 5-year growth forecasts for both the ticker and its sector/industry. Report:

| Metric | Ticker | Sector |
|---|---|---|
| Next-FY growth | X% | X% |
| 5-yr growth (annualized) | X% | X% |

A one-sentence read: is the ticker expected to outgrow or underperform its sector?

### 8. **Calibration prompt for Phase 8** (the key section)

Pull the consensus base case in one paragraph that Phase 8's projection brainstorm will use as a foil:

> "Consensus expects revenue +X% next year, EPS +Y% next year, and 5-year revenue growth of Z%/yr. Mean price target $XXX implies +XX% upside in 12 months. The bull case in our projection should typically beat this; the base case should match or modestly beat; the bear case should sit below consensus. **What do you know that consensus doesn't?**"

The orchestrator uses this prompt verbatim during Phase 8 to anchor the brainstorm.

## Output contract (recap)

- `market-expectations.json` (script-produced) + `market-expectations.md` (your write-up)
- ~500-word summary with the consensus snapshot AND the calibration prompt for Phase 8

## Failure modes

- **`DONE_WITH_CONCERNS`** if analyst coverage is empty (rare; small-cap names sometimes)
- **`DONE`** otherwise
````

- [ ] **Step 2: Commit**

```bash
git add claude/skills/stock-research/phases/07-market-expectations.md
git commit -m "stock-research(claude): add phases/07-market-expectations.md"
```

---

## Task 16: Fill in `SKILL.md` body (the orchestrator)

**Files:**
- Modify: `claude/skills/stock-research/SKILL.md`

This is the largest single content task — SKILL.md is what the main agent reads to walk through the entire skill.

- [ ] **Step 1: Replace the placeholder SKILL.md with the full orchestrator content**

File: `claude/skills/stock-research/SKILL.md` (full replacement)

```markdown
---
name: stock-research
description: Use when researching a US-listed company end-to-end — fundamentals deep dive, building or refreshing an investment thesis, evaluating whether to buy/watch/avoid at the current price. Triggers on phrases like "research AAPL", "deep dive on Microsoft", "should I buy NVDA", "analyze TSLA's fundamentals". Long-running session (1–2 hours) producing durable artifacts in a separate git-versioned research repo. Not for: short-term trading, technical analysis, options strategies, or stock-recap (quarterly update of an existing thesis — that's a separate skill).
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

3. **Check existing ticker folder.** If `/Users/trocaneduard/Documents/Personal/investing-research/tickers/<TICKER>/` exists, prompt the user:
   - **Refresh** — re-run all phases, overwrite (commits as `update(TICKER)`)
   - **Archive & restart** — move existing to `archive/<TICKER>-<old-date>/`, start fresh (commits as `archive(TICKER)` then `research(TICKER)` v2)
   - **Abort** — leave it, suggest `stock-recap` for quarterly update

4. **GVD lens declaration.** Ask the user:
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

Format (output exactly this shape):

```
=== CHECKPOINT 1: Business Model & Moat ===

Drafted at <ticker_dir>/business-and-moat.md.

Summary: <paste the subagent's ~500-word summary, trimmed to the most load-bearing 3–5 sentences>

Quick verification before we fan out the data-gathering batch:
1. Does the ELI5 match how YOU think about this business?
2. Any segment, geography, or customer-concentration risk I missed?
3. Moat — am I overrating or underrating any of pricing power / network / scale / brand?
4. Anything you already know that should color the rest of the analysis?

Reply with corrections, raise something different, or "continue" to proceed.
```

Wait for user input. Possible responses:
- "continue" → proceed to Phases 3–7 batch
- Corrections → relay them to a fresh Phase 2 subagent (re-dispatch with the user's corrections in the context) → return to Checkpoint 1
- Free-form discussion → engage, then ask for an explicit "continue" before proceeding

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
| Any `BLOCKED` | Present to user: "Phase X failed because <reason>. Retry / skip-and-continue / abort?" |
| Any `NEEDS_CONTEXT` (almost always from Phase 5's transcript scrapers) | Ask user to paste the missing transcript, re-dispatch only that single sub-subagent with `--manual`, then continue |

## Checkpoint 2

```
=== CHECKPOINT 2: Earnings Calls — Tone, Direction, Recent Events ===

Last 3 calls analyzed at <ticker_dir>/earnings-calls/.
Cross-call themes at <ticker_dir>/earnings-calls/cross-call-themes.md.

Summary: <paste Phase 5's tone-trajectory + cross-call summary>

Worth discussing before we move to projections:
1. <Phase 5's "CP2 prep" items, 3–5 bullets>

Reply with reactions, additional context, or "continue" to start the projection brainstorm.
```

Wait for user input. This is the most conversation-heavy checkpoint — the user often has a take on recent events that should color the projections. Engage substantively before continuing.

## Phase 8: Bull/Base/Bear projections

This phase runs in the main agent (you), not a subagent — it's an interactive brainstorm.

**Read these references before starting:**
- `references/gvd-tailoring.md` — how to push back on assumptions for this GVD bucket
- `references/projection-kpis.md` — the full KPI list + formulas + dialogue flow

Open the brainstorm:

```
=== PHASE 8: Bull / Base / Bear 5-Year Projections ===

I'll walk us through the base case row-by-row, anchored in everything we've gathered:
- Historical 5-yr trends (financials.json)
- Peer averages (competitors.md)
- Mgmt forward guidance (cross-call-themes.md)
- Reverse-DCF implied growth (valuation.md)
- **Consensus expectations** (market-expectations.md):
  <paste Phase 7's calibration prompt verbatim>

Base case first. Then bull and bear as perturbations from base. Then probabilities.

Starting with revenue growth — Y1, Y2, Y3, Y4, Y5. The historical 3-yr CAGR is X%, peers average Y%, mgmt guides Z%, consensus expects W%. My base-case proposal: <proposed-numbers>. Push back, adjust, or accept.
```

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

```
=== CHECKPOINT 3: Projection Refinement ===

projections.{md,json} written to <ticker_dir>.

Summary table:
| Scenario | Probability | 5-yr Total Return CAGR (low/high) |
|---|---|---|
| Bull | XX% | +XX% / +XX% |
| Base | XX% | +XX% / +XX% |
| Bear | XX% | -XX% / -XX% |
| **Probability-weighted** | — | +XX% / +XX% |

Margin of safety today: XX%
Bear-case max drawdown from current: -XX%

Quick sanity check:
1. Does the asymmetry feel right? (Bull upside vs bear downside.)
2. Any assumption locked above you want to revisit?
3. Probabilities — does the bull scenario require what you'd call "everything going right"? Should we push base case probability up?

"continue" to construct the verdict, or push back.
```

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

```
=== CHECKPOINT 4: Verdict Approval ===

verdict.{md,json} drafted at <ticker_dir>.

| Field | Value |
|---|---|
| Classification | BUY/WATCH/AVOID |
| Conviction | High/Medium/Low |
| GVD bucket | <category> |
| Target position % | XX% |
| Buy zone | $XXX–$XXX (first tranche) |
| Active sell triggers | <count> |
| Watch KPIs | 5 generic + N story-custom |

Final review before commit:
1. Classification — does the BUY/WATCH/AVOID match your gut after all this analysis?
2. Sizing — too small, too big, right?
3. Sell triggers — any too strict (would fire on noise) or too loose (would never fire)?
4. Anything missing from verdict.md?

"approve" to commit, or push back.
```

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

5. **Optional remote push** (if a remote is configured, ask the user "push to GitHub?"). Default: skip — let the user push when they want.

6. **Confirm completion** to the user:
   ```
   === Research complete ===
   <TICKER> — <NAME>
   Verdict: <BUY|WATCH|AVOID>, conviction <level>, GVD <category>
   Target position: XX%, buy zone $XXX–$XXX
   Artifacts: <ticker_dir>
   Commit: <SHA>
   Tag: <TICKER>/v1
   ```

## Recovery / setup errors

If Phase 1 finds:
- `SR_SEC_USER_AGENT` unset → print:
  ```
  Set this in your shell rc and reload:
  export SR_SEC_USER_AGENT="<Your Name> <your@email>"
  ```
- Research repo missing → print:
  ```
  Research repo not found at /Users/trocaneduard/Documents/Personal/investing-research.
  Bootstrap (one-time):
    mkdir -p /Users/trocaneduard/Documents/Personal/investing-research
    cd $_ && git init -b main
    # Then create README.md, INDEX.md, tickers.json, .gitignore per docs/superpowers/specs/2026-05-11-stock-research-plan-2-design.md §10
  ```
- Python venv missing → print:
  ```
  Set up the skill venv:
    cd ~/.claude/skills/stock-research/scripts
    python -m venv .venv
    .venv/bin/pip install -r requirements.txt
  ```

## File references

- `phases/02-business-model.md` through `phases/07-market-expectations.md` — subagent prompts
- `references/gvd-tailoring.md`, `references/projection-kpis.md`, `references/sizing-matrix.md`, `references/investor-gates.md`, `references/sell-trigger-templates.md`, `references/watch-kpis-by-gvd.md` — Phase 8/9 reference data
- `scripts/mirror.sh` — refresh install-dir from worktree
- `scripts/` — Plan 1 Python scripts (call via `<scripts>/.venv/bin/python <script>.py`)

## Iron rule: never write to user code

This skill only writes to the research repo at `/Users/trocaneduard/Documents/Personal/investing-research/`, the skill's own `.raw/` cache, and stdout. It does NOT touch the user's code projects, git config, or anything outside the research-repo path. The Python scripts are read-only (no edits) — they're already shipped by Plan 1.
```

- [ ] **Step 2: Verify the file size is in the target range**

```bash
wc -l claude/skills/stock-research/SKILL.md
# Expected: 250-350 lines (target per spec was ~250; some slop is OK)
```

- [ ] **Step 3: Verify the YAML frontmatter parses**

```bash
python3 -c "
import yaml
with open('claude/skills/stock-research/SKILL.md') as f:
    text = f.read()
parts = text.split('---', 2)
meta = yaml.safe_load(parts[1])
print('name:', meta.get('name'))
print('description len:', len(meta.get('description', '')))
"
# Expected: name: stock-research; description len: should be under ~600 chars
```

- [ ] **Step 4: Commit**

```bash
git add claude/skills/stock-research/SKILL.md
git commit -m "stock-research(claude): fill in SKILL.md orchestrator body"
```

---

## Task 17: Mirror Claude variant to `~/.claude/skills/stock-research/`

**Files:**
- Modify: `~/.claude/skills/stock-research/` (mirror target)

- [ ] **Step 1: Run mirror.sh**

```bash
claude/skills/stock-research/scripts/mirror.sh
```

Expected output: `Mirroring .../claude/skills/stock-research -> /Users/trocaneduard/.claude/skills/stock-research` and then `Done.`

- [ ] **Step 2: Verify parity**

```bash
diff -rq \
  claude/skills/stock-research/ \
  ~/.claude/skills/stock-research/ \
  --exclude=.venv \
  --exclude=.pytest_cache \
  --exclude=__pycache__
# Expected: no output (no differences)
```

- [ ] **Step 3: Spot-check SKILL.md mirror**

```bash
diff claude/skills/stock-research/SKILL.md ~/.claude/skills/stock-research/SKILL.md
# Expected: no output
```

- [ ] **Step 4: (No commit — this step modifies only ~/.claude/skills which isn't tracked here. The mirror is operational, not source.)**

---

## Task 18: Duplicate Claude tree → `codex/skills/stock-research/`

**Files:**
- Create: `codex/skills/stock-research/` (entire tree, copied from Claude variant)

- [ ] **Step 1: Copy the Claude skill tree to Codex**

```bash
mkdir -p codex/skills/stock-research
rsync -av --delete \
  --exclude='.venv/' \
  --exclude='.pytest_cache/' \
  --exclude='__pycache__/' \
  --exclude='.git' \
  --exclude='.DS_Store' \
  claude/skills/stock-research/ codex/skills/stock-research/
```

- [ ] **Step 2: Remove Claude-only files that don't apply to Codex**

```bash
# commands/ is Claude-specific (Codex uses agents/openai.yaml instead)
rm -rf codex/skills/stock-research/commands
```

- [ ] **Step 3: Create `codex/skills/stock-research/agents/openai.yaml`**

File: `codex/skills/stock-research/agents/openai.yaml`

```yaml
interface:
  display_name: "Stock Research"
  short_description: "End-to-end fundamentals deep dive on a US-listed company"
  default_prompt: "Use $stock-research to begin a fundamentals research session on a ticker."
```

- [ ] **Step 4: Update any Claude-specific references in the Codex SKILL.md**

In `codex/skills/stock-research/SKILL.md`, replace:
- `~/.claude/skills/` → `~/.codex/skills/`
- "claude/skills/" → "codex/skills/" (in setup instructions)

Apply via:

```bash
sed -i '' 's|~/.claude/skills/|~/.codex/skills/|g' codex/skills/stock-research/SKILL.md
sed -i '' 's|claude/skills/|codex/skills/|g' codex/skills/stock-research/SKILL.md
```

(On Linux, use `sed -i` without the empty string.)

- [ ] **Step 5: Verify the Codex tree structure**

```bash
ls codex/skills/stock-research/
# Expected: SKILL.md  agents/  phases/  references/  scripts/

ls codex/skills/stock-research/agents/
# Expected: openai.yaml

ls codex/skills/stock-research/commands/ 2>/dev/null
# Expected: ls: ... No such file or directory
```

- [ ] **Step 6: Commit**

```bash
git add codex/skills/stock-research/
git commit -m "stock-research(codex): duplicate skill tree from Claude variant + add agents/openai.yaml"
```

---

## Task 19: Duplicate Plan 1 scripts into Codex variant

The Codex variant must be self-contained — it can't reach into `claude/skills/.../scripts/`. Duplicate the Plan 1 scripts physically.

**Files:**
- Modify: `codex/skills/stock-research/scripts/` (this dir was rsync-copied in Task 18 from Claude, but verify it includes everything)

- [ ] **Step 1: Verify all Plan 1 scripts copied across**

```bash
ls codex/skills/stock-research/scripts/
# Expected (12 scripts + 5 _lib + supporting files):
#   _lib/  README.md  compute_financials.py  compute_pe_band.py
#   compute_reverse_dcf.py  diff_risk_factors.py  extract_10k_sections.py
#   extract_10q_sections.py  fetch_analyst_estimates.py  fetch_prices.py
#   fetch_sec.py  fetch_transcript.py  mirror.sh  pytest.ini  requirements.txt
#   tests/  update_index.py  upsert_ticker.py
```

If any files are missing, re-rsync:
```bash
rsync -av --delete \
  --exclude='.venv/' --exclude='.pytest_cache/' --exclude='__pycache__/' \
  claude/skills/stock-research/scripts/ codex/skills/stock-research/scripts/
```

- [ ] **Step 2: Create a fresh venv in the Codex scripts directory**

```bash
cd codex/skills/stock-research/scripts
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

- [ ] **Step 3: Run the test suite to confirm scripts work in the Codex tree**

```bash
codex/skills/stock-research/scripts/.venv/bin/pytest \
  codex/skills/stock-research/scripts/tests/ -q 2>&1 | tail -5
# Expected: 51 passed
```

- [ ] **Step 4: Verify `mirror.sh` auto-detects Codex target**

```bash
codex/skills/stock-research/scripts/mirror.sh --dry 2>&1 | head -2
# Expected: mentions ~/.codex/skills/stock-research (NOT ~/.claude/skills/)
```

If it prints the wrong target, the auto-detection logic in `mirror.sh` is wrong — fix the parent-dir detection in the script:

```bash
# Check the PLATFORM_DIR detection at the top of mirror.sh:
grep PLATFORM_DIR codex/skills/stock-research/scripts/mirror.sh
```

Should produce `PLATFORM_DIR="$(basename "$(dirname "$(dirname "$SKILL_DIR")")")"` which resolves to `codex` for this tree.

- [ ] **Step 5: Commit**

The `codex/skills/stock-research/scripts/` should already be committed from Task 18's `git add codex/skills/stock-research/`. Verify and only commit if anything new (the venv is gitignored):

```bash
git status codex/skills/stock-research/scripts/
# Expected: clean working tree (no new files since Task 18 committed everything)
```

If there are new untracked files (e.g., test artifacts):

```bash
git add codex/skills/stock-research/scripts/
git commit -m "stock-research(codex): venv setup + smoke test parity confirmed"
```

---

## Task 20: Mirror Codex variant to `~/.codex/skills/stock-research/`

- [ ] **Step 1: Run mirror.sh from the Codex scripts directory**

```bash
codex/skills/stock-research/scripts/mirror.sh
```

Expected output: `Mirroring .../codex/skills/stock-research -> /Users/trocaneduard/.codex/skills/stock-research` and then `Done.`

- [ ] **Step 2: Verify parity**

```bash
diff -rq \
  codex/skills/stock-research/ \
  ~/.codex/skills/stock-research/ \
  --exclude=.venv \
  --exclude=.pytest_cache \
  --exclude=__pycache__
# Expected: no output (no differences)
```

- [ ] **Step 3: Verify Claude install dir is untouched**

```bash
ls ~/.claude/skills/stock-research/ | head -5
# Expected: SKILL.md, commands, phases, references, scripts — same as before Task 20
```

- [ ] **Step 4: (No commit — install dirs aren't tracked here.)**

---

## Task 21: Bootstrap the research repo (one-time manual step)

This is the spec-mandated one-time step. After this, the skill can be invoked end-to-end.

**Files (in `/Users/trocaneduard/Documents/Personal/investing-research/`):**
- Create: `README.md`, `INDEX.md`, `tickers.json`, `.gitignore`
- Create: `tickers/`, `notes/`, `archive/` directories

- [ ] **Step 1: Create the directory and initialize git**

```bash
mkdir -p /Users/trocaneduard/Documents/Personal/investing-research
cd /Users/trocaneduard/Documents/Personal/investing-research
git init -b main
```

- [ ] **Step 2: Create README.md**

File: `/Users/trocaneduard/Documents/Personal/investing-research/README.md`

```markdown
# investing-research

Durable artifacts from the `stock-research` skill — fundamentals theses for US-listed companies, written for a long-horizon, business-owner investing philosophy (Buffett/Munger/Dalio, modernized).

## Methodology in one paragraph

A long-horizon, business-owner approach to public markets. Buying partial ownership of real companies and holding through cycles. Diversified across **G**rowth, **V**alue, and **D**ividend stocks (the "GVD" framework). Stock selection runs in a strict order: business model first, then financials, then valuation. Research is deep and ongoing (conference calls, annual reports). Risk is managed through diversification (10–20 names), small position sizes on speculative bets, no margin, and willingness to hold cash. The edge is psychological: stay invested through fear, welcome recessions as buying opportunities, ignore Wall Street's short-term noise.

## How this repo is used

- `INDEX.md` — human dashboard of every ticker analyzed
- `tickers.json` — machine-readable mirror; source of truth (the `stock-recap` skill reads this)
- `tickers/<TICKER>/` — per-ticker thesis folder (artifact files from a research session)
- `notes/` — cross-cutting notes (market regime, lessons learned, books, mental models). Manually curated.
- `archive/` — positions sold or theses abandoned

## How to start a research session

In Claude Code: `/stock-research <TICKER>` or describe natural-language ("research AAPL"). The skill walks through 10 phases with 4 checkpoints. Total time ~1–2 hours per name.

## Conventions

- Every committed `.md` opens with YAML frontmatter (`ticker`, `artifact`, `session`, `date`, `schema_version`)
- Every JSON artifact has `schema_version: 1` at top level
- Commit messages follow Conventional Commits + machine-parseable trailers (see the spec)
- Tags: `<TICKER>/v<N>` for thesis versions; `<TICKER>/exit-<YYYY-MM-DD>` when closing a position

## Specs

The skill's design spec lives at: `docs/superpowers/specs/2026-05-11-stock-research-skill-design.md` in the [ai-skills](https://github.com/eduard-trocan/ai-skills) repo.
```

- [ ] **Step 3: Create INDEX.md**

File: `/Users/trocaneduard/Documents/Personal/investing-research/INDEX.md`

```markdown
# Index

_No tickers yet._
```

- [ ] **Step 4: Create tickers.json**

File: `/Users/trocaneduard/Documents/Personal/investing-research/tickers.json`

```json
{
  "schema_version": 1,
  "tickers": {}
}
```

- [ ] **Step 5: Create .gitignore**

File: `/Users/trocaneduard/Documents/Personal/investing-research/.gitignore`

```
# Raw cached SEC filings, transcript HTML, etc. — reproducible, never committed.
**/.raw/

# OS files
.DS_Store
Thumbs.db

# Python caches (in case any scripts run inside this repo)
__pycache__/
*.pyc
*.pyo
```

- [ ] **Step 6: Create the subdirectories**

```bash
cd /Users/trocaneduard/Documents/Personal/investing-research
mkdir -p tickers notes archive
touch tickers/.gitkeep notes/.gitkeep archive/.gitkeep
```

- [ ] **Step 7: Initial commit**

```bash
cd /Users/trocaneduard/Documents/Personal/investing-research
git add README.md INDEX.md tickers.json .gitignore tickers/.gitkeep notes/.gitkeep archive/.gitkeep
git commit -m "$(cat <<'EOF'
chore: bootstrap investing-research repo

Initialized by stock-research skill Plan 2.
Schema version 1.

ticker: -
session: bootstrap
date: $(date +%Y-%m-%d)
trigger: skill-creation
EOF
)"
```

- [ ] **Step 8: Verify**

```bash
cd /Users/trocaneduard/Documents/Personal/investing-research
git log --oneline
# Expected: 1 commit ("chore: bootstrap investing-research repo")

ls -la
# Expected: README.md, INDEX.md, tickers.json, .gitignore, tickers/, notes/, archive/, .git/

cat tickers.json
# Expected: {"schema_version": 1, "tickers": {}}
```

- [ ] **Step 9: Optional — set up GitHub remote**

Ask the user (don't unilaterally push):

> "The research repo is ready. Want to push to a private GitHub repo? If yes, run:
> ```bash
> cd /Users/trocaneduard/Documents/Personal/investing-research
> gh repo create eduard-trocan/investing-research --private --source=. --remote=origin
> git push -u origin main
> ```"

The user can do this or skip — the skill works either way (local-only is fine).

(No git commit in the ai-skills repo for this task — the research repo is separate.)

---

## Task 22: End-to-end dry run on AAPL

The validation step. Run a full `stock-research` session on AAPL in Claude Code, observe whether all 10 phases complete cleanly, the 4 checkpoints render correctly, the expected artifact set appears under `tickers/AAPL/`, and the final commit + tag land in the research repo.

This is an **interactive task** — the skill expects user input at 4 checkpoints. The implementer guides the user through it as a smoke test, not a hands-off run.

- [ ] **Step 1: Verify all prerequisites are in place**

```bash
# 1. Env var
echo "$SR_SEC_USER_AGENT"
# Expected: "Eduard Trocan eduard.valentin1996@gmail.com" (or whatever the user set)

# 2. Skill is mirrored to install dir
ls ~/.claude/skills/stock-research/SKILL.md
# Expected: file exists

# 3. Research repo bootstrapped
ls /Users/trocaneduard/Documents/Personal/investing-research/tickers.json
# Expected: file exists, contains {"schema_version": 1, "tickers": {}}

# 4. Scripts work
~/.claude/skills/stock-research/scripts/.venv/bin/python \
  ~/.claude/skills/stock-research/scripts/fetch_sec.py --help
# Expected: usage message
```

If any fail, fix before proceeding — Tasks 1–21 should have set everything up.

- [ ] **Step 2: Start the skill in Claude Code**

In a fresh Claude Code session, invoke:

```
/stock-research AAPL
```

Or, equivalently, natural language: "Research AAPL — let's do a deep dive."

The skill should trigger and start Phase 1.

- [ ] **Step 3: Walk through Phase 1 — Setup**

The orchestrator will:
- Resolve AAPL → Apple Inc., CIK 0000320193
- Ask GVD lens — answer: `quality-growth` (typical bucket for AAPL; we want to test that lens)
- Ask session-context one-liner — answer something like: "Curious whether AAPL's services growth justifies current multiple after recent hardware deceleration."
- Confirm the ticker dir at `tickers/AAPL/` doesn't exist (or, if it does from a prior test, choose "archive & restart")
- Initialize the folder

Verify:
```bash
ls /Users/trocaneduard/Documents/Personal/investing-research/tickers/AAPL/
# Expected: .raw/, earnings-calls/, THESIS.md (skeleton)
```

- [ ] **Step 4: Walk through Phase 2 — Business model + moat**

The orchestrator dispatches the Phase 2 subagent. Wait for it to return (could take 1–3 minutes — it fetches the 10-K and extracts sections).

Verify the artifact:
```bash
cat /Users/trocaneduard/Documents/Personal/investing-research/tickers/AAPL/business-and-moat.md | head -30
# Expected: YAML frontmatter, then # 1. ELI5 section with plain-language description
```

The ELI5 must be plain language. If it's full of jargon, Phase 2's prompt needs tightening — iterate on `phases/02-business-model.md` and re-run.

- [ ] **Step 5: Walk through Checkpoint 1**

The orchestrator pauses with the 4-question format. Answer "continue" to proceed (or push back if anything's wrong).

- [ ] **Step 6: Walk through Phases 3–7 batch**

The orchestrator dispatches all 5 phase subagents in parallel. This can take 5–15 minutes depending on competitor and transcript fetches.

Watch for `NEEDS_CONTEXT` returns from Phase 5 sub-subagents (one or more quarter transcripts may not be on Motley Fool). If so, the orchestrator will pause and ask for manual paste. Paste from Seeking Alpha / IR page / wherever you have access.

Verify all expected artifacts appear:
```bash
ls /Users/trocaneduard/Documents/Personal/investing-research/tickers/AAPL/
# Expected:
#   THESIS.md
#   business-and-moat.md
#   financials.md  financials.json
#   competitors.md  swor.md
#   valuation.md
#   market-expectations.md  market-expectations.json
#   earnings-calls/  (3 transcript files + 3 analysis files + cross-call-themes.md)
#   .raw/  (cached source data)
```

- [ ] **Step 7: Walk through Checkpoint 2**

Engage substantively with the earnings-call discussion. The orchestrator should surface tone shifts and let you discuss them.

- [ ] **Step 8: Walk through Phase 8 — Projections brainstorm**

This is the most interactive phase. The orchestrator proposes base-case row by row, you push back / accept, then bull / bear / probabilities. Take 15–30 minutes; this is the value.

Verify when done:
```bash
ls /Users/trocaneduard/Documents/Personal/investing-research/tickers/AAPL/projections.*
# Expected: projections.md, projections.json

jq '.scenarios | keys' /Users/trocaneduard/Documents/Personal/investing-research/tickers/AAPL/projections.json
# Expected: ["base", "bear", "bull"]

jq '.probability_weighted' /Users/trocaneduard/Documents/Personal/investing-research/tickers/AAPL/projections.json
# Expected: an object with expected return + bear drawdown
```

- [ ] **Step 9: Walk through Checkpoint 3 + Phase 9 — Verdict**

Walk through the verdict construction. All 6 investor gates must have substantive answers. Sell triggers must be specific.

Verify:
```bash
cat /Users/trocaneduard/Documents/Personal/investing-research/tickers/AAPL/verdict.md | head -50
# Expected: 10 numbered sections, frontmatter present
```

- [ ] **Step 10: Walk through Checkpoint 4 + Phase 10 — Commit**

Approve, watch the orchestrator update `tickers.json`, regenerate `INDEX.md`, commit, and tag.

Verify:
```bash
cd /Users/trocaneduard/Documents/Personal/investing-research
git log --oneline | head -3
# Expected:
#   <SHA> research(AAPL): initial deep dive — verdict <BUY|WATCH|AVOID> @ $<price>
#   <SHA> chore: bootstrap investing-research repo

git tag
# Expected: AAPL/v1

jq '.tickers.AAPL' tickers.json
# Expected: full AAPL entry with name, sector, gvd, status, etc.

cat INDEX.md
# Expected: # Index header + table with the AAPL row
```

- [ ] **Step 11: Failure-mode iteration**

If any phase produced wildly wrong output (e.g., garbled ELI5, projections that don't compute, verdict that contradicts the projection asymmetry), iterate on the underlying phase prompt at `claude/skills/stock-research/phases/<NN>-<name>.md`:

1. Read the actual output that's wrong
2. Diagnose: was the prompt unclear? Was a script bug? Was the model misreading data?
3. Edit the phase prompt
4. Re-mirror via `mirror.sh`
5. Re-archive the AAPL folder (`mv tickers/AAPL tickers/AAPL-failed-<date>` then move to `archive/`)
6. Re-run `/stock-research AAPL`

Iterate until the workflow produces an artifact set that you'd be happy to revisit in 6 months. Document any tweaks made in commits.

- [ ] **Step 12: Final state confirmation + commit the spec amendments (if any)**

After E2E passes:

```bash
# Confirm the research-repo state
cd /Users/trocaneduard/Documents/Personal/investing-research
git status
# Expected: clean working tree

git log --oneline
# Expected: 2 commits — bootstrap + AAPL research
```

If during E2E you edited any phase prompts in the ai-skills repo, commit those:

```bash
cd /Users/trocaneduard/Documents/Personal/ai-skills/.claude/worktrees/cool-nightingale-72c276
git status
git add claude/skills/stock-research/phases/
git commit -m "stock-research: refine phase prompts based on AAPL E2E findings"
```

Then mirror.sh both variants to push the refinements to install dirs.

- [ ] **Step 13: Mark Plan 2 complete**

Update todos. The skill is now fully operational on Claude Code (and structurally ready for Codex once you invoke it there for the first time).

---

## Self-Review Notes

**Spec coverage check:**
- §3 (variants): Tasks 1, 18 build Claude + Codex variants.
- §4 (file layout): Tasks 1–7 (references), 8–15 (phases), 16 (SKILL.md), 18 (Codex), 19 (Codex scripts) cover the full file structure.
- §5 (orchestration mechanics): Task 16 (SKILL.md) embodies this.
- §6 (checkpoint format): Task 16 sections "Checkpoint 1" through "Checkpoint 4" implement the hybrid format.
- §7 (subagent dispatch contract): Each phase prompt file (Tasks 8–15) follows the role / context / inputs / output / failure pattern.
- §8 (failure handling): Task 16 "Failure handling in the batch" table + each phase's "Failure modes" section.
- §9 (mirror sync): Task 1 (`mirror.sh`), Tasks 17, 20 (run mirror.sh), and per-edit `cp` noted in SKILL.md.
- §10 (prerequisites + bootstrap): Task 21 bootstraps the research repo; Task 16's SKILL.md "Prerequisites" documents env setup.
- §11 (E2E): Task 22 walks the full AAPL run with verification.
- §12 (open items): Stock-recap explicitly out of scope; resumability not implemented.

**Placeholder scan:** No "TBD", "TODO", "implement later", "appropriate error handling" — every step has full content. The `<TICKER>`, `<YYYY-MM-DD>`, etc. placeholders in markdown templates are intentional templating, not plan placeholders; they're filled in by the skill at runtime.

**Type / signature consistency:**
- `ticker_dir`, `scripts_dir`, `raw_dir` injection names are consistent across all phase prompts.
- The `gvd_category` enum values (`growth | quality-growth | value | dividend | speculative-growth`) match across the spec, SKILL.md, and `references/gvd-tailoring.md`.
- The artifact filenames (`business-and-moat.md`, `financials.{md,json}`, `competitors.md`, etc.) match across SKILL.md, the phase prompts, and the bootstrap repo's expected structure.
- Frontmatter `schema_version: 1` is consistent across every markdown and JSON artifact.
- Commit message conventions in Task 16 Phase 10 match overall-spec §8.1.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-11-stock-research-plan-2-orchestration.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration. Same approach that worked for Plan 1. Each task's content (especially the larger ones like Task 16 SKILL.md and Tasks 8–15 phase prompts) is best handled in a clean context.

**2. Inline Execution** — Execute tasks in this session via `executing-plans`, batch execution with checkpoints. Workable but Task 16 (SKILL.md) and Task 22 (interactive E2E) benefit from focused attention.

Which approach?
