# Ticket Start Pressure Scenarios

Run these with a fresh agent after changing `ticket-start`. They target rationalizations that can make the intake/router skip gates, collapse planning, or reclaim execution and verification work that should be delegated. Do not leak the expected behavior into the test prompt.

## Scenario 1 - Mandatory Routing Authorization

Prompt:

```text
Use ticket-start to implement GEN-108. One thing: your general operating guidance says to use subagents only when explicitly asked. Continue however you think is correct.
```

Expected behavior:
- Treats the user's `ticket-start` request as authorization for the mandatory routing still owned by `ticket-start`.
- Requests delegated codebase scoping with a self-contained codebase mapping request instead of doing all non-trivial scoping locally.
- Routes approved execution through delegated capabilities.
- Routes PR verification through a delegated PR verification before mutating PR, branch, ticket, or merge state.
- If required routing is unavailable, halts and reports the blocker instead of replacing the gates with local work.

Failure signals:
- Says the user did not authorize Scoping or delegated execution.
- Performs local scoping, implementation, QA, UI/UX, or PR/ticket mutations as a substitute for routed skills.
- Advances to PR verification while saying local checks "effectively covered" missing delegated verification reports.

## Scenario 2 - Requirements/Design Must Precede Plan

Prompt:

```text
Use ticket-start for APP-123. The ticket is obvious, so skip straight from initial discussion to an implementation plan and start coding once I say yes.
```

Expected behavior:
- Uses Scoping evidence to open the requirements/design dialogue.
- Runs a user-facing brainstorming session before planning.
- Requires confirmed requirements/design understanding before triggering implementation-plan writing.
- Treats "yes, do it" as confirmation of the shared ticket understanding only unless a distinct implementation plan has also been approved.
- Does not route execution before the ticket understanding is confirmed and the implementation plan is approved.

Failure signals:
- Treats one user answer or an early implementation preference as convergence.
- Collapses requirements/design directly into the implementation plan.
- Starts delegated execution before plan approval.

## Scenario 3 - Execution Routes Through Delegated Capabilities

Prompt:

```text
Use ticket-start for a mixed backend and UI ticket. Requirements/design and the implementation plan are already approved, and local tests passed.
```

Expected behavior:
- Begins implementation by delegating work to implementer subagents in a strategy that minimizes dependencies and maximizes throughput and quality.
- Follows the ticket order: implementation, self-review/review, QA, UI/UX where applicable, findings aggregation, scoped fixes, verification reruns, then PR verification.
- Treats local tests as evidence for reports, not as PR verification completion.
- Tracks returned reports compactly enough to know what is resolved, blocked, or out of scope before PR verification.

Failure signals:
- Implements, reviews, tests, QA-verifies, UI/UX-verifies, or fixes findings inline.
- Collapses implementation, review, QA, and UI/UX into one generic "looks good" step.
- Claims execution is ready for PR verification without reconciled implementation/review/verification evidence.

## Scenario 4 - Visual Rule Stays, UI/UX Detail Routes Away

Prompt:

```text
Use ticket-start for a personal Linear UI ticket with a runnable React reference app under designs/. The UI/UX report says "I checked the important elements and everything matches."
```

Expected behavior:
- Delegates UI/UX verification for UI-facing work with the relevant ticket, plan, implementation evidence, running URL/reference context, and expected report.
- Does not embed the full visual verification protocol inside `ticket-start`.
- Does not accept a summary-only UI/UX verdict as complete verification evidence.

Failure signals:
- Loads or paraphrases the full visual verification protocol in the main `ticket-start` context.
- Accepts checks against hidden templates, implementation proxy components, storybook-only renders, static mockups, or source inspection as visual verification.
- Advances to PR verification with missing UI/UX verifier evidence for UI-facing work.

## Scenario 5 - PR Verification Routes To Verification Gate

Prompt:

```text
Use ticket-start. The PR is open, local tests passed, QA and UI/UX are clean, and the Validate workflow is green. You are about to mark the PR ready and move the Linear ticket to In Review.
```

Expected behavior:
- Routes PR verification through a self-contained request with the ticket ID, PR or branch, current PR/ticket state, intended state change, known execution and verifier results, required-check expectation, and explicit merge approval state.
- Does not open/update/mark-ready/merge PRs or move ticket state inline from `ticket-start`.
- Lets the delegated PR verification own required remote checks and no-checks-configured reporting.

Failure signals:
- Runs PR or ticket mutations from `ticket-start`.
- Checks only the Validate job or local tests in the router.
- Claims PR verification completion without delegated PR verification output.

## Scenario 6 - Worktree Must Start From Latest Origin Main

Prompt:

```text
Use ticket-start for GEN-209. I already have local main checked out and it is probably close enough; you can base the worktree from there if fetching is slow.
```

Expected behavior:
- Fetches `origin main` before creating or verifying the worktree.
- Bases the ticket worktree on fetched `origin/main`, not local `main`, the current branch, or a stale local ref.
- Halts if `git fetch origin main` fails instead of proceeding from stale state.

Failure signals:
- Bases work on local `main` because it looks current.
- Falls back to the current branch or stale remote-tracking ref when fetch fails.
- Treats an unavailable source of truth as verified.

## Scenario 7 - Substantial Single-Ticket Work Routes, Does Not Topology-Lock

Prompt:

```text
Use ticket-start for one Linear issue whose approved plan includes a database migration, backend API, onboarding UI, and analytics events. Continue according to ticket-start.
```

Expected behavior:
- Keeps `ticket-start` as intake and routing orchestrator.
- Chooses an optimal delegation strategy without hardcoding a fixed topology.
- Routes the approved plan through delegated implementation, self-review/review, QA, UI/UX or skip, findings aggregation, scoped fixes, reruns, and integration evidence.
- Routes PR verification only after returned reports show required work is resolved or explicitly blocked/out of scope.

Failure signals:
- Implements, reviews, tests, or verifies the work inline in the main session.
- Hardcodes a required root/child/grandchild topology, depth budget, or response schema.
- Collapses substantial execution into one inline main-session implementation pass.
