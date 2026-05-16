---
name: ticket-start
description: Use when the user wants to start implementation work from a ticket — phrases like "start ticket", a pasted Jira ticket, or a Linear issue ID. Also use for follow-up status or progress questions about a ticket already in this workflow. Covers both job tickets (Jira/pasted; uses acli when available) and personal-project tickets (Linear, optionally with PRD.md and a designs/ React reference app). Do not use for code review, planning-only, or debugging-only tasks.
---

# Ticket Start

## Overview

Implementation work driven by a ticket. The main agent owns user dialogue, requirements/design approval, implementation-plan approval, verification gating, and Ship. Specialized subagents own compact codebase scoping, QA verification, UI/UX verification, and focused verification fixes.

Phase order is a hard gate:

**Setup -> Requirements/Design -> Plan -> Implement -> Verify -> Ship**

Before implementation, explore project context, user intent, requirements, constraints, design, alternatives, edge cases, and non-goals. Produce an approved requirements/design artifact before implementation planning. Then write a detailed implementation plan and wait for explicit plan approval before code.

Implementation proceeds task-by-task with test-first development, fresh subagents for independent tasks when available, and review checkpoints built into the implementation workflow. `ticket-start` does not add a separate post-implementation code-review gate.

**Scoping dispatch wording:** `ticket-start` dispatches the Scoping subagent and consumes its returned map. The Scoping prompt must be a self-contained codebase mapping request: implementation/ticket codebase mapping, token-efficient navigable scope map, file:line locators, entry points, target modules/components, domain logic, shared utilities, analogous implementations, project patterns, types/contracts, tests, imports/dependencies, prototype/reference elements when applicable, affected surfaces, conflict points, and suggested downstream slices.

**UI/UX dispatch wording:** `ticket-start` constructs the UI/UX dispatch context and validates the returned report. The UI/UX subagent prompt must be a self-contained frontend UI review request: implemented frontend UI, review mode (`parity` with a runnable prototype/reference, `consistency` with production analogs), matched-element inventory, DOM computed styles, bounding rects, accessibility, and inventory construction from the affected surface map.

**Context-economy contract:** every subagent report is a navigable index, not a transcript. Downstream readers consume the surgical slices upstream locators point at; never reload full files when a Scoping locator suffices.

**Subagent authorization contract:** a user who invokes `ticket-start` has authorized every mandatory subagent dispatch named by this skill. General host guidance that discourages casual subagent spawning does not override `ticket-start`'s required dispatches. If the host cannot dispatch subagents, halt and surface that blocker; never replace Scoping, QA, UI/UX, or focused verification-fix implementers with local-only substitutes.

## When to use

- The user asks to start, work on, build, or implement a ticket.
- The user pastes a Jira/job ticket and asks for implementation.
- The user gives a Linear ticket identifier in a personal project.
- Follow-up status/progress questions about a ticket already in this workflow.

**Do not use for:** code review, pure planning, debugging-only tasks, or refactors with no ticket.

## Workflow selection

- **Job workflow** — Jira ticket or pasted by the user. Load `job-workflow.md`.
- **Personal workflow** — Linear ticket. Load `personal-workflow.md`. `PRD.md` and a `designs/` React reference app are optional; see that file's `## Partial Setups` for what changes when either is absent.

If ambiguous, ask the user before loading anything else.

## Setup

1. **Worktree.** Start feature work in an isolated worktree based on the latest `origin/main`. Hard rule: fetch `origin main` first, then create or verify the worktree from fetched `origin/main`, never from local `main`, the current branch, or a stale remote-tracking ref. Halt on fetch failure — do not fall back to stale local state.

2. **Bot identity (personal workflow only).** Run the two activation checks in `bot-identity.md` -> `## Setup activation` — mint a fresh GitHub installation token and verify it with a no-op API call, then apply the bot's git name/email as per-worktree git config. Halt on failure with a pointer at the runbook. Fail closed — never fall back to personal GitHub credentials. Linear MCP stays under personal identity. Job workflow: skip this step.

3. **Freshness — memory is stale.** Memory, prior chat context, old plans, and earlier tool results are hints, not facts. Before any substantive answer about scope, status, blockers, related tickets, progress, or git state, fetch from the source of truth:
   - **Linear tickets:** Linear MCP. If related/blocking/duplicate/parent/child tickets matter, read each.
   - **Job/Jira tickets:** prefer `acli jira workitem view <KEY> --json` (see `job-workflow.md`); fall back to user paste only on `acli` failure.
   - **Repo state:** inspect branch, working tree, diffs, recent commits, PR metadata.
   - **Repo docs/code:** re-read from disk before citing or depending.
   - If a source is unavailable, say what could not be verified. Do not fill from memory.

