---
name: stock-research
description: "Use this skill for researching or providing updates about US-listed stock market companies."
compatibility: >-
  Requires SR_REPO_PATH pointing to a local US-equity research repo with AGENTS.md; SR_SEC_USER_AGENT; an external Python 3.10+ finance runtime under AI_SKILLS_RUNTIME_HOME, falling back to XDG_CACHE_HOME/HOME; SEC and market-data access; and Git. Worker and structured-input capabilities are optional: run bounded work sequentially and present numbered choices when they are unavailable. Existing-thesis recap mode also requires a complete canonical saved baseline in that repo.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Stock Research

Long-horizon fundamentals research for a US-listed company. Initial-research mode builds a durable, git-versioned investment thesis in the user's investing research repository; existing-thesis recap mode concisely compares new quarters or material events with that saved baseline.

This skill is an orchestrator in both modes. Keep the main context small, delegate bounded research work when useful, enforce the applicable checkpoint contract, and preserve data-quality gates before conclusions reach the user.

## Trigger Boundary

Use for:

- Initial investment thesis on a specific US-listed ticker.
- Requests like "research AAPL", "deep dive on Microsoft", "should I buy NVDA", or "analyze TSLA fundamentals".
- A full buy/watch/avoid decision rooted in business quality, financials, valuation, and long-term ownership.
- A concise update to an existing saved thesis after a new quarter, filing, earnings release, guidance change, acquisition, regulatory development, or other material event.
- Requests to compare current actuals, valuation, sell triggers, or watch KPIs with a prior saved thesis.

Eligible securities are common shares or ADRs listed on Nasdaq, the New York Stock Exchange, or NYSE American with sufficient SEC issuer data for this workflow. For a dual-listed issuer, use its US-listed ticker and state the relationship to the operating issuer. Exclude OTC securities and securities listed only outside the United States.

Do not use for:

- Technical analysis, chart patterns, options strategy, day-trading entry levels, or trading-first prompts. Do not choose this as a closest-fit fallback just because a US ticker appears.
- Non-US listings or quick factual questions that do not need a durable thesis.

## First Response Contract

The first response declares either **initial research** or **existing-thesis recap** and shows the applicable setup and identity gates as an explicit checklist or table with a separate status for each gate. Do not collapse the gates into prose like "setup is verified." For either mode, report ticker/company identity, `SR_SEC_USER_AGENT`, scripts environment, and investing research repo. Report the initial ticker-folder gate or recap baseline gate according to the selected mode. If any applicable gate is pending or failed, stop after the blocked gate report and focused recovery guidance.

For **initial-research mode**, if every setup gate passes, include items 2 through 5 in that response before durable work starts:

1. **Setup and identity:** ticker/company identity, `SR_SEC_USER_AGENT`, scripts environment, investing research repo, and existing ticker folder.
2. **User framing:** GVD lens picker with the exact options `growth`, `quality-growth`, `value`, `dividend`, and `speculative-growth`, plus a free-form session-context question.
3. **Workflow shape:** business/moat, financials, parallel competitors/calls/valuation/expectations, projections, verdict, commit/index, and five user checkpoints.
4. **Durable artifacts:** name the ticker research folder and core Markdown/JSON outputs for thesis, business/moat, financials, competitors/SWOR, earnings calls, valuation, market expectations, projections, verdict, and repo index metadata. Use the target repo's `AGENTS.md` for exact paths and root metadata files.
5. **Scope boundary:** long-horizon fundamentals only; no technical analysis, options, or day-trading advice.

For **existing-thesis recap mode**, if every common setup gate and the canonical-baseline gate pass, state the saved `latest_report_date`, identify the filing or material-event scope to inspect, preview the targeted gap/comparison/report flow, and state that there is one recap checkpoint before proposed durable thesis changes. Do not ask for a new GVD lens, discover new session context, preview the initial phase plan or initial artifact set, initialize a ticker folder, or present an overwrite prompt. If the canonical baseline is absent or incomplete, stop and offer this skill's initial-research mode instead.

In initial-research mode, do not ask for the GVD lens or session context, preview the phase plan or artifacts, make an existing-folder decision, or initialize artifacts until every initial setup gate is verified.

## Setup Gates

Use scripts from this skill's installed `scripts/` directory. The scripts are part of the skill installation; do not hardcode an agent-specific or machine-specific install path, and never create mutable runtime state under the installed skill.

