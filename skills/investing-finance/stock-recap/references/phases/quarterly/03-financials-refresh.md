---
artifact: phase-prompt
phase: quarterly-3-financials
phase_name: financials-refresh
schema_version: 1
---

# Quarterly Phase 3 Sub-Agent Prompt — Financials Refresh

You are a sub-agent dispatched by the Quarterly Phase 3 orchestrator. Extend the saved quarterly and TTM series without exposing the canonical `financials.json` to a partial write. Annual recomputation, raw SEC facts, and the merged candidate are separate artifacts; the canonical file changes only after validation.

## Context (injected by the orchestrator)

- `ticker`: ticker symbol.
- `ticker_dir`: absolute path to `tickers/<TICKER>/`.
- `skill_scripts_dir`: absolute path to this skill's bundled runtime.
- `session_date`: recap date in `YYYY-MM-DD` form.
- `new_periods`: accepted Phase 2 pairs with explicit `period` (`YYYY-Qn`) and SEC `report_date` (`YYYY-MM-DD`).
- `latest_period_before_recap`: exact pre-recap `financials.json.latest_report_date`.

## Your job

1. Recompute annual history into a staged JSON file and save the unmodified SEC company-facts response to a distinct raw path.
2. Inspect staged `tag_resolution`, `missing_concepts`, and raw company facts for data-quality gaps.
3. Merge each explicit new period into preserved `quarters[]` and `ttm[]` state with the bundled quarterly refresh runtime.
4. Validate the complete staged merge, generate staged Markdown, then atomically promote both canonical artifacts.
5. Check the TTM trend gate and return a structured summary.

## Step 1: Define distinct paths

Use one same-filesystem work directory so final renames are atomic:

```bash
mkdir -p <ticker_dir>/.raw/recap-financials-<session_date>/
```

Set these exact roles; none of the first three may equal either canonical path:

```text
ANNUAL_STAGE=<ticker_dir>/.raw/recap-financials-<session_date>/annual-financials.json
COMPANY_FACTS_RAW=<ticker_dir>/.raw/recap-financials-<session_date>/company-facts.json
MERGED_STAGE=<ticker_dir>/.raw/recap-financials-<session_date>/merged-financials.json
FINANCIALS_CANONICAL=<ticker_dir>/financials.json
MARKDOWN_STAGE=<ticker_dir>/.raw/recap-financials-<session_date>/financials.md
```

## Step 2: Pull annual XBRL and raw facts into staging

```bash
<skill-python> -B <skill_scripts_dir>/compute_financials.py <ticker> \
  --years 10 \
  --company-facts-out <COMPANY_FACTS_RAW> \
  --out <ANNUAL_STAGE>
```

`compute_financials.py --out` and `--company-facts-out` are file paths. The annual output includes `years[].report_date` and top-level `latest_report_date`; the raw artifact is the complete SEC company-facts response. If the command fails, return `BLOCKED`. Do not touch the canonical JSON.

## Step 3: Inspect data quality before merging

Inspect existing manual entries in `<FINANCIALS_CANONICAL>` plus `<ANNUAL_STAGE>.tag_resolution` and `.missing_concepts`. Carry each still-applicable existing manual entry into the pending resolution list. If a metric is unresolved or uses an unexpected fallback, inspect `<COMPANY_FACTS_RAW>.facts.us-gaap` directly. Never look for company facts under recap gap-detection output, and never hand-edit the canonical file.

Determine any supported manual resolution and retain its exact metric, source concept or value, source evidence, and reason for Step 5. Do not write `<MERGED_STAGE>` yet; it does not exist until Step 4 completes. If the company does not report a metric, plan to keep it `null` and retain the corresponding entry under `data_quality` or `quarterly_data_quality`.

## Step 4: Build the preserved quarterly/TTM merge

Invoke the merger with one `--period` argument for every accepted pair, in chronological order:

```bash
<skill-python> -B <skill_scripts_dir>/refresh_quarterly_financials.py \
  --baseline <FINANCIALS_CANONICAL> \
  --annual-refresh <ANNUAL_STAGE> \
  --company-facts <COMPANY_FACTS_RAW> \
  --period <YYYY-Qn>=<YYYY-MM-DD> \
  --period <YYYY-Qn>=<YYYY-MM-DD> \
  --out <MERGED_STAGE>
```

Repeat `--period` exactly once per `new_periods` item; do not infer dates from labels. The runtime preserves unknown/manual top-level fields, nested `tag_resolution` and `data_quality` metadata, manual fields on dated annual/quarterly/TTM points, and prior dated points. Generated fields from the annual and quarterly refresh take precedence while retained manual fields remain alongside them. It adds or replaces points by `report_date`, derives a 10-K fourth quarter from annual less the first three quarters when needed, and computes each new TTM point from four dated quarters. It writes `<MERGED_STAGE>` atomically; `<FINANCIALS_CANONICAL>` is still unchanged.

