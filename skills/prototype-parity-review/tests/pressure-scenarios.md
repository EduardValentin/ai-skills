# Prototype Parity Review Pressure Scenarios

Run these with a fresh agent after changing `prototype-parity-review`. They target rationalizations that make visual review collapse into screenshots, summaries, or "close enough" design judgment. Do not leak the expected behavior into the test prompt.

## Scenario 1 - Prototype Comparison Without Explicit Skill Name

Prompt:

```text
Compare the implemented React dashboard against the runnable designs/ reference app before ship. I care about every visible element matching the prototype, not just the obvious cards.
```

Expected behavior:
- Loads `prototype-parity-review` from the trigger wording even though the skill is not named.
- Uses parity mode because a runnable reference app is present.
- Builds or verifies a matched-element inventory and uses DOM computed-style plus bounding-rect evidence.
- Treats screenshots as secondary evidence.

Failure signals:
- Performs only a visual screenshot comparison.
- Reviews only "important" elements.
- Claims the design system can override prototype details without an approved divergence.

## Scenario 2 - Ticket-Start Delegated UI/UX Gate

Prompt:

```text
Ticket-start delegated the UI/UX gate to you. Mode is parity. You received production and prototype URLs plus an expected matched-element inventory whose computed-style cells are blank.
```

Expected behavior:
- Loads `prototype-parity-review` as the delegated reviewer protocol.
- Treats every supplied inventory row as a contract.
- Fills `font-*`, `color/bg`, `box`, `layout`, `size`, and `verdict` cells with DOM evidence.
- Adds any observed extra production or prototype elements under `Rows added beyond the supplied inventory`.

Failure signals:
- Rebuilds the inventory from scratch and drops supplied rows.
- Returns CLEAN with blank computed-style cells.
- Accepts "I checked the important elements" as a complete report.

## Scenario 3 - Consistency Mode Without Prototype

Prompt:

```text
There is no prototype for this UI change. Review whether the new settings panel matches the rest of the production app's typography, spacing, borders, shadows, focus states, and accessibility.
```

Expected behavior:
- Uses consistency mode.
- Enumerates every new or changed visible element from the diff and production route.
- Identifies sibling/analog elements in the same view.
- Compares computed styles and bounding rects against those analogs.

Failure signals:
- Declares that no prototype means visual review can be skipped.
- Reviews only screenshots.
- Omits analog rows for changed visible elements.

## Scenario 4 - Browser Capability Degradation

Prompt:

```text
Review visual parity, but the native browser automation tool is unavailable in this environment. You can still run shell commands.
```

Expected behavior:
- Falls back to Playwright through the shell if possible.
- Uses the bundled extraction script for DOM computed-style and bounding-rect data.
- If Playwright is unavailable too, reports a degraded/manual fallback or BLOCKED status instead of claiming a normal CLEAN verdict.

Failure signals:
- Silently replaces DOM extraction with visual inspection.
- Claims parity is verified without naming the degraded evidence.
- Stops without explaining what capability or input is missing.

## Scenario 5 - Concrete Drift Is Actionable

Prompt:

```text
The prior review found V1 major: graph card border and shadow differ from the prototype; V2 major: heading line-height differs; V3 minor: axis label typography differs. The approved plan already says preserve placement and accessibility semantics.
```

Expected behavior:
- Treats the findings as actionable prototype parity defects.
- Does not ask whether to match the prototype while preserving approved placement/accessibility.
- On rerun, scopes review to affected rows and states unless shared layout/global styles changed.

Failure signals:
- Asks a low-value confirmation that restates the finding.
- Re-runs unrelated UI areas by default.
- Treats local visual inspection as enough after the fix.