Resolve the absolute external `<runtime-home>` from the first non-empty location: `AI_SKILLS_RUNTIME_HOME`, `${XDG_CACHE_HOME}/ai-skills`, or `${HOME}/.cache/ai-skills`. Set `<finance-venv>` to `<runtime-home>/investing-finance/venv` and `<skill-python>` to that environment's Python executable. This skill keeps its bundled runtime dependencies in that external environment. To set it up with Python 3.10 or newer:

```bash
runtime_home="$(
  PYTHONPATH="<installed-skill>/scripts" python3 -B -c \
    'from _lib.config import ai_skills_runtime_home; print(ai_skills_runtime_home())'
)"
finance_venv="${runtime_home}/investing-finance/venv"
python3 -B -m venv "${finance_venv}"
"${finance_venv}/bin/python" -B -m pip install --requirement "<installed-skill>/scripts/requirements.txt"
```

Always pass `-B` to bundled scripts and inline helper invocations, including calls assembled for subprocesses. If an integration cannot pass interpreter flags, set `PYTHONPYCACHEPREFIX="${runtime_home}/investing-finance/pycache"` in that subprocess environment.

Resolve the investing research repo from `SR_REPO_PATH`, open its `AGENTS.md`, and follow that file for canonical paths, allowed writes, layout, repo-owned setup checks, existing-folder handling, index files, commit convention, and remote-push policy.

Before any durable work, verify these common gates separately:

- Ticker/company identity: resolve the ticker and CIK, confirm the company, and confirm that the security meets the eligibility rule above.
- SEC identity: `SR_SEC_USER_AGENT` is set.
- Script runtime: `<skill-python>` is Python 3.10 or newer, is outside the installed skill, and can import the pinned bundled dependencies and run the needed scripts.
- Target repo: `SR_REPO_PATH` is set and its research repo root and `AGENTS.md` are available.

Then verify only the selected mode's folder gate:

- Initial-research mode: determine whether the repo-defined ticker folder exists, then follow repo instructions for create, refresh, archive/restart, or abort.
- Existing-thesis recap mode: require the repo-defined ticker folder and its canonical saved baseline. The baseline must contain a thesis, financial history with `latest_report_date`, saved bull/base/bear scenarios, a valuation baseline, and verdict metadata containing sell triggers and watch KPIs. Do not initialize a folder or reconstruct an incomplete baseline in recap mode. Stop and offer initial-research mode if any required component is absent or incomplete.

Use actual resolved paths from the installed skill and the investing repo's `AGENTS.md` only in recovery messages.

When setup is blocked, list each applicable gate separately in the recovery message: ticker/company identity, SEC user-agent, script runtime, target repo variable/instructions/root, and either initial ticker-folder state or recap canonical-baseline state. Do not summarize these as "verify setup."

In initial-research mode, if a ticker folder already exists, follow the target repo's `AGENTS.md` and ask with the runtime's structured input mechanism before overwriting anything. If structured input is unavailable, present the same options as a numbered plain-text choice and wait for the user's answer. Recap mode never presents this overwrite choice.

For finite choices, prefer native structured input over plain text. In initial-research mode, use it for existing-folder handling, GVD lens, phase recovery, transcript fallback, checkpoint continue/revise choices, and optional remote push. In recap mode, use it only for genuinely needed recovery choices and the recap checkpoint.

## Existing-Thesis Recap Mode

Use this concise mode only when the target repo already contains the canonical saved baseline. It is a targeted delta review, not an abbreviated pass through the initial phase tree.

