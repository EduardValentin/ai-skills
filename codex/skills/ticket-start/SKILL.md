---
name: ticket-start
description: Start implementation work from a software ticket with a plan-first workflow. Use when the user wants to begin building a feature or fix from a ticket, especially when they say phrases such as "start ticket", and for follow-up status or progress questions about that ticket. Supports both job/Jira tickets and personal-project/Linear tickets. Gather the minimum relevant repo context, research version-specific third-party documentation when needed, produce an implementation plan, and wait for explicit approval before making code changes. For personal projects, inspect only the relevant areas of `PRD.md` and the `designs/` React reference app, treat that reference app as the UI/UX source of truth, use Linear MCP for ticket reads and status changes, and create the PR before handing off for review. Always refresh ticket, relation, and git facts from their source of truth before answering; do not rely on memory or stale chat context. Do not use for code review, pure planning, or debugging-only tasks.
---

# Ticket Start

## Workflow Selection

1. Confirm that the request is implementation work driven by a ticket, or a follow-up status/progress question about a ticket already in this workflow. If the task is review, planning-only, or debugging-only, do not use this skill.
2. Decide which workflow applies before gathering more context:
   - `Job workflow`: tickets come from Jira or the user pastes the full ticket content directly.
   - `Personal workflow`: tickets come from Linear and the project uses `PRD.md` plus a `designs/` reference app.
3. Read and follow repository-local instructions first. Start with the nearest applicable `AGENTS.md`, then load only the additional instruction files and project docs that materially affect the task.

## Freshness And Source Of Truth

1. Treat memory, prior chat context, old plans, and earlier tool results as stale hints, not facts. This is especially important in long chats, after resumes, and after context compaction.
2. Before any substantive response about ticket scope, status, blockers, related tickets, implementation progress, PR readiness, or git state, fetch current facts from the source of truth.
3. For Linear tickets, read the current ticket from Linear. If blocked, blocking, related, duplicate, parent, or child tickets matter to the answer, read each relevant ticket from Linear too instead of relying on relation names or earlier context.
4. For job/Jira tickets without a live Jira connector, require the current full ticket content from the user when ticket freshness matters. Do not treat a stale summary or previously pasted excerpt as current truth.
5. For implementation or progress answers, inspect the current repository state and history that matters to the question, such as the current branch, working tree, relevant diffs, recent commits, and PR metadata when available.
6. For repository docs, design references, and product code, re-read the relevant files from disk before citing or depending on them.
7. If a source of truth is unavailable, say what could not be verified and do not fill the gap from memory. Separate verified facts from assumptions in the response.

## Job Workflow

1. Require the full ticket title and the full ticket description before starting. The description must include acceptance criteria and any implementation context the user has. If any of these are missing, stop and ask for the missing details.
2. Extract and restate the important requirements:
   - acceptance criteria
   - constraints
   - explicit context
   - non-goals, if present
   - open ambiguities that could change the implementation
3. Ask concise clarifying questions before doing code changes whenever the ticket leaves material ambiguity. Prefer a short focused set of questions over broad brainstorming.

## Personal Workflow

1. Use the Linear MCP tool as the source of truth for the ticket whenever the user provides a Linear identifier or the task is clearly in a personal project that uses Linear.
2. If the request is for a personal-project ticket and no Linear ticket identifier is available, stop and ask for the Linear issue identifier before proceeding.
3. Read the ticket from Linear before planning. Capture the title, description, acceptance criteria, related constraints, and any workflow metadata that matters for delivery.
4. When work begins, move the Linear ticket to `In Progress`. If the Linear MCP server is unavailable or the team/state cannot be resolved safely, pause and surface the blocker.
5. Inspect `PRD.md` only in the areas relevant to the ticket. Do not load the whole document by default. Narrow scope by feature name, user flow, domain terms, affected screens, and nearby sections first, then read only the matching slices.
6. Inspect the `designs/` reference app only in the areas relevant to the ticket. When it is a React reference app, treat it as the absolute source of truth for the feature's UI, UX, styling, layout, animation, and front-end behavior. Look for the relevant routes, screens, mocked API flows, state transitions, and components that express the desired UX without loading unrelated parts of the design app into context.
7. Use the scoped PRD findings to understand business logic and edge cases. Use the scoped `designs/` findings to understand UX, styling, interaction flow, and expected front-end behavior. Keep technical implementation decisions in the product codebase, not in the PRD.
8. If the personal project includes a runnable React design reference app, identify the matching feature route and the important UI states up front so the same flows can be exercised in both apps during end-of-session visual verification.
9. Ask concise clarifying questions only when the ticket, PRD, and design reference still leave material ambiguity.

## React Reference App Parity

Apply these rules in the personal workflow whenever the scoped `designs/` reference app is a runnable React app:

1. Replicate the reference app's current UI/UX behavior 100% for the ticketed feature, including layout, spacing, colors, typography, sizing, radii, shadows, responsive behavior, interaction states, transitions, and animations.
2. Inspect both apps' styling systems before implementing visual work. Compare Tailwind versions, theme configuration, CSS variables, design tokens, breakpoints, base styles, and any component-library defaults that affect the feature.
3. Do not assume identical class names produce identical CSS across apps. Verify scale-sensitive utilities such as `size-*`, spacing, typography, radius, shadow, color, and breakpoint classes, then translate to exact production-equivalent values or tokens when the scales differ.
4. Carry over every relevant animation and transition from the React reference app, including trigger conditions, duration, delay, easing, transform/opacity/property changes, mount/unmount behavior, and reduced-motion handling when present.
5. If the production app uses a different technology stack or lacks the same styling or animation primitives, surface that during planning and discuss the direction with the user before coding or finalizing approximations. Prefer existing production libraries and out-of-the-box styling/animation primitives when they can reproduce the reference app faithfully.
6. Document the reference route, production route, important UI states, styling scale findings, and animation findings in the implementation plan so the user can approve the parity approach before code changes begin.

