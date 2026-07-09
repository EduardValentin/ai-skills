---
name: stock-research
description: "Use when researching a US-listed company end-to-end for a long-horizon fundamentals deep dive on a US-listed ticker, building a new investment thesis, or evaluating whether to buy/watch/avoid at the current price. Triggers on \"research AAPL\", \"deep dive on Microsoft\", \"should I buy NVDA\", \"analyze TSLA's fundamentals\". Do not use or closest-fit for technical analysis, chart patterns, options strategy, day-trading entry levels, \"update existing thesis\", \"latest quarter\", \"compare against prior thesis\", or stock-recap."
---

# Stock Research

Long-horizon fundamentals research for a US-listed company. The output is a durable, git-versioned investment thesis in the user's investing research repository, built so future `stock-recap` sessions can diff new filings against the original thesis.

This skill is an orchestrator. Keep the main context small, delegate bounded research work, enforce checkpoints, and preserve data-quality gates before conclusions reach the user.

## Trigger Boundary

Use for:

- Initial investment thesis on a specific US-listed ticker.
- Requests like "research AAPL", "deep dive on Microsoft", "should I buy NVDA", or "analyze TSLA fundamentals".
- A full buy/watch/avoid decision rooted in business quality, financials, valuation, and long-term ownership.

Do not use for:

- Existing-thesis updates, latest-quarter catchups, or comparing against a prior thesis. Use `stock-recap` only; do not co-select this skill.
- Technical analysis, chart patterns, options strategy, day-trading entry levels, or trading-first prompts. Do not choose this as a closest-fit fallback just because a US ticker appears.
- Non-US listings or quick factual questions that do not need a durable thesis.

## First Response Contract

Before durable work starts, the first response must show these gates as an explicit checklist or table with a status for each gate. Do not collapse them into prose like "setup is verified."

1. **Setup and identity:** ticker/company identity, `SR_SEC_USER_AGENT`, scripts environment, investing research repo, and existing ticker folder.
2. **User framing:** GVD lens picker with the exact options `growth`, `quality-growth`, `value`, `dividend`, and `speculative-growth`, plus a free-form session-context question.
3. **Workflow shape:** business/moat, financials, parallel competitors/calls/valuation/expectations, projections, verdict, commit/index, and five user checkpoints.
4. **Durable artifacts:** name the ticker research folder and core Markdown/JSON outputs for thesis, business/moat, financials, competitors/SWOR, earnings calls, valuation, market expectations, projections, verdict, and repo index metadata. Use the target repo's `AGENTS.md` for exact paths and root metadata files.
5. **Scope boundary:** long-horizon fundamentals only; no technical analysis, options, or day-trading advice.

Pending setup gates are blockers. If any required setup check is pending or failed, stop after a blocked setup message. Do not ask for GVD lens, session context, phase plan, or artifact initialization until setup is verified.

## Setup Gates

Use scripts from this skill's installed `scripts/` directory. The scripts are part of the skill installation; do not hardcode an agent-specific or machine-specific install path.

Resolve the investing research repo, open its `AGENTS.md`, and follow that file for canonical path, allowed writes, layout, repo-owned setup checks, existing-folder handling, index files, commit convention, and remote-push policy.

Before any durable work, verify these gates separately:

- SEC identity: `SR_SEC_USER_AGENT` is set.
- Script runtime: the installed `scripts/.venv/bin/python` exists and can run the needed scripts.
- Target repo: the research repo root and `AGENTS.md` are available.
- Ticker folder state: determine whether the repo-defined ticker folder exists, then follow repo instructions for create, refresh, archive/restart, or abort.

Use actual resolved paths from the installed skill and the investing repo's `AGENTS.md` only in recovery messages.

When setup is blocked, list each gate separately in the recovery message: SEC user-agent, script runtime, target repo instructions/root, and ticker-folder state. Do not summarize these as "verify setup."