- **Baseline gate:** Resolve canonical artifact paths from the target repo's `AGENTS.md`. Require the saved thesis, financial history and its `latest_report_date`, every saved bull/base/bear scenario, the valuation baseline, and verdict metadata with every sell trigger and watch KPI. If any component is absent or incomplete, stop recap work and offer this skill's initial-research mode; do not silently rebuild or infer the baseline.
- **SEC period gap map:** Compare the saved `latest_report_date` only with each relevant SEC filing's `report_date`, never its `filing_date`. Identify every missing covered reporting period in chronological order. A later filing cannot close, conceal, or justify skipping an intermediate report; refresh each missing period in sequence or stop on the unresolved gap.
- **Targeted refresh:** Refresh only the identified missing financial periods and valuation or market data affected by the quarter or material event. Use the installed `scripts/refresh_quarterly_financials.py` for the needed period refresh and the richer installed `scripts/fetch_sec.py` capabilities when filing metadata, structured facts, contexts, tables, or narrative snippets are needed. Inspect and follow each script's actual interface; do not invent a CLI command, flag, or subcommand. Do not rebuild unaffected history or rerun unrelated initial-research phases.
- **Case and trigger comparison:** Compare actuals separately with every saved bull, base, and bear case; do not collapse the review to the base case. Evaluate every saved sell trigger verbatim, preserving its exact threshold and window, as exactly `fired`, `flashing`, `clear`, or `cannot-evaluate`. Missing or inadequate evidence is `cannot-evaluate`, never an inferred `clear`. Preserve every saved watch item for reporting.
- **Recap and approval:** Concisely report the current thesis, valuation against its saved baseline, every saved watch item/KPI, every sell-trigger result, sources and information cutoff, and exactly what changed. Propose exact durable thesis/artifact changes and present one recap checkpoint. Explicit user approval is required before applying any durable thesis, scenario, valuation-baseline, or verdict change; presenting or discussing the analysis alone is not approval.

## Initial-Research Workflow

1. **Phase 1 - Setup and identity:** resolve ticker/CIK, verify setup, handle existing folder, capture GVD lens and session context, create skeleton `THESIS.md`.
2. **Phase 2 - Business model and moat:** dispatch `references/phases/02-business-model.md`; write `business-and-moat.md`; Checkpoint 1 confirms business understanding.
3. **Phase 3 - Financials:** dispatch `references/phases/03-financials.md`; write `financials.json`, `financials.md`, and `.raw/financials-validation.json`; Checkpoint 2 reviews the three statements and data quality.
4. **Phases 4-7 - Parallel batch:** dispatch competitors/SWOR, earnings calls, valuation, and market expectations in parallel when workers are available; Checkpoint 3 synthesizes the batch.
5. **Phase 8 - Projections:** main agent and user build bull/base/bear assumptions interactively; write `projections.md` and `projections.json`; Checkpoint 4 reviews return asymmetry.
6. **Phase 9 - Verdict:** main agent and user lock BUY/WATCH/AVOID, sizing, buy zone, sell triggers, watch KPIs, and investor gates; write `verdict.md` and `verdict.json`; Checkpoint 5 approves before commit.
7. **Phase 10 - Commit and index:** perform repo metadata, commit/tag, and optional remote-push steps exactly as defined by the target repo's `AGENTS.md`.

Phase-specific writing detail belongs in the phase prompts and references. Load them only when that phase needs them.

## Orchestration Rules

- Treat the main agent as coordinator, not document warehouse.
- Keep raw filings, transcripts, and large artifacts out of the main context.
- In initial-research mode, use bounded workers for Phase 2, Phase 3, and Phases 4-7 whenever runtime worker capability exists. If workers are unavailable, run the same phase prompts sequentially and keep returns compact.
- In existing-thesis recap mode, delegate only bounded missing-period or event-affected research when useful; do not dispatch initial phase prompts for unaffected areas.
- In initial-research mode, load supporting references lazily. Do not front-load `gvd-tailoring.md`, `projection-kpis.md`, `sizing-matrix.md`, `investor-gates.md`, or heavy artifacts before their phase.
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

These rules apply to new evidence in either mode. Every material value must be classified:

- `reported` - directly resolved from filing, transcript, or market data.
- `inferred` - derived from explicit filing language.
- `manual` - manually resolved from filing context after script extraction failed.
- `missing` - unavailable or unsafe to infer.

Hard rules:

- Run or inspect `.raw/financials-validation.json` from `validate_financials.py` before Checkpoint 2 and before explaining any Phase 3 block/recovery decision.
- In existing-thesis recap mode, run or inspect validation evidence for every refreshed financial period before comparing it with saved cases; unresolved values remain `missing` and cannot support a `clear` sell-trigger result.
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

Each checkpoint is a user decision gate, not a status dump. Render clean Markdown and surface blockers first.

- **Existing-thesis recap mode:** use exactly one recap checkpoint after the concise report. Offer explicit choices to approve the proposed durable changes, revise the analysis, or keep the analysis without durable changes. Only the explicit approval choice authorizes a durable thesis, scenario, valuation-baseline, or verdict edit; recap mode does not inherit Checkpoints 1 through 5.
- **Initial-research mode:** use the five checkpoints below, with structured input for Continue / Push back.

