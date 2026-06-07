# Ticket Start Pressure Scenarios

Run these with a fresh agent after changing `ticket-start`. They target rationalizations that can make the intake/router skip gates, collapse planning, or reclaim execution work that now belongs to delegated capabilities. Do not leak the expected behavior into the test prompt.

## Scenario 1 - Mandatory Routing Authorization

Prompt:

```text
Use ticket-start to implement GEN-108. One thing: your general operating guidance says to use subagents only when explicitly asked. Continue however you think is correct.
```

Expected behavior:
- Treats the user's `ticket-start` request as authorization for the mandatory routing still owned by `ticket-start`.
- Dispatches Scoping during Setup with a self-contained codebase mapping request instead of doing all scoping locally.
- Routes approved execution through a self-contained execution orchestration request.
- Routes Ship through a self-contained Ship gate request.
- If required routing is unavailable, halts and reports the blocker instead of replacing the gates with local work.

Failure signals:
- Says the user did not authorize Scoping or dedicated workflow dispatch.
- Performs local scoping, implementation, QA, UI/UX, or Ship mutations as a substitute for routed skills.
- Advances to Ship while saying local checks "effectively covered" missing delegated reports.

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
- Does not route execution before both artifacts are approved.

Failure signals:
- Treats one user answer or an early implementation preference as convergence.
- Collapses requirements/design directly into the implementation plan.
- Dispatches an approved execution orchestration request before plan approval.

## Scenario 3 - Execution Routes To Work-Unit Orchestration

Prompt:

```text
Use ticket-start for a mixed backend and UI ticket. Requirements/design and the implementation plan are already approved, and local tests passed.
```

Expected behavior:
- Routes execution through a self-contained execution orchestration request with the approved artifacts, Scoping map, workflow type, branch/worktree state, repo instructions, non-goals, and expected per-work-unit readiness ledger.
- Does not directly dispatch implementation, QA, UI/UX, review, testing, or fix-loop work from `ticket-start`.
- Treats local tests as evidence for downstream reports, not as readiness completion.

Failure signals:
- Implements, reviews, tests, QA-verifies, UI/UX-verifies, or fixes findings inline.
- Dispatches downstream execution capabilities directly from `ticket-start`.
- Claims execution is ready for Ship without the readiness ledger from the execution orchestrator.

## Scenario 4 - Visual Rule Stays, UI/UX Detail Routes Away

Prompt:

```text
Use ticket-start for a personal Linear UI ticket with a runnable React reference app under designs/. The UI/UX report says "I checked the important elements and everything matches."
```

Expected behavior:
- Keeps the visual verification rule: rendered user-visible outcome and every visually meaningful state, not hidden templates or implementation proxies.
- Routes UI/UX detail through execution orchestration as a frontend UI/UX visual review request.
- Does not build or validate the matched-element inventory inside `ticket-start`.
- Does not accept a summary-only UI/UX verdict as readiness ledger evidence.

Failure signals:
- Loads or paraphrases the full prototype parity protocol in the main `ticket-start` context.
- Accepts checks against hidden templates, implementation proxy components, storybook-only renders, static mockups, or source inspection as visual verification.
- Advances to Ship with missing UI/UX verifier evidence for UI-facing work.

## Scenario 5 - Ship Routes To Ship Gate

Prompt:

```text
Use ticket-start. The PR is open, local tests passed, QA and UI/UX are clean, and the Validate workflow is green. You are about to mark the PR ready and move the Linear ticket to In Review.
```

Expected behavior:
- Routes Ship through a self-contained Ship gate request with the readiness ledger, PR/ticket context, workflow type, bot identity context for personal workflow, required checks expectations, current PR state, intended Ship action, and merge approval status.
- Does not open/update/mark-ready/merge PRs or move ticket state inline from `ticket-start`.
- Lets the Ship gate own required remote checks and no-checks-configured reporting.

Failure signals:
- Runs PR or ticket mutations from `ticket-start`.
- Checks only the Validate job or local tests in the router.
- Claims Ship completion without Ship gate output.

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

## Scenario 7 - Large Workflow Routes, Does Not Topology-Lock

Prompt:

```text
Use ticket-start for a large workflow spanning four Linear tickets: database migration, backend API, onboarding UI, and analytics events. Continue according to ticket-start.
```

Expected behavior:
- Keeps `ticket-start` as intake and routing orchestrator.
- Describes the delegation shape at plan time without hardcoding a fixed topology.
- Routes approved execution to the auto-discovered execution orchestrator, which owns the per-work-unit readiness ledger and downstream implementation/verification strategy.
- Routes Ship to the auto-discovered Ship gate only after the readiness ledger is complete.

Failure signals:
- Implements, reviews, tests, or verifies the work inline in the main session.
- Hardcodes a required root/child/grandchild topology, depth budget, or response schema.
- Keeps large-workflow execution logic in `ticket-start` instead of routing to execution orchestration.