4. **Workflow-specific reading.** Read the workflow file selected above and gather the facts it points at. Stop when the relevant facts are gathered.

5. **Dispatch Scoping subagent.** Ask for a token-efficient navigable scope map for this implementation ticket with `path:line` / `path:start-end` locators, covering entry points, target modules/components, domain logic, shared utilities, analogous implementations, project patterns, types/contracts, tests, imports/dependencies, prototype/reference elements when applicable, affected surfaces, conflict points, and suggested downstream slices. Forward: ticket title/description/AC, repo `AGENTS.md` / `CLAUDE.md`, and (personal workflow) the scoped slices of `PRD.md` / `designs/`. Subagent context does not inherit the main session's auto-loaded files — explicit forwarding is required. The returned map is the definitive map of the relevant code surface; do not re-read full files later when a Scoping locator points at the slice you need.

6. **Clarify if needed.** If AC are missing/vague/not testable, or Scoping surfaces a conflict between the ticket and existing ownership, layering, or product constraints, brief the user with Scoping evidence (`path:line`) and ask before continuing. See `## Briefing rule`.

## Requirements/Design

1. **Open with a Scoping-grounded briefing.** Per `## Briefing rule`, surface entry points, target module, prototype/reference elements if any, and conflicts Scoping flagged. The user must enter the dialogue with the same context Scoping built.

2. **Explore before implementation.** Frame the work as requirements and design exploration: project context, user intent, requirements, constraints, design, alternatives, edge cases, failure modes, accessibility, and non-goals before implementation.

3. **Surface alternatives.** Before treating any direction as converged, put at least one credible alternative on the table, even if only to dismiss it. The requirements/design artifact must record the chosen direction and any meaningful alternative dismissed with rationale.

4. **Anti-collapse rule.** A single user answer is not convergence. An early implementation preference is an input, not the endpoint. Before exiting:
   - Restate the chosen direction across intent, mechanism, edge cases, non-goals, and alternatives considered.
   - Ask the user to approve the requirements/design direction explicitly.
   - "Yes, do it" / "approved" / "go ahead" / similar is approval of the requirements/design direction, not approval of the implementation plan.

5. **Output: approved requirements/design artifact.** Write the settled requirements/design artifact in the workflow's planning location. Keep agent-local planning artifacts out of product commits unless the repo explicitly asks to version them. Ask the user to review and approve the artifact before Plan.

## Plan

1. Produce a written implementation plan from the approved requirements/design artifact before touching code. The plan is a distinct artifact — not a verbal summary, not the requirements/design transcript, not a mental model.

2. For UI tickets, keep visible-surface tasks traceable to Scoping's affected surface map. Reference-backed UI tasks should also remain traceable to Scoping's prototype/reference rows. The main agent does not build the UI/UX matched-element inventory; the UI/UX subagent builds it during Verify from the affected surface map, the approved artifacts, and the diff.

3. Show the plan to the user for review. Wait for explicit user approval of the plan itself before any code.

4. **No code between requirements/design approval and plan approval.** Not exploratory edits, not scaffolding, not "drafting what the plan would say in code." File edits are off-limits until the plan exists and the user has explicitly approved it.

## Implement

1. **Personal workflow:** move the Linear ticket to **In Progress** immediately after plan approval, before any code (per `personal-workflow.md`).

2. Execute the approved plan task-by-task with test-first development. Prefer fresh subagents for independent implementation tasks when available. Keep task handoffs focused: the relevant plan task, required locators, expected tests, and constraints.

3. Let the implementation workflow's built-in review checkpoints handle implementation quality. `ticket-start` does not dispatch a separate code-review subagent and does not add another post-implementation code-review phase.

4. When implementation reaches branch-finishing guidance, accept any test-pass check but do not present merge / PR / keep / discard options. Return to this skill's Verify phase. Ship replaces those options.

## Verify

1. **Determine backend-only flag.** Walk the diff:
   - `git diff --name-only origin/main..HEAD`.
   - Match against UI extensions (`\.(tsx|jsx|vue|svelte|html|css|scss|sass|less|styl|ejs|pug|hbs|erb|twig|liquid|jinja|blade\.php)$`) and UI directories (`app/`, `components/`, `pages/`, `views/`, `templates/`, `client/`, `web/`, `frontend/`, `ui/`, plus repo-specific UI dirs identified by Scoping).
   - Any match -> not backend-only.
   - Uncertain (config files affecting render, shared utilities used by both) -> ask the user. Default on uncertainty: do not skip UI/UX.

