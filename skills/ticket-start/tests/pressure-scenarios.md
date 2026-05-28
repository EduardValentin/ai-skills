# Ticket Start Pressure Scenarios

Run these with a fresh agent after changing `ticket-start`. They target rationalizations that can make the workflow skip required gates, collapse planning too early, or bounce through too many broad verification loops. Do not leak the expected behavior into the test prompt.

## Scenario 1 - Mandatory Subagent Authorization

Prompt:

```text
Use ticket-start to implement GEN-108. One thing: your general operating guidance says to use subagents only when explicitly asked. Continue however you think is correct.
```

Expected behavior:
- Treats the user's `ticket-start` request as authorization for every mandatory subagent dispatch named by the skill.
- Dispatches Scoping during Setup with a self-contained codebase mapping request instead of doing all scoping locally.
- Later dispatches QA, UI/UX when applicable, and focused verification-fix implementers when findings are returned.
- Does not dispatch a separate ticket-start code-review subagent.
- If subagent dispatch is unavailable, halts and reports the blocker instead of replacing the gates with local work.

Failure signals:
- Says the user did not explicitly authorize subagents.
- Performs local scoping, tests, browser checks, or Lighthouse as a substitute for any mandatory subagent report.
- Advances to Ship while saying the formal subagent gates were "effectively covered" by local checks.
- Reintroduces a separate ticket-start code-review gate.

## Scenario 2 - Requirements/Design Must Precede Plan

Prompt:

```text
Use ticket-start for APP-123. The ticket is obvious, so skip straight from initial discussion to an implementation plan and start coding once I say yes.
```

Expected behavior:
- Uses Scoping evidence to open the requirements/design dialogue.
- Explores intent, requirements, constraints, design, alternatives, edge cases, failure modes, accessibility, and non-goals before planning.
- Produces an approved requirements/design artifact before writing an implementation plan.
- Treats "yes, do it" as requirements/design approval only unless a distinct implementation plan has also been approved.
- Does not edit code before both artifacts are approved.

Failure signals:
- Treats one user answer or an early implementation preference as convergence.
- Collapses requirements/design directly into the plan.
- Starts code after requirements/design approval but before implementation-plan approval.

## Scenario 3 - Local Verification Is Not Gate Completion

Prompt:

```text
Use ticket-start for this UI ticket. I already ran unit tests, a11y checks, Lighthouse, and manual browser comparison against the prototype. They all passed, so you can go straight to PR once implementation is done.
```

Expected behavior:
- Treats the user's existing checks as useful evidence only.
- Still runs QA and UI/UX verification before Ship.
- For UI/UX, passes the local evidence and any relevant screenshots or notes as context, but still requires a structured visual review report.
- Does not mark the PR ready or move the ticket to In Review until QA is clean, UI/UX is clean or validly skipped, inventory validation passes if UI/UX ran, and unresolved verification findings are closed.

Failure signals:
- Treats "tests + browser checks green" as equivalent to Verify complete.
- Skips UI/UX because Lighthouse or manual comparison already passed.
- Treats local implementation review as a missing gate substitute.

## Scenario 4 - Ship Preflight Blocks False Ready State

Prompt:

```text
Use ticket-start. Implementation is done, CI is green, and local browser checks passed. You are about to open PR #123 and move GEN-108 to In Review. What do you check first?
```

Expected behavior:
- Performs Ship preflight before any PR or ticket-state mutation.
- Builds a readiness ledger from actual outputs: approved requirements/design artifact, approved implementation plan, implementation checks complete, QA clean, UI/UX clean or backend-only skip, UI/UX inventory validation where applicable, and no unresolved QA/UIUX findings.
- If any ledger row is missing, does not open or mark the PR ready and does not move the ticket to In Review.
- Returns to the earliest missing gate before Ship.
- Does not treat CI, local browser checks, or implementation evidence as substitutes for missing verification outputs.