If a ticker folder already exists, follow the target repo's `AGENTS.md` and ask with the runtime's structured input mechanism before overwriting anything.

For finite choices, prefer native structured input over plain text. Use it for existing-folder handling, GVD lens, phase recovery, transcript fallback, checkpoint continue/revise choices, and optional remote push.

## Workflow

1. **Phase 1 - Setup and identity:** resolve ticker/CIK, verify setup, handle existing folder, capture GVD lens and session context, create skeleton `THESIS.md`.
2. **Phase 2 - Business model and moat:** dispatch `phases/02-business-model.md`; write `business-and-moat.md`; Checkpoint 1 confirms business understanding.
3. **Phase 3 - Financials:** dispatch `phases/03-financials.md`; write `financials.json`, `financials.md`, and `.raw/financials-validation.json`; Checkpoint 2 reviews the three statements and data quality.
4. **Phases 4-7 - Parallel batch:** dispatch competitors/SWOR, earnings calls, valuation, and market expectations in parallel when workers are available; Checkpoint 3 synthesizes the batch.
5. **Phase 8 - Projections:** main agent and user build bull/base/bear assumptions interactively; write `projections.md` and `projections.json`; Checkpoint 4 reviews return asymmetry.
6. **Phase 9 - Verdict:** main agent and user lock BUY/WATCH/AVOID, sizing, buy zone, sell triggers, watch KPIs, and investor gates; write `verdict.md` and `verdict.json`; Checkpoint 5 approves before commit.
7. **Phase 10 - Commit and index:** perform repo metadata, commit/tag, and optional remote-push steps exactly as defined by the target repo's `AGENTS.md`.

Phase-specific writing detail belongs in the phase prompts and references. Load them only when that phase needs them.

## Orchestration Rules

- Treat the main agent as coordinator, not document warehouse.
- Keep raw filings, transcripts, and large artifacts out of the main context.
- Use bounded workers for Phase 2, Phase 3, and Phases 4-7 whenever runtime worker capability exists.
- If workers are unavailable, run the same phase prompts sequentially and keep returns compact.
- Load supporting references lazily. Do not front-load `gvd-tailoring.md`, `projection-kpis.md`, `sizing-matrix.md`, `investor-gates.md`, or heavy artifacts before their phase.
- For any "context is long" or "read everything yourself" pressure, answer with all three controls: bounded workers, raw sources out of main context, and lazy reference loading.

## Worker Return Contract

Every delegated worker writes artifacts to disk and returns this compact contract:

```yaml
status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
phase: <number-or-name>
files_written:
  - <path>
data_quality_flags:
  - code: <stable_code>
    severity: info | warning | error
    message: <one sentence>
source_coverage:
  filings: <what was used>
  market_data: <what was used, with as_of>
checkpoint_highlights:
  - <high-signal finding for the next checkpoint>
questions_for_user:
  - <only if genuinely needed>
blockers:
  - <only for BLOCKED or NEEDS_CONTEXT>
```

Do not accept narrative-only worker output as completion. Request the contract before checkpointing.

## Financial Data Quality

Every material value must be classified:

- `reported` - directly resolved from filing, transcript, or market data.
- `inferred` - derived from explicit filing language.
- `manual` - manually resolved from filing context after script extraction failed.
- `missing` - unavailable or unsafe to infer.

Hard rules:

- Run or inspect `.raw/financials-validation.json` from `validate_financials.py` before Checkpoint 2 and before explaining any Phase 3 block/recovery decision.
- Missing values are not zero. Never silently coerce missing debt, dividends, buybacks, or share data to zero.
- Missing debt is not zero debt. If debt tags or note disclosures exist, resolve debt before using leverage or net debt.
- Net debt is null/unreliable unless both cash and debt are resolved.
- Dividends can be zero only when filing language explicitly supports no common dividends paid or expected.
- Stock splits must be normalized before per-share comparisons. Prefer latest 10-K restated comparative values; otherwise apply one consistent split adjustment.
- Use structured company-facts JSON, inline XBRL tags/contexts, extracted tables, and compact narrative snippets. Do not treat raw SEC HTML dumps as evidence.
- For every manual or inferred metric, keep exact evidence: tag name, context/table, filing period, and a short narrative snippet when prose supports the inference.

