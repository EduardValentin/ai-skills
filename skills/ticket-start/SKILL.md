---
name: ticket-start
description: Use when the user wants to start implementation work from a ticket — phrases like "start ticket", a pasted Jira ticket, or a Linear issue ID. Also use for follow-up status or progress questions about a ticket already in this workflow. Covers both job tickets (Jira/pasted; uses acli when available) and personal-project tickets (Linear with PRD.md and a designs/ React reference app). Do not use for code review, planning-only, or debugging-only tasks.
---

# Ticket Start

## Overview

Implementation work driven by a ticket. The skill is a **hybrid orchestrator**: the main agent owns user dialogue, plan-writing, and phase gating; six specialized subagents own the deep work (Scoping, Architect, Reviewer, Security, QA, UI/UX). The skill enforces a strict phase order with explicit gates: Setup → Solution Exploration → Brainstorm → Plan → Implement → Review → Security → Verify → Ship. Brainstorm, Plan, and Implement defer to the superpowers methodology — the relevant skills auto-trigger from their own descriptions; this skill adds explicit dispatch and override points where its workflow diverges. Workflow- and phase-specific detail files are loaded only when they apply, to keep context lean.

**Context-economy contract:** every subagent's report is a navigable index, not a transcript. Downstream agents read only the surgical slices upstream reports point at. Main agent never reloads full files when a Scoping locator suffices.

## When To Use

- The user asks to start, work on, build, or implement a ticket.
- The user pastes a Jira/job ticket and asks for implementation.
- The user gives a Linear ticket identifier in a personal project.
- Follow-up status/progress questions about a ticket already in this workflow.

**Do not use for:** code review, pure planning, debugging-only tasks, or refactors with no ticket.

## Workflow Selection (Decide First)

Choose one before reading any detail file:

- **Job workflow** — ticket comes from Jira or is pasted by the user. Load `job-workflow.md`.
- **Personal workflow** — ticket comes from Linear; project has `PRD.md` and a `designs/` reference app. Load `personal-workflow.md` (which loads `react-parity.md` when applicable).

If the workflow is ambiguous, ask the user before loading anything else.

## Phase Order (Hard Gates)

Each phase is a gate. Do not advance until the prior gate is satisfied. Each named sub-skill below is **REQUIRED** — invoke it, do not paraphrase its workflow.

```
Setup → Solution Exploration → Brainstorm → Plan → Implement → Review → Security → Verify → Ship
                                                                  │        │         │
                                                              Reviewer Security  QA → UI/UX
                                                                                (UI/UX skipped
                                                                                on backend-only)
```

1. **Setup** — see "Setup" below. Includes Scoping subagent dispatch and the pre-Architect understanding dialogue.
2. **Solution Exploration** — Architect subagent dispatch (with the pre-Architect brainstorm summary as input). See "Solution Exploration" below.
3. **Brainstorm** — user-facing convergence on Architect's proposals via a question-driven dialogue. See "Brainstorm" below.
4. **Plan** — `superpowers:writing-plans`. See "Plan" below.
5. **Implement** — execute via `superpowers:subagent-driven-development` (auto-triggers TDD + per-task review) or `superpowers:executing-plans` fallback. See "Implement" below.
6. **Review** — Reviewer subagent dispatch. See "Review" below.
7. **Security** — Security subagent dispatch (sequential after Reviewer). See "Security" below.
8. **Verify** — QA subagent dispatch, then UI/UX subagent dispatch (or UI/UX skipped on backend-only). See "Verify" below.
9. **Ship** — see "Ship" below.

After **every** auditor agent (Reviewer, Security, QA, UI/UX), the **self-improvement extraction pass** runs. See `self-improvement.md`.

If **any** auditor returns a non-clean verdict, the **bug-fix loop** runs. See `bug-fix-loop.md`.

## Setup

1. **Worktree discipline.** REQUIRED SUB-SKILL: `superpowers:using-git-worktrees`. Base the worktree off `origin/<default>` (not the local branch). Halt on `git fetch` failure — do not fall back to stale local state.

