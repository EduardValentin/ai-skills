# `stock-recap` Skill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the canonical `skills/stock-recap/` skill — SKILL.md orchestrator, sub-agent phase prompts, and references — for the two-flow recap workflow (Quarterly catch-up + News mode), and wire it into the repo's trigger-test infrastructure and dual-sync.

**Architecture:** One canonical copy at `skills/stock-recap/`, dual-synced via `scripts/sync_skill.py` to both `~/.claude/skills/stock-recap/` and `~/.codex/skills/stock-recap/`. SKILL.md is the main-agent orchestrator; `phases/quarterly/` and `phases/news/` carry sub-agent prompts; `references/` holds rubrics the orchestrator pulls into checkpoint UX (sell-trigger evaluation, diff thresholds, auto-recommend rules, update flow). **Zero new scripts** — every data operation calls into the existing `toolkits/financial-toolkit/` install.

**Tech Stack:** Markdown (SKILL.md, phase prompts, references), YAML (frontmatter, `agents/openai.yaml`), Python only via the existing `toolkits/financial-toolkit/` (already on disk and venv-installed). Skill validation happens via `tests/skill-trigger/static_contract.py` and the scenarios in `tests/skill-trigger/scenarios.toml`. End-to-end validation in Task 13 against a real ticker (NOW, the user's only existing thesis).

**Spec reference:**
- `docs/superpowers/specs/2026-05-12-stock-recap-skill-design.md` (commit `54b00d1`)

**Setup gate before starting:**
- `SR_SEC_USER_AGENT="Eduard Trocan eduard.valentin1996@gmail.com"` must be exported (already in zsh rc per prior session work).
- `toolkits/financial-toolkit/` must exist and be installed in both `~/.claude/toolkits/` and `~/.codex/toolkits/` with a working `.venv`. Confirm: `ls ~/.claude/toolkits/financial-toolkit/.venv/bin/python ~/.codex/toolkits/financial-toolkit/.venv/bin/python`.
- `/Users/trocaneduard/Documents/Personal/investing-research/tickers/NOW/verdict.json` must exist (the only ticker `stock-research` has produced so far). Confirm: `ls /Users/trocaneduard/Documents/Personal/investing-research/tickers/NOW/verdict.json`.
- `scripts/sync_skill.py` must be present (lands from origin/main via the merge). Confirm: `ls scripts/sync_skill.py`.
- `tests/skill-trigger/static_contract.py` must currently pass: `python3 tests/skill-trigger/static_contract.py`.

---

## File Structure (what this plan creates / modifies)

```
skills/stock-recap/
├── SKILL.md                                       ~600 lines — orchestrator (built across Tasks 2-11)
├── commands/
│   └── stock-recap.md                             slash command wrapper
├── agents/
│   └── openai.yaml                                Codex agent metadata
├── phases/
│   ├── quarterly/
│   │   ├── 02-fetch-sub.md                        per-quarter SEC+transcript fetcher
│   │   ├── 03-financials-refresh.md               extend financials.json + roll TTM
│   │   ├── 03-valuation-refresh.md                re-pull prices/consensus/P-E band/reverse-DCF
│   │   └── 04-quarter-analysis-sub.md             per-quarter analysis + actuals slice
│   └── news/
│       └── 02-context-fetch-sub.md                event-driven targeted fetcher
└── references/
    ├── sell-trigger-evaluation.md                 4-state rubric (🔴/🟡/🟢/⚪) with examples
    ├── auto-recommend-rules.md                    6 conditions that auto-recommend update
    ├── diff-thresholds.md                         default tolerances + override-capture rules
    └── update-flow.md                             surgical / reclassification / pivot-recommend

tests/skill-trigger/scenarios.toml                 + 2 new [[scenario]] blocks (quarterly, news)

~/.claude/skills/stock-recap/                      mirrored via sync_skill.py
~/.codex/skills/stock-recap/                       mirrored via sync_skill.py
```

**No files in `toolkits/financial-toolkit/` are added or modified.** If a need arises (e.g., a `diff_actuals_vs_projections.py`), it lands in the toolkit in a separate change — not in this plan.

---

## Task 1: Scaffold the canonical skill tree

**Files:**
- Create: `skills/stock-recap/SKILL.md` (frontmatter + placeholder body)
- Create: `skills/stock-recap/commands/stock-recap.md`
- Create: `skills/stock-recap/agents/openai.yaml`
- Create: `skills/stock-recap/phases/quarterly/.gitkeep`
- Create: `skills/stock-recap/phases/news/.gitkeep`
- Create: `skills/stock-recap/references/.gitkeep`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p skills/stock-recap/commands skills/stock-recap/agents \
         skills/stock-recap/phases/quarterly skills/stock-recap/phases/news \
         skills/stock-recap/references
touch skills/stock-recap/phases/quarterly/.gitkeep \
      skills/stock-recap/phases/news/.gitkeep \
      skills/stock-recap/references/.gitkeep
```

- [ ] **Step 2: Write `skills/stock-recap/SKILL.md` (frontmatter + placeholder body)**

Note the description is **double-quoted** because it contains colons (`Triggers on phrases like ...`, `Not for: ...`). Per memory rule `skill_yaml_frontmatter_and_slash_command.md`, any description containing `:` or other YAML-special characters MUST be double-quoted, otherwise `yaml.safe_load` silently fails and skill discovery breaks.

Use this content verbatim:

```markdown
---
name: stock-recap
description: "Use when recapping an existing US-listed stock thesis — catching up on every quarter (10-Q/10-K) filed since the last analysis, or analyzing the impact of a material event (M&A, CEO change, regulatory ruling, restated guidance). Triggers on phrases like \"catch me up on NVDA\", \"recap MSFT since last quarter\", \"how does this acquisition affect my AAPL thesis\", \"new earnings just dropped for TSLA\". Mechanically diffs actuals vs saved bull/base/bear projections, LLM-evaluates the saved English sell triggers in 4 states (🔴 fired / 🟡 flashing / 🟢 clear / ⚪ cannot-evaluate), and optionally proposes a surgical or reclassifying thesis update. Not for: initial deep dive on a brand-new ticker (that's stock-research), portfolio P&L tracking, short-term trading, or non-US listings."
---

# Stock Recap

(Body to be filled in by subsequent tasks.)
```

- [ ] **Step 3: Write `skills/stock-recap/commands/stock-recap.md`**

```markdown
---
description: Start a stock-recap session on a US-listed ticker. Usage: /stock-recap <TICKER>
argument-hint: <TICKER>
---

Start a `stock-recap` session on the ticker {{args}}.

Invoke the `stock-recap` skill and pass the ticker symbol as the initial input. The skill's Phase 1 will resolve the ticker, verify preconditions (prior `verdict.json` exists), detect any 10-Q/10-K filings since the last recap, and ask the user to pick the mode (Quarterly catch-up vs News event).
```

- [ ] **Step 4: Write `skills/stock-recap/agents/openai.yaml`**

```yaml
interface:
  display_name: "Stock Recap"
  short_description: "Quarterly catch-up or news-event recap of an existing stock thesis"
  default_prompt: "Use $stock-recap to recap an existing thesis after new quarters or a material event."
```

- [ ] **Step 5: Validate frontmatter parses**

Run:
```bash
python3 -c "import yaml,re; t=open('skills/stock-recap/SKILL.md').read(); fm=re.split(r'^---\s*$', t, maxsplit=2, flags=re.M)[1]; d=yaml.safe_load(fm); print('OK', d['name']); assert d['name']=='stock-recap'; assert 'Use when recapping' in d['description']"
```

Expected: prints `OK stock-recap`. Any traceback means the description string broke YAML parsing — re-quote until it parses.

Also validate the command file:
```bash
python3 -c "import yaml,re; t=open('skills/stock-recap/commands/stock-recap.md').read(); fm=re.split(r'^---\s*$', t, maxsplit=2, flags=re.M)[1]; print('OK', yaml.safe_load(fm)['argument-hint'])"
```

Expected: prints `OK <TICKER>`.

- [ ] **Step 6: Push to both install dirs**

Run: `python3 scripts/sync_skill.py push stock-recap`

Expected: two `synced: ... -> ...` lines, one for `~/.claude/skills/stock-recap/`, one for `~/.codex/skills/stock-recap/`. Exit code 0.

- [ ] **Step 7: Run static_contract test**

Run: `python3 tests/skill-trigger/static_contract.py`

Expected: still passes for all existing skills. `stock-recap` will be added to the test scenarios in Task 12; until then static_contract just checks that existing skills still parse — adding a new skill to the tree must not break existing ones.

- [ ] **Step 8: Commit**

```bash
git add skills/stock-recap/
git commit -m "$(cat <<'EOF'
stock-recap: scaffold canonical skill tree

Adds the bare directory layout, frontmatter-only SKILL.md (description
double-quoted because it contains colons), slash-command stub, and
Codex agent metadata. Body of SKILL.md is filled in by subsequent
commits. Synced to both install dirs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: SKILL.md preamble — purpose, prerequisites, input policy, mode router

**Files:**
- Modify: `skills/stock-recap/SKILL.md` (replace `(Body to be filled in by subsequent tasks.)`)

- [ ] **Step 1: Replace the placeholder body with the preamble**

Use `Edit` to replace exactly `(Body to be filled in by subsequent tasks.)` with:

```markdown
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
```

- [ ] **Step 2: Validate the file still parses and the body has the new content**

```bash
python3 -c "import yaml,re; t=open('skills/stock-recap/SKILL.md').read(); fm=re.split(r'^---\s*$', t, maxsplit=2, flags=re.M)[1]; yaml.safe_load(fm); assert 'Mode router' in t; assert 'plain-English' in t; print('OK')"
```

Expected: prints `OK`. Any traceback = re-quote or re-edit.

- [ ] **Step 3: Sync and commit**

```bash
python3 scripts/sync_skill.py push stock-recap
git add skills/stock-recap/SKILL.md
git commit -m "$(cat <<'EOF'
stock-recap: write SKILL.md preamble and mode router

Adds the When-to-use, Prerequisites, native-interactive-input policy,
plain-English voice rules, and the Quarterly-vs-News mode router that
runs at the end of Phase 1. The two flows are mutually exclusive per
session.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Phase 1 — preconditions, gap detection, session-context capture

Phase 1 is main-agent (per spec §5), so it lives inline in SKILL.md, not in a phase file.

**Files:**
- Modify: `skills/stock-recap/SKILL.md` (append new section after the Mode router section)

- [ ] **Step 1: Append the Phase 1 section to SKILL.md**

Append this content at the end of the file:

```markdown
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
```

- [ ] **Step 2: Sanity-check the file**

```bash
grep -c "^## " skills/stock-recap/SKILL.md
```

Expected: at least 4 (`# Stock Recap`, `## When to use`, `## Prerequisites`, `## Asking the user for input`, `## Plain-English voice in every output`, `## Mode router (Phase 1, Step 1.4)`, `## Phase 1: ...`).

- [ ] **Step 3: Sync and commit**

```bash
python3 scripts/sync_skill.py push stock-recap
git add skills/stock-recap/SKILL.md
git commit -m "$(cat <<'EOF'
stock-recap: Phase 1 — preconditions, gap detection, mode router

Adds the shared Phase 1 orchestration: hard-precondition asserts on the
four saved JSON artifacts, gap detection via fetch_sec.py --list-only,
mode picker via native interactive-input (Quarterly / News, with a
zero-filings branch that offers a valuation-only recap), and free-form
session-context capture.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Quarterly Phase 2 — per-quarter fetch sub-agent + orchestrator dispatch

**Files:**
- Create: `skills/stock-recap/phases/quarterly/02-fetch-sub.md`
- Modify: `skills/stock-recap/SKILL.md` (append Quarterly Phase 2 section)

- [ ] **Step 1: Write `phases/quarterly/02-fetch-sub.md`**

```markdown
---
artifact: phase-prompt
phase: quarterly-2
phase_name: per-quarter-fetch
schema_version: 1
---

# Quarterly Phase 2 Sub-Agent Prompt — Per-Quarter Fetch

You are a sub-agent dispatched by the Quarterly Phase 2 orchestrator. Your job is to pull the SEC filing and earnings-call transcript for **one** quarter and stage them on disk for downstream phases. You do not analyze; you fetch.

## Context (injected by the orchestrator)

- `ticker`: the ticker symbol (uppercase).
- `quarter`: the period in `YYYY-Qn` form (e.g., `2026-Q2`).
- `quarter_end_date`: the period-end date in `YYYY-MM-DD` form (e.g., `2026-06-30`). Same date as the filing's `report_date` in SEC EDGAR's manifest.
- `form_type`: `10-Q` or `10-K`.
- `ticker_dir`: absolute path to `tickers/<TICKER>/`.
- `toolkit_dir`: absolute path to the `financial-toolkit` install (`~/.claude/toolkits/financial-toolkit/` or `~/.codex/toolkits/financial-toolkit/`).
- `company_slug`: lowercase, hyphen-separated company name (for transcript scraper URL guessing; best-effort).
- `manual_transcript_path` *(optional, only set on a re-dispatch after the user pasted a transcript)*: absolute path to a temp file containing the pasted transcript text. When this is set, skip the scraper and feed this file into `fetch_transcript.py --manual` via stdin (see Step 4b).

## Your job

1. Create per-quarter scratch dir.
2. Download the SEC filing (full HTML) into the scratch dir.
3. Run the right section extractor (`extract_10q_sections.py` or `extract_10k_sections.py`).
4. Fetch the earnings-call transcript with the standard scraper → IR-page → manual-paste fallback chain.
5. Return a 1-paragraph fetch-status summary.

## Step 1: Create scratch dir

```bash
mkdir -p <ticker_dir>/.raw/recap-<quarter>/ <ticker_dir>/earnings-calls/
```

## Step 2: Download SEC filing

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_sec.py <ticker> \
  --forms <form_type> \
  --since <quarter_end_date> \
  --out <ticker_dir>/.raw/recap-<quarter>/
```

`fetch_sec.py` downloads every filing matching `<form_type>` with `filing_date >= --since`. Companies typically file 10-Qs within ~45 days of quarter-end and 10-Ks within ~75 days, so setting `--since` to `<quarter_end_date>` is enough to catch the right filing without pulling unrelated later filings.

**Identify the right filing.** `fetch_sec.py` writes a manifest at `<ticker_dir>/.raw/recap-<quarter>/_filings_index.json` with shape:
```json
{ "ticker": "...", "cik": "...", "filings": [
    { "accession": "...", "form": "10-Q", "filing_date": "2026-08-01",
      "report_date": "2026-06-30", "filename": "..." }
  ] }
```
Find the entry whose `report_date` equals `<quarter_end_date>`. That entry's `filename` (joined to the `--out` dir) is the filing HTML to feed into the section extractor in Step 3. Set `FILING_PATH` in your return summary (Step 5) to that absolute path.

**Failure detection.** `fetch_sec.py` returns exit 0 even when zero filings match `--since`. If the resulting `_filings_index.json.filings` array is empty, OR no entry's `report_date` matches `<quarter_end_date>`, return status `NEEDS_CONTEXT_FILING` (see Step 5 for the enum split) with the message `"No <form_type> with report_date=<quarter_end_date> found in SEC EDGAR for <ticker>"`. Exit code 2 from `fetch_sec.py` means the ticker is not on EDGAR at all — also return `NEEDS_CONTEXT_FILING` in that case.

## Step 3: Extract sections

If `form_type == "10-Q"`:

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/extract_10q_sections.py <ticker> \
  --quarter <quarter> \
  --out <ticker_dir>/.raw/recap-<quarter>/
```

If `form_type == "10-K"`:

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/extract_10k_sections.py <ticker> \
  --year <fiscal-year> \
  --out <ticker_dir>/.raw/recap-<quarter>/
```

Where `<fiscal-year>` is the 4-digit year prefix of `<quarter>` (so `2026-Q4` → `2026`); `extract_10k_sections.py` interprets it as the fiscal year covered by the 10-K.

If the extractor exits non-zero, return status `DONE_WITH_CONCERNS` and note in the summary which sections couldn't be extracted (so Phase 4 knows what's missing).

## Step 4: Fetch earnings-call transcript

**Step 4a — first dispatch (no `manual_transcript_path` in your context):**

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_transcript.py <ticker> \
  --quarter <quarter> \
  --company-slug <company_slug> \
  --out <ticker_dir>/earnings-calls/
```

This script's fallback chain is: Motley Fool scraper → IR-page guess → manual-paste prompt. The first two are tried automatically; if both fail, the script exits with code 3 and prints the manual-paste instruction. On exit 3, return status `NEEDS_CONTEXT_TRANSCRIPT` with the instruction text — the orchestrator will surface a native-interactive prompt asking the user to paste, write the paste to a temp file, and re-dispatch you with `manual_transcript_path` set in your context block.

**Step 4b — re-dispatch with `manual_transcript_path` set:**

When you are re-dispatched after a paste, skip the scraper attempt entirely and pipe the staged file directly into the script:

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_transcript.py <ticker> \
  --quarter <quarter> \
  --manual \
  --out <ticker_dir>/earnings-calls/ < <manual_transcript_path>
```

On success, set `TRANSCRIPT_SOURCE: manual-paste` and `STATUS: DONE` in your return summary.

On success of either step, the script writes `<ticker_dir>/earnings-calls/<quarter>.md` (cleaned transcript with frontmatter).

## Step 5: Return summary

Return a structured paragraph the orchestrator can compose. Required fields:

```
QUARTER: <quarter>
FILING_PATH: <ticker_dir>/.raw/recap-<quarter>/<filename>
SECTIONS_EXTRACTED: <comma-list, e.g., "MD&A, Item 1A, segment-reporting" or "all">
TRANSCRIPT_PATH: <ticker_dir>/earnings-calls/<quarter>.md
TRANSCRIPT_SOURCE: <"motley-fool" | "ir-page" | "manual-paste">
STATUS: <DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT_FILING | NEEDS_CONTEXT_TRANSCRIPT>
NOTES: <one sentence — anomalies, missing sections, anything the orchestrator should know>
```

`STATUS` must be exactly one of those four uppercase strings — no variants (no lowercase, no missing `S`, no `NEEDS_CONTEXT` without a suffix).

## Failure modes (recap)

- **`NEEDS_CONTEXT_FILING`** if SEC has no `<form_type>` whose `report_date` matches `<quarter_end_date>` (either zero filings returned, or filings returned but none matched the period). The orchestrator surfaces a "Drop this quarter and continue / Abort the recap" choice to the user.
- **`NEEDS_CONTEXT_TRANSCRIPT`** if the SEC filing was fetched cleanly but all transcript fallbacks (Motley Fool scraper → IR-page guess) failed and manual paste is required. The orchestrator surfaces a "Paste transcript inline / Skip this quarter" choice; on paste, it stages the content to a temp file and re-dispatches you with `manual_transcript_path` set (Step 4b).
- **`DONE_WITH_CONCERNS`** if the filing was fetched but the section extractor (Step 3) couldn't pull every expected section.
- **`DONE`** otherwise.
```

- [ ] **Step 2: Append Quarterly Phase 2 dispatch section to SKILL.md**

Append to the end of `skills/stock-recap/SKILL.md`:

```markdown
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
```

- [ ] **Step 3: Sync and commit**

```bash
python3 scripts/sync_skill.py push stock-recap
git add skills/stock-recap/SKILL.md skills/stock-recap/phases/quarterly/02-fetch-sub.md
git commit -m "$(cat <<'EOF'
stock-recap: Quarterly Phase 2 — per-quarter fetch fan-out

Adds the per-quarter SEC + transcript fetch sub-agent prompt and the
orchestrator dispatch loop. One sub-agent per detected filing, all
dispatched in parallel. The transcript fallback chain (scraper → IR →
manual paste) and the missing-filing branch are both wired into the
orchestrator's NEEDS_CONTEXT handling via native interactive-input.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Quarterly Phase 3 — financials & valuation refresh sub-agents + dispatch

**Files:**
- Create: `skills/stock-recap/phases/quarterly/03-financials-refresh.md`
- Create: `skills/stock-recap/phases/quarterly/03-valuation-refresh.md`
- Modify: `skills/stock-recap/SKILL.md` (append Quarterly Phase 3 section)

- [ ] **Step 1: Write `phases/quarterly/03-financials-refresh.md`**

```markdown
---
artifact: phase-prompt
phase: quarterly-3-financials
phase_name: financials-refresh
schema_version: 1
---

# Quarterly Phase 3 Sub-Agent Prompt — Financials Refresh

You are a sub-agent dispatched by the Quarterly Phase 3 orchestrator. Your job is to extend the saved `financials.json` with every new quarter the user has accumulated, roll TTM forward across those quarters, and rewrite `financials.{md,json}`.

## Context (injected by the orchestrator)

- `ticker`: ticker symbol.
- `ticker_dir`: absolute path to `tickers/<TICKER>/`.
- `toolkit_dir`: absolute path to the `financial-toolkit` install.
- `new_quarters`: list of `YYYY-Qn` strings that Phase 2 successfully fetched (skip any that Phase 2 dropped).
- `latest_period_before_recap`: the period that was the latest in `financials.json` BEFORE this recap (so the diff before/after is reportable).

## Your job

1. Re-run `compute_financials.py` with enough years to cover the new window.
2. Inspect `tag_resolution` and `missing_concepts`; fall back to direct company-facts inspection only if a metric is missing.
3. Roll TTM across the new quarters; check the methodology gate (revenue + net income trending up-and-to-the-right on TTM) and flag inflection points relative to `latest_period_before_recap`.
4. Overwrite `financials.{md,json}` (prior snapshot lives in git history; no separate archive file).
5. Return a ~500-word structured summary.

## Step 1: Pull XBRL financials

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/compute_financials.py <ticker> \
  --years 10 \
  --out <ticker_dir>/financials.json
```

Note: `--out` is a FILE path (not a directory). The script writes the JSON document to that exact path, overwriting if it already exists.

The output JSON includes:
- annual series for the last 10 fiscal years
- `tag_resolution` — which us-gaap candidate resolved each metric
- `missing_concepts` — metrics that no candidate in the script's list could find
- `available_us_gaap_concepts` — only populated when something is missing, lists everything the company DOES report

The script does NOT write `financials.md` — you generate that in Step 5 from the refreshed JSON.

If exit code != 0, return status `BLOCKED` with the script's stderr.

## Step 2: Critical thinking on gaps

If `missing_concepts` is non-empty OR `tag_resolution` resolved any metric to an unexpected candidate (e.g., `SalesRevenueNet` instead of `Revenues`):

1. Open `<ticker_dir>/.raw/recap-gap-detection/company-facts.json` (downloaded as part of `compute_financials.py`'s pipeline) and search for the missing concept under any candidate name not in the script's default list.
2. If found, hand-fill the metric in `financials.json` and note the resolution in `tag_resolution` under a new key `manual_resolution`.
3. If not found, leave the metric `null` and add an explicit note to the section "Data quality" of `financials.md`.

Do not stretch — if a metric truly isn't reported, mark it `null` and say so. The orchestrator will surface unresolved gaps in Checkpoint 1.

## Step 3: Roll TTM and check the trend gate

For revenue, gross profit, operating income, net income, and FCF: compute TTM at each of the new quarter-ends by summing the trailing 4 quarters. Append the new TTM points to the existing TTM series in `financials.json`.

**Trend gate verdict** — answer in the markdown summary section "Trend gate":

- **Pass:** every metric on the TTM series is up YoY in the most recent quarter.
- **Pass-with-caveats:** revenue + net income are up but FCF or a margin metric is mixed.
- **Fail:** revenue or net income is down YoY on the TTM series at the most recent quarter.

State the specific metric and direction either way.

## Step 4: Identify inflection points

Compare each metric's TTM at `latest_period_before_recap` vs at the latest new quarter. If any metric moved by more than ±10% (revenue, EPS, FCF) or ±200bps (margin), flag it. List flagged inflections at the top of the markdown summary section "What changed since last touch".

## Step 5: Rewrite `financials.{md,json}`

Use the same shape `stock-research` Phase 3 produced (frontmatter, Income / Balance Sheet / Cash Flow sections, Trend gate, Capital allocation scorecard). Add a new section near the top: **"Data quality"** if there are gaps, **"What changed since last touch"** always (even if "no meaningful change" — say so).

## Step 6: Return summary

Return a structured ~500-word summary the orchestrator uses to compose Checkpoint 1. Required fields:

```
STATUS: <DONE | DONE_WITH_CONCERNS | BLOCKED>
NEW_QUARTERS_INTEGRATED: <comma-list>
TREND_GATE: <Pass | Pass-with-caveats | Fail with specifics>
INFLECTIONS: <bullet list of metrics that moved >10% / 200bps>
DATA_QUALITY_GAPS: <bullet list, or "none">
FILES_WRITTEN: financials.md, financials.json
NOTES: <one sentence on anything unusual>
```
```

- [ ] **Step 2: Write `phases/quarterly/03-valuation-refresh.md`**

```markdown
---
artifact: phase-prompt
phase: quarterly-3-valuation
phase_name: valuation-refresh
schema_version: 1
---

# Quarterly Phase 3 Sub-Agent Prompt — Valuation Refresh

You are a sub-agent dispatched by the Quarterly Phase 3 orchestrator. Your job is to re-pull today's prices, analyst consensus, P/E historical band, and reverse-DCF at today's price; then rewrite `valuation.md` and `market-expectations.{md,json}`.

Runs in parallel with the financials-refresh sub-agent.

## Context (injected by the orchestrator)

- `ticker`: ticker symbol.
- `ticker_dir`: absolute path to `tickers/<TICKER>/`.
- `toolkit_dir`: absolute path to the `financial-toolkit` install.
- `saved_buy_zones`: the full `verdict.json.buy_zones` list (each entry has `name`, `price_range` like `"$80-$88"`, `action`). The orchestrator computes the overall low and high by parsing the `price_range` strings and taking `min(low)` / `max(high)` across all zones to pass to the sub-agent as `saved_buy_zone_overall_low` and `saved_buy_zone_overall_high` for the buy-zone-position check below.
- `saved_reverse_dcf_implied_growth`: from the saved `valuation.md` (parse the line if present, else `null`).

## Your job

1. Pull today's price + dividends + splits via yfinance.
2. Pull analyst consensus.
3. Compute 5- and 10-year P/E percentile band.
4. Compute reverse-DCF implied growth at today's price.
5. Rewrite `valuation.md` and `market-expectations.{md,json}`.
6. Return a ~500-word summary.

## Step 1: Prices + dividends + splits

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_prices.py <ticker> \
  --years 10 \
  --out <ticker_dir>/prices/
```

If exit code 2 (yfinance empty — delisted / halted), return status `BLOCKED` with the message — Phase 5 needs price.

## Step 2: Analyst consensus

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_analyst_estimates.py <ticker> \
  --out <ticker_dir>/
```

`--out` is a directory; the script writes `<out>/market-expectations.json`. It does NOT write `market-expectations.md` — generate that in Step 5 from the JSON.

If exit code != 0, return status `DONE_WITH_CONCERNS` with the message; the orchestrator will note "no analyst coverage available" in Checkpoint 1. Skip the auto-recommend rule based on consensus drift in that case.

## Step 3: P/E historical band

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/compute_pe_band.py \
  --prices <ticker_dir>/prices/prices.json \
  --financials <ticker_dir>/financials.json \
  --out <ticker_dir>/.raw/pe-band-<today-YYYY-MM-DD>.json
```

`compute_pe_band.py` takes no ticker positional — only the two input JSON paths and an output JSON path. It writes a single JSON document at `--out`. Read that JSON and incorporate the 25th/50th/75th percentile P/E band figures into the refreshed `valuation.md` section you write in Step 5.

## Step 4: Reverse-DCF at today's price

Read today's close from `<ticker_dir>/prices/prices.json` (latest bar; written by Step 1).

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/compute_reverse_dcf.py \
  --financials <ticker_dir>/financials.json \
  --price <today-close> \
  --discount-rate 0.10 \
  --terminal-growth 0.025 \
  --out <ticker_dir>/.raw/reverse-dcf-<today-YYYY-MM-DD>.json
```

`compute_reverse_dcf.py` takes no ticker positional — only `--financials` (the JSON written by `compute_financials.py`), `--price`, the discount/terminal-growth rates, and `--out` (a JSON file path). Read the output JSON; capture the resulting implied growth rate (a percent) into the summary and into the refreshed `valuation.md` you write in Step 5.

## Step 5: Compute deltas worth flagging

- **Buy-zone position:** today's close vs `saved_buy_zone_overall_low`–`saved_buy_zone_overall_high`. One of: `above-zone-high` / `inside-zone` / `below-zone-low`.
- **Reverse-DCF drift:** `(new_implied_growth - saved_reverse_dcf_implied_growth) / saved_reverse_dcf_implied_growth * 100`. Flag if `|drift| > 50%`. If saved is `null`, mark `cannot-compute-drift`.
- **Consensus drift:** compare new mean price target vs the one in the prior `market-expectations.json` (read from git's index for the file's previous version — `git show HEAD:...market-expectations.json`). Flag if `>15%` change.

## Step 6: Return summary

```
STATUS: <DONE | DONE_WITH_CONCERNS | BLOCKED>
TODAY_CLOSE: $<price>
BUY_ZONE_POSITION: <above-zone-high | inside-zone | below-zone-low>
PE_TTM: <X.X>×
PE_PERCENTILE_10YR: <XX>%
REVERSE_DCF_IMPLIED_GROWTH: <XX>%/yr
REVERSE_DCF_DRIFT_VS_SAVED: <+/-XX%, or cannot-compute-drift>
CONSENSUS_DRIFT_VS_SAVED: <+/-XX%, or cannot-compute-drift>
FILES_WRITTEN: valuation.md, market-expectations.md, market-expectations.json, prices/prices.json
NOTES: <one sentence>
```
```

- [ ] **Step 3: Append Quarterly Phase 3 dispatch section to SKILL.md**

```markdown
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
```

- [ ] **Step 4: Sync and commit**

```bash
python3 scripts/sync_skill.py push stock-recap
git add skills/stock-recap/SKILL.md skills/stock-recap/phases/quarterly/
git commit -m "$(cat <<'EOF'
stock-recap: Quarterly Phase 3 — financials + valuation refresh

Adds the two parallel sub-agent prompts and orchestrator dispatch.
financials-refresh extends financials.json with the new quarters and
flags inflections vs the pre-recap period; valuation-refresh re-pulls
prices, consensus, P/E band, and reverse-DCF, then reports the drift
against the saved values. The valuation-only recap branch is wired in
for the "no new filings" path from Phase 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Quarterly Phase 4 — per-quarter analysis sub-agent + Checkpoint 1

**Files:**
- Create: `skills/stock-recap/phases/quarterly/04-quarter-analysis-sub.md`
- Modify: `skills/stock-recap/SKILL.md` (append Quarterly Phase 4 + Checkpoint 1)

- [ ] **Step 1: Write `phases/quarterly/04-quarter-analysis-sub.md`**

```markdown
---
artifact: phase-prompt
phase: quarterly-4
phase_name: per-quarter-analysis
schema_version: 1
---

# Quarterly Phase 4 Sub-Agent Prompt — Per-Quarter Analysis

You are a sub-agent dispatched by the Quarterly Phase 4 orchestrator. Your job is to analyze ONE quarter's filing + earnings-call transcript, produce the analysis artifact, and return a structured per-quarter "actuals slice" the orchestrator uses to build the cross-quarter diff table.

## Context (injected by the orchestrator)

- `ticker`: ticker symbol.
- `quarter`: `YYYY-Qn`.
- `ticker_dir`: absolute path.
- `toolkit_dir`: absolute path to financial-toolkit.
- `filing_path`: absolute path to the cleaned filing extracts written by Phase 2 (in `.raw/recap-<quarter>/`).
- `transcript_path`: absolute path to the cleaned transcript (`earnings-calls/<quarter>.md`).
- `projection_kpis`: the list of KPI names tracked in the saved `projections.json` (e.g., `["revenue", "gross_margin_pct", "operating_margin_pct", ..., "diluted_eps", ...]`).
- `thesis_year_for_quarter`: which thesis-year this quarter maps to (1-indexed from when the original thesis was written), e.g., `1` if the quarter falls within the first 12 months after thesis creation.

## Your job

1. Read the filing extracts + transcript.
2. Write `earnings-calls/<quarter>-analysis.md` with the same shape as `stock-research` Phase 5's per-quarter sub-agent output: prepared-remarks summary, Q&A themes, forward-looking statements, KPI mentions, tone (confidence / hedging / defensiveness).
3. For each KPI in `projection_kpis`, find the actual reported value in the filing (or "not reported this quarter") and compute the TTM-equivalent where applicable. Compare it to the bull / base / bear projection for `thesis_year_for_quarter` and tag the row.
4. Return a structured summary.

## Step 1: Write the per-quarter analysis file

Use this template for `<ticker_dir>/earnings-calls/<quarter>-analysis.md`:

```yaml
---
ticker: <TICKER>
quarter: <quarter>
artifact: earnings-call-analysis
schema_version: 1
---

# <TICKER> — <quarter> earnings call & filing analysis

## Headline numbers

| Metric | Reported | TTM | YoY change |
|---|---|---|---|
| Revenue | $X.XB | $Y.YB | +X.X% |
| Operating income | ... | ... | ... |
| Net income | ... | ... | ... |
| Diluted EPS | $X.XX | $Y.YY | +X.X% |
| FCF | ... | ... | ... |

## Prepared remarks — summary

<3-5 sentences. What management led with. What they emphasized vs prior quarter.>

## Q&A themes

<Bullet list. The top 3-4 themes that came up in analyst questions.>

## Forward-looking statements

<Guidance issued or affirmed. Specific numbers if given.>

## KPI mentions and guidance trajectory

<Any KPI the user is watching (from watch_kpis in verdict.json) that came up. Note direction vs prior quarter.>

## Tone

<One paragraph. Confidence vs hedging vs defensiveness. Cite specific phrases or moments.>
```

## Step 2: Compute per-quarter actuals slice vs projections

For each KPI in `projection_kpis`:

1. Find the reported value for this quarter in the filing (or note "not reported this quarter" — common for things like ROIC that companies don't disclose quarterly).
2. Where the KPI is a flow metric (revenue, net income, FCF, etc.), use the TTM ending at this quarter; where it's a stock/ratio (margin %, share count, net debt), use the spot value at quarter-end.
3. Read the bull / base / bear projection for `thesis_year_for_quarter` from `<ticker_dir>/projections.json`.
4. Tag the row using the default thresholds (the orchestrator may override these in Phase 5):
   - For revenue / EPS / FCF (absolute or growth %): `ahead` if actual > base + 10%; `behind` if actual < base − 10%; `on-track` otherwise. Compare separately to bull and bear to see which scenario the actual most closely matches.
   - For margins: `ahead` if actual > base + 200bps; `behind` if actual < base − 200bps; `on-track` otherwise.
   - For other KPIs (story-custom): `ahead` if > base + 15%; `behind` if < base − 15%; `on-track` otherwise.
   - `cannot-evaluate` if the actual is "not reported this quarter" or if the saved projection has no value for `thesis_year_for_quarter` for this KPI.

## Step 3: Return summary

```
QUARTER: <quarter>
ANALYSIS_FILE: <ticker_dir>/earnings-calls/<quarter>-analysis.md
HEADLINE_TONE: <confident | mixed | hedging | defensive>
GUIDANCE_DIRECTION: <raised | maintained | lowered | no-guidance>
ACTUALS_VS_PROJECTIONS:
  - revenue: actual=$X.XB | base=$Y.YB | tag=on-track | closest-scenario=base
  - operating_margin_pct: actual=22.4 | base=23.0 | tag=on-track | closest-scenario=base
  - diluted_eps: actual=$1.45 | base=$1.62 | tag=behind | closest-scenario=bear
  - <... one row per projection_kpi>
SCENARIO_LANDING: <which of bull/base/bear this quarter most closely matches across the majority of metrics, with a 1-sentence justification>
NOTES: <one sentence on anything unusual or unique to this quarter>
```
```

- [ ] **Step 2: Append Quarterly Phase 4 + Checkpoint 1 to SKILL.md**

```markdown
## Quarterly Phase 4: Per-quarter analysis fan-out (parallel)

For each quarter Phase 2 accepted (excluding any dropped via NEEDS_CONTEXT), dispatch one sub-sub-agent in parallel using `phases/quarterly/04-quarter-analysis-sub.md`.

Inject the standard context block plus:

- `filing_path`: from Phase 2's return for this quarter.
- `transcript_path`: from Phase 2's return.
- `projection_kpis`: list pulled from the saved `projections.json` top-level keys (excluding metadata).
- `thesis_year_for_quarter`: integer computed as `(quarter_end - thesis_creation_date) // 365 days + 1`. Read `thesis_creation_date` from the `date` field of `verdict.json`'s frontmatter (or from `tickers.json.<TICKER>.first_analyzed`).

Issue all dispatches in a single message.

Wait for all sub-sub-agents to return. Collect their `ACTUALS_VS_PROJECTIONS` blocks for use in Phase 5's diff table.

## Quarterly Checkpoint 1 — Per-quarter walkthrough

This checkpoint walks the user through every newly-ingested quarter in chronological order before the orchestrator synthesizes the cross-quarter trajectory.

**Before rendering: re-read each quarter's `earnings-calls/<quarter>-analysis.md` and pull the headline numbers + tone + guidance from each return summary. Also surface any `DATA_QUALITY_GAPS` from the Phase 3 financials-refresh return.**

Format (rendered Markdown, not in a code block):

```markdown
## Checkpoint 1 — Quarterly walkthrough

*Per-quarter analysis files written under `<ticker_dir>/earnings-calls/`. Refreshed `financials.{md,json}` and `valuation.md` are also on disk.*

### Data quality

<If Phase 3 reported gaps: surface them here first. Example:
"⚠️ `roic` is null for 2026-Q1 — the company didn't disclose it this quarter (they only report ROIC annually in the 10-K). The diff table will mark ROIC `cannot-evaluate` for this thesis-year." >

<If no gaps: write "No data-quality gaps. All projection KPIs were resolvable from the new filings.">

### Quarter-by-quarter

For each quarter <YYYY-Qn> in chronological order:

#### <YYYY-Qn> <thesis-year>

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
```

- [ ] **Step 3: Sync and commit**

```bash
python3 scripts/sync_skill.py push stock-recap
git add skills/stock-recap/SKILL.md skills/stock-recap/phases/quarterly/04-quarter-analysis-sub.md
git commit -m "$(cat <<'EOF'
stock-recap: Quarterly Phase 4 + Checkpoint 1

Per-quarter analysis sub-sub-agent prompt writes
earnings-calls/<YYYY-Qn>-analysis.md and returns a structured actuals
slice vs the saved bull/base/bear projections for the matching
thesis-year. The orchestrator fans out one sub-agent per accepted
quarter, then renders Checkpoint 1 — a chronological walkthrough
surfacing data-quality gaps from Phase 3, headline numbers per
quarter, tone, guidance direction, and which scenario each quarter
lands in.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: References — sell-trigger evaluation, diff thresholds, auto-recommend rules

**Files:**
- Create: `skills/stock-recap/references/sell-trigger-evaluation.md`
- Create: `skills/stock-recap/references/diff-thresholds.md`
- Create: `skills/stock-recap/references/auto-recommend-rules.md`

- [ ] **Step 1: Write `references/sell-trigger-evaluation.md`**

```markdown
---
artifact: reference
topic: sell-trigger-evaluation
schema_version: 1
---

# Sell-Trigger Evaluation Rubric

This reference is loaded by Phase 5 (Quarterly mode) and Phase 3 (News mode) to evaluate every English sell trigger saved in `verdict.json.sell_triggers`. That field is a dict with three keys — `materially_overvalued` (list of strings), `thesis_broken` (list of strings), and `better_opportunity` (string or null). The agent flattens these into a single list of trigger strings (preserving category labels so the recap doc can group them), reads each trigger string, the refreshed data, and assigns ONE of four states per trigger. The state plus a 1-2 sentence justification goes into the recap doc.

## The four states

| State | Symbol | Meaning |
|---|---|---|
| **fired** | 🔴 | The condition described by the trigger string is met **right now**. The thesis says to sell (or reduce); the agent surfaces this prominently and recommends entering Phase 6. |
| **flashing** | 🟡 | Within striking distance — one more quarter of the same trend, or one modest worsening, would fire it. Two or more 🟡 triggers auto-recommend a thesis update. |
| **clear** | 🟢 | Comfortably clear. The condition would require a meaningful shift to trigger. |
| **cannot-evaluate** | ⚪ | The data needed to evaluate this trigger is missing, OR the trigger is too ambiguous to evaluate against today's data. The agent proposes a sharper restatement and surfaces it for Phase 6 to either drop, rewrite, or keep as-is. |

## How to evaluate

For each English trigger:

1. **Parse the condition.** What's the metric, what's the threshold, what's the time window? Examples:
   - "Revenue YoY < 5% for two consecutive quarters" → metric: revenue YoY %, threshold: 5%, window: 2 consecutive quarters.
   - "Gross margin < 43%" → metric: gross margin %, threshold: 43%, window: most recent quarter.
   - "Customer concentration crosses 25% from any single client" → metric: any disclosed customer >25% of revenue, window: latest 10-K.

2. **Find the data.** Refreshed `financials.json` covers most quantitative triggers. `earnings-calls/<quarter>-analysis.md` files cover narrative triggers ("management starts hedging on cloud growth"). The 10-K's Item 1 reference to >10% customers covers concentration triggers.

3. **Assign a state.**
   - **🔴 fired** — the most recent data point clearly meets the condition AND any time-window is satisfied.
     - Example: "Revenue YoY < 5% for two consecutive quarters" with 2026-Q1 at +3.2% and 2026-Q2 at +4.1% → 🔴 fired.
   - **🟡 flashing** — the most recent data point is within ~20% of the threshold OR the time-window is partially satisfied (e.g., one of two consecutive quarters has already breached).
     - Example: same trigger, with 2026-Q1 at +4.5% but 2026-Q2 at +6.0% → 🟡 flashing (one of two quarters breached, current at +6% is within 20% relative distance of the 5% threshold). State the math.
     - Example: "Gross margin < 43%" with current at 44.0% → 🟡 flashing (within ~2 percentage points of the threshold).
   - **🟢 clear** — the data point is comfortably away from the threshold AND no part of the time-window is breached.
     - Example: same revenue trigger with 2026-Q1 at +18% and 2026-Q2 at +16% → 🟢 clear.
   - **⚪ cannot-evaluate** — write down WHY:
     - Data missing: "The 10-Q doesn't break out customer concentration; only the 10-K does. We won't know until the next 10-K filing."
     - Ambiguous trigger: "Trigger says 'gross margin trending materially lower' — 'materially' isn't defined. Propose: 'gross margin < 41% (last-known FY 43.5%) on a TTM basis'."

4. **Write the justification.** 1–2 sentences. Include the data point that drove the state. If 🟡 or 🔴, include the dollar/percentage gap so Phase 6 can sharpen the trigger if needed.

## Example output (renders into Phase 5's Checkpoint 2)

```markdown
### Sell triggers — current state

1. **🟢 Revenue YoY < 5% for two consecutive quarters.** 2026-Q1: +14.2%; 2026-Q2: +12.8%. Comfortably above threshold.
2. **🟡 Gross margin < 43%.** Current FY TTM: 43.9%. Within 90bps of the threshold; one of the last three quarters (2026-Q1) dipped to 43.1%. Worth watching closely.
3. **⚪ Customer concentration crosses 25% from any single client.** The 10-Qs in this window don't disclose customer concentration; only the 10-K does. Next disclosure expected ~2027-Q1. Propose sharpening: "On the next 10-K, any single customer >20% of revenue (currently top customer is 14% in FY2025)."
4. **🔴 iPhone unit decline > 10% YoY.** 2026-Q2 iPhone units were down 12.3% YoY (from the segment table in the 10-Q). Trigger fired. Recommend entering Phase 6 to discuss.
```

## Boundary cases

- **A trigger references a number that's reported only annually** (e.g., ROIC, customer concentration). If the recap window contains a 10-K, evaluate using its data; otherwise mark ⚪ cannot-evaluate and propose either a quarterly proxy or marking the trigger "evaluate only at year-end."
- **A trigger references qualitative tone** (e.g., "management starts hedging on cloud growth"). Read the per-quarter analysis files' "Tone" sections and look for the specific phrase or pattern. Quote the verbatim language in the justification.
- **A trigger contradicts the refreshed data in an unexpected way** (e.g., a trigger about dilution where the share count has actually been falling). Mark 🟢 but note that the trigger may be stale — surface as a candidate for Phase 6 surgical sharpening.
```

- [ ] **Step 2: Write `references/diff-thresholds.md`**

```markdown
---
artifact: reference
topic: diff-thresholds
schema_version: 1
---

# Actuals-vs-Projection Diff Thresholds

Phase 5 (Quarterly mode) renders a diff table showing, for each thesis-year that has a corresponding filed quarter in the recap window, how the actual lands vs the bull / base / bear projection from `projections.json`. Each row gets a tag.

## Default thresholds

| KPI family | `ahead` if actual is | `behind` if actual is | `on-track` otherwise |
|---|---|---|---|
| Revenue, EPS, FCF (absolute or growth %) | > base + 10% | < base − 10% | |
| Margins (gross / operating / net / FCF / ROIC) | > base + 200 bps | < base − 200 bps | |
| Story-custom KPIs (everything else — restaurants opened, ARPU, NRR, rig count, etc.) | > base + 15% | < base − 15% | |
| Any KPI where the actual is "not reported this quarter" OR the projection is missing for the thesis-year | — | — | `cannot-evaluate` |

## Closest-scenario tag

Independently of `ahead` / `on-track` / `behind` (which compare to base), each row also gets a **closest-scenario** tag — `bull`, `base`, or `bear` — based on which projection the actual is numerically nearest to. This lets the orchestrator say things like "Revenue lands base / EPS lands bear / FCF lands bull" without overcounting the base-only tag.

## Override capture

The user may decide a default threshold is wrong for this thesis (e.g., a high-growth name where ±10% on revenue is too narrow; or a steady-state name where ±5% would be tighter). Phase 5 surfaces the defaults at the start of the diff-table section and uses native interactive-input to let the user override:

- 2 options: **Use defaults** / **Override one or more thresholds**.
- On override: the user names which KPI family and the new tolerance (free-form). The agent confirms back.

**The agreed overrides MUST be written into the recap doc's frontmatter** under a new field `diff_threshold_overrides`, so the next recap session sees the same labeling rules:

```yaml
diff_threshold_overrides:
  revenue_growth_pct: "+/- 5%"
  operating_margin_pct: "+/- 100bps"
```

If a future recap reads a prior recap's overrides, it pre-fills them as the new defaults and asks the user to confirm or change again.

## Cumulative-deviation check

In addition to the per-row tag, Phase 5 computes a **cumulative deviation from base** for each scenario-defining KPI (revenue, EPS, FCF margin) across the quarters in the recap window:

`cumulative_deviation = (Σ(actual_q - base_q) / Σ base_q) * 100`

If `|cumulative_deviation| > 25%` for ANY of those KPIs across ≥ 2 consecutive quarters, that's one of the auto-recommend triggers (see `auto-recommend-rules.md`).
```

- [ ] **Step 3: Write `references/auto-recommend-rules.md`**

```markdown
---
artifact: reference
topic: auto-recommend-rules
schema_version: 1
---

# Auto-Recommend Rules — when to propose a thesis update

After Checkpoint 2 in Quarterly mode (or Checkpoint 1 in News mode), the agent decides whether to recommend entering Phase 6 to update the thesis. The user can always override either way via native interactive-input.

## Trigger conditions (any one is sufficient)

The agent **auto-recommends** a thesis update if any of the following is true after Phase 5 (Quarterly) or Phase 3 (News):

1. **Any sell trigger is 🔴 fired.** See `sell-trigger-evaluation.md` for state definitions.

2. **Two or more sell triggers are 🟡 flashing.** One 🟡 alone doesn't auto-recommend; two does.

3. **Cumulative deviation from base case > 25% on any scenario-defining KPI (revenue, EPS, FCF margin) for ≥ 2 consecutive quarters in the window.** See `diff-thresholds.md` for the cumulative-deviation formula. Quarterly mode only — news mode doesn't compute this.

4. **GVD bucket fit no longer matches the saved classification.** Concretely: the data now scores higher for a different GVD bucket than the saved one (e.g., a saved `growth` name where the last 4 quarters show ≤5% revenue YoY and the company has started raising its dividend would score higher as `dividend` than as `growth`). The agent runs a quick re-score against the 5 GVD buckets using the same scorecard `stock-research` Phase 8 uses; if a different bucket scores higher than the saved one, this rule fires.

5. **Reverse-DCF-implied growth at today's price has moved by > 50% relative to the saved one** (in either direction). If the saved value is `null` (no prior reverse-DCF saved), this rule is skipped.

6. **A capital-allocation event in the window changed the share count, debt level, or dividend policy by > 10%.** Compare share count between `latest_period_before_recap` and the latest new quarter; compare net debt the same way; compare dividend per share annualized. Any one moving >10% (in absolute terms for share count and net debt, in growth rate for dividend) fires this rule.

## Recommendation rendering

If any rule fires:

```markdown
**Recommendation: enter Phase 6 to update the thesis.**

Why:
- <Rule 1 text>: <specific evidence, e.g., "Trigger 'iPhone unit decline > 10% YoY' fired; 2026-Q2 was -12.3%.">
- <Rule 4 text>: <evidence>
```

Then native interactive-input — 2 options:
1. **Enter Phase 6 to update** (the recommended path).
2. **Continue without updating** (the user disagrees with the recommendation — they may want to wait one more quarter for confirmation).

If NO rule fires:

```markdown
**No automatic update recommended.**

All sell triggers are 🟢 clear or 🟡 flashing-but-not-elevated. Cumulative deviation from base is within ±25% on all scenario-defining KPIs. GVD bucket fit unchanged. Reverse-DCF drift within ±50%. No major capital-allocation event.
```

Then native interactive-input — 2 options:
1. **Continue without updating** (the default).
2. **Update anyway** (the user wants to make a surgical edit despite no automatic trigger).
```

- [ ] **Step 4: Sync and commit**

```bash
python3 scripts/sync_skill.py push stock-recap
git add skills/stock-recap/references/
git commit -m "$(cat <<'EOF'
stock-recap: references — sell-trigger eval, diff thresholds, auto-recommend rules

Adds the three rubrics Phase 5 (Quarterly) and Phase 3 (News) load to
evaluate the saved thesis against refreshed data. sell-trigger-evaluation
defines the 4-state model with worked examples and boundary cases;
diff-thresholds defines default tolerances and the override-capture
flow that persists to the recap doc's frontmatter; auto-recommend-rules
lists the six conditions that propose a thesis update (and the
rendering when none fire).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Quarterly Phase 5 — trajectory synthesis + Checkpoint 2

**Files:**
- Modify: `skills/stock-recap/SKILL.md` (append Quarterly Phase 5 + Checkpoint 2)

- [ ] **Step 1: Append Quarterly Phase 5 + Checkpoint 2 to SKILL.md**

```markdown
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
```

- [ ] **Step 2: Sync and commit**

```bash
python3 scripts/sync_skill.py push stock-recap
git add skills/stock-recap/SKILL.md
git commit -m "$(cat <<'EOF'
stock-recap: Quarterly Phase 5 + Checkpoint 2

Phase 5 is interactive synthesis in the main agent: cross-quarter
trajectory narrative appended to cross-call-themes.md, three diff
tables (bull/base/bear), cumulative deviation check, 4-state
sell-trigger evaluation, and GVD bucket fit re-check. Checkpoint 2
assembles all five sub-sections and renders the auto-recommend
evaluation, then uses native interactive-input to branch to Phase 6
(update) or Phase 7 (commit-only).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: References — update-flow + Quarterly Phase 6 + Checkpoint 3

**Files:**
- Create: `skills/stock-recap/references/update-flow.md`
- Modify: `skills/stock-recap/SKILL.md` (append Quarterly Phase 6 + Checkpoint 3)

- [ ] **Step 1: Write `references/update-flow.md`**

```markdown
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
```

- [ ] **Step 2: Append Quarterly Phase 6 + Checkpoint 3 to SKILL.md**

```markdown
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
```

- [ ] **Step 3: Sync and commit**

```bash
python3 scripts/sync_skill.py push stock-recap
git add skills/stock-recap/SKILL.md skills/stock-recap/references/update-flow.md
git commit -m "$(cat <<'EOF'
stock-recap: Quarterly Phase 6 + Checkpoint 3 + update-flow reference

Phase 6 routes through three sub-modes — surgical, reclassification,
or recommend-full-pivot — picked via native interactive-input. The
reference doc spells out each workflow. Checkpoint 3 renders a unified
diff of the proposed verdict.{md,json} (and projections.{md,json} if
touched) changes BEFORE any write; the user applies or revises. On
reclassification, the prior files are snapshotted to
verdict-archive/projections-archive before overwrite.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Quarterly Phase 7 — commit, index, tag-on-reclassification

**Files:**
- Modify: `skills/stock-recap/SKILL.md` (append Quarterly Phase 7)

- [ ] **Step 1: Append Quarterly Phase 7 to SKILL.md**

```markdown
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
```

- [ ] **Step 2: Sync and commit**

```bash
python3 scripts/sync_skill.py push stock-recap
git add skills/stock-recap/SKILL.md
git commit -m "$(cat <<'EOF'
stock-recap: Quarterly Phase 7 — recap doc, index, commit, tag-on-reclass

Phase 7 composes recap-<YYYY-MM-DD>-quarterly.md per spec §7.2, calls
upsert_ticker.py + update_index.py from the toolkit, then commits with
the full structured-trailer message. Tag <TICKER>/v<N+1> only fires
when Phase 6 ran in reclassification sub-mode — surgical updates and
no-update sessions commit on the existing version. Closes the
Quarterly flow.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: News mode — event capture, context fetch sub-agent, impact analysis, commit

**Files:**
- Create: `skills/stock-recap/phases/news/02-context-fetch-sub.md`
- Modify: `skills/stock-recap/SKILL.md` (append News mode section — Phases 1.5 / 2 / 3 / 4 / 5 + Checkpoints 1, 2)

- [ ] **Step 1: Write `phases/news/02-context-fetch-sub.md`**

```markdown
---
artifact: phase-prompt
phase: news-2
phase_name: targeted-context-fetch
schema_version: 1
---

# News Mode Phase 2 Sub-Agent Prompt — Targeted Context Fetch

You are a sub-agent dispatched by the News mode Phase 2 orchestrator. The orchestrator has decided that ONE specific data refresh is warranted for the event being analyzed. Your job is to run that refresh and return a tight summary.

## Context (injected by the orchestrator)

- `ticker`: ticker symbol.
- `ticker_dir`: absolute path to `tickers/<TICKER>/`.
- `toolkit_dir`: absolute path to financial-toolkit.
- `fetch_kind`: one of `latest-8K` / `prices+consensus` / `target-financials` / `risk-factors-diff` / `competitor-pull`.
- `extra_args`: kind-specific arguments (see below).

## Your job

Dispatch the right toolkit script for `fetch_kind`, write the output to disk, return a structured summary.

## Step 1: Branch by `fetch_kind`

### `fetch_kind == "latest-8K"`

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_sec.py <ticker> \
  --forms 8-K \
  --since <extra_args.since-date> \
  --out <ticker_dir>/.raw/news-<YYYY-MM-DD>/
```

`fetch_sec.py` does not support `--until` — it fetches every 8-K with `filing_date >= --since`. Inspect the resulting `_filings_index.json` and find the entry whose `filing_date` is closest to (and within ±7 days of) `extra_args.event-date`. Return the path to that 8-K HTML and a 2-3 sentence summary of what it discloses (read it).

### `fetch_kind == "prices+consensus"`

Run both in sequence:
```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_prices.py <ticker> --years 2 --out <ticker_dir>/prices/
<toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_analyst_estimates.py <ticker> --out <ticker_dir>/
```

Return the latest close, the day-over-event-day price reaction (if `extra_args.event-date` is set: close on event_date+1 vs close on event_date-1), and analyst-consensus drift (if a prior `market-expectations.json` existed).

### `fetch_kind == "target-financials"` (M&A target's financials)

If `extra_args.target_ticker` is US-listed:
```bash
mkdir -p <ticker_dir>/.raw/news-<YYYY-MM-DD>/
<toolkit_dir>/.venv/bin/python <toolkit_dir>/compute_financials.py <extra_args.target_ticker> \
  --years 5 \
  --out <ticker_dir>/.raw/news-<YYYY-MM-DD>/target-<extra_args.target_ticker>.json
```

`compute_financials.py`'s `--out` is a FILE path (writes JSON to it). Return a 1-paragraph summary of the target's revenue scale, margins, growth, and how they compare to the parent.

### `fetch_kind == "risk-factors-diff"`

`diff_risk_factors.py` takes the two 10-K filing files directly — it doesn't fetch them itself. So this is a two-step fetch:

```bash
# Step 1: fetch both years' 10-Ks (if not already present in tickers/<ticker>/.raw/)
<toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_sec.py <ticker> \
  --forms 10-K \
  --since <extra_args.prior-year>-01-01 \
  --out <ticker_dir>/.raw/news-<YYYY-MM-DD>/

# Step 2: diff the two HTML files (the orchestrator passes their on-disk paths in extra_args)
<toolkit_dir>/.venv/bin/python <toolkit_dir>/diff_risk_factors.py \
  --ticker <ticker> \
  --file-a <extra_args.file-a-path> \
  --file-b <extra_args.file-b-path> \
  --out <ticker_dir>/.raw/news-<YYYY-MM-DD>/risk-factors-diff.json \
  --out-md <ticker_dir>/.raw/news-<YYYY-MM-DD>/risk-factors-diff.md
```

After Step 1's fetch, inspect `_filings_index.json` to identify the prior-year and current-year 10-K HTML paths (matching by `report_date`'s year). Then run Step 2 with those paths.

Return the list of NEW risk factors added in `current-year` vs `prior-year` (read from the JSON or MD output).

### `fetch_kind == "competitor-pull"`

Re-use `stock-research`'s Phase 4 sub-sub-agent pattern: pull one competitor's financials. Args: `extra_args.competitor_ticker`.

```bash
mkdir -p <ticker_dir>/.raw/news-<YYYY-MM-DD>/
<toolkit_dir>/.venv/bin/python <toolkit_dir>/compute_financials.py <extra_args.competitor_ticker> \
  --years 5 \
  --out <ticker_dir>/.raw/news-<YYYY-MM-DD>/competitor-<extra_args.competitor_ticker>.json
```

`compute_financials.py`'s `--out` is a FILE path. Return a 1-paragraph comparison.

## Step 2: Return structured summary

```
FETCH_KIND: <kind>
STATUS: <DONE | DONE_WITH_CONCERNS | BLOCKED>
FILES_WRITTEN: <list>
SUMMARY: <2-4 sentences>
NOTES: <one sentence>
```
```

- [ ] **Step 2: Append News mode section to SKILL.md**

```markdown
---

# News mode

The following phases apply only when the user picked **News mode** at Phase 1's mode picker.

## News mode Phase 1.5: Event capture

(Phase 1 ran already in shared form; News mode adds an event-capture step before any fetch.)

### Step 1.5.1 — Capture the event (free-form)

Ask the user, in plain Markdown:

> What's the event? Be specific — date, what was announced, where it was disclosed (8-K, press release, news article, transcript, etc.).

Capture the answer verbatim into a session variable `event_description`.

Also ask:

> What date did the event take place? (YYYY-MM-DD)

Capture as `event_date`.

### Step 1.5.2 — Classify the event (agent + user)

The agent proposes a classification from this fixed list:

- `M&A` — acquisition, divestiture, merger.
- `leadership` — CEO / CFO / Chair change, board resignation.
- `regulatory` — ruling, fine, antitrust action, new compliance regime.
- `guidance-restated` — pre-announcement, profit warning, reaffirmation.
- `customer-or-supply-chain` — major customer loss / win / supplier disruption.
- `litigation` — verdict, settlement, class-action.
- `other` — anything else.

Use native interactive-input — 7 options (one per class). The user confirms or picks a different class.

Capture as `event_class`.

## News mode Phase 2: Optional context fetch

The agent proposes which refreshes are warranted based on `event_class`. Defaults:

| event_class | Default proposed fetches |
|---|---|
| M&A | `latest-8K`, `target-financials` (if target US-listed and known) |
| leadership | (none — usually no fetch needed) |
| regulatory | `latest-8K`, `risk-factors-diff` (latest 10-K vs prior) |
| guidance-restated | `latest-8K`, `prices+consensus` |
| customer-or-supply-chain | `latest-8K`, `competitor-pull` (if a peer is named in the event) |
| litigation | `latest-8K`, `risk-factors-diff` |
| other | (none — agent asks the user what to fetch) |

Surface the proposed fetches via native interactive-input — multi-select with one option per proposed fetch, plus "Skip all fetches" as an alternative. The user can pick a subset.

For each selected fetch, dispatch one sub-agent in parallel using `phases/news/02-context-fetch-sub.md`. Wait for all to return.

On any `BLOCKED` status: surface via native interactive-input — 2 options: **Continue without that data** / **Retry**.

## News mode Phase 3: Impact analysis (interactive)

This phase runs in the main agent. It does NOT fan out.

**Read these references before starting:**
- `references/sell-trigger-evaluation.md` — for sub-step 3.4.
- `references/auto-recommend-rules.md` — for the recommendation evaluation.

For each affected thesis layer, walk the user through what changes:

### Step 3.1 — Business model / moat

Does this event widen, narrow, or leave the moat unchanged? One paragraph. Cite specific evidence from Phase 2's fetched data (or, if no fetch, from the saved `business-and-moat.md`).

### Step 3.2 — Financials

Which line items are affected over the next 4 quarters? Direction (up / down) and rough magnitude (small / material / transformative). One bullet per affected line.

### Step 3.3 — Projection levers

For each of bull / base / bear, propose deltas on the affected yearly KPI rows. Use free-form dialogue:

> Phase 3 of the news analysis: I think this event shifts the **base case** Y2 revenue from $X.XB to $Y.YB (a -<delta>% impact) because <reason>. Bull case Y2 revenue: from $A.AB to $B.BB. Bear case Y2 revenue: from $C.CB to $D.DB (worst-affected scenario). What do you think?

The user accepts / disputes / proposes alternates. Capture agreed shifts.

### Step 3.4 — Sell triggers — re-evaluate only the affected ones

Identify the subset of triggers across all three categories in `verdict.json.sell_triggers` (`materially_overvalued`, `thesis_broken`, `better_opportunity`) that this event plausibly affects (the agent proposes; the user confirms with a quick "yes / I'd add this one too" exchange). Apply `references/sell-trigger-evaluation.md` to each of those. The unaffected triggers stay marked "not re-evaluated this session."

## News mode Checkpoint 1 — Impact review

**Before rendering:** assemble §3.1–§3.4 plus the auto-recommend evaluation from `references/auto-recommend-rules.md` (rules 1, 2, 4, 6 apply in news mode; rules 3 and 5 are quarterly-mode specific and skipped).

Format (rendered Markdown):

```markdown
## Checkpoint 1 — News impact review

### Event

> <event_description from Phase 1.5>

Class: **<event_class>** | Date: <event_date>

### Business model / moat impact

<§3.1, one paragraph.>

### Financials impact

<§3.2, bullet list of affected line items.>

### Projection levers shifted

<§3.3, table of bull/base/bear yearly KPI changes.>

### Sell triggers re-evaluated

<§3.4, list of affected triggers with new state + justification. Note explicitly which triggers were NOT re-evaluated this session.>

---

### Auto-recommend evaluation

<Same as Quarterly Checkpoint 2's auto-recommend block — apply rules 1, 2, 4, 6 only. If any fires, recommend Phase 4 update. Otherwise, no automatic update.>
```

Use native interactive-input — same 2 options as Quarterly Checkpoint 2 (depending on the recommendation): **Enter Phase 4 to update** vs **Continue without updating**, OR **Continue without updating** vs **Update anyway**.

If continue → jump to Phase 5 (commit & index).
If enter Phase 4 → proceed.

## News mode Phase 4: Update thesis (optional)

Identical to Quarterly Phase 6 — same three sub-modes (surgical / reclassification / pivot-to-restart), same `update-flow.md` workflow, same diff-before-write Checkpoint 2.

## News mode Checkpoint 2 — Diff before write

Identical to Quarterly Checkpoint 3 — same diff rendering, same Apply / Revise further options, same write-on-Apply logic.

## News mode Phase 5: Commit & index

Identical to Quarterly Phase 7 with two differences:

1. The recap doc is named `<ticker_dir>/recaps/recap-<YYYY-MM-DD>-news.md` (mode = `news` in frontmatter).
2. The commit trailer has `session: news-recap` and `trigger: 8-K-<event_date>` if Phase 2 fetched an 8-K, otherwise `trigger: news` or `trigger: catalyst-event` depending on what the event was.

The body of the recap doc uses the News mode sections defined in spec §7.2:

```yaml
---
ticker: <TICKER>
artifact: recap
mode: news
session: news-recap
session_date: <YYYY-MM-DD>
window_start: <event_date>
window_end: <event_date>
event_summary: "<short version of event_description>"
event_class: <event_class>
periods_processed: []
thesis_version_before: <vN>
thesis_version_after: <vN | vN+1>
schema_version: 1
---

# <TICKER> — News recap, <YYYY-MM-DD>

## Event

<event_description verbatim.>

Class: **<event_class>** | Date: <event_date> | Disclosure: <8-K | press release | etc.>

## Affected thesis layers

### Business model / moat
<§3.1>

### Financials
<§3.2>

### Projection levers
<§3.3>

## Affected sell triggers

<§3.4 — only the re-evaluated ones, with state + justification. Explicit note that unaffected triggers remain in the state from the last quarterly recap.>

## Thesis update applied

<Same shape as Quarterly Phase 7 step 7.1.>

## Next review trigger

<today + 90 days, or earlier if user specified.>
```
```

- [ ] **Step 3: Sync and commit**

```bash
python3 scripts/sync_skill.py push stock-recap
git add skills/stock-recap/SKILL.md skills/stock-recap/phases/news/02-context-fetch-sub.md
git commit -m "$(cat <<'EOF'
stock-recap: News mode — event capture, targeted fetch, impact analysis, commit

Adds the News mode flow: Phase 1.5 captures event description and
class via free-form + native interactive-input (7 event classes);
Phase 2 dispatches one or more targeted-context-fetch sub-agents
chosen by the event class; Phase 3 walks impact across business
model, financials, projection levers, and the affected subset of
sell triggers; Phase 4 reuses Quarterly Phase 6's update-flow (three
sub-modes, diff-before-write); Phase 5 commits a news-mode recap doc
distinguishable by filename suffix and frontmatter mode field.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Trigger-test scenarios + behavioral pressure scaffold

**Files:**
- Modify: `tests/skill-trigger/scenarios.toml`

- [ ] **Step 1: Read the existing scenarios.toml structure**

```bash
grep -n "^\[\[scenario\]\]" tests/skill-trigger/scenarios.toml | wc -l
```

Note the count so we can confirm two new scenarios got added.

- [ ] **Step 2: Append two new scenarios to `tests/skill-trigger/scenarios.toml`**

Append at the end of the file (after the last `[[scenario]]` block):

```toml

[[scenario]]
id = "stock-recap-quarterly-catch-up"
skill = "stock-recap"
prompt = "I last researched NOW back in February. Catch me up on the quarters that have been filed since then — I want to see whether the thesis still holds."
description_terms = ["recapping an existing US-listed stock thesis", "catching up on every quarter", "Mechanically diffs actuals vs saved bull/base/bear projections", "LLM-evaluates the saved English sell triggers"]
skill_terms = ["Quarterly catch-up", "phases/quarterly/02-fetch-sub.md", "auto-recommend", "Checkpoint 2 — Trajectory, diff, and triggers"]
forbidden_terms = ["CP1", "CP2", "CP3", "ELI5"]

[[scenario]]
id = "stock-recap-news-impact"
skill = "stock-recap"
prompt = "Microsoft just announced acquiring Activision for $69B. I have an existing thesis on MSFT — recap it through the lens of this acquisition."
description_terms = ["impact of a material event", "M&A, CEO change, regulatory ruling", "how does this acquisition affect"]
skill_terms = ["News mode", "phases/news/02-context-fetch-sub.md", "event_class", "Checkpoint 1 — News impact review"]
forbidden_terms = ["CP1", "CP2", "CP3", "ELI5"]
```

Note that `forbidden_terms` is checked by `static_contract.py` against the FULL `SKILL.md` body (not just the description) and against the test `prompt` — so it cannot include `"stock-research"` even though the routing intent is "this prompt should pick stock-recap, not stock-research." The stock-recap SKILL.md legitimately references the sibling `stock-research` skill many times in its prereqs and abort messages. The behavioral pressure suite (separate from static_contract) is the place that exercises actual routing between sibling skills.

- [ ] **Step 3: Verify the scenarios were added**

```bash
grep -n "^\[\[scenario\]\]" tests/skill-trigger/scenarios.toml | wc -l
```

Expected: 2 more than the count from Step 1.

```bash
grep -n "stock-recap" tests/skill-trigger/scenarios.toml | head -10
```

Expected: at least 4 lines (2 `id =` and 2 `skill =` references) mentioning `stock-recap`.

- [ ] **Step 4: Run static_contract**

```bash
python3 tests/skill-trigger/static_contract.py
```

Expected: passes for all skills, including the new `stock-recap` scenarios. The static contract validates:
- Each scenario's `skill` exists at `skills/<skill>/SKILL.md`.
- Each `description_terms` entry appears in the skill's description.
- Each `skill_terms` entry appears somewhere in `SKILL.md` body or in one of its `phases/`, `references/`, or `commands/` files.
- No `forbidden_terms` entries appear in the SKILL.md description.

If any `description_terms` fails: the strings must literally appear in the SKILL.md description. Re-check the description text for that exact phrase, or update the test phrase to match what's actually there.

If any `skill_terms` fails: the strings must appear somewhere in the skill tree. They should — the prompts and references we wrote include them.

- [ ] **Step 5: Commit**

```bash
git add tests/skill-trigger/scenarios.toml
git commit -m "$(cat <<'EOF'
stock-recap: add quarterly + news trigger-test scenarios

Two scenarios exercising the two flows. The quarterly scenario
explicitly forbids "stock-research" in the description match so the
"I last researched X, catch me up" phrasing routes to stock-recap
rather than stock-research. Both forbid the legacy abbreviations
(CP1/CP2/CP3, ELI5) per the no-abbreviations rule.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: End-to-end dry run + final dual-sync verification

**Files:** none modified — this is verification only.

This task confirms the skill is install-ready and runs cleanly against the only ticker the user has actually researched (NOW).

- [ ] **Step 1: Confirm both install dirs are current**

```bash
python3 scripts/sync_skill.py push stock-recap
diff -rq skills/stock-recap/ ~/.claude/skills/stock-recap/
diff -rq skills/stock-recap/ ~/.codex/skills/stock-recap/
```

Expected: both diffs report no differences (the sync command's `shutil.copytree` ignores `.gitkeep`, so the install dirs may lack those files; if `diff` flags only `.gitkeep` files as missing, that's fine).

- [ ] **Step 2: Validate every YAML frontmatter parses**

```bash
python3 - <<'PY'
import re, yaml, pathlib
root = pathlib.Path("skills/stock-recap")
errors = []
for md in root.rglob("*.md"):
    txt = md.read_text()
    parts = re.split(r"^---\s*$", txt, maxsplit=2, flags=re.M)
    if len(parts) < 2:
        continue
    try:
        yaml.safe_load(parts[1])
    except Exception as e:
        errors.append(f"{md}: {e}")
print("OK" if not errors else "FAIL:\n" + "\n".join(errors))
PY
```

Expected: prints `OK`. Any failure means a frontmatter description has unquoted special characters.

- [ ] **Step 3: Confirm references are link-clean**

```bash
python3 - <<'PY'
import re, pathlib
root = pathlib.Path("skills/stock-recap")
missing = []
for md in root.rglob("*.md"):
    txt = md.read_text()
    # Pull `references/...md` and `phases/...md` references
    for m in re.finditer(r"`(references/[a-z0-9-]+\.md|phases/(?:quarterly|news)/[a-z0-9-]+\.md)`", txt):
        target = root / m.group(1)
        if not target.exists():
            missing.append(f"{md} -> {m.group(1)}")
print("OK" if not missing else "FAIL:\n" + "\n".join(missing))
PY
```

Expected: prints `OK`. Any failure means a phase or reference path mentioned in the SKILL.md or a phase prompt doesn't actually exist on disk — fix by either creating the missing file or correcting the reference.

- [ ] **Step 4: Run static_contract one more time**

```bash
python3 tests/skill-trigger/static_contract.py
```

Expected: full pass — all 17+ skills (now including `stock-recap`) covered.

- [ ] **Step 5: Manual smoke walkthrough (no commit)**

This is a read-only walkthrough by the implementer (you, the agent executing this plan) — not an actual recap run. Verify the workflow makes sense when read end-to-end:

1. Open `skills/stock-recap/SKILL.md` and read top to bottom. Confirm:
   - Frontmatter description is double-quoted.
   - Mode router precedes both flows.
   - Quarterly flow has 7 phases + 3 checkpoints (matching spec §5).
   - News flow has 5 phases + 2 checkpoints (matching spec §6).
   - Every sub-agent prompt referenced in SKILL.md exists at the expected path under `phases/`.
   - Every reference file mentioned exists under `references/`.
2. Open each phase prompt and confirm it has the standard `artifact: phase-prompt` frontmatter, a Context section listing the orchestrator-injected variables, numbered steps, and a Failure modes / return-summary section.
3. Open each reference file and confirm it's self-contained — readable in isolation when the orchestrator loads it mid-phase.

If anything is missing or inconsistent, fix it inline (small edits only — major reshuffles mean reopening the plan).

- [ ] **Step 6: Final commit (only if Step 5 surfaced any fixes)**

If Step 5 produced any fixes:

```bash
python3 scripts/sync_skill.py push stock-recap
git add skills/stock-recap/
git commit -m "$(cat <<'EOF'
stock-recap: end-to-end cleanup pass

Small consistency fixes surfaced by reading the skill top-to-bottom
after the implementation tasks: <list of fixes>.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If Step 5 surfaced no fixes: no commit. The implementation is done.

- [ ] **Step 7: Confirm git state is clean**

```bash
git status --short
```

Expected: empty output. Every change from this plan has been committed.

```bash
git log --oneline aeddf7a..HEAD
```

Expected: ~13 commits, one per task, in order. Each commit message starts with `stock-recap:` and has the structured trailer.

---

## Self-Review Notes

### Spec coverage check

- **Spec §1 Purpose** → Tasks 2 (preamble), 3 (Phase 1 ticks the trajectory-first intent), 8 (Phase 5 trajectory synthesis).
- **Spec §2 Scope and non-goals** → Task 2 (When to use / Do not use sections).
- **Spec §3 High-level architecture** → Task 1 (canonical-copy scaffold), Task 12 (trigger scenarios), Task 13 (final dual-sync verification).
- **Spec §3.3 Versioning policy** → Task 9 (update-flow's reclassification sub-mode), Task 10 (Phase 7.5 tag-on-reclassification only).
- **Spec §4 Two flows + mode router** → Task 2 (Mode router section), Task 3 (Phase 1 mode picker).
- **Spec §5 Quarterly Phase 1** → Task 3.
- **Spec §5 Quarterly Phase 2** → Task 4.
- **Spec §5 Quarterly Phase 3** → Task 5.
- **Spec §5 Quarterly Phase 4 + Checkpoint 1** → Task 6.
- **Spec §5 Quarterly Phase 5 (trajectory + diff + triggers) + Checkpoint 2** → Tasks 7 (references) + 8.
- **Spec §5 Quarterly Phase 6 (update) + Checkpoint 3** → Tasks 7 (auto-recommend reference) + 9.
- **Spec §5 Quarterly Phase 7** → Task 10.
- **Spec §6 News mode Phases 1–5 + Checkpoints 1, 2** → Task 11.
- **Spec §7 Artifact and naming conventions** → Tasks 10 (Quarterly recap doc shape) + 11 (News recap doc shape).
- **Spec §8 Failure modes** → Distributed across Tasks 4, 5, 6, 11 (each phase has its own failure-handling table).
- **Spec §9 Inheritance from stock-research** → Task 2 (preamble inherits conventions explicitly).
- **Spec §10 Open items** → No tasks (deferred by design).
- **Spec §11 Implementation order** → This plan follows it 1:1.

### Placeholder scan

- No `TODO`, `TBD`, `FIXME`, `XXX`, `<placeholder>` markers anywhere.
- Every code block has actual content — no "write the test" without showing the test.
- Every step has a concrete command or concrete file content.
- The two appearances of `...` in CLI examples (`--field ...`) are intentional shorthand matching the `stock-research` spec convention.

### Type-consistency check

- Sub-agent return summary fields are named consistently: `STATUS`, `FILES_WRITTEN`, `NOTES` appear in every phase sub-agent's return contract.
- The state symbols 🔴🟡🟢⚪ are used identically in Tasks 7, 8, 9, 11.
- `update_applied` enum: `"none"`, `"surgical"`, `"reclassification"`, `"pivot-recommended"` — used consistently in Tasks 9, 10, 11.
- `event_class` enum: `M&A`, `leadership`, `regulatory`, `guidance-restated`, `customer-or-supply-chain`, `litigation`, `other` — defined once in Task 11 and not re-defined elsewhere.
- `fetch_kind` enum in `phases/news/02-context-fetch-sub.md`: `latest-8K`, `prices+consensus`, `target-financials`, `risk-factors-diff`, `competitor-pull` — used consistently in the sub-agent prompt and in the orchestrator's defaults table.

---

End of plan.
