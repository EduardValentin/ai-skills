# Personal Workflow

Use when the ticket lives in Linear and may have `PRD.md` plus a `designs/` reference app. Loaded by `SKILL.md` once when the personal workflow is selected. The Ticket Intake, Scoped Reading, and React Reference App sections apply during Setup. The Verification mode-mapping section specifies the review modes the QA and UI/UX subagents receive. The Linear State Transitions section applies during Implement and Ship. Return to `SKILL.md` for phase ordering, dispatch points, verification fix loops, and Ship.

## Ticket Intake (Linear)

1. Use the Linear MCP tool as the source of truth for the ticket whenever the user provides a Linear identifier or the task is clearly in a personal project that uses Linear.
2. If no Linear ticket identifier is available, stop and ask for it before proceeding.
3. Read the ticket directly from Linear. Capture title, description, acceptance criteria, related constraints, and any workflow metadata that matters for delivery. Do not rely on a partial retelling.
4. State transitions for the Linear ticket are defined in the **Linear State Transitions** section below. Do not move the ticket out of order or skip transitions.

After intake, proceed to Scoped Reading, then dispatch the Scoping subagent as `SKILL.md`'s Setup phase directs.

## Bot Identity (REQUIRED for this workflow)

Personal-workflow tickets always use a dedicated GitHub App identity for PRs and commits — the skill never uses your personal GitHub credentials on personal-workflow tickets. Linear MCP continues to authenticate as you (ticket reads, transitions, and comments stay under your personal Linear identity).

See `bot-identity.md` for the full one-time setup runbook, the two Setup activation checks the main agent performs, the Ship-phase token refresh, and the failure-mode catalog. If the GitHub bot creds are not configured in macOS Keychain, the skill halts at Setup with a pointer to the relevant runbook step. **Fail-closed by design.**

## Scoped Reading

Inspect only the areas of `PRD.md` and `designs/` that are relevant to this ticket. Do not load either in full by default.

- **PRD.md** — narrow scope by feature name, user flow, domain terms, affected screens, and nearby sections. Read only the matching slices. Use this for business logic, edge cases, and rules.
- **designs/** — narrow scope to the relevant routes, screens, mocked API flows, state transitions, and components. Use this for UX, styling, interaction flow, and front-end behavior.
- Keep technical implementation decisions in the production codebase, not in the PRD.

The scoped slices feed directly into the Scoping subagent's input set.

## React Reference App

If `designs/` is a runnable React app, treat the reference app as the absolute source of truth for the feature's UI, UX, styling, layout, animation, and front-end behavior. During Verify, the UI/UX subagent receives a self-contained frontend UI review request in parity mode.

Identify up front:

- The reference route/screen for this feature.
- The matching production route/screen.
- The important UI states the feature has (default, loading, empty, hover, focus, active, disabled, error, success, expanded/collapsed, modal-open, validation, navigation), so the same flows can be exercised in both apps during verification.

These are passed to the UI/UX subagent during Verify.

### Prototype parity dominates all other rules

When the personal workflow has a runnable React reference app, **prototype visual parity is the highest-priority rule** for that ticket's visual surface. It overrides "use the design system's existing primitives" guidance, "match existing project patterns," and any other style heuristic.

If a production design-system primitive does not reproduce the prototype's visual exactly:

- **Right path:** add or extend the primitive so it matches the prototype. Surface the design-system gap during planning so the user can approve the new primitive.
- **Wrong path:** silently substitute a "close-enough" production primitive (e.g., translating a prototype `<span>+✔` eyebrow into a production `Badge` component with pill background and shadow). That is parity drift dressed up as design-system discipline.

When the prototype and the design system disagree, the prototype wins. The design system is a tool for achieving parity, not a replacement for it.

**Corollary:** prototype enumeration in Scoping is mandatory in parity mode. The parity-dominance rule depends on having an authoritative list of what to maintain parity with; Scoping's `## Prototype or reference elements` section is that list. An empty section is a Scoping failure, not a clean report.

## Verification — Mode Mapping For QA And UI/UX

The Verify phase is run by the QA and UI/UX subagents. This file specifies the review mode they receive in the personal workflow.

### QA mode

Determined from the diff (main agent decides), same as the job workflow:

- **`backend`** — diff touches only backend / service files. QA Mode A.
- **`ui`** — diff touches only user-facing files. QA Mode B.
- **`mixed`** — both. QA Mode C.

### UI/UX mode

- **`parity`** — when `designs/` is a runnable React reference app. The UI/UX prompt asks the subagent to review the implemented frontend UI against the runnable prototype/reference app for visual parity, build the matched-element inventory from Scoping's prototype/reference element enumeration plus affected production surfaces, extract DOM computed styles and bounding rects, cover relevant states and breakpoints, and check accessibility. Reference app is the absolute source of truth.
- **`consistency`** — fallback when `designs/` is missing or not runnable. The UI/UX prompt asks the subagent to review the implemented frontend UI against credible production sibling/analog elements for visual consistency, plus accessibility checks.

UI/UX is **skipped** if main agent determines the change is backend-only.

## Hand-off to Requirements/Design

When ticket intake, scoped PRD/designs reading, and the Scoping subagent's report are complete, return to `SKILL.md` and proceed to Requirements/Design. Use that dialogue to map the prototype design into the production app — do not re-litigate copy, design, UI interactions, or animations already settled by the prototype unless the ticket or PRD conflicts with it.

## Linear State Transitions

Move the Linear ticket through these states at these exact moments. `SKILL.md`'s Implement and Ship phases defer to this list.

- **In Progress** — at the start of the Implement phase, immediately after the user approves the plan and before any code is written. Not during Setup, not during Requirements/Design, not during Plan.
- **In Review** — at the start of the Ship phase, immediately after the PR is opened with `gh`.
- **Completed state** (whichever state the team uses for done) — only after the user has explicitly approved the merge and the merge has actually completed.

If the Linear MCP server is unavailable or the team/state cannot be resolved safely at any of these points, pause and surface the blocker. Do not silently skip a transition or guess the destination state.

## Partial Setups

If the project has a Linear ticket but is missing `PRD.md`, `designs/`, or both, treat it as personal workflow and adapt as follows. Surface the gap to the user during Setup so the Requirements/Design dialogue can compensate.

- **No `PRD.md`:** gather requirements from the Linear ticket alone and flag missing context during Requirements/Design. Do not invent business rules to fill the gap.
- **No `designs/`:** skip the React reference app and skip parity mode. UI/UX runs in **consistency mode** instead.
- **Neither present:** gather everything from the ticket, confirm scope and acceptance criteria with the user before Requirements/Design. UI/UX runs in **consistency mode** during Verify.
