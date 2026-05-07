# Personal Workflow

Use when the ticket lives in Linear and the project has `PRD.md` plus a `designs/` reference app. Loaded by `SKILL.md` once when the personal workflow is selected. The Ticket Intake, Scoped Reading, and React Reference App sections apply during Setup; the Linear State Transitions section applies during Implement and Ship. Return to `SKILL.md` for phase ordering, standards, Verify, and Ship.

## Ticket Intake (Linear)

1. Use the Linear MCP tool as the source of truth for the ticket whenever the user provides a Linear identifier or the task is clearly in a personal project that uses Linear.
2. If no Linear ticket identifier is available, stop and ask for it before proceeding.
3. Read the ticket directly from Linear. Capture title, description, acceptance criteria, related constraints, and any workflow metadata that matters for delivery. Do not rely on a partial retelling.
4. State transitions for the Linear ticket are defined in the **Linear State Transitions** section below. Do not move the ticket out of order or skip transitions.

## Scoped Reading (Required)

Inspect only the areas of `PRD.md` and `designs/` that are relevant to this ticket. Do not load either in full by default.

- **PRD.md** — narrow scope by feature name, user flow, domain terms, affected screens, and nearby sections. Read only the matching slices. Use this for business logic, edge cases, and rules.
- **designs/** — narrow scope to the relevant routes, screens, mocked API flows, state transitions, and components. Use this for UX, styling, interaction flow, and front-end behavior.
- Keep technical implementation decisions in the production codebase, not in the PRD.

## React Reference App

If `designs/` is a runnable React app, additionally read `react-parity.md` and treat the reference app as the absolute source of truth for the feature's UI, UX, styling, layout, animation, and front-end behavior.

Identify up front:

- The reference route/screen for this feature.
- The matching production route/screen.
- The important UI states the feature has (default, loading, empty, hover, focus, active, disabled, error, success, expanded/collapsed, modal-open, validation, navigation), so the same flows can be exercised in both apps during verification.

## Hand-off To Brainstorm

When the scoped PRD and `designs/` findings are gathered, return to `SKILL.md` and proceed to the Brainstorm gate (`superpowers:brainstorming`). Use the brainstorm to map the prototype design into the production app — do not re-litigate copy, design, UI interactions, or animations already settled by the prototype unless the ticket or PRD conflicts with it.

## Linear State Transitions

Move the Linear ticket through these states at these exact moments. `SKILL.md`'s Verify and Ship sections defer to this list.

- **In Progress** — at the start of the Implement phase, immediately after the user approves the plan and before any code is written. Not during Setup, not during Brainstorm, not during Plan.
- **In Review** — at the start of the Ship phase, immediately after the PR is opened with `gh`.
- **Completed state** (whichever state the team uses for done) — only after the user has explicitly approved the merge and the merge has actually completed.

If the Linear MCP server is unavailable or the team/state cannot be resolved safely at any of these points, pause and surface the blocker. Do not silently skip a transition or guess the destination state.

## Partial Setups

If the project has a Linear ticket but is missing `PRD.md`, `designs/`, or both, treat it as personal workflow and adapt as follows. Surface the gap to the user during Setup so the brainstorm can compensate.

- **No `PRD.md`:** gather requirements from the Linear ticket alone and flag missing context during Brainstorm. Do not invent business rules to fill the gap.
- **No `designs/`:** skip the React reference app, skip `react-parity.md`, and skip `verification.md`. Verification falls back to the procedure in `job-workflow.md` (Mode A for backend, Mode B for UI, Mode C for mixed).
- **Neither present:** gather everything from the ticket, confirm scope and acceptance criteria with the user before brainstorming, and use the `job-workflow.md` Verification procedure at the Verify phase.
