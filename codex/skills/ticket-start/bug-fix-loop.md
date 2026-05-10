# Bug-Fix Loop

Loaded by the main agent during the Review, Security, and Verify phases when any auditor agent (Reviewer, Security, QA, UI/UX) returns a non-clean verdict. This file defines the protocol for converging back to clean.

## Trigger

Any of the following triggers the loop:
- Reviewer returns CHANGES REQUIRED.
- Security returns CHANGES REQUIRED.
- QA returns BUGS FOUND.
- UI/UX returns FINDINGS.

## Three-tier complexity classification

The main agent classifies each fix into one of three tiers. **The main agent decides classification.** When ambiguous, default to the **higher** tier (safer, fewer surprises).

| Tier | Definition | Path |
|---|---|---|
| **Trivial** | Typo, one-liner, mechanical change with no design implication. Examples: rename a variable, fix a copy string, swap a constant. | Straight to Implementer. **No** brainstorm, **no** plan, **no** architect. |
| **Non-trivial, non-architectural** | Real change that doesn't alter the architecture of the solution. Examples: add a missing validation branch, restructure a function's control flow, fix an off-by-one bug, add error handling on an existing path. | Main re-runs `superpowers:brainstorming` + `superpowers:writing-plans` with the user. **No** architect involvement. |
| **Architectural** | Fix changes the solution's architecture: module boundaries, data model, integration approach, or what gets persisted. Examples: a fix requires extracting a shared service, changing a type that ripples across consumers, moving logic between layers. | Main re-engages **Architect**, then re-runs brainstorm + plan (full initial loop). |

If a fix touches both a trivial typo and an architectural change, classify as architectural — the higher tier.

## Re-review scope after a fix lands

After the fix lands and tests pass:

| Agent | Re-run scope |
|---|---|
| **Reviewer** | **Full diff** (original + fix). A fix can introduce regressions in the reviewed surface. |
| **Security** | **Full diff.** Cross-cutting concerns require full audit. |
| **QA** | **Full behavior pass.** A fix can introduce regressions in unrelated states. |
| **UI/UX** | **Scoped to affected states** (the state(s) where the visual finding surfaced + immediately adjacent states). Visual issues are localized; full re-runs are wasteful. |

These scopes are non-negotiable — they reflect the cost-of-miss tradeoff for each agent's domain.

## Iteration cap

**Cap = 3 fix iterations** per ticket. After the third unresolved fix attempt, the main agent stops and produces an **intervention report**:

```markdown
# Intervention requested — <ticket title>

## What's persistent
<one-paragraph summary of the recurring issue or pattern>

## Why fixes haven't landed
<one-paragraph honest assessment: agent disagreement, environmental issue, ambiguous AC, missing context, etc.>

## What could unblock this
- <option 1: clarify AC X>
- <option 2: change scope of ticket>
- <option 3: provide environment access for QA mode A>
- <etc.>

## State of the work
- Branch: <branch name>
- Last passing gate: <Reviewer / Security / QA / UI/UX>
- Outstanding findings: <list>
```

The cap protects against runaway loops on genuinely hard problems. Do not exceed it silently.

## User intervention principle (always-on)

At **any** point in the loop — not just at the cap — if the main agent hits a judgment call, blocker, ambiguity, or environmental issue that exceeds its authority to decide, the workflow **stops** and surfaces. The main agent does not guess on the user's behalf. Surfaces include:

- Conflict between two agents' findings (e.g., Reviewer suggests A, Security suggests not-A).
- Ambiguous classification of fix tier when the architectural impact is unclear after honest assessment.
- Environmental blocker that cannot be diagnosed from the session (e.g., dev server crashes with no obvious cause).
- A finding that requires changing the ticket's scope.

## Sequencing of re-runs

After a fix:

1. Implementer commits the fix on the same branch.
2. Tests run; if they fail, fix-the-fix before any agent re-runs.
3. Re-run the agent that originally reported (Reviewer / Security / QA / UI/UX).
4. If that agent goes CLEAN, **continue downstream** through the remaining gates that hadn't run yet *plus* any earlier gate whose scope rule above mandates a full re-run.
5. If that agent stays non-clean, increment the iteration counter and loop.

Specifically, after a Security-found bug is fixed:
- Reviewer re-runs (full diff, per scope rule).
- Then Security re-runs (full diff).
- Then QA runs.
- Then UI/UX runs (or skips if backend-only).

After a QA-found bug:
- Reviewer re-runs.
- Security re-runs.
- QA re-runs (full pass).
- Then UI/UX (if applicable).

After a UI/UX-found bug:
- Reviewer re-runs.
- Security re-runs.
- QA does **not** re-run unless the fix touches behavior code (main agent's judgment).
- UI/UX re-runs scoped to affected states.

The full-rerun rule for code/security after **any** fix is a deliberate cost: a fix anywhere can break a review or audit, and we'd rather catch that here than ship it.

## Self-improvement extraction during the loop

Each pass through the loop is a candidate for the self-improvement loop. After each clean re-run of an auditor agent, scan its `Patterns to codify next time` section for new entries (entries that weren't there in the previous run). Those are the most valuable candidates — they represent lessons learned from this specific bug-fix cycle, not just the original implementation.

See `self-improvement.md` for the rule-extraction protocol.

## Exit conditions

The loop exits when:
- Every relevant gate (Reviewer, Security, QA, UI/UX-or-skipped) has returned CLEAN in sequence after the most recent fix; OR
- The 3-iteration cap is reached and the main agent has produced an intervention report; OR
- The main agent has stopped on an explicit user-intervention condition.

The first is the only "success" exit. The other two pause the workflow pending user action.
