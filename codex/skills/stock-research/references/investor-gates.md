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
