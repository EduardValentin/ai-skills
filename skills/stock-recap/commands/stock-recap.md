---
description: Start a stock-recap session on a US-listed ticker. Usage: /stock-recap <TICKER>
argument-hint: <TICKER>
---

Start a `stock-recap` session on the ticker {{args}}.

Invoke the `stock-recap` skill and pass the ticker symbol as the initial input. The skill's Phase 1 will resolve the ticker, verify preconditions (prior `verdict.json` exists), detect any 10-Q/10-K filings since the last recap, and ask the user to pick the mode (Quarterly catch-up vs News event).