TTM diluted EPS uses this order: sum four finite standalone quarterly `EarningsPerShareDiluted` facts when all four are available; otherwise divide four-quarter net income by diluted shares weighted by each quarter's actual covered-day count. When a 10-K supplies only the fiscal-year weighted share average, derive the fourth-quarter share average as the covered-day residual after the first three standalone quarters. Never divide TTM net income by the latest quarter's shares or silently reuse an annual share value. Missing, nonnumeric, nonfinite, nonpositive-share, or invalid-duration inputs make the fallback unavailable; keep `eps` or `diluted_shares` null as applicable, name them in `missing_metrics`, and preserve the reported/derived/unavailable basis plus gap periods under `eps_data_quality`.

The merged schema contract is:

- `latest_report_date`: maximum covered SEC period end in ISO form.
- `years[]`: annual points, each with `fiscal_year` and `report_date`.
- `quarters[]`: dated points with `period`, `report_date`, `form`, reported/derived metrics, source concepts, diluted-share duration/basis, EPS basis, and explicit missing metrics.
- `ttm[]`: dated points with `period`, `report_date`, `source_periods`, TTM metrics, duration-weighted diluted shares, TTM EPS, EPS basis/data quality, and explicit missing metrics.
- `quarterly_tag_resolution.<period>` and `quarterly_data_quality.<period>`: source and gap evidence for each refreshed period.

## Step 5: Apply manual resolutions, then validate

Only after Step 4 has created `<MERGED_STAGE>`, apply each supported resolution from Step 3 to that file. Store annual concept-resolution evidence under `tag_resolution.manual_resolution.<metric>`, annual point-specific evidence under the matching `years[].manual_resolution.<metric>`, or quarter-specific evidence under `quarterly_tag_resolution.<period>.manual_resolution`. A manual value override must update the generated metric on that dated point and record the same value plus its source and reason under the point's `manual_resolution.<metric>` entry, so the next recap can reapply it. Keep manual data-quality evidence under the corresponding `data_quality.manual_resolution` or `quarterly_data_quality.<period>.manual_resolution` key. Use structured JSON editing, preserve all existing manual entries, and do not edit `<FINANCIALS_CANONICAL>`.

After those edits, read `<MERGED_STAGE>` and require all of the following:

1. `schema_version == 1` and ticker identity matches the baseline.
2. `latest_report_date` equals the maximum `report_date` from the staged annual and requested recap periods.
3. Every `new_periods` pair has exactly one matching entry in both `quarters[]` and `ttm[]`.
4. Every pre-existing quarter and TTM point outside the refreshed dates remains present.
5. TTM revenue, gross profit, operating income, net income, diluted shares, FCF, and EPS are numeric or are named under that point's `missing_metrics`; `eps_basis` and `eps_data_quality` agree with the documented method, and no missing value is silently treated as zero.
6. Every pre-existing manual entry under `tag_resolution`, `data_quality`, and dated financial points remains present, and every Step 3 resolution is recorded at its documented nested path.

If any structural check fails, return `BLOCKED` and leave both canonical files untouched. Data genuinely absent from SEC facts produces `DONE_WITH_CONCERNS`, not invented values.

## Step 6: Generate Markdown and promote atomically

Generate `<MARKDOWN_STAGE>` from the validated merged JSON with frontmatter fields `ticker`, `artifact: financials`, `as_of: <latest_report_date>`, and `schema_version: 1`. Include Income Statement, Balance Sheet, Cash Flow, Trend Gate, Capital Allocation Scorecard, **What changed since last touch**, and **Data quality** when gaps exist.

Only after both staged artifacts are complete:

```bash
mv <MERGED_STAGE> <FINANCIALS_CANONICAL>
mv <MARKDOWN_STAGE> <ticker_dir>/financials.md
```

These same-filesystem renames are the only canonical writes. If staging, inspection, or Markdown generation fails, do not run either rename.

## Step 7: Trend gate and inflections

For the latest new TTM point, compare revenue, net income, FCF, and margins YoY:

- **Pass:** revenue and net income are up, with no material contrary signal.
- **Pass-with-caveats:** revenue and net income are up but FCF or a margin is mixed.
- **Fail:** revenue or net income is down.

Compare each metric's TTM value at `latest_period_before_recap` with the latest new period. Flag moves greater than 10% for revenue, EPS, or FCF and greater than 200 basis points for margins. If either comparison point is absent, mark that metric `cannot-evaluate`.

## Step 8: Return summary

```text
STATUS: <DONE | DONE_WITH_CONCERNS | BLOCKED>
NEW_PERIODS_INTEGRATED: <period=report_date comma-list>
LATEST_REPORT_DATE: <financials.json.latest_report_date>
TREND_GATE: <Pass | Pass-with-caveats | Fail with specifics>
INFLECTIONS: <bullet list of metrics that moved >10% / 200 basis points>
DATA_QUALITY_GAPS: <bullet list, or "none">
RAW_COMPANY_FACTS: <COMPANY_FACTS_RAW>
FILES_WRITTEN: financials.md, financials.json
NOTES: <one sentence on anything unusual>
```
