# Bug-Fix Loop

Loaded by the main agent during the Review and Verify phases when any auditor agent (Reviewer, QA, UI/UX) returns a non-clean verdict. This file defines the protocol for converging back to clean.

## Trigger

Any of the following triggers the loop:
- Reviewer returns CHANGES REQUIRED.
- QA returns BUGS FOUND.
- UI/UX returns FINDINGS.

## Three-tier complexity classification

The main agent classifies each fix into one of three tiers. **The main agent decides classification.** When ambiguous, default to the **higher** tier (safer, fewer surprises).

| Tier | Definition | Path |
|---|---|---|
| **Trivial** | Typo, one-liner, mechanical change with no design implication. Examples: rename a private variable, fix a comment typo, swap a constant import path, correct a log-message string with no UI surface. | Straight to Implementer. **No** brainstorm, **no** plan. |
| **Non-trivial, non-architectural** | Real change that doesn't alter the architecture of the solution. Examples: add a missing validation branch, restructure a function's control flow, fix an off-by-one bug, add error handling on an existing path, correct visual parity drift already identified by UI/UX. | Main writes a tight scoped fix plan from the auditor findings, then implements. **No user-facing brainstorm or approval checkpoint** unless there is a material judgment call under `## User intervention principle`. The original brainstorm summary and approved plan stay valid. |
| **Architectural** | Fix changes the solution's architecture: module boundaries, data model, integration approach, or what gets persisted. Examples: a fix requires extracting a shared service, changing a type that ripples across consumers, moving logic between layers. | Main re-runs the full brainstorm + plan loop — the relentless interview surfaces alternatives, the anti-collapse rule applies, and the new brainstorm summary must record the architectural choice and the alternatives considered. If the fix introduces a genuinely new architectural question that needs focused research, dispatch a focused research subagent ad-hoc during the brainstorm. |

If a fix touches both a trivial typo and an architectural change, classify as architectural — the higher tier.

## Re-review scope after a fix lands

After the fix lands and tests pass:

| Agent | Re-run scope |
|---|---|
| **Reviewer** | **Full diff** (original + fix). A fix can introduce regressions in the reviewed surface. |
| **QA** | **Full behavior pass.** A fix can introduce regressions in unrelated states. |
| **UI/UX** | **Scoped to affected states** (the state(s) where the visual finding surfaced + immediately adjacent states). Visual issues are localized; full re-runs are wasteful. |

These scopes are non-negotiable — they reflect the cost-of-miss tradeoff for each agent's domain.

## Fix packet and batching

Before editing, compress the current non-clean reports into a fix packet:
- finding IDs + severity;
- affected `path:line` / selector / state;
- one-line intended fix;
- test or browser check to rerun;
- cross-gate collateral to update, especially tokens, design docs, tests, copy, focus styling, and shared component docs.

Batch same-pass findings that share the same tier and surface into one scoped fix. Do not bounce one UI parity row at a time through Implementer when the auditor returned a set of related drifts. For UI/UX parity findings, fix every concrete drift in the current report and any directly required token/docs/test collateral in the same implementation pass unless a finding creates a material judgment call under `## User intervention principle`.

Keep the main context to the fix packet, compact diff summary, and verification results. Do not paste full auditor reports, full logs, screenshots, or source snippets when finding IDs and locators are enough.

## Iteration cap

**Cap = 3 fix iterations per ticket.** The counter increments on every auditor-gate cycle that returns non-clean, regardless of which agent triggered it. It is **not** per-agent. (Test-failure repair does not increment the counter — only auditor-gate cycles do.) After the third unresolved iteration, the main agent stops and produces an **intervention report**:

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
- Last passing gate: <Reviewer / QA / UI/UX>
- Outstanding findings: <list>
```

The cap protects against runaway loops on genuinely hard problems. Do not exceed it silently.

## User intervention principle (always-on)

At **any** point in the loop — not just at the cap — if the main agent hits a judgment call, blocker, ambiguity, or environmental issue that exceeds its authority to decide, the workflow **stops** and surfaces. The main agent does not guess on the user's behalf. Surfaces include:

- Conflict between two agents' findings (e.g., Reviewer suggests A, QA suggests not-A).
- Ambiguous classification of fix tier when the architectural impact is unclear after honest assessment.
- Environmental blocker that cannot be diagnosed from the session (e.g., dev server crashes with no obvious cause).
- A finding that requires changing the ticket's scope.

When surfacing to the user, brief per `SKILL.md` → `## Dispatch → user briefing protocol` (handoff type 7: bug-fix loop architectural intervention) before asking the user to decide on direction. Present the relevant finding(s), the auditor's suggested fix if any, and the architectural tradeoff main agent sees, so the user can weigh in with the same context main agent has.

