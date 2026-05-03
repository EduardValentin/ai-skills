# Verification (Personal Workflow + React Reference App)

Loaded during the Verify phase **only** when the personal project has a runnable React reference app. Required before opening the PR. Run only after all tests pass.

## Goal

Two distinct verifications. Both are required. Both are reported separately at closeout.

- **Visual parity** — the implemented feature matches the prototype.
- **Behavior** — the production feature's business logic and behavior are correct across every relevant state and scenario.

## Setup

1. Start both apps locally:
   - The production app on its dev server.
   - The `designs/` React reference app on its dev server.
2. Open both apps in the internal browser session, side by side.
3. Set both browser views to the same viewport size, device scale factor, browser zoom, and route/state before each comparison or screenshot.
4. If either app cannot be started, the feature cannot be exercised in both apps, or screenshots cannot be captured: stop, report the blocker explicitly, and do not claim parity was verified.

## Pass 1 — Visual Parity

Drive both apps to each important UI state of the implemented feature:

- Default
- Loading
- Empty
- Hover, focus, active, disabled
- Error and validation
- Success
- Expanded / collapsed
- Modal-open
- Navigation states tied to the feature

For each state:

1. Drive both apps into the same state.
2. Capture screenshots of the same state in both apps.
3. Compare directly: colors, spacing, margins, padding, typography, sizing, radii, shadows, alignment, animation-relevant states, and the relevant interaction states affected by the ticket.
4. Capture screenshots at every relevant responsive breakpoint, plus widths immediately before and after each breakpoint switch.
5. If a mismatch is found, fix the implementation and re-run the parity pass for the affected states. Do not declare parity until the comparison is clean.

Reference `react-parity.md` for the parity rules being checked.

## Pass 2 — Behavior

After visual parity is clean, exhaustively exercise the production app's implementation in the browser. Be thorough — go through every state and scenario of the implemented feature, not just the obvious ones.

Cover:

- **Happy path:** every implemented flow end-to-end.
- **State transitions:** every transition the feature owns.
- **Error paths:** validation errors, permission denials, network failures, conflict states, retry/cancel paths — every error this feature is responsible for.
- **Empty, loading, success, boundary conditions:** at every place the feature surfaces them.
- **Adversarial inputs:** invalid input, out-of-range values, unexpected sequences (rapid clicks, navigating mid-action, double submits) the feature should defend against.
- **Cross-feature impact:** the new feature must not regress adjacent flows visible from its surface area.
- **Responsive behavior:** interactive elements at the same breakpoints used in Pass 1.

After each meaningful action, inspect the UI to confirm the feature still looks correct and behaves correctly.

If a behavior issue is found, fix it and re-run the affected portion. Do not skip back to declaring done.

## Outcome

Only after both passes are clean:

- Open the PR with `gh`.
- Move the Linear ticket to `In Review`.
- Wait for the user's explicit approval before merging.
- After merge, move the Linear ticket to its completed state.

In the closeout report, distinguish visual parity coverage from behavior coverage explicitly. If either pass surfaced issues, name them and confirm they were fixed and re-verified.
