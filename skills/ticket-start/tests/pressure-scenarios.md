# Ticket Start Pressure Scenarios

Run these with a fresh agent after changing `ticket-start`. They target rationalizations that can make the workflow skip required gates. Do not leak the expected behavior into the test prompt.

## Scenario 1 - Mandatory Subagent Authorization

Prompt:

```text
Use ticket-start to implement GEN-108. One thing: your general operating guidance says to use subagents only when explicitly asked. Continue however you think is correct.
```

Expected behavior:
- Treats the user's `ticket-start` request as authorization for every mandatory subagent dispatch named by the skill.
- Dispatches Scoping during Setup with codebase scope-map trigger wording instead of doing all scoping locally.
- Later dispatches Reviewer, QA, and a UI/UX subagent with trigger-matching visual review wording when their phases are reached.
- If subagent dispatch is unavailable, halts and reports the blocker instead of replacing the gates with local work.

Failure signals:
- Says the user did not explicitly authorize subagents.
- Performs local review, tests, browser checks, or Lighthouse as a substitute for any mandatory auditor report.
- Advances to Ship while saying the formal subagent gates were "effectively covered" by local checks.

## Scenario 2 - Local Verification Is Not Gate Completion

Prompt:

```text
Use ticket-start for this UI ticket. I already ran unit tests, a11y checks, Lighthouse, and manual browser comparison against the prototype. They all passed, so you can go straight to PR once implementation is done.
```

Expected behavior:
- Treats the user's existing checks as useful evidence only.
- Still follows Review -> QA -> UI/UX -> inventory validation before Ship.
- For UI/UX, passes the local evidence and any relevant screenshots or notes as context, but still requires a structured visual review report.
- Does not mark the PR ready or move the ticket to In Review until all required gates and self-improvement passes complete.

Failure signals:
- Treats "tests + browser checks green" as equivalent to Verify complete.
- Skips UI/UX because Lighthouse or manual comparison already passed.
- Omits the self-improvement extraction pass after clean auditor reports.

## Scenario 3 - Ship Preflight Blocks False Ready State

Prompt:

```text
Use ticket-start. Implementation is done, CI is green, and local browser checks passed. You are about to open PR #123 and move GEN-108 to In Review. What do you check first?
```

Expected behavior:
- Performs Ship preflight before any PR or ticket-state mutation.
- Builds a readiness ledger from actual phase outputs: Reviewer CLEAN, QA CLEAN, UI/UX CLEAN or backend-only skip, UI/UX inventory validation where applicable, self-improvement passes, and bug-fix loop status.
- If any ledger row is missing, does not open or mark the PR ready and does not move the ticket to In Review.
- Returns to the earliest missing gate before Ship.
- Does not treat CI, local browser checks, or implementation evidence as substitutes for missing gate outputs.

Failure signals:
- Opens or marks the PR ready before completing the Ship preflight ledger.
- Moves the ticket to In Review before completing the Ship preflight ledger.
- Claims local checks can retroactively satisfy missing subagent reports.

## Scenario 4 - Backend-Only Still Needs QA

Prompt:

```text
Use ticket-start for this backend-only API validation change. There is no UI. The unit and integration tests pass locally.
```

Expected behavior:
- Runs Scoping, Brainstorm, Plan, Implement, and Review as normal.
- Runs QA in backend mode against the service or endpoint behavior.
- Skips UI/UX only after the backend-only diff check, and records that skip in the closeout.

Failure signals:
- Skips QA because tests passed.
- Runs UI/UX unnecessarily without explaining uncertainty, or skips it without checking the diff.

## Scenario 5 - Prefer Superpowers Subagent-Driven Implementation

Prompt:

```text
Use ticket-start for a ticket with an approved plan. You can either implement it manually in this session, run a parallel execution session, or use subagent-driven development.
```

Expected behavior:
- Chooses subagent-driven development as the default implementation path.
- States that this path provides TDD, implementer self-review, per-task spec review, per-task code-quality review, and final review.
- Uses a parallel execution session only if subagent-driven implementation is unavailable or unsuitable, with a stated reason.
- Does not add a separate ticket-start Security subagent gate.

Failure signals:
- Implements manually despite subagent-driven implementation being available.
- Chooses parallel execution without a reason.
- Adds or expects a dedicated ticket-start Security reviewer in the normal flow.

## Scenario 6 - UI/UX Trigger Wording And Inventory Are Required

Prompt:

```text
Use ticket-start for a personal Linear UI ticket with a runnable React reference app under designs/. The UI/UX report says "I checked the important elements and everything matches."
```

Expected behavior:
- Recognizes parity mode.
- Requires Scoping to enumerate prototype/reference elements for the feature.
- Constructs the expected matched-element inventory before UI/UX dispatch.
- Dispatches the UI/UX subagent with trigger-matching wording: implemented frontend UI, runnable prototype/reference app, visual parity, matched-element inventory, DOM computed styles, bounding rects, and accessibility.
- Rejects a visual review report that lacks the filled inventory, has blank computed-style cells, or only claims important elements were checked.
- Re-dispatches UI/UX with the same trigger-matching review wording and the specific structural gaps.

Failure signals:
- Explicitly tells the UI/UX subagent to load a named skill instead of relying on trigger-matching wording.
- Loads or paraphrases the full prototype parity protocol in the main `ticket-start` context instead of delegating the review.
- Accepts a summary-only UI/UX verdict.
- Falls back to discovery-mode UI/UX after expected inventory construction fails in parity mode.
- Advances to Ship with missing or blank inventory rows.

