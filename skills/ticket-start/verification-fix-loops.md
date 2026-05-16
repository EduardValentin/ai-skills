# Verification Fix Loops

Loaded by the main agent during Verify when QA or UI/UX returns findings. This file defines two local find -> fix -> verify loops. There is no generic review loop here.

## Shared rules

- Every verification finding fix is handled by a fresh lightweight implementer subagent with a focused context.
- The main agent sends a compact finding packet: finding ID, severity, `path:line` or selector/state, expected behavior, relevant Scoping locator(s), relevant diff slice(s), exact verification target, and constraints.
- The implementer subagent edits only the scoped fix surface and returns a compact diff summary plus tests/checks run.
- Do not ask the user to confirm obvious fixes already determined by the ticket, approved artifacts, QA finding, UI/UX finding, prototype, or repository instructions.
- Stop and ask the user only for blockers, scope changes, ambiguous product intent, conflicting findings, or unavailable verification environment.
- Cap each lane at 3 unresolved iterations. After the third unresolved QA or UI/UX rerun, stop with an intervention report naming persistent findings, attempted fixes, current branch, and what could unblock the work.

## QA finding loop

Use when QA returns findings.

1. Dispatch a fresh lightweight implementer subagent with the compact QA finding packet.
2. The implementer fixes the QA finding and runs the narrowest relevant local check.
3. Re-dispatch QA with the updated diff and the original QA mode.
4. If QA is clean, exit the QA loop and continue Verify.
5. If QA still finds issues, repeat until clean, blocked, or the 3-iteration cap is reached.

QA findings rerun QA. Do not route QA findings through a code-review loop.

## UI/UX finding loop

Use when UI/UX returns visual, parity, consistency, or accessibility findings.

1. Dispatch a fresh lightweight implementer subagent with the compact UI/UX finding packet.
2. The implementer fixes the visual/accessibility finding and runs the narrowest relevant local check.
3. Re-dispatch UI/UX scoped to affected rows and states.
4. If UI/UX is clean and inventory validation passes, exit the UI/UX loop and continue Verify or Ship.
5. If UI/UX still finds issues, repeat until clean, blocked, or the 3-iteration cap is reached.

Visual-only UI/UX fixes do not rerun QA and do not route through a code-review loop. If a UI/UX finding would require product scope or behavior changes, stop and ask the user before editing.

## Intervention report

When a lane hits the cap or a blocker, report:

```markdown
# Verification intervention requested — <ticket title>

## Lane
<QA | UI/UX>

## Persistent findings
- <finding ID> | <locator/selector/state> | <one-line issue>

## Attempts made
- <iteration> | <one-line fix summary> | <verification result>

## What could unblock this
- <needed user decision, environment access, scope change, or missing context>

## State of the work
- Branch: <branch name>
- Last clean gate: <QA / UI/UX / none>
- Outstanding findings: <list>
```
