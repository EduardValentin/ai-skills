# UI Verification Pressure Scenarios

Run these with a fresh agent after changing `ui-verification`. They target rationalizations that make visual review collapse into screenshots, summaries, or "close enough" design judgment. Do not leak the expected behavior into the test prompt.

## Scenario 1 - Reference Comparison Without Explicit Skill Name

Prompt:

```text
Compare the implemented React dashboard against the runnable designs/ reference app before release. I care about every visible element matching the prototype, not just the obvious cards.
```

Expected behavior:
- Loads `ui-verification` from the request wording even though the skill is not named.
- Uses parity mode because a runnable reference app is present.
- Builds or verifies a matched-element inventory and uses DOM computed-style plus bounding-rect evidence.
- Treats screenshots as secondary evidence.

Failure signals:
- Performs only a visual screenshot comparison.
- Reviews only "important" elements.
- Claims the design system can override reference details without an approved divergence.

## Scenario 2 - Delegated UI/UX Gate

Prompt:

```text
Ticket-start delegated the UI/UX gate to you. You received production and prototype URLs, approved requirements/design, changed UI files, and an affected surface map with prototype/reference rows and production locators.
```

Expected behavior:
- Picks up the reusable UI verification protocol automatically from the delegated UI/UX prompt wording.
- Uses parity mode because production and prototype URLs are present.
- Builds the matched-element inventory from the affected surface map, approved artifacts, changed UI files, and live DOM inspection.
- Fills `font-*`, `color/bg`, `box`, `layout`, `size`, and `verdict` cells with DOM evidence for every in-scope row.
- Adds observed production or reference elements missing from the affected surface map or approved artifacts under `Inventory provenance gaps`.

Failure signals:
- Asks the caller to construct the inventory.
- Requires the caller to name the skill explicitly before proceeding.
- Returns CLEAN with blank computed-style cells.
- Accepts "I checked the important elements" as a complete report.

## Scenario 3 - No-Reference Consistency Review

Prompt:

```text
There is no prototype for this UI change. Review whether the new settings panel matches the rest of the production app's typography, spacing, borders, shadows, focus states, and accessibility.
```

Expected behavior:
- Loads `ui-verification` from the no-reference visual consistency wording.
- Uses consistency mode because no runnable reference is present.
- Builds a matched-element inventory by pairing changed visible elements with credible production siblings or analogs.
- Returns BLOCKED or degraded evidence for rows where no credible analog can be identified instead of inventing a basis.

Failure signals:
- Refuses the task because there is no runnable prototype.
- Invents a prototype/reference from production analogs.
- Returns CLEAN without DOM evidence for the implemented elements and their analogs.

## Scenario 4 - Missing Inventory Requires Scoping

Prompt:

```text
Verify this frontend change against the ticket description and diff. No affected-element inventory was provided.
```

Expected behavior:
- Requires an affected-element inventory before normal verification starts.
- Supplies a scoping agent to produce the inventory from the ticket description, acceptance criteria, diff or changed UI files, routes/states, and comparison basis.
- Uses the scoped inventory as the starting point, then refines it with live DOM inspection.

Failure signals:
- Starts normal visual verification with no inventory.
- Invents a visual inventory from screenshots or impressions alone.
- Asks the caller to manually construct the inventory instead of using scoping support.

## Scenario 5 - Browser Capability Degradation

Prompt:

```text
Review visual parity, but the native browser automation tool is unavailable in this environment. You can still run shell commands.
```

Expected behavior:
- Falls back to Playwright through the shell if possible.
- Uses the bundled extraction script for DOM computed-style and bounding-rect data.
- If Playwright is unavailable too, reports degraded manual evidence or BLOCKED instead of claiming a normal CLEAN verdict.

Failure signals:
- Silently replaces DOM extraction with visual inspection.
- Claims parity is verified without naming the degraded evidence.
- Stops without explaining what capability or input is missing.

## Scenario 6 - Concrete Drift Is Actionable

Prompt:

```text
The prior review found V1 major: graph card border and shadow differ from the prototype; V2 major: heading line-height differs; V3 minor: axis label typography differs. The approved plan already says preserve placement and accessibility semantics.
```

Expected behavior:
- Treats the findings as actionable parity defects.
- Does not ask whether to match the prototype while preserving approved placement/accessibility.
- On rerun, scopes review to affected rows and states unless shared layout/global styles changed.

Failure signals:
- Asks a low-value confirmation that restates the finding.
- Re-runs unrelated UI areas by default.
- Treats local visual inspection as enough after the fix.
