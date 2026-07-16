---
artifact: reference
name: financial-data-quality
schema_version: 1
---

# Financial Data Quality

## Core Rule

Extraction success is not the same as data correctness. Before financials reach the user, the Phase 3 worker must check whether every reported, inferred, manual, missing, and derived value is safe to use downstream.

## Metric Statuses

| Status | Meaning | Allowed downstream? |
|---|---|---|
| `reported` | Directly resolved from SEC XBRL, transcript, or market-data source. | Yes, with source tag/date. |
| `inferred` | Set from explicit filing language, such as no common dividend policy. | Yes, with narrative citation. |
| `manual` | Resolved by inspecting filing tables/tags after script extraction failed. | Yes, with evidence snippet and tag/table. |
| `missing` | Not resolved and not safe to infer. | No; dependent metrics must be null/unreliable. |

## Postmortem Checks

### Debt Mapping

If `long_term_debt` is missing, inspect available tags and the latest 10-K debt note before treating the company as debt-free.

Debt tags that require follow-up include:

- `LongTermDebt`
- `LongTermDebtNoncurrent`
- `LongTermDebtCurrent`
- `LongTermDebtAndFinanceLeaseObligationsNoncurrent`
- `LongTermDebtAndFinanceLeaseObligationsCurrent`
- `ConvertibleDebtNoncurrent`
- `ConvertibleDebtCurrent`
- `DebtInstrumentFaceAmount`

If any are present, resolve the debt value or mark debt as `manual`/`missing`; do not leave a derived net-cash figure in place.

### Derived Metrics

Derived metrics must be null or marked unreliable when inputs are missing.

| Derived metric | Required inputs |
|---|---|
| `net_debt` | `cash`, `long_term_debt` |
| `P/E` | `current_price`, `eps` |
| `P/FCF` | `market_cap`, `fcf` |
| `FCF/share` | `fcf`, `diluted_shares` |
| shareholder yield | `market_cap`, `buybacks`, `dividends_paid`, debt paydown if used |

### Dividends

Missing dividend tags mean unknown, not zero. Set `dividends_paid = 0` only when filing language explicitly supports it, for example a statement that the company does not intend to pay cash dividends on common stock for the foreseeable future or paid no common dividends in the period.

### Stock Splits

Watch for split-like jumps in diluted shares, usually ratios above `2.5x` or below `0.4x` between adjacent years. If detected:

1. Read the latest 10-K for split date, ratio, record date, and effective date.
2. Prefer the latest 10-K's restated comparative share and per-share values.
3. If restated values are unavailable, apply one consistent split factor to all pre-split per-share and share-count data.
4. State the normalization method in `financials.md`.

### SEC HTML Extraction

Raw inline XBRL HTML is often a huge single-line document. Avoid raw text search as evidence. Prefer:

- SEC company-facts JSON for tagged concepts.
- Inline XBRL tag/context parsing.
- Extracted 10-K sections and tables.
- Short nearby narrative snippets around a located tag or table.

## Required Phase 3 Gate

Run:

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/validate_financials.py \
  <ticker_dir>/financials.json \
  --out <ticker_dir>/.raw/financials-validation.json
```

If the validation status is `fail`, resolve the issue or surface it as a blocker before Checkpoint 2. If the status is `warn`, lead Checkpoint 2 with the warning and explain whether downstream valuation/projections are affected.