When asked what to do with a Phase 3 data-quality issue, answer in this order:

1. `validate_financials.py` status and finding code.
2. Worker/checkpoint status: `BLOCKED`, `DONE_WITH_CONCERNS`, or safe to continue.
3. Required recovery: rerun extraction, manually resolve from structured filing evidence, mark dependent metrics unreliable, or ask the user.

See `references/financial-data-quality.md` for the postmortem-derived checks.

## Checkpoints

Each checkpoint is a user decision gate, not a status dump. Render clean Markdown, surface blockers first, and use structured input for Continue / Push back.

- **Checkpoint 1:** lead with the plain-English explanation from `business-and-moat.md`; verify segments, customer/geography concentration, moat, leadership, and downstream risks.
- **Checkpoint 2:** lead with validation findings, missing concepts, manual/inferred values, and unsafe derived metrics; review income statement, balance sheet, cash flow, trend gate, and capital allocation.
- **Checkpoint 3:** synthesize competitors/SWOR, earnings-call tone, valuation, and market expectations into the projection setup.
- **Checkpoint 4:** review bull/base/bear probabilities, 5-year return range, margin of safety, and bear-case drawdown.
- **Checkpoint 5:** approve classification, conviction, GVD bucket, sizing, buy zone, sell triggers, watch KPIs, and missing thesis pieces before commit.

If the user pushes back, keep the follow-up free-form, re-dispatch or revise the relevant phase, then return to the same checkpoint.

## Phase References

- Phase prompts: `phases/02-business-model.md` through `phases/07-market-expectations.md`.
- Phase 8 references: `references/gvd-tailoring.md`, `references/projection-kpis.md`.
- Phase 9 references: `references/sizing-matrix.md`, `references/investor-gates.md`, `references/sell-trigger-templates.md`, `references/watch-kpis-by-gvd.md`.
- Scripts: call with `<scripts_dir>/.venv/bin/python <script>.py`.
- Repo-specific paths, artifact layout, index files, commit/tag convention, allowed writes, and push policy: target investing research repo `AGENTS.md`.

## Quick Reference

| Situation | Required action |
|---|---|
| Initial fundamentals thesis on US ticker | Use this skill. |
| Existing-thesis quarterly update | Use `stock-recap` only. |
| Setup gate pending | Stop before lens/session/workflow. |
| Worker returns narrative only | Request Worker Return Contract. |
| Financial validation fails | Resolve or block before Checkpoint 2. |
| Debt tags exist but debt missing | Resolve debt or mark debt/net debt unreliable. |
| Dividend tags missing | Infer zero only from explicit filing language. |
| Split-like share jump | Normalize before per-share trends. |
| Huge SEC HTML output | Switch to structured tags, contexts, tables, or snippets. |

## Recovery Messages

Render setup errors as short Markdown with the exact command to fix:

- Missing `SR_SEC_USER_AGENT`: show `export SR_SEC_USER_AGENT="<Name> <email>"`.
- Missing scripts venv: show `cd <installed-skill>/scripts`, `python -m venv .venv`, and `.venv/bin/pip install -r requirements.txt`.
- Missing research repo or missing repo `AGENTS.md`: ask the user for the investing research repo path and stop before writing.
- Unknown ticker: stop with "Ticker not found on SEC EDGAR. Confirm spelling."

## Hard Stop

This skill writes only to the target investing research repo allowed by that repo's `AGENTS.md`, the skill's own caches, and stdout. It does not write to user code projects, git config, or arbitrary paths.