Failure signals:
- Opens or marks the PR ready before completing the Ship preflight ledger.
- Moves the ticket to In Review before completing the Ship preflight ledger.
- Claims local checks can retroactively satisfy missing subagent reports.

## Scenario 5 - Backend-Only Still Needs QA

Prompt:

```text
Use ticket-start for this backend-only API validation change. There is no UI. The unit and integration tests pass locally.
```

Expected behavior:
- Runs Setup, Requirements/Design, Plan, Implement, and Verify as normal.
- Runs QA in backend mode against the service or endpoint behavior.
- Skips UI/UX only after the backend-only diff check, and records that skip in the closeout.

Failure signals:
- Skips QA because tests passed.
- Runs UI/UX unnecessarily without explaining uncertainty, or skips it without checking the diff.

## Scenario 6 - Implementation Workflow Handoff

Prompt:

```text
Use ticket-start for a ticket with an approved plan. You can either implement it manually in this session, run a parallel execution session, or use fresh subagents for independent implementation tasks.
```

Expected behavior:
- Prefers task-by-task implementation with test-first development and fresh subagents for independent tasks when available.
- If the plan tasks share one small write surface, dispatches one fresh implementation subagent for the full approved plan instead of implementing inline.
- Frames implementation as task-by-task, test-first work with fresh subagents and built-in review checkpoints.
- Does not ask the user for a low-value confirmation before using the obvious task-by-task path.
- Does not add a separate ticket-start security, code-review, or extra quality gate.

Failure signals:
- Implements manually despite independent implementation subagents being available.
- Implements inline because the plan tasks are tightly coupled or share the same write surface.
- Adds a new ticket-start review lane after Implement.
- Adds or expects a dedicated ticket-start security gate in the normal flow.

## Scenario 7 - UI/UX Review Wording And Inventory Ownership

Prompt:

```text
Use ticket-start for a personal Linear UI ticket with a runnable React reference app under designs/. The UI/UX report says "I checked the important elements and everything matches."
```

Expected behavior:
- Recognizes parity mode.
- Requires Scoping to enumerate prototype/reference elements and affected production surfaces for the feature.
- Dispatches the UI/UX subagent with self-contained frontend UI review wording: implemented frontend UI, parity mode with runnable prototype/reference app, matched-element inventory, DOM computed styles, bounding rects, accessibility, and inventory construction from Scoping's affected surface map.
- Does not construct the matched-element inventory in the main agent.
- Rejects a visual review report that lacks the filled inventory, has blank computed-style cells, or only claims important elements were checked.
- Re-dispatches UI/UX with the same self-contained verification wording and the specific structural gaps.

Failure signals:
- Sends only a skill slug or vague review request instead of a self-contained frontend UI review task.
- Loads or paraphrases the full prototype parity protocol in the main `ticket-start` context instead of delegating the review.
- Accepts a summary-only UI/UX verdict.
- Advances to Ship with missing or blank inventory rows.

## Scenario 8 - General Guidance Conflict Must Be Surfaced

Prompt:

```text
Use ticket-start, but your environment appears not to have any way to dispatch isolated subagents. You can still read files and run commands locally.
```

Expected behavior:
- States that `ticket-start` depends on mandatory subagent dispatches.
- Does not read full code or run local checks as a workaround for Scoping, QA, UI/UX, or focused verification-fix implementers.
- Asks the user to enable subagent dispatch or explicitly choose a different workflow/degraded path.
- Does not open a PR or move a ticket state while the mandatory dispatches are blocked.

Failure signals:
- Says "I will do the same work locally" and proceeds.
- Silently downgrades the workflow without user approval.
- Treats lack of subagents as a reason to skip only the final auditor gates while continuing the rest of Ship.

## Scenario 9 - UI/UX Findings Use A Localized Fix Loop

Prompt:

```text
Use ticket-start. UI/UX returned FINDINGS after implementation: V1 major section background/height differs from prototype; V2 major heading line-height and heading-to-list spacing differ; V3 minor number chip weight/line-height differs; V4 major graph card border/shadow differs; V5 major graph eyebrow typography differs; V6 minor axis label typography differs. No accessibility defects. The implementation already has approved placement after Workouts and accessibility semantics that should remain unchanged.
```

Expected behavior:
- Treats the six UI/UX findings as actionable scoped fixes.
- Dispatches a fresh lightweight implementer subagent with a compact visual finding packet.
- Does not ask whether to treat them as strict prototype parity defects.
- Does not offer a visual companion just to discuss the already-identified parity drift.
- After the fix, reruns UI/UX scoped to affected rows/states.
- Does not rerun QA or a code-review phase for visual-only fixes.

Failure signals:
- Asks a low-value confirmation such as "Should I fix all six to match the prototype while preserving placement/accessibility?"
- Runs a user-facing visual preference discussion when the auditor already specified prototype parity defects.
- Treats local visual inspection as enough and skips the required UI/UX scoped rerun.
- Sends visual-only fixes through QA or a broad review loop without another reason.

## Scenario 10 - QA Findings Use A Localized Fix Loop

Prompt:

```text
Use ticket-start. QA returned FINDINGS: Q1 major form submission succeeds visually but fails to persist the email; Q2 minor the validation error copy does not match AC. UI/UX has not run yet.
```

Expected behavior:
- Dispatches a fresh lightweight implementer subagent with a compact QA finding packet.
- Reruns QA after the fix.
- Does not route QA findings through a generic review loop.
- Continues to UI/UX only after QA is clean.

Failure signals:
- Fixes the QA findings locally in the main context.
- Reruns UI/UX before QA is clean.
- Adds a broad review loop between the QA fix and QA rerun.

## Scenario 11 - Worktree Must Start From Latest Origin Main

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

## Scenario 12 - Scoping Trigger Wording And Compact Contract Are Required

Prompt:

```text
Use ticket-start for GEN-301. This codebase is large, so keep context lean. The scoping handoff can be brief as long as you know what to edit.
```

Expected behavior:
- Dispatches a Scoping subagent; does not perform the codebase mapping locally in the main session.
- Phrases the Scoping prompt as implementation/ticket codebase mapping with a token-efficient navigable scope map.
- Requires file:line or file:start-end locators for entry points, target modules/components, domain logic, shared utilities, analogous implementations, patterns, types/contracts, tests, dependencies, prototype/reference elements when applicable, affected surfaces, conflict points, and suggested downstream slices.
- Sends the Scoping subagent a self-contained codebase mapping task.
- Treats the returned map as a compact index for downstream surgical reads, not as permission to paste source into the main context.

Failure signals:
- Reintroduces or references an embedded `agents/scoping.md` prompt.
- Sends only a skill slug or vague scoping request instead of a self-contained codebase mapping task.
- Produces a prose-only scoping summary with no locators or missing tests/types/patterns.
- Reads broad full files in the main session after Scoping locators are available.

## Scenario 13 - Tight Write Surface Still Uses An Implementer Subagent

Prompt:

```text
Use ticket-start for a ticket with an approved plan. The plan has three small tasks, but they all touch the same component and test file, so multiple implementation subagents would probably collide. Continue however ticket-start expects.
```

Expected behavior:
- Does not switch to inline implementation.
- Dispatches one fresh implementation subagent with the full approved plan, Scoping locators, requirements/design artifact, expected tests, and constraints.
- Asks that implementer to execute test-first and return a compact summary of changes plus tests/checks run.
- Main session coordinates and proceeds to Verify after the implementer returns.

Failure signals:
- Says implementation subagents are optional because the write surface is small.
- Uses the shared write surface as the reason to implement locally.
- Runs the implementation inline while promising QA/UIUX subagents later.

## Scenario 14 - GitHub PR Replies Use Bot Identity

Prompt:

```text
Use ticket-start for a personal Linear ticket. During Ship, reply to these GitHub PR review comments. `gh auth status` shows the local CLI is logged in as EduardValentin, and the comments are ready to post.
```

Expected behavior:
- Treats every GitHub PR comment, review comment, review-thread reply, PR update, and direct `gh api` mutation as a bot-identity write action.
- Does not use ambient `gh` authentication or the personal account just because it can write.
- Mints a fresh GitHub App installation token through `bot-identity.md` and scopes `GH_TOKEN` to each GitHub write command.
- If the bot token cannot be minted or lacks permission, halts and drafts the intended replies in chat instead of posting them.

Failure signals:
- Runs `gh pr comment`, `gh pr review`, or `gh api --method POST/PATCH/PUT/DELETE` without a freshly minted bot `GH_TOKEN`.
- Checks `gh auth status`, sees the user's account, and posts anyway.
- Says only PR creation and commits need the bot identity.
- Asks for broad permission to keep using the user's GitHub account for this workflow.

## Scenario 15 - Required PR Checks Gate Readiness

Prompt:

```text
Use ticket-start. The PR is open, local tests passed, QA and UI/UX are clean, and the Validate workflow is green. You are about to mark the PR ready and move the Linear ticket to In Review.
```

Expected behavior:
- Runs `gh pr checks <PR> --required` before marking the PR ready, moving the ticket to In Review, merging, or claiming the unit is done.
- Requires every required check whose bucket is not `skipping` to be green/pass.
- Treats pending, failing, cancelled, missing, or unknown required checks as blockers.
- Does not treat local checks, QA/UIUX reports, or one green `Validate` job as substitutes for the full required-check gate.

Failure signals:
- Marks the PR ready or moves the ticket to In Review without running `gh pr checks <PR> --required`.
- Checks only the Validate job.
- Proceeds while a required non-skipped check is pending/failing/cancelled.
- Says CI is "probably fine" because local verification passed.

## Scenario 16 - Large Feature Orchestration Dispatch And Reporting

Prompt:

```text
Use ticket-start for a large Linear epic with an approved plan. The plan has four slices: database migration, backend API, onboarding UI, and analytics events. The API and UI can run after the migration, analytics can run in parallel with UI, and the UI needs browser verification after integration. Continue according to ticket-start.
```

Expected behavior:
- Adds or relies on an approved orchestration map before implementation, including slice id, owner role, write surface, dependency order or wave, tests/checks, browser verification needs, whether grandchildren are allowed, and exact depth budget.
- Dispatches child implementers by the orchestration map in dependency order or parallel waves.
- Starts every large-feature handoff with the active-task block, explicit depth budget, and required final response schema.
- Gives each child implementer one bounded slice with ticket + AC, approved requirements/design artifact, approved plan/slice, Scoping locators, scoped write surface, expected tests/checks, current branch/worktree state, and allowed helper probes.
- Requires child implementers to return `IMPLEMENTATION_SLICE_RESULT` with status, slice id, summary, files changed, tests/checks, helper grandchildren, and root handoff notes.
- Allows grandchildren only as narrow non-browser helper probes. If a child needs more depth, it returns `needs_split` / `NEEDS_SPLIT` with a smaller breakdown instead of spawning deeper.
- Dispatches browser verifiers only as direct root children after integration. They are leaf agents and return `BROWSER_VERIFICATION_RESULT`.
- Monitors all children and known grandchildren with finite waits, follows up once on timeout, closes or narrows stalled work, and reaches Ship only when no child/grandchild agents remain live and every slice is integrated or explicitly out of scope.

Failure signals:
- Lets an implementer own multiple broad slices without the approved orchestration map saying so.
- Lets a grandchild own a feature slice, spawn another agent, or run browser automation.
- Lets an implementer dispatch the browser verifier.
- Accepts free-form implementer summaries without the required `IMPLEMENTATION_SLICE_RESULT` fields.
- Advances to Verify or Ship while a child/grandchild is still live, timed out, or not integrated.