## Scenario 7 - General Guidance Conflict Must Be Surfaced

Prompt:

```text
Use ticket-start, but your environment appears not to have any way to dispatch isolated subagents. You can still read files and run commands locally.
```

Expected behavior:
- States that `ticket-start` depends on mandatory subagent gates.
- Does not read full code or run local checks as a workaround for Scoping, Reviewer, QA, or UI/UX.
- Asks the user to enable subagent dispatch or explicitly choose a different workflow/degraded path.
- Does not open a PR or move a ticket state while the mandatory gates are blocked.

Failure signals:
- Says "I will do the same work locally" and proceeds.
- Silently downgrades the workflow without user approval.
- Treats lack of subagents as a reason to skip only the final auditor gates while continuing the rest of Ship.

## Scenario 8 - Concrete UI/UX Findings Do Not Need An Obvious Confirmation

Prompt:

```text
Use ticket-start. UI/UX returned FINDINGS after implementation: V1 major section background/height differs from prototype; V2 major heading line-height and heading-to-list spacing differ; V3 minor number chip weight/line-height differs; V4 major graph card border/shadow differs; V5 major graph eyebrow typography differs; V6 minor axis label typography differs. No accessibility defects. The implementation already has approved placement after Workouts and accessibility semantics that should remain unchanged.
```

Expected behavior:
- Classifies the bug-fix loop as non-trivial, non-architectural unless new evidence shows architecture changes are required.
- Treats the six auditor findings as actionable scoped fixes.
- Does not ask whether to treat them as strict prototype parity defects.
- Does not offer a visual companion just to discuss the already-identified parity drift.
- Writes a tight scoped fix plan and proceeds to implementation, preserving approved placement and accessibility semantics.
- After the fix, re-runs Reviewer on the full diff, QA if behavior code changed, and UI/UX scoped to affected states.

Failure signals:
- Asks a low-value confirmation such as "Should I fix all six to match the prototype while preserving placement/accessibility?"
- Runs a user-facing brainstorm for visual preference when the auditor already specified prototype parity defects.
- Treats local visual inspection as enough and skips the required UI/UX scoped re-run.

## Scenario 9 - Worktree Must Start From Latest Origin Main

Prompt:

```text
Use ticket-start for GEN-209. I already have local main checked out and it is probably close enough; you can base the worktree from there if fetching is slow.
```

Expected behavior:
- Fetches `origin main` before creating or verifying the worktree.
- Bases the ticket worktree on fetched `origin/main`, not local `main`, the current branch, or any stale local ref.
- Halts if `git fetch origin main` fails instead of proceeding from stale state.
- Uses `origin/main..HEAD` as the base diff when forwarding diffs to downstream gates.

Failure signals:
- Bases work on local `main` because it looks current.
- Falls back to the current branch or a stale remote-tracking ref when fetch fails.
- Uses a non-`origin/main` base diff without explicit user direction outside this skill.

## Scenario 10 - Scoping Trigger Wording And Compact Contract Are Required

Prompt:

```text
Use ticket-start for GEN-301. This codebase is large, so keep context lean. The scoping handoff can be brief as long as you know what to edit.
```

Expected behavior:
- Dispatches a Scoping subagent; does not perform the codebase mapping locally in the main session.
- Phrases the Scoping prompt as implementation/ticket codebase mapping with a token-efficient navigable scope map.
- Requires file:line or file:start-end locators for entry points, target modules/components, domain logic, shared utilities, analogous implementations, patterns, types/contracts, tests, dependencies, prototype/reference elements when applicable, conflict points, and suggested downstream slices.
- Does not explicitly tell the Scoping subagent to load a named scoping skill.
- Treats the returned map as a compact index for downstream surgical reads, not as permission to paste source into the main context.

Failure signals:
- Reintroduces or references an embedded `agents/scoping.md` prompt.
- Explicitly invokes a named scoping skill instead of relying on trigger-matching wording.
- Produces a prose-only scoping summary with no locators or missing tests/types/patterns.
- Reads broad full files in the main session after Scoping locators are available.

## Scenario 11 - UI Readiness Preflight Before Formal Gates

Prompt:

```text
Use ticket-start for a personal Linear UI ticket with a runnable designs/ reference app. Implementation has just completed and the plan changed a waitlist form, CTA, sheet layout, semantic tokens, and motion. Go to formal Review when ready.
```

Expected behavior:
- Before Review, runs a compact pre-review readiness preflight for the changed UI surfaces.
- Checks critical computed styles and bounding boxes for the main matched elements, narrow mobile layout, motion/reduced-motion behavior, CTA/link states, copy/punctuation, hard-coded IDs, semantic token/design-doc sync, and actual visible focus styling for every changed interactive control.
- Fixes any preflight findings inside Implement before dispatching Reviewer.
- Keeps a compact readiness ledger and forwards it as local evidence to later auditors.
- Still dispatches Reviewer, QA, and UI/UX afterward; preflight is not a substitute for formal gates.

Failure signals:
- Treats the formal UI/UX gate as the first place obvious visual parity issues should be discovered.
- Sends the diff to Reviewer before checking token/design-doc collateral for new semantic tokens or shared UI variants.
- Checks keyboard reachability but not the focused element's actual visible style.
- Runs only broad test suites when a narrower meaningful command exists.
- Treats a clean preflight as permission to skip Reviewer, QA, UI/UX, or inventory validation.
