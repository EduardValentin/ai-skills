# Matched-element inventory as a cross-phase contract — design

**Status:** approved by user, ready for implementation plan
**Scope:** `skills/ticket-start/` only (canonical location after PR #6)
**Depends on:** PR #6 (`ticket-start: harden visual parity enforcement after observed failure`)
**Activation:** personal workflow + runnable React reference app (parity mode). Inactive otherwise.

## 1. Problem statement

Today the matched-element inventory in `agents/ui-ux.md` is built by the UI/UX subagent at verification time, from scratch, against the live DOM + the prototype + the diff. UI/UX is therefore doing two jobs in one pass: discovery (what should be in the inventory) and verification (does each row match between prototype and production).

Two structural problems follow:

1. **Discovery happens with the staleest context.** By Verify time, Setup's prototype context (the `designs/` slices Scoping read), Brainstorm's architectural decisions, the Plan's task-level intent, and the Implement phase's per-task knowledge of what was written have all moved out of the active reasoning surface. UI/UX has to re-acquire them cold.

2. **Step 6a has only one inventory to spot-check.** The main agent compares UI/UX's self-built inventory against the live apps and the diff, but it has no independent "expected" inventory to cross-reference. If UI/UX's inventory omits an element, the spot-check has to discover that omission by walking the diff and production DOM again. The protocol works but the work is duplicative and the failure mode (UI/UX selectively builds the inventory) is the exact failure mode the visual-parity hardening tried to prevent.

The user-stated goal: the main agent should already have the inventory built from the initial phases (Scoping + Plan + Implement), feed it into UI/UX as input, and validate UI/UX's returned verification against the pre-built version. The inventory becomes a contract that grows across phases rather than a one-shot artifact built at the end.

## 2. Goals and non-goals

### Goals

- Make the matched-element inventory a **contract**: built progressively in the phases that have the freshest context (Scoping seeds the prototype side; Plan declares production-side mappings; Implement lands them at file:lines; Verify dispatch stitches the expected table from those phases' outputs).
- Pass the **expected inventory** to UI/UX as a dispatch input. UI/UX's role narrows to **verification** of the supplied inventory, not first-time discovery.
- Cross-check **two inventories at step 6a** (expected vs verified). Reject any verdict where expected rows are absent in verified or have blank verification columns.
- Activate the contract only in **parity mode** (personal workflow + runnable React reference app). Leave consistency mode and job workflow on today's protocol.
- Preserve every existing protection from PR #6 — REQUIRED + EXHAUSTIVE inventory, four completeness rules, prototype-parity dominance, step 6a, three new red flags. The contract is additive in parity mode and unchanged elsewhere.

### Non-goals

- No persistent `inventory.md` file. The expected inventory lives in the dispatch payload to UI/UX; the verified inventory lives in the UI/UX report. Both are visible through existing artifacts.
- No new subagent. Main agent does the construction at dispatch in its own context.
- No structural change to the bug-fix loop (`bug-fix-loop.md`). Row-level re-run scoping refines today's "re-run scoped to affected states" rule but lives inside `agents/ui-ux.md`.
- No backfill onto in-flight tickets. The contract activates on tickets that go through Scoping/Plan/Implement after the change ships.
- No change to consistency mode or to job workflow.

## 3. Architectural decisions

Three decisions settled during brainstorming. Each has multiple alternatives that were considered and rejected.

| Decision | Choice | Alternative rejected | Why |
|---|---|---|---|
| **Inventory storage format** | Phase reports own their slices; main agent stitches the table at dispatch. (C from Q1) | Persistent `inventory.md` file enriched across phases; or inline per phase with no central table | Persistent file adds a new lifecycle to keep in sync. Inline-only forces UI/UX to walk multiple reports. The stitch-at-dispatch approach localises assembly to the one moment the table is needed, and the expected/verified pair travels through existing artifacts (dispatch payload + UI/UX report). |
| **Row granularity** | JSX-declaration level on each side; atomic verification per row. (C from Q2) | Component-only with root-level verification; or atomic rendered-DOM rows | Component-only loses sub-element drift detection (the exact failure mode of the originating ticket). Atomic rows force Scoping to predict render expansion from source — impossible reliably. JSX-declaration level matches Scoping's natural capability AND UI/UX still does atomic verification inside each row. |
| **Inventory scope** | Implementation-scoped only. (A from Q3) | Feature-surface-scoped; or implementation-scoped main + surface-completion at verify | Feature-surface-scoped forces Scoping to load more prototype context than its current charter (scoped slices). Hybrid creates rows with two provenances and complicates step 6a. Implementation-scoped matches the user's stated mental model ("elements to implement and their prototype counterpart") and is sufficient for the originating ticket's failure mode (every drifted element was implementation-scoped). |

## 4. Phase data flow

Activated only when **personal workflow + runnable React reference app**. Otherwise the workflow runs exactly as it does after PR #6.

```
Setup → Scoping subagent
   produces: prototype-element enumeration
   one row per visible JSX declaration in the scoped designs/
   slices, with:
     - designs/path:start-end
     - element type or component name
     - accessible name / role / text content
     - one-line purpose

Brainstorm → Architect
   unchanged. Architect doesn't touch element-level detail.

Plan → superpowers:writing-plans (driven by ticket-start's Plan section)
   per UI-touching task, plan body includes an `**Element mapping:**`
   block declaring:
     - prototype counterpart: reference to a Scoping row
     - planned production file:line

Implement → superpowers:subagent-driven-development
   unchanged. Implementers land elements at the planned file:lines.
   The diff is the source of truth for actual post-implementation locators.

Verify (dispatch, before UI/UX runs) → main agent stitches the table
   for each (Scoping prototype row + plan mapping + actual post-diff state):
     produces a row with:
       | prototype file:line | prototype selector hint
       | production file:line (resolved from diff)
       | production selector hint
       | verdict column blank
       | computed-style columns blank
   the constructed table is passed to UI/UX as a new input.

Verify (UI/UX subagent runs)
   receives the expected table. Per row:
     - locate rendered DOM atoms in both browsers
     - read getComputedStyle() + getBoundingClientRect() per atom
     - fill in computed-style columns
     - set verdict: MATCH / DRIFT / MISSING-in-production
   drift inside a row's subtree → V1/V2/... findings
   adjacent-element drift (outside inventory) still reportable as a finding

Verify (step 6a, main agent)
   cross-checks two artifacts:
     - expected inventory (constructed at dispatch)
     - verified inventory (returned by UI/UX)
   rejects the UI/UX verdict if:
     - any expected row is absent in verified
     - any expected row has blank computed-style columns
     - sampled spot-check (2 diff elements + 2 prototype elements) absent
   on reject: re-dispatch UI/UX with the specific gaps named.
```

### 4.1 Invariants that fall out of this design

- **"Visual findings: None" without a filled inventory is structurally impossible in parity mode.** UI/UX cannot skip the inventory because it's supplied at dispatch; cannot selectively check rows because step 6a's spot-check verifies every expected row appears in verified; cannot omit DOM evaluation because every row's computed-style columns must be filled.
- **Provenance is unambiguous.** A row in the verified inventory that was not in the expected inventory means main agent's construction missed it — a planning gap, not a UI/UX bug. A Scoping-named prototype element with no plan mapping is a plan gap that surfaces at dispatch (the row can't be constructed without a mapping). Both are visible before the ticket reaches Verify.

## 5. File-by-file changes

### 5.1 `agents/scoping.md`

Add a new section to the output format, after `## Existing implementations of similar behavior` and before `## Project patterns to reuse`:

```markdown
## Prototype elements relevant to this feature
_(populate only when the project has a runnable React reference app under designs/ and the ticket touches UI; otherwise emit `_None._`)_
- `designs/path:start-end` | component name or HTML element | accessible name / role / text content | one-line purpose
```

Update mandate paragraph to note that the prototype-elements section is **required** for parity-mode UI tickets — an empty enumeration when the ticket touches UI in a parity-mode project is a Scoping failure.

Extend forbidden behaviors with: "Emitting `_None._` for the prototype-elements section in a parity-mode UI ticket. If Scoping cannot enumerate (composition is too dynamic), surface the limitation under `## Conflicts surfaced for main` instead — the workflow can then decide whether to degrade to consistency mode."

No new inputs (Scoping already receives scoped slices of `designs/`).

### 5.2 `SKILL.md`

**Plan phase (existing item 1).** Add guidance immediately after the `superpowers:writing-plans` invocation: for parity-mode tickets, each task that adds or modifies a visible element includes an `**Element mapping:**` block in the task body declaring:
- prototype counterpart (reference to a Scoping prototype-element row)
- planned production file:line for the new/changed JSX declaration

Tasks that don't add/modify visible elements (state management, route handlers, infrastructure) omit the block.

**Verify phase, step 5 (UI/UX dispatch).** Add a new pre-dispatch sub-step in parity mode:

> **In parity mode, construct the expected matched-element inventory before dispatch.** Combine:
> - Scoping's `## Prototype elements relevant to this feature` rows (prototype side)
> - Each plan task's `**Element mapping:**` block (the prototype↔production declaration)
> - Actual post-diff production file:lines, resolved by walking `git diff origin/<default>..HEAD` on the touched UI files
>
> The constructed table is passed to UI/UX as an additional input. In consistency mode, no inventory is constructed and dispatch proceeds as today.

If the construction fails (e.g., Scoping's prototype-elements section can't be parsed, or a plan task's element-mapping block can't be matched to a Scoping row), halt with `cannot dispatch UI/UX in parity mode — expected inventory could not be constructed`. No fallback to discovery-mode UI/UX in parity mode.

**Verify step 6a.** Rewrite to cross-check expected vs verified rather than validate UI/UX's self-built inventory:

> **6a. Validate the verified inventory against the expected inventory before accepting any verdict.**
>
> Applies in parity mode. In consistency mode, today's step-6a spot-check (against the live apps + diff) still applies.
>
> - Confirm the UI/UX report contains a verified inventory section matching the expected inventory passed at dispatch.
> - Spot-check the verified inventory:
>   - Every expected row must appear in the verified inventory.
>   - Every expected row must have non-blank computed-style and bounding-rect columns (the verification work was actually done).
>   - Sample 2 rows whose underlying file appears in the diff; confirm both verified.
>   - Sample 2 rows from the Scoping prototype enumeration; confirm both verified or marked MISSING.
> - If any check fails, reject the verdict and re-dispatch UI/UX with the specific gaps named.
> - Do not accept "I checked the major rows" or "the rest match by inspection" as substitutes for filled computed-style columns.

**Red flags.** Add three:

- "Main agent dispatches UI/UX in parity mode without supplying the expected inventory."
- "Scoping report's `## Prototype elements relevant to this feature` section is empty or `_None._` for a parity-mode UI ticket."
- "UI/UX returns a verified inventory with rows that have blank computed-style or bounding-rect columns."

### 5.3 `agents/ui-ux.md`

**Inputs section.** Add a new bullet (parity mode only):

> - In parity mode: the **expected matched-element inventory** table supplied by main agent at dispatch — one row per JSX declaration, with prototype + production file:lines populated and verdict + computed-style columns blank. Your job in parity mode is to fill in the blank columns, not to build the inventory from scratch.

**Mandate paragraph.** Clarify that in parity mode the role is verification of a supplied inventory; in consistency mode behavior is unchanged.

**Mode A (Parity) rewrite.** Per-row procedure:
1. For each row in the supplied inventory, locate the rendered DOM atoms inside that JSX declaration's output in both the prototype and the production browsers.
2. Per atom: read computed styles and bounding rects via DOM evaluation (using `scripts/extract-element-style.browser.js` injected through the host's DOM-evaluation capability per the Browser bootstrap fallback chain).
3. Fill in the row's computed-style and bounding-rect columns with the actual values.
4. Set the row's verdict: **MATCH** (every atom's properties agree), **DRIFT** (one or more atoms diverge), **MISSING** (the production JSX declaration doesn't render the expected atom).
5. Per drifting atom inside a DRIFT row, file a finding (V1, V2, ...) citing the specific atom and property.
6. Sibling-parent geometry: for rows that share a parent JSX declaration, compare the parent's `getBoundingClientRect()` for children; file findings for alignment / gap / sizing drift.

Adjacent-element drift outside the supplied inventory is still reportable as a finding (the existing `## Out-of-scope flags` section in the output format already accommodates this).

**Completeness rules** become cross-checks against the supplied inventory rather than standalone discovery rules. The "Selectivity is parity drift" forbidden behavior is rephrased for parity mode:

> Skipping rows in the supplied inventory or marking them MATCH without filling computed-style and bounding-rect columns. In parity mode, the inventory is a contract — every row gets verified.

**Mode B (Consistency) unchanged.** Today's exhaustive enumeration rules still apply because there's no supplied inventory in consistency mode.

**Stop conditions.** Update parity-mode stop condition: done when every supplied row has filled computed-style columns + verdict, every drifting row has a corresponding finding, and accessibility checks are complete.

For bug-fix re-runs in parity mode, the scope narrows to **affected rows ∩ affected states**: rows that had findings on the previous pass + rows whose production file:line changed due to the fix, restricted to the UI states where those rows render. The re-run is done when the delta verified inventory's rows have updated computed-style columns + verdict, drifting rows have corresponding findings, and the rows that previously had findings now report MATCH (or report a new finding that re-routes through bug-fix-loop).

Consistency-mode stop condition unchanged — today's state-based re-run scoping still applies because there's no inventory contract.

### 5.4 `personal-workflow.md`

The "Prototype parity dominates all other rules" subsection gets a corollary at the end: "Prototype enumeration in Scoping is mandatory in parity mode. The parity-dominance rule depends on having an authoritative list of what to maintain parity with; Scoping's `## Prototype elements relevant to this feature` section is that list. An empty section is a Scoping failure, not a clean report."

The parity-mode line under "Verification — Mode mapping" gets a one-sentence note: "Main agent constructs the expected matched-element inventory at Verify dispatch (per `SKILL.md`'s Verify step 5) and passes it to UI/UX as input."

### 5.5 `verification.md`

The `### Matched-element inventory (do this first)` section's opening paragraph is updated to note that in parity mode the inventory is supplied at dispatch (not built by UI/UX). The per-state procedure stays largely the same; step 3 of the per-state procedure changes from "build the inventory" to "verify the supplied inventory row-by-row".

### 5.6 Files that don't change

- `agents/qa.md` — orthogonal.
- `agents/architect.md`, `agents/reviewer.md`, `agents/security.md` — no element-level concern.
- `bug-fix-loop.md` — row-level re-run scoping lives in `agents/ui-ux.md`'s stop-conditions, not here.
- `self-improvement.md` — orthogonal.
- `job-workflow.md` — not parity mode.
- `react-parity.md` — philosophy doc.
- `scripts/extract-element-style.browser.js` — unchanged.
- `agents/openai.yaml` — Codex interface descriptor, unchanged.

## 6. Activation, bug-fix loop, and edge cases

### 6.1 Activation gate

The pre-built inventory + step-6a-cross-check applies **only when both conditions hold**:
1. Personal workflow, not job.
2. `designs/` exists AND is a runnable React reference app.

If either is false, the contract is inactive:
- Scoping's `## Prototype elements relevant to this feature` section emits `_None._`.
- Plan tasks omit `**Element mapping:**` blocks.
- Main agent dispatches UI/UX without supplying an inventory.
- UI/UX runs in consistency mode (or in parity mode without contract if `designs/` is present but non-runnable — same as today).

The activation gate lives in `SKILL.md`'s Verify phase as a one-paragraph branch.

### 6.2 Bug-fix loop interaction

When UI/UX returns FINDINGS in parity mode:
- The expected inventory **does not change**. Same Scoping, same plan.
- Main agent **re-resolves production file:lines** for rows whose underlying production file was touched by the fix.
- UI/UX **re-runs scoped to affected rows**: rows that had findings + rows whose production file:line changed due to the fix. UI/UX returns a delta verified inventory.
- Main agent **merges the delta into the existing verified inventory** and re-runs step 6a on the merged result.
- The 3-iteration cap from `bug-fix-loop.md` still applies.

`bug-fix-loop.md` itself doesn't change. The row-level scoping refinement lives in `agents/ui-ux.md`'s stop-conditions section.

### 6.3 Edge cases

- **Scoping can't enumerate cleanly** (render props, dynamic children, third-party components that obscure rendered DOM from static reading): Scoping puts the limitation in `## Conflicts surfaced for main`. Main agent surfaces to the user before Brainstorm. The user picks: (a) reduce the slice to a portion of the prototype where enumeration is clean and proceed with a partial inventory (main agent's expected inventory is then known-incomplete); (b) degrade to consistency mode for this ticket. No silent fallback.

- **Plan task with no prototype counterpart** (state-management work, route handlers, backend stubs alongside the visual feature): the task body omits the `**Element mapping:**` block. Main agent's dispatch-time construction skips tasks without mappings. Not every task implements a visible element.

- **Implementation diverges from the plan's declared file:line** (implementer lands the element at a different line or refactors it to a different file): main agent resolves production-side locators from the **actual diff**, not the plan's declared values. The plan's declaration is the spec; the post-diff state is truth.

- **Prototype-only elements** (deliberately not implemented in this ticket): Scoping enumerates them. Plan declares them deliberately omitted. Main agent's expected inventory includes the row with production side blank. UI/UX verifies absence and reports verdict = MISSING. Step 6a accepts MISSING for rows the plan marked deliberately omitted; rejects MISSING for rows the plan said would be implemented.

- **Production-only elements** (added by the implementation with no prototype counterpart, e.g., a tagline the production app adds): plan task declares `prototype counterpart: (none — production-only)`. Main agent's expected inventory has the row with prototype side blank. UI/UX verifies presence and reports MATCH against an empty prototype expectation (presence-only check).

- **Inventory construction fails at dispatch** (Scoping output drifted from format, plan task's element-mapping block can't be matched): hard halt with `cannot dispatch UI/UX in parity mode — expected inventory could not be constructed`. The specific parsing or matching error is named. No fallback to discovery-mode UI/UX in parity mode.

### 6.4 What we explicitly don't add

- No persistent `inventory.md` file. The expected inventory lives in the dispatch payload; the verified inventory lives in the UI/UX report.
- No automatic backfill onto in-flight tickets. The contract activates on tickets that go through Scoping/Plan/Implement after the change ships.
- No new subagent. Main agent does the construction at dispatch.
- No fallback from parity-with-contract to discovery-mode UI/UX. If the contract can't be constructed, the workflow halts and surfaces the blocker.

## 7. Deferred to implementation plan

The following implementation details are deferred to the plan:

- **Whether main agent's dispatch-time construction is backed by a script.** Per AGENTS.md rule 3 (non-trivial logic in scripts), if the markdown/diff parsing turns out non-trivial, a helper script under `skills/ticket-start/scripts/` is appropriate. The plan will evaluate this after seeing the actual mechanics. The spec says "main agent constructs the expected inventory at dispatch"; the how is plan-level.
- **Exact format of the `**Element mapping:**` block in plan tasks.** Probably a small structured block with two fields (prototype counterpart, planned production file:line); the plan will pin down the exact syntax.
- **Exact format of the dispatch-payload table.** Same column set as today's matched-element inventory in `agents/ui-ux.md`'s output format, but the plan will specify how main agent serialises it into the dispatch input string.

## 8. Migration and scope

This is additive in parity mode only. No behavioral change in job workflow or in personal-workflow tickets without a runnable React reference app. The rollback is reverting the PR — every existing protection from PR #6 stays intact regardless.

In-flight tickets that were started before this PR ships finish on the existing protocol (no Scoping prototype-elements section to consume). New tickets start under the contract automatically once their Setup runs.

## 9. Why this is meaningful

This is the second hardening pass on the visual-parity protocol. The first (PR #6) made the matched-element inventory mandatory + exhaustive and added a main-agent spot-check. The failure it didn't structurally prevent: UI/UX still owned discovery, so a subagent that decided to "check the major elements only" could still produce an inventory that looked complete but wasn't.

This pass moves discovery upstream — into Scoping (prototype side) and the plan (production-side mapping) — where context is freshest and the work is naturally bounded by what the ticket touches. UI/UX's role narrows to verification. Step 6a gains a second inventory to cross-reference, which closes the loophole where "the inventory looks complete because I built it to look complete".

The protocol now has three independent witnesses to inventory completeness: Scoping's enumeration, the plan's mapping, and UI/UX's verification. Each can be inspected against the others. The orchestrator main agent is the one that compares them.