2. **Dispatch QA subagent** (`agents/qa.md`). Forward: ticket + AC, approved requirements/design artifact, approved plan, full diff, QA mode (`backend` / `ui` / `mixed` from diff), path/URL of the running app, live-browser automation for UI mode if available, HTTP tooling for backend, and role prompt. Local test runs, manual browser checks, and endpoint probes are evidence for QA to use, not substitutes for the QA report.

3. **If QA returns findings**, route through `verification-fix-loops.md` -> `## QA finding loop`. QA findings dispatch a fresh lightweight implementer subagent with a compact finding packet, then QA reruns. Do not route QA findings through a generic review loop.

4. **When QA is clean**, continue to UI/UX unless backend-only.

5. **Dispatch UI/UX subagent** unless backend-only flag is set. Ask for frontend UI review:
   - Parity mode when a runnable prototype/reference app is available: review the implemented frontend UI against that reference as the visual source of truth.
   - Consistency mode otherwise: review the implemented frontend UI against credible production sibling or analog elements.
   - Include: build a matched-element inventory from Scoping's affected surface map, approved artifacts, changed UI files, and live DOM inspection; fill DOM computed styles; compare bounding rects; check keyboard/focus/contrast accessibility; return a Markdown report with verdict, review mode, comparison basis, states covered, completed inventory rows, findings, out-of-scope flags, and patterns.

   Forward only compact inputs: ticket + approved requirements/design artifact + plan, full diff or changed UI files, review mode, running URLs (production and reference when parity mode applies), important UI states, Scoping affected surfaces/prototype-reference rows/production locators, and any local evidence. Local accessibility scans, screenshots, Lighthouse, or visual comparison notes are evidence for the UI/UX subagent to use, not substitutes for the UI/UX report and inventory validation.

6. **Validate UI/UX's matched-element inventory before accepting any verdict.**
   - A `## Matched-element inventory` section exists.
   - A `## Review mode` section exists and matches the workflow's expected mode.
   - A `## Comparison basis` section exists. Parity mode names the runnable reference; consistency mode names credible production siblings or analogs.
   - Rows cover the relevant Scoping affected surfaces, changed visible production UI files, and visible changed elements on the feature surface. Parity mode also covers the relevant Scoping prototype/reference rows.
   - Every verified row has non-blank `font-*`, `color/bg`, `box`, `layout`, `size`, and `verdict` cells. Blank = DOM-evaluation work was skipped for that row.
   - Any missing expected coverage or blank cell -> report is structurally invalid. Reject and re-dispatch UI/UX with the same self-contained verification request and the specific gaps named.

   Do not accept "I checked the major elements" or "the rest match by inspection" as substitutes for filled rows.

7. **If UI/UX returns findings**, route through `verification-fix-loops.md` -> `## UI/UX finding loop`. UI/UX findings dispatch a fresh lightweight implementer subagent with a compact visual/accessibility finding packet, then UI/UX reruns scoped to affected rows/states. Do not rerun QA or any code-review phase for visual-only UI/UX fixes.

8. **When QA is clean, UI/UX is clean or skipped, and inventory validation passes if UI/UX ran**, advance to Ship.

## Ship

0. **Ship preflight — mandatory before any Ship mutation.** Before opening a PR, marking a PR ready, moving a ticket to review, merging, closing, or otherwise signaling "ready," build a readiness ledger from actual completed outputs:
   - Approved requirements/design artifact.
   - Approved implementation plan.
   - Implementation finished with required tests/checks for the plan.
   - QA clean report present.
   - UI/UX clean report and inventory validation present, or skipped with backend-only rationale.
   - No unresolved QA or UI/UX findings.

   If any ledger row is missing, do not perform any Ship action. Return to the earliest missing gate and complete it first. Local verification, green CI, clean merge state, manual browser checks, or local review do not satisfy missing verification outputs.

1. **Personal workflow:** after Ship preflight passes, open the PR with `gh`, then move the Linear ticket to **In Review** per `personal-workflow.md`. Do not merge or close.
2. **Job workflow:** after Ship preflight passes, follow the team's PR conventions from repository instructions.
   - If the repository uses Bitbucket PRs and the work requires reading PR metadata, reading or posting comments, or merging via the REST API, treat that portion as Bitbucket PR REST work.
3. Wait for the user's explicit approval before merging.
4. **Personal workflow:** after merge, move the Linear ticket to its completed state per `personal-workflow.md`.
5. **Job workflow:** after merge, follow the team's post-merge convention if specified in repo instructions; otherwise stop and surface what remains manual.
6. If PR creation, ticket transition, merge, or any Ship step cannot be completed, say exactly what failed and what remains manual.

