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
- `skill_scripts_dir`: absolute path to the bundled financial runtime install (`<skill-root>/scripts/`).
- `company_slug`: lowercase, hyphen-separated company name (for transcript scraper URL guessing; best-effort).
- `manual_transcript_path` *(optional, only set on a re-dispatch after the user pasted a transcript)*: absolute path to a temp file containing the pasted transcript text. When this is set, skip the scraper and feed this file into `fetch_transcript.py --manual` via stdin (see Step 4b).

## Your job

1. Create distinct per-quarter raw-filing and extracted-section scratch dirs.
2. Download the SEC filing (full HTML) into the scratch dir.
3. Run the right section extractor (`extract_10q_sections.py` or `extract_10k_sections.py`).
4. Fetch the earnings-call transcript with the standard scraper → IR-page → manual-paste fallback chain.
5. Return a 1-paragraph fetch-status summary.

## Step 1: Create scratch dir

```bash
mkdir -p \
  <ticker_dir>/.raw/recap-<quarter>/filing/ \
  <ticker_dir>/.raw/recap-<quarter>/sections/ \
  <ticker_dir>/earnings-calls/
```

## Step 2: Download SEC filing

```bash
<skill-python> -B <skill-scripts-dir>/fetch_sec.py <ticker> \
  --forms <form_type> \
  --since <quarter_end_date> \
  --out <ticker_dir>/.raw/recap-<quarter>/filing/
```

`fetch_sec.py` downloads every filing matching `<form_type>` with `filing_date >= --since`. Companies typically file 10-Qs within ~45 days of quarter-end and 10-Ks within ~75 days, so setting `--since` to `<quarter_end_date>` is enough to catch the right filing without pulling unrelated later filings.

**Identify the right filing.** `fetch_sec.py` writes a manifest at `<ticker_dir>/.raw/recap-<quarter>/filing/_filings_index.json` with shape:
```json
{ "ticker": "...", "cik": "...", "filings": [
    { "accession": "...", "form": "10-Q", "filing_date": "2026-08-01",
      "report_date": "2026-06-30", "filename": "..." }
  ] }
```
Find the entry whose `report_date` equals `<quarter_end_date>`. Join that entry's `filename` to the `--out` directory and call the result `<raw_filing_path>`. This is the raw SEC HTML passed to the section extractor; it is not a cleaned analysis input.

**Failure detection.** `fetch_sec.py` returns exit 0 even when zero filings match `--since`. If `filing/_filings_index.json.filings` is empty, OR no entry's `report_date` matches `<quarter_end_date>`, return status `NEEDS_CONTEXT_FILING` (see Step 5 for the enum split) with the message `"No <form_type> with report_date=<quarter_end_date> found in SEC EDGAR for <ticker>"`. Exit code 2 from `fetch_sec.py` means the ticker is not on EDGAR at all — also return `NEEDS_CONTEXT_FILING` in that case.

## Step 3: Extract sections

If `form_type == "10-Q"`:

```bash
<skill-python> -B <skill-scripts-dir>/extract_10q_sections.py <ticker> \
  --html <raw_filing_path> \
  --quarter <quarter> \
  --out <ticker_dir>/.raw/recap-<quarter>/sections/
```

If `form_type == "10-K"`:

```bash
<skill-python> -B <skill-scripts-dir>/extract_10k_sections.py <ticker> \
  --html <raw_filing_path> \
  --year <fiscal-year> \
  --out <ticker_dir>/.raw/recap-<quarter>/sections/
```

Where `<fiscal-year>` is the 4-digit year prefix of `<quarter>` (so `2026-Q4` → `2026`); `extract_10k_sections.py` interprets it as the fiscal year covered by the 10-K.

Read `sections/_10q_sections_index.json` or `sections/_10k_sections_index.json` after extraction. Resolve each name in its `sections[]` array to `<sections-dir>/<name>.md`; those are the cleaned paths Phase 4 receives. If the extractor exits non-zero, or an indexed Markdown file is missing, return status `DONE_WITH_CONCERNS` and name the absent sections so Phase 4 does not fall back to raw HTML.

## Step 4: Fetch earnings-call transcript

**Step 4a — first dispatch (no `manual_transcript_path` in your context):**

```bash
<skill-python> -B <skill-scripts-dir>/fetch_transcript.py <ticker> \
  --quarter <quarter> \
  --company-slug <company_slug> \
  --out <ticker_dir>/earnings-calls/
```

This script's fallback chain is: Motley Fool scraper → IR-page guess → manual-paste prompt. The first two are tried automatically; if both fail, the script exits with code 3 and prints the manual-paste instruction. On exit 3, return status `NEEDS_CONTEXT_TRANSCRIPT` with the instruction text — the orchestrator will surface a native-interactive prompt asking the user to paste, write the paste to a temp file, and re-dispatch you with `manual_transcript_path` set in your context block.

**Step 4b — re-dispatch with `manual_transcript_path` set:**

When you are re-dispatched after a paste, skip the scraper attempt entirely and pipe the staged file directly into the script:

```bash
<skill-python> -B <skill-scripts-dir>/fetch_transcript.py <ticker> \
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
RAW_FILING_PATH: <ticker_dir>/.raw/recap-<quarter>/filing/<filename>
FILING_SECTIONS_INDEX_PATH: <ticker_dir>/.raw/recap-<quarter>/sections/<_10q_sections_index.json | _10k_sections_index.json>
EXTRACTED_SECTION_PATHS: <comma-list of absolute .md paths from the extractor index>
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