2. **Subagent context discipline.** When dispatching subagents, explicitly forward `AGENTS.md` and any workflow-relevant project docs as inputs — subagent context does not always inherit the main session's auto-loaded files, and explicit forwarding is the host-agnostic discipline.

3. **Freshness — treat memory as stale.** Memory, prior chat context, old plans, and earlier tool results are hints, not facts. Before any substantive answer about scope, status, blockers, related tickets, progress, PR readiness, or git state, fetch current facts from the source of truth:
   - **Linear tickets:** read the current ticket via Linear MCP. If blocked/blocking/related/duplicate/parent/child tickets matter, read each one too — do not infer from relation names or earlier context.
   - **Job/Jira tickets:** prefer `acli jira workitem view <KEY> --json` (per `job-workflow.md`); fall back to user paste if `acli` is unavailable. Stale summaries and previously pasted excerpts are not current truth.
   - **Repo state:** inspect the current branch, working tree, relevant diffs, recent commits, and PR metadata when relevant.
   - **Repo docs and code:** re-read from disk before citing or depending on them.
   - If a source of truth is unavailable, say what could not be verified. Do not fill the gap from memory.

4. **Workflow-specific reading.** Read the workflow file selected above. Stop when the relevant facts are gathered — do not push past the Brainstorm gate without them.

5. **Dispatch Scoping subagent.** Load the role prompt from `agents/scoping.md`. Invoke a subagent on the host platform's native subagent API with:
   - The ticket title, description, AC.
   - The repo's `AGENTS.md` and `CLAUDE.md`.
   - For personal workflow: the scoped slices of `PRD.md` and `designs/` identified above.
   - The role-prompt content from `agents/scoping.md` as the subagent's instruction set.
   Wait for the Scoping report (a Markdown document with locator-rich sections per the role-prompt's output format). Treat that report as the definitive map of the relevant code surface — do **not** re-read full files later when a Scoping locator points at the slice you need.

6. **Clarifications.** If acceptance criteria are missing, vague, or not testable, stop and ask before continuing. If the Scoping report surfaces a conflict between the ticket and existing architecture, surface the conflict before brainstorming. Ask concise clarifying questions when material ambiguity remains after Scoping. Before asking the user any clarifying question, brief per `## Dispatch → user briefing protocol` (handoff type 1: Scoping → user dialogue).

7. **Pre-Architect understanding.** Before the Architect proposes a direction, explore user intent, constraints, and design preferences not captured in the ticket. Pursue a question-driven dialogue with the user covering: implicit preferences ("how should this feel?"), constraints not in the AC ("are there areas of the code we should avoid?"), domain-specific intuitions, design-language preferences, and any unknowns the ticket leaves open. Cover whatever ground the Architect would benefit from before generating proposals.

   Brief per `## Dispatch → user briefing protocol` (handoff type 1: Scoping → user dialogue) before the first question — surface the Scoping report's relevant findings (entry points, target module, prototype elements if any) so the user has the same context the Architect will get.

   Capture the outcome as a short **brainstorm summary** that will be passed to the Architect as a new input in Solution Exploration. The summary covers the user's stated intent, the constraints they surfaced, and any preferences they expressed.

## Solution Exploration

1. **Dispatch Architect subagent.** Load the role prompt from `agents/architect.md`. Invoke a subagent with:
   - The ticket and AC.
   - The Scoping report.
   - The repo's `AGENTS.md` / `CLAUDE.md`.
   - The **pre-Architect brainstorm summary** from Setup step 7 (the user's stated intent, constraints, and preferences). Treat as authoritative on questions the ticket and AC don't cover.
   - The role-prompt content from `agents/architect.md`.
   Wait for the Architect's proposals (2–3 candidate solutions with tradeoffs, per the role-prompt's output format).

## Brainstorm

1. **Brief per `## Dispatch → user briefing protocol` (handoff type 2: Architect → Brainstorm dialogue), then explore the Architect's proposals with the user via a question-driven dialogue.** Brief BEFORE the first question — present the Architect's recommended approach + rationale, alternatives + tradeoffs, and any open questions with their motivating context, as a single message. Only after this synthesis is in the user's view, walk through the proposals with the user. Converge on a chosen direction.

2. **On-demand Architect re-dispatch.** If during the dialogue a follow-up architectural question arises that the original proposals didn't cover, re-dispatch the Architect with the focused question (per `agents/architect.md`'s follow-up handling). When you bring the re-dispatched Architect's answer back, brief the user on what the Architect found (recommended adjustment + rationale + any new tradeoffs) before continuing the dialogue.