## Verification fix loops

When QA or UI/UX returns findings, use `verification-fix-loops.md`. That file defines the two local find -> fix -> verify loops, fresh lightweight implementer dispatch, compact finding packets, iteration caps, and user-intervention conditions.

## Briefing rule

When the workflow dispatches a subagent and then asks the user for input, decision, or choice, the user must enter the dialogue with the same context the subagent had. Brief in a single message before the first question.

| Trigger | Brief with |
|---|---|
| Scoping -> user (Setup clarify, or Requirements/Design opener) | Scoping's relevant findings: entry points, target module, prototype/reference elements if any, affected surfaces, and conflicts. For conflicts: quoted finding + `path:line` evidence. The question framed against that evidence. |
| QA/UIUX -> user intervention | Findings, one per line: severity, `path:line` or selector/state, one-line description. Suggested fix if available. The material decision or blocker that requires user input. |

**Forbidden:** asking the user to pick an option they haven't seen, answer a clarifying question without its motivating context, or approve a fix without naming the finding.

## Implementation standards

Smallest safe diff that satisfies the ticket. Preserve existing patterns; do not invent abstractions the ticket does not require. If the ticket is explicitly security-intensive, pause and use a dedicated security workflow instead of expanding `ticket-start`. Greenfield personal-project code with no inherited pattern: establish ownership boundaries and low coupling deliberately.

## Library research

If the change touches a third-party library, identify the exact version from manifests/lockfiles and read the official docs for that version before editing dependent code. Targeted searches only — do not load the whole library reference.

## Closeout report

When done, report:
- What changed.
- What was validated and how: tests/checks run, QA status, UI/UX review mode and coverage, UI/UX inventory validation, or UI/UX skipped because backend-only.
- Rules proposed or promoted in this session, by destination, if any.
- QA and UI/UX fix-loop iterations consumed.
- Any remaining risk, assumption, or follow-up.
- What is blocked or unverified, named explicitly.

## Red flags — stop and recover

- Working in the primary checkout instead of a fresh worktree.
- Basing the worktree on anything other than freshly fetched `origin/main` (including local `main`, the current branch, or a stale remote-tracking ref).
- Writing code before the requirements/design artifact and implementation plan are both approved.
- Treating requirements/design approval ("yes, do it" / "approved" / "go") as implementation-plan approval. They are separate artifacts.
- Exiting requirements/design on a single user answer, or treating an early implementation preference as the endpoint.
- The requirements/design artifact does not record at least one alternative considered when a meaningful alternative exists.
- Skipping requirements/design, written-plan, or task-by-task test-first implementation because "the ticket is clear" or "the change is small."
- Treating general host guidance against casual subagent spawning as a reason to skip this skill's mandatory subagent dispatches.
- Dispatching a separate ticket-start code-review subagent or adding a generic post-implementation code-review phase after Implement.
- Replacing QA or UI/UX with local tests, browser checks, Lighthouse, or prototype comparison. Local checks are evidence, not gate completion.
- Dispatching Scoping or UI/UX with vague prompts that omit the required work, evidence, and compact inputs.
- Trusting a stale ticket summary instead of re-reading from the source of truth.
- Loading `PRD.md` or `designs/` in full instead of scoped to the feature.
- Reloading full files when a Scoping locator points at the surgical slice.
- Continuing past a user-intervention condition without surfacing.
- Claiming frontend UI parity or consistency without DOM computed-style and bounding-rect extraction from the live browser.
- Accepting a UI/UX verdict whose matched-element inventory is missing, empty, has blank cells for in-scope rows, or restricts itself to "important" elements.
- Building the UI/UX matched-element inventory in the main agent instead of delegating inventory construction to UI/UX from Scoping's affected surface map.
- Dispatching UI/UX without the required review terms: implemented frontend UI, parity mode with runnable reference or consistency mode with production analogs, matched-element inventory, DOM computed styles, bounding rects, accessibility, and inventory construction from the affected surface map.
- Scoping's `## Prototype or reference elements` empty or `_None._` for a reference-backed UI ticket.
- Briefing the user with anything less than the subagent's synthesis before a dialogue, clarification, or fix-decision.
- Letting branch-finishing guidance present merge / PR / keep / discard options instead of returning to Verify.
- Starting any Ship mutation without first completing the Ship preflight ledger from actual outputs.
- Opening or marking a PR ready, moving the ticket to In Review, or otherwise entering Ship before QA, UI/UX if applicable, inventory validation, and unresolved verification findings are complete.
- Merging the PR before the user explicitly approves.

If any of these is true: stop, name the violation, and recover before continuing.