### Low-value checkpoint guard

Do **not** stop to ask the user a question whose answer is already determined by the ticket, approved plan, prototype parity mode, auditor finding, or repository instructions. Auditor findings are actionable by default.

Ask only when the answer would change the fix in a material way:
- Two valid fixes trade off scope, architecture, semantics, accessibility, data behavior, or user-visible product intent.
- The auditor finding conflicts with the approved plan, ticket, prototype, or another auditor.
- The suggested fix would alter the feature's architecture, user flow, accessibility semantics, or accepted non-goals.
- The environment blocks verification or implementation and the user must choose a path.

Do not ask to confirm the obvious scoped path. Examples of forbidden low-value questions:
- "Should I treat all UI/UX parity drifts as strict prototype-parity defects?"
- "Should I preserve the approved placement and current accessibility semantics while fixing visual drift?"
- "Should I implement the auditor's suggested fix for this concrete bug?"

For concrete UI/UX parity findings in parity mode, default to strict prototype parity while preserving approved placement, behavior, and accessibility semantics unless the auditor or ticket says otherwise. Do not offer the visual companion or pause for a design preference question just to restate the auditor's report; fix the drift and re-run the required gates.

## Sequencing of re-runs

**Gate order:** Reviewer → QA → UI/UX (matches the phase order in `SKILL.md`).

**Sequencing rule:** after any fix, all full-rerun gates run in **upstream-first** order regardless of which agent originated the finding. Reviewer findings can render QA findings moot, so running upstream gates first avoids wasted work and prevents cross-gate contradictions.

**After a fix:**

1. Implementer commits the fix on the same branch.
2. Tests run; if they fail, fix-the-fix before any agent re-runs. Test-failure repair does **not** increment the iteration counter — only auditor-gate cycles do.
3. Re-run all upstream full-rerun gates in order (Reviewer → QA), then re-run UI/UX scoped to affected states if applicable. Skip UI/UX entirely if backend-only.
4. If every gate that ran returned CLEAN, the loop exits successfully.
5. If any gate returns non-clean, increment the iteration counter and re-enter the loop with the new finding.

**Worked chains:**

- **After a Reviewer-found bug:** Reviewer re-runs (full diff) → QA runs (full pass) → UI/UX runs scoped (or skips if backend-only).
- **After a QA-found bug:** Reviewer re-runs (full diff) → QA re-runs (full pass) → UI/UX runs scoped (or skips if backend-only).
- **After a UI/UX-found bug:** Reviewer re-runs (full diff) → QA re-runs only if the fix touches behavior code (main agent's judgment) → UI/UX re-runs scoped to affected states.

The full-rerun rule for code review after **any** fix is a deliberate cost: a fix anywhere can break the reviewed surface, and we'd rather catch that here than ship it.

## Self-improvement extraction during the loop

Each pass through the loop is a candidate for the self-improvement loop. After each clean re-run of an auditor agent, scan its `Patterns to codify next time` section for new entries (entries that weren't there in the previous run). Those are the most valuable candidates — they represent lessons learned from this specific bug-fix cycle, not just the original implementation.

See `self-improvement.md` for the rule-extraction protocol.

## Exit conditions

The loop exits when:
- Every relevant gate (Reviewer, QA, UI/UX-or-skipped) has returned CLEAN in sequence after the most recent fix; OR
- The 3-iteration cap is reached and the main agent has produced an intervention report; OR
- The main agent has stopped on an explicit user-intervention condition.

The first is the only "success" exit. The other two pause the workflow pending user action.