3. **Convergence is not plan approval.** When the dialogue converges and the user says "yes, do it," "approved," "go ahead," or similar, that is approval of the *approach*. It is **not** approval of the plan. The plan still has to be written by `superpowers:writing-plans` and re-approved as its own artifact. Do not collapse the two.

## Plan

1. **`superpowers:writing-plans`.** Produce a written implementation plan from the brainstorm outcome. The plan is a distinct artifact produced by that sub-skill — not a verbal summary of the brainstorm, not the brainstorm transcript itself, and not a mental model in your head.

1a. **For parity-mode UI tickets** (personal workflow with a runnable React reference app under `designs/`), each plan task that adds or modifies a visible element includes an `**Element mapping:**` block in its body declaring (a) the prototype counterpart via reference to a `## Prototype elements relevant to this feature` row from the Scoping report, and (b) the planned production file:line for the new/changed JSX declaration. Tasks that don't add/modify visible elements (state management, route handlers, backend stubs, infrastructure) omit this block. Main agent uses these mappings at Verify dispatch (step 4a) to construct the expected matched-element inventory passed to UI/UX.

   Example block inside a plan task body:
   ```
   **Element mapping:**
   - Prototype: Scoping row `designs/components/Hero/Eyebrow.tsx:8` (`<span class="eyebrow">`)
   - Planned production: `web/src/components/Hero/Eyebrow.tsx:12` (new `<span class="eyebrow">`)
   ```

2. Show the plan to the user as `superpowers:writing-plans` directs. Wait for explicit user approval of the *plan itself* before writing any code.
3. **No code between brainstorm convergence and plan approval.** Not exploratory edits. Not scaffolding. Not "drafting what the plan would say in code." Not small or obvious changes. Not "let me just sketch the structure." File-edit capabilities are off-limits until the written plan exists and the user has explicitly approved it.

## Implement

1. **Personal workflow:** Move Linear ticket to `In Progress` immediately after plan approval, before any code (per `personal-workflow.md`).
2. Execute the approved plan using the superpowers methodology. The relevant skills (`superpowers:subagent-driven-development` for in-session work, `superpowers:executing-plans` for a parallel session, with `superpowers:test-driven-development` and per-task spec + code-quality review baked into the subagent-driven path) auto-trigger from their own descriptions; let them.
3. **Two overrides this skill adds:**
   - On the `superpowers:executing-plans` fallback path, this skill adds an explicit `superpowers:requesting-code-review` invocation after the final task and before advancing to the Review phase — that path has no other end-of-feature review.
   - When superpowers' flow reaches `superpowers:finishing-a-development-branch`, accept its test-pass check but do **not** present its 4-option prompt (merge locally / PR / keep / discard) to the user. Return control to ticket-start's Review phase. Ship replaces options 1–4 with the PR + ticket-transition flow defined below.

## Review

1. **Dispatch Reviewer subagent.** Load the role prompt from `agents/reviewer.md`. Invoke a subagent with:
   - The full diff (`git diff origin/<default>..HEAD`).
   - The ticket, AC, and approved plan.
   - The Architect proposals — specifically the recommended option that was chosen during brainstorm.
   - The repo's `AGENTS.md`.
   - The Scoping report.
   - The role-prompt content from `agents/reviewer.md`.
   Wait for the Reviewer report.

2. **If Reviewer returns CHANGES REQUIRED**, brief the user per `## Dispatch → user briefing protocol` (handoff types 3–6: auditor → fix decision) before routing through `bug-fix-loop.md`.

3. **When Reviewer returns CLEAN**, run the **self-improvement extraction pass** on Reviewer findings (see `self-improvement.md`). Then advance to Security.

## Security