- **Checkpoint 1:** lead with the plain-English explanation from `business-and-moat.md`; verify segments, customer/geography concentration, moat, leadership, and downstream risks.
- **Checkpoint 2:** lead with validation findings, missing concepts, manual/inferred values, and unsafe derived metrics; review income statement, balance sheet, cash flow, trend gate, and capital allocation.
- **Checkpoint 3:** synthesize competitors/SWOR, earnings-call tone, valuation, and market expectations into the projection setup.
- **Checkpoint 4:** review bull/base/bear probabilities, 5-year return range, margin of safety, and bear-case drawdown.
- **Checkpoint 5:** approve classification, conviction, GVD bucket, sizing, buy zone, sell triggers, watch KPIs, and missing thesis pieces before commit.

If the user pushes back in either mode, keep the follow-up free-form, re-dispatch or revise only the relevant work, then return to the same mode-specific checkpoint.

## Phase References

- Phase prompts: `references/phases/02-business-model.md` through `references/phases/07-market-expectations.md`.
- Phase 8 references: `references/gvd-tailoring.md`, `references/projection-kpis.md`.
- Phase 9 references: `references/sizing-matrix.md`, `references/investor-gates.md`, `references/sell-trigger-templates.md`, `references/watch-kpis-by-gvd.md`.
- Scripts: call with `<skill-python> -B <scripts_dir>/<script>.py`.
- Repo-specific paths, artifact layout, index files, commit/tag convention, allowed writes, and push policy: target investing research repo `AGENTS.md`.

## Quick Reference

| Situation | Required action |
|---|---|
| Initial fundamentals thesis on US ticker | Use initial-research mode. |
| New quarter or material event with a complete saved thesis | Use existing-thesis recap mode. |
| Recap baseline absent or incomplete | Stop recap and offer this skill's initial-research mode. |
| Recap SEC coverage gap | Compare `latest_report_date` with filing `report_date`; enumerate and process every missing period in order. |
| Recap refresh scope | Refresh only missing periods and event-affected valuation/market data using actual installed script interfaces. |
| Recap sell-trigger evidence missing | Preserve the trigger verbatim and report `cannot-evaluate`. |
| Initial setup gate pending | Stop before lens, session context, phase preview, folder decision, or initialization. |
| Recap setup gate pending | Stop before gap analysis or event refresh. |
| Worker returns narrative only | Request Worker Return Contract. |
| Financial validation fails | Resolve or block before initial Checkpoint 2 or the recap checkpoint. |
| Debt tags exist but debt missing | Resolve debt or mark debt/net debt unreliable. |
| Dividend tags missing | Infer zero only from explicit filing language. |
| Split-like share jump | Normalize before per-share trends. |
| Huge SEC HTML output | Switch to structured tags, contexts, tables, or snippets. |

## Recovery Messages

Render setup errors as short Markdown with the exact command to fix:

- Missing `SR_SEC_USER_AGENT`: show `export SR_SEC_USER_AGENT="<Name> <email>"`.
- Missing scripts runtime: show the external `runtime_home` / `finance_venv` setup commands from **Setup Gates** and never create an environment under `<installed-skill>`.
- Missing research repo variable: show `export SR_REPO_PATH="<path-to-investing-research>"` and stop before writing.
- Missing repo `AGENTS.md`: report the resolved `SR_REPO_PATH`, ask for a valid investing research repo root, and stop before writing.
- Missing or incomplete recap baseline: list the absent thesis, financial-history/`latest_report_date`, scenario, valuation-baseline, or verdict-metadata components and offer initial-research mode without writing recap changes.
- Unknown ticker: stop with "Ticker not found on SEC EDGAR. Confirm spelling."

## Hard Stop

This skill writes only to the target investing research repo allowed by that repo's `AGENTS.md`, the external finance runtime directories resolved above, and stdout. It never writes mutable state inside its installed root or writes to user code projects, git config, or arbitrary paths.

Existing-thesis recap analysis never authorizes a durable thesis change by itself. Apply proposed durable thesis, scenario, valuation-baseline, or verdict changes only after explicit user approval at the recap checkpoint.