## Shared Research Rules

1. Gather only the minimum code context needed to understand the current architecture and implementation path. Prefer:
   - the entry points or feature boot path
   - the target module or component
   - nearby reducers, services, fetchers, transformers, hooks, tests, or shared utilities that define the current pattern
   - existing implementations of similar behavior in the repo
2. Reuse existing project patterns before inventing new abstractions. Aim for the smallest safe diff that satisfies the ticket cleanly.
3. In personal projects that are earlier-stage or less pattern-rich, introduce clean patterns deliberately instead of improvising. Favor simple architecture, clear ownership boundaries, composable modules, and low-coupling designs that can scale with the codebase.
4. If the implementation touches a third-party library, identify the exact version used by the project from manifests or lockfiles, then read the official or primary documentation for that version before editing code that depends on it.

## Ticket Requirements

- Treat the ticket as the source of truth for scope.
- In the job workflow, do not accept a partial summary when the full ticket title or full description is required to implement safely.
- In the personal workflow, prefer reading the Linear ticket directly instead of relying on a partial retelling.
- If acceptance criteria are missing, vague, or not testable, stop and ask for clarification.
- If the ticket conflicts with repository instructions or existing architecture constraints, surface the conflict before implementation.

## Research Rules

- Read broadly enough to understand the architecture, but keep context disciplined.
- Prefer targeted file discovery with existing repo patterns over large exploratory sweeps.
- For personal projects, keep both `PRD.md` and `designs/` discovery scoped to the feature area being implemented. Search first, then read only the relevant sections and files.
- Favor primary sources for library and framework behavior.
- Use internet research only when needed for unstable or version-sensitive information, especially third-party libraries, APIs, framework behavior, or current guidance.

## Planning Gate

- Do not start coding immediately after reading the ticket.
- Produce an implementation plan only after:
  - the ticket details are complete enough
  - clarifying questions have been answered
  - the relevant repo instructions have been read
  - the minimum necessary architecture research is done
  - for personal projects, the relevant `PRD.md` and `designs/` areas have been inspected
- Treat this plan as a hard approval gate.
- Wait for an explicit user message approving the plan before making code changes.

## Implementation Standards

- Keep code readable, maintainable, and easy to reason about.
- Preserve or improve the repository's code quality standard. Do not degrade it to ship faster.
- Prefer simple, efficient solutions with clear control flow and low blast radius.
- Keep functions, modules, and components focused on a single responsibility.
- Preserve existing architecture unless the ticket truly requires change.
- Prefer small composable changes over cross-cutting rewrites.
- Apply clean code practices even in greenfield personal projects. Choose names, module boundaries, and abstractions that stay understandable as the project grows.
- Consider performance as part of the solution, especially on hot paths, repeated work, unnecessary rendering, or avoidable network and memory cost.
- Consider security implications for every new feature and every change to existing behavior. Pay special attention to trust boundaries, authentication, authorization, user-controlled input, data exposure, persistence, file handling, redirects, external requests, privileged actions, and sensitive logs.
- Avoid leaving the app vulnerable to common attack vectors such as injection, cross-site scripting, cross-site request forgery, server-side request forgery, insecure direct object references, broken access control, open redirects, path traversal, unsafe deserialization, secret leakage, insecure dependency usage, and unsafe client-side trust.
- If secure behavior is ambiguous or the change affects access to sensitive data or privileged actions, surface the risk during planning and include targeted validation for the relevant security behavior.

## Validation, PR, And Closeout

- Run the smallest meaningful validation set that proves the change works and does not obviously regress quality.
- Prefer targeted tests first, then broader lint or test suites as appropriate for the repo.
- In the personal workflow, when a runnable React design reference app exists, end the session by starting both the product app and the design reference app, opening the same feature in both, and capturing screenshots of the same states.
- Use internal browser capabilities for this visual verification. Set both apps to the same viewport size, device scale factor, browser zoom, and route/state before each screenshot.
- Compare those screenshots directly and make sure the implemented feature matches the design reference closely for colors, spacing, margins, typography, sizing, animation-relevant states, and the relevant interaction states affected by the ticket.
- Cover the meaningful states for the feature exhaustively, such as default, loading, empty, hover, focus, active, disabled, error, success, expanded, collapsed, modal open, validation, and navigation states, whenever they are part of the ticketed behavior.
- Capture screenshots at every relevant responsive breakpoint and at widths immediately before and after each breakpoint switch so responsive behavior can be assessed against the reference app.
- If the visual comparison shows mismatches, iterate on the implementation and re-run the screenshot check before calling the work done.
- If either app cannot be started, the feature cannot be exercised in both apps, or screenshots cannot be captured, report the blocker explicitly and do not claim that design parity was verified.
- After parity checks, use internal browser capabilities to thoroughly test the production app's implemented business flows and state transitions. Exercise every implemented path and inspect the UI after each important action to confirm the feature still looks correct and behaves correctly.
- This production browser testing may be combined with the visual parity workflow, but the closeout must clearly distinguish visual parity coverage from business-logic coverage.
- In the personal workflow, after implementation and validation, create a pull request with the GitHub CLI tool and then move the Linear ticket to `In Review`.
- Do not close the Linear ticket and do not merge the PR immediately after creating it. Treat your user as the reviewer gate.
- Only after the user explicitly approves the PR should you merge the PR and then move the Linear ticket to its completed state.
- If PR creation, Linear state transition, merge, or closeout cannot be completed, say exactly what failed and what remains manual.
- Report:
  - what was changed
  - what was validated
  - any remaining risk, assumption, or follow-up worth noting