1. **Dispatch Security subagent.** Load the role prompt from `agents/security.md`. Invoke a subagent with:
   - The full diff.
   - The ticket and AC.
   - Package manifests / lockfiles for dependency analysis.
   - The repo's `AGENTS.md`.
   - The Scoping and Reviewer reports (Reviewer's out-of-scope flags pointed at Security feed into this).
   - The role-prompt content from `agents/security.md`.
   Wait for the Security report.

2. **If Security returns CHANGES REQUIRED**, brief the user per `## Dispatch → user briefing protocol` (handoff types 3–6: auditor → fix decision) before routing through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **Reviewer + Security re-run on the full diff**.

3. **When Security returns CLEAN**, run the self-improvement extraction pass on Security findings. Then advance to Verify.

## Verify

1. **Determine backend-only flag.** Walk the diff:
   - List changed files: `git diff --name-only origin/<default>..HEAD`.
   - Match against UI extensions (`\.(tsx|jsx|vue|svelte|html|css|scss|sass|less|styl|ejs|pug|hbs|erb|twig|liquid|jinja|blade\.php)$`) and UI directories (`app/`, `components/`, `pages/`, `views/`, `templates/`, `client/`, `web/`, `frontend/`, `ui/`, plus repo-specific UI dirs identified by Scoping).
   - Any match → not backend-only.
   - No matches but uncertainty (config files affecting render, shared utilities used by both backend and UI) → ask the user.
   - Default on uncertainty: **do not skip** UI/UX (running it unnecessarily is cheap; skipping it incorrectly is expensive).

2. **Dispatch QA subagent.** Load the role prompt from `agents/qa.md`. Invoke a subagent with:
   - The ticket, AC, and approved plan.
   - The full diff.
   - The mode parameter: `backend` / `ui` / `mixed` per the diff (this is QA's mode, not the backend-only flag — even a mixed change runs QA in mixed mode).
   - The path/URL of the running app or service.
   - Live-browser automation (navigation, clicks, keyboard input, viewport control, DOM evaluation, element-level screenshots, tab control) for UI mode; HTTP tooling for backend mode. See `agents/qa.md` → `## Browser bootstrap` for the fallback chain when a native browser capability is missing.
   - The role-prompt content from `agents/qa.md`.
   Wait for the QA report.

3. **If QA returns BUGS FOUND**, brief the user per `## Dispatch → user briefing protocol` (handoff types 3–6: auditor → fix decision) before routing through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **QA re-runs the full behavior pass**.

4. **When QA returns CLEAN**, run the self-improvement extraction pass on QA findings.

4a. **In parity mode, construct the expected matched-element inventory before dispatching UI/UX.** Skip this step in consistency mode (UI/UX runs with no supplied inventory and discovers as today). Parity mode means personal workflow with a runnable React reference app under `designs/`.

   Combine:
   - The Scoping report's `## Prototype elements relevant to this feature` rows (prototype side).
   - Each plan task's `**Element mapping:**` block (the prototype↔production declaration).
   - Actual post-diff production file:lines, resolved by walking `git diff origin/<default>..HEAD --name-only` for touched UI files and locating each plan-declared JSX declaration in the post-diff state (e.g., `grep -n` on a stable selector like `class="..."` or `data-testid="..."` from the plan's element mapping).

   Produce a markdown table with one row per JSX declaration in scope. Column order matches the matched-element inventory in `agents/ui-ux.md` → `## Output format`:

   | Pair | Prototype selector | Production selector | font-* | color/bg | box | layout | size | verdict |

   For each row at dispatch:
   - `Pair` cell carries the prototype:line ↔ production:line locator pair (or `(none)` on the side where the element is deliberately one-sided per the plan).
   - `Prototype selector` and `Production selector` cells are filled with the JSX-derivable selector hint (component name, `data-testid`, or stable class).
   - `font-*` through `size` cells are **blank** — UI/UX fills these by running DOM evaluation on each row's rendered atoms.
   - `verdict` cell is **blank** — UI/UX sets it (MATCH / DRIFT / MISSING).

   If construction fails (Scoping's prototype-elements section can't be parsed, a plan task's element-mapping block can't be matched to a Scoping row, the production-side post-diff lookup returns nothing), halt with `cannot dispatch UI/UX in parity mode — expected inventory could not be constructed` and name the specific parsing or matching error. Do not fall back to discovery-mode UI/UX in parity mode.

5. **If backend-only flag is set: skip UI/UX. Otherwise, dispatch UI/UX subagent.** Load the role prompt from `agents/ui-ux.md`. Invoke a subagent with:
   - The ticket and approved plan.
   - The full diff.
   - The mode parameter: `parity` (personal workflow with React reference) or `consistency` (job workflow OR personal workflow without React reference).
   - For `parity`: paths/URLs to **both** the production app and the React reference app.
   - For `parity`: the **expected matched-element inventory** table constructed in step 4a. UI/UX's job in parity mode is to fill in the verdict and computed-style cells, not to discover the inventory from scratch.
   - For `consistency`: path/URL to the production app.
   - Live-browser automation (navigation, clicks, keyboard input, viewport control, DOM evaluation, element-level screenshots, tab control). See `agents/ui-ux.md` → `## Browser bootstrap` for the fallback chain when a native browser capability is missing.
   - The role-prompt content from `agents/ui-ux.md`.
   Wait for the UI/UX report.

6. **If UI/UX returns FINDINGS**, brief the user per `## Dispatch → user briefing protocol` (handoff types 3–6: auditor → fix decision) before routing through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **UI/UX re-runs scoped to affected states**.

6a. **Validate the UI/UX report's matched-element inventory before accepting any verdict.**

   The check differs by mode:

   **Parity mode (expected inventory was supplied at step 4a):** cross-check the verified inventory (returned by UI/UX) against the expected inventory (constructed at dispatch).
   - Every row in the expected inventory must appear in the verified inventory.
   - Every row in the verified inventory must have non-blank `font-*`, `color/bg`, `box`, `layout`, `size`, and `verdict` cells. Blank cells mean UI/UX skipped the DOM-evaluation work for that row.
   - Spot-check: sample 2 rows whose underlying file appears in the diff and 2 rows from the prototype enumeration. Each sampled row must be present in the verified inventory with non-blank cells.
   - Verdicts of `MISSING` (production side) are accepted **only** for rows where the plan deliberately marked the element as not implemented in this ticket; otherwise a `MISSING` verdict is a finding.
   - If any check fails, the report is **structurally invalid**. Reject and re-dispatch UI/UX with the specific gaps named (which rows are absent, which rows have blank cells).

   **Consistency mode (no expected inventory was supplied):** apply today's spot-check against the running production app and the diff.
   - Confirm the report has a `## Matched-element inventory` section.
   - From the diff, pick 2 changed UI files. List their rendered elements. Each one must appear in the inventory.
   - From the running production app, sample 3 visible elements on the feature surface. Each must appear in the inventory.
   - If any sample is not in the inventory, the report is **structurally invalid**. Reject and re-dispatch UI/UX with the specific missing elements named.

   In either mode, do not accept "I checked the major elements" or "the rest match by inspection" as substitutes for filled inventory rows.

7. **When UI/UX returns CLEAN** (or is skipped), and the inventory validation in step 6a has passed, run the self-improvement extraction pass on UI/UX findings (or skip the UI/UX pass if skipped). Advance to Ship.

## Ship

1. **Personal workflow:** open the PR with `gh`, then move the Linear ticket to `In Review` per the transitions in `personal-workflow.md`. Do not merge or close the ticket.
2. **Job workflow:** follow the team's PR conventions from repository instructions.
3. Wait for the user's explicit approval before merging.
4. **Personal workflow:** after merge, move the Linear ticket to its completed state per `personal-workflow.md`.
5. **Job workflow:** after merge, follow the team's post-merge ticket convention if specified in repository instructions; otherwise stop and surface what remains manual rather than guessing the destination state.
6. If PR creation, ticket transition, merge, or any Ship step cannot be completed, say exactly what failed and what remains manual.

## Bug-Fix Loop

When any auditor agent returns a non-clean verdict, route through `bug-fix-loop.md`. That file defines:
- Three-tier complexity classification (trivial / non-architectural / architectural).
- Per-agent re-review scope after a fix (full for Reviewer/Security/QA, scoped for UI/UX).
- 3-iteration cap with intervention report on exhaustion.
- Always-on user-intervention principle.
- Sequencing rules for re-runs.

## Self-Improvement Loop

After **each** auditor agent (Reviewer, Security, QA, UI/UX) returns a CLEAN report (or after a CHANGES-REQUIRED report becomes CLEAN through the bug-fix loop), run the rule-extraction pass per `self-improvement.md`. That file defines:
- Rule promotion bar (pattern-based, high-cost, declarative, non-stylistic, non-duplicate).
- Repo-specific vs universal classification.
- Destinations: repo `AGENTS.md` (separate commit, same PR) for repo-specific; both `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` (kept in sync) for universal.
- Mandatory user-approval gate per rule.

## Dispatch → user briefing protocol

Whenever the workflow dispatches a subagent and then asks the user for input, a decision, or a choice, main agent does NOT bring the user into the dialogue cold. Main agent first **briefs the user** with a synthesis of what the subagent surfaced.

The principle: **the user must enter the dialogue with the same context the subagent had.** Never ask the user to pick between options they haven't seen, answer a question whose backstory wasn't surfaced, or decide on a fix whose finding wasn't named.

A briefing is always presented as a single user-facing message (or short paragraph at the top of a longer one), BEFORE the first question / decision / choice is asked. The minimum required contents differ by handoff type.

### Handoff type 1 — Scoping → user clarification (Setup)

When Scoping returns with items under `## Conflicts surfaced for main` or with insufficient AC coverage and main agent needs the user to clarify:

- The specific conflict or ambiguity Scoping flagged, quoted from the report.
- The `path:line` evidence Scoping gave (so the user can drill in).
- The clarification main agent is asking for, framed against the surfaced conflict.

### Handoff type 2 — Architect → Brainstorm dialogue

When the Architect returns proposals and main agent runs `superpowers:brainstorming` with the user:

- The Architect's **recommended approach** + the Architect's rationale for recommending it.
- The **alternative approaches** considered, with the tradeoffs Architect captured.
- Any **open questions** the Architect surfaced for user input, each accompanied by the context that motivated the question (what code / constraint / design choice raised it).
- Pointers into the Scoping report for any locator references the Architect built on, so the user can drill in if they want to.

Only after this synthesis is in the user's view does the one-question-at-a-time brainstorming dialogue start.

### Handoff types 3–6 — Auditor (Reviewer / Security / QA / UI/UX) → fix decision

When an auditor returns CHANGES REQUIRED / BUGS FOUND / FINDINGS and the workflow routes through `bug-fix-loop.md`:

- The finding(s), one per line, with severity, location (`path:line` if known), and one-line description.
- The auditor's suggested fix (if any).
- The complexity tier the bug-fix loop assigned (trivial / non-architectural / architectural).
- For architectural complexity: the architectural tradeoff main agent sees, presented as options the user can weigh in on.

### Handoff type 7 — Bug-fix loop architectural intervention

Already structured around user input. Apply handoff types 3–6's briefing content (findings + suggested fix + tradeoff) before asking the user to decide on the architectural direction.

### Forbidden behaviors (briefing-specific)

- Asking the user to pick an option they haven't seen.
- Asking the user to answer a clarifying question without explaining what raised it.
- Asking the user to approve a fix without naming the finding.
- Routing through bug-fix-loop's architectural-intervention path without surfacing the architectural tradeoff to the user first.

## Implementation Standards

Apply for every change:

- Smallest safe diff that satisfies the ticket. Reuse existing patterns; do not invent abstractions the ticket does not require.
- Preserve or improve the repository's code quality; never degrade it to ship faster.
- Keep functions, modules, and components single-responsibility. Preserve existing architecture unless the ticket truly requires change.
- Apply clean-code principles to every change regardless of workflow. In greenfield personal projects with no established pattern to inherit, additionally establish clear ownership boundaries, low coupling, and composable modules deliberately rather than improvising.
- Consider performance on hot paths, repeated work, unnecessary rendering, and avoidable I/O.
- Consider security on every change. Pay attention to trust boundaries, authn/z, user-controlled input, data exposure, persistence, file handling, redirects, external requests, privileged actions, and sensitive logs. (The Security subagent audits formally; this standard is for the implementation pass.)
- Avoid common attack vectors: injection, XSS, CSRF, SSRF, IDOR, broken access control, open redirects, path traversal, unsafe deserialization, secret leakage, insecure dependencies, unsafe client-side trust.

## Library Research

If the change touches a third-party library, identify the exact version from manifests/lockfiles, then read the official or primary documentation for that version before editing dependent code. Use targeted searches; do not load the whole library reference.

## Report (Closeout)

When done, report:
- What changed.
- What was validated and how — name each form of evidence explicitly: tests run; Reviewer report status; Security report status; QA mode and coverage; UI/UX mode and coverage (or skipped because backend-only). Omit only the ones that did not apply, and say so.
- Rules promoted in this session, by destination (per `self-improvement.md`).
- Bug-fix iterations consumed (out of 3 cap).
- Any remaining risk, assumption, or follow-up.
- What is blocked or unverified, named explicitly.

## Red Flags — Stop And Recover

- Working in the primary checkout instead of a fresh worktree.
- Basing the worktree on a local branch instead of fetched `origin/<default>`.
- Skipping `superpowers:brainstorming` because "the ticket is clear".
- Writing code before the plan is approved.
- Treating design approval at the end of `superpowers:brainstorming` ("yes, do it" / "approved" / "go") as plan approval. They are separate artifacts; the plan still has to exist and be approved on its own.
- Skipping `superpowers:writing-plans` because "the path is obvious," "the change is small," "the brainstorm covered it," or "I'll write the plan after."
- Writing exploratory code, scaffolding, or "sketching the structure" between brainstorm convergence and plan approval.
- Trusting a stale ticket summary instead of re-reading from the source of truth (acli or Linear MCP).
- Loading `PRD.md` or `designs/` in full instead of scoped to the feature.
- Reloading full files when a Scoping locator points at the surgical slice. The Scoping report exists so this doesn't happen.
- Running QA / UI/UX without dispatching the corresponding subagent (paraphrasing the protocol from memory instead).
- Skipping the Security phase or merging it into Reviewer's pass.
- Skipping the self-improvement extraction pass after an auditor report.
- Auto-applying any rule (repo or universal) without explicit user approval.
- Editing `~/.claude/CLAUDE.md` or `~/.codex/AGENTS.md` without keeping them in sync.
- Exceeding the 3-iteration bug-fix cap silently instead of producing the intervention report.
- Continuing past a user-intervention condition without stopping and surfacing.
- Claiming visual parity / consistency without DOM computed-style and bounding-rect extraction from the live browser.
- Accepting a UI/UX `CLEAN` verdict (or any verdict) whose Matched-element inventory section is missing, empty, or missing rows for elements visibly present on the feature surface.
- UI/UX subagent restricting the inventory to "important" elements instead of every visible element in the feature surface.
- Main agent dispatching UI/UX in parity mode without supplying the expected matched-element inventory constructed in step 4a.
- Scoping report's `## Prototype elements relevant to this feature` section is empty or `_None._` for a parity-mode UI ticket — surface this at Setup, do not proceed to Brainstorm.
- UI/UX returns a verified inventory with rows that have blank `font-*`, `color/bg`, `box`, `layout`, `size`, or `verdict` cells. The DOM-evaluation work was skipped for those rows; reject the verdict at step 6a.
- Starting a brainstorming dialogue, a clarification question, or a fix-decision request to the user without first presenting the relevant subagent's synthesis (per `## Dispatch → user briefing protocol`). The user must enter the conversation with the same context the subagent had.
- Routing an auditor's findings through bug-fix-loop's architectural-intervention path without surfacing the architectural tradeoff to the user.
- Using the `superpowers:executing-plans` fallback path and skipping `superpowers:requesting-code-review` before advancing to Review — that path has no other end-of-feature review.
- Letting `superpowers:finishing-a-development-branch` present its 4-option prompt to the user instead of returning to this skill's Review phase.
- Merging the PR before the user explicitly approves.

If any of these is true: stop, name the violation, and recover before continuing.
