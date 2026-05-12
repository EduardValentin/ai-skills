---
name: ticket-start
description: Use when the user wants to start implementation work from a ticket — phrases like "start ticket", a pasted Jira ticket, or a Linear issue ID. Also use for follow-up status or progress questions about a ticket already in this workflow. Covers both job tickets (Jira/pasted; uses acli when available) and personal-project tickets (Linear with PRD.md and a designs/ React reference app). Do not use for code review, planning-only, or debugging-only tasks.
---

# Ticket Start

## Overview

Implementation work driven by a ticket. The skill is a **hybrid orchestrator**: the main agent owns user dialogue, plan-writing, and phase gating; six specialized subagents own the deep work (Scoping, Architect, Reviewer, Security, QA, UI/UX). The skill enforces a strict phase order with explicit gates: Setup → Brainstorm → Plan → Implement → Review → Security → Verify → Ship. Brainstorm, Plan, and Implement defer to the superpowers methodology — the relevant skills auto-trigger from their own descriptions; this skill adds explicit dispatch and override points where its workflow diverges. Workflow- and phase-specific detail files are loaded only when they apply, to keep context lean.

**Context-economy contract:** every subagent's report is a navigable index, not a transcript. Downstream agents read only the surgical slices upstream reports point at. Main agent never reloads full files when a Scoping locator suffices.

## When To Use

- The user asks to start, work on, build, or implement a ticket.
- The user pastes a Jira/job ticket and asks for implementation.
- The user gives a Linear ticket identifier in a personal project.
- Follow-up status/progress questions about a ticket already in this workflow.

**Do not use for:** code review, pure planning, debugging-only tasks, or refactors with no ticket.

## Workflow Selection (Decide First)

Choose one before reading any detail file:

- **Job workflow** — ticket comes from Jira or is pasted by the user. Read `job-workflow.md`.
- **Personal workflow** — ticket comes from Linear; project has `PRD.md` and a `designs/` reference app. Read `personal-workflow.md` (which loads `react-parity.md` when applicable).

If the workflow is ambiguous, ask the user before loading anything else.

## Phase Order (Hard Gates)

Each phase is a gate. Do not advance until the prior gate is satisfied. Each named sub-skill below is **REQUIRED** — invoke it, do not paraphrase its workflow.

```
Setup → Brainstorm → Plan → Implement → Review → Security → Verify → Ship
                                            │        │         │
                                        Reviewer Security  QA → UI/UX
                                                          (UI/UX skipped
                                                          on backend-only)
```

1. **Setup** — see "Setup" below. Includes Scoping subagent dispatch.
2. **Brainstorm** — Architect subagent dispatch, then `superpowers:brainstorming`. See "Brainstorm" below.
3. **Plan** — `superpowers:writing-plans`. See "Plan" below.
4. **Implement** — execute via `superpowers:subagent-driven-development` (auto-triggers TDD + per-task review) or `superpowers:executing-plans` fallback. See "Implement" below.
5. **Review** — Reviewer subagent dispatch. See "Review" below.
6. **Security** — Security subagent dispatch (sequential after Reviewer). See "Security" below.
7. **Verify** — QA subagent dispatch, then UI/UX subagent dispatch (or UI/UX skipped on backend-only). See "Verify" below.
8. **Ship** — see "Ship" below.

After **every** auditor agent (Reviewer, Security, QA, UI/UX), the **self-improvement extraction pass** runs. See `self-improvement.md`.

If **any** auditor returns a non-clean verdict, the **bug-fix loop** runs. See `bug-fix-loop.md`.

## Setup

1. **Worktree first.** Before reading the ticket body, before exploring code, create an isolated worktree from the freshest remote default branch. Do not work in the primary checkout. Identifying which workflow applies (Job vs Personal) requires only knowing the ticket's source system, not its contents — that minimal awareness is allowed before the worktree is in place.
   - Detect the upstream default branch (`main` or `master`).
   - `git fetch origin` to refresh remotes.
   - Base the new worktree off `origin/<default>`, not the local branch.
   - **REQUIRED SUB-SKILL:** `superpowers:using-git-worktrees` for the exact procedure and safety checks.
   - If `git fetch` fails, surface the blocker and stop. Do not silently fall back to a stale local branch.

2. **Repository instructions.** Inside the worktree, read the nearest applicable `AGENTS.md` first, then load only the additional instruction files and project docs that materially affect the task.

3. **Freshness — treat memory as stale.** Memory, prior chat context, old plans, and earlier tool results are hints, not facts. Before any substantive answer about scope, status, blockers, related tickets, progress, PR readiness, or git state, fetch current facts from the source of truth:
   - **Linear tickets:** read the current ticket via Linear MCP. If blocked/blocking/related/duplicate/parent/child tickets matter, read each one too — do not infer from relation names or earlier context.
   - **Job/Jira tickets:** prefer `acli jira workitem view <KEY> --json` (per `job-workflow.md`); fall back to user paste if `acli` is unavailable. Stale summaries and previously pasted excerpts are not current truth.
   - **Repo state:** inspect the current branch, working tree, relevant diffs, recent commits, and PR metadata when relevant.
   - **Repo docs and code:** re-read from disk before citing or depending on them.
   - If a source of truth is unavailable, say what could not be verified. Do not fill the gap from memory.

4. **Workflow-specific reading.** Read the workflow file selected above. Stop when the relevant facts are gathered — do not push past the Brainstorm gate without them.

5. **Dispatch Scoping subagent.** Read `agents/scoping.md` for the role prompt. Invoke a subagent on the host platform's native subagent API with:
   - The ticket title, description, AC.
   - The repo's `AGENTS.md` and `CLAUDE.md`.
   - For personal workflow: the scoped slices of `PRD.md` and `designs/` identified above.
   - The role-prompt content from `agents/scoping.md` as the subagent's instruction set.
   Wait for the Scoping report (a Markdown document with locator-rich sections per the role-prompt's output format). Treat that report as the definitive map of the relevant code surface — do **not** re-read full files later when a Scoping locator points at the slice you need.

6. **Clarifications.** If acceptance criteria are missing, vague, or not testable, stop and ask before continuing. If the Scoping report surfaces a conflict between the ticket and existing architecture, surface the conflict before brainstorming. Ask concise clarifying questions when material ambiguity remains after Scoping.

## Brainstorm

1. **Dispatch Architect subagent.** Read `agents/architect.md` for the role prompt. Invoke a subagent with:
   - The ticket and AC.
   - The Scoping report.
   - The repo's `AGENTS.md` / `CLAUDE.md`.
   - The role-prompt content from `agents/architect.md`.
   Wait for the Architect's proposals (2–3 candidate solutions with tradeoffs, per the role-prompt's output format).

2. **Run `superpowers:brainstorming` with the user.** Use the Architect's proposals as the starting material. Standard one-question-at-a-time dialogue. Converge on a chosen direction.

3. **On-demand re-dispatch.** If a follow-up architectural question arises mid-brainstorm that the original proposals didn't cover, re-dispatch the Architect with the focused question (per `agents/architect.md`'s follow-up handling) and bring the answer back into the conversation.

4. **Convergence is not plan approval.** When the brainstorm converges and the user says "yes, do it," "approved," "go ahead," or similar, that is approval of the *approach*. It is **not** approval of the plan. The plan still has to be written by `superpowers:writing-plans` and re-approved as its own artifact. Do not collapse the two.

## Plan

1. **`superpowers:writing-plans`.** Produce a written implementation plan from the brainstorm outcome. The plan is a distinct artifact produced by that sub-skill — not a verbal summary of the brainstorm, not the brainstorm transcript itself, and not a mental model in your head.
2. Show the plan to the user as `superpowers:writing-plans` directs. Wait for explicit user approval of the *plan itself* before writing any code.
3. **No code between brainstorm convergence and plan approval.** Not exploratory edits. Not scaffolding. Not "drafting what the plan would say in code." Not small or obvious changes. Not "let me just sketch the structure." Edit tools are off-limits until the written plan exists and the user has explicitly approved it.

## Implement

1. **Personal workflow:** Move Linear ticket to `In Progress` immediately after plan approval, before any code (per `personal-workflow.md`).
2. Execute the approved plan using the superpowers methodology. The relevant skills (`superpowers:subagent-driven-development` for in-session work, `superpowers:executing-plans` for a parallel session, with `superpowers:test-driven-development` and per-task spec + code-quality review baked into the subagent-driven path) auto-trigger from their own descriptions; let them.
3. **Two overrides this skill adds:**
   - On the `superpowers:executing-plans` fallback path, this skill adds an explicit `superpowers:requesting-code-review` invocation after the final task and before advancing to the Review phase — that path has no other end-of-feature review.
   - When superpowers' flow reaches `superpowers:finishing-a-development-branch`, accept its test-pass check but do **not** present its 4-option prompt (merge locally / PR / keep / discard) to the user. Return control to ticket-start's Review phase. Ship replaces options 1–4 with the PR + ticket-transition flow defined below.

## Review

1. **Dispatch Reviewer subagent.** Read `agents/reviewer.md` for the role prompt. Invoke a subagent with:
   - The full diff (`git diff origin/<default>..HEAD`).
   - The ticket, AC, and approved plan.
   - The Architect proposals — specifically the recommended option that was chosen during brainstorm.
   - The repo's `AGENTS.md`.
   - The Scoping report.
   - The role-prompt content from `agents/reviewer.md`.
   Wait for the Reviewer report.

2. **If Reviewer returns CHANGES REQUIRED**, route through `bug-fix-loop.md`.

3. **When Reviewer returns CLEAN**, run the **self-improvement extraction pass** on Reviewer findings (see `self-improvement.md`). Then advance to Security.

## Security

1. **Dispatch Security subagent.** Read `agents/security.md` for the role prompt. Invoke a subagent with:
   - The full diff.
   - The ticket and AC.
   - Package manifests / lockfiles for dependency analysis.
   - The repo's `AGENTS.md`.
   - The Scoping and Reviewer reports (Reviewer's out-of-scope flags pointed at Security feed into this).
   - The role-prompt content from `agents/security.md`.
   Wait for the Security report.

2. **If Security returns CHANGES REQUIRED**, route through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **Reviewer + Security re-run on the full diff**.

3. **When Security returns CLEAN**, run the self-improvement extraction pass on Security findings. Then advance to Verify.

## Verify

1. **Determine backend-only flag.** Walk the diff:
   - List changed files: `git diff --name-only origin/<default>..HEAD`.
   - Match against UI extensions (`\.(tsx|jsx|vue|svelte|html|css|scss|sass|less|styl|ejs|pug|hbs|erb|twig|liquid|jinja|blade\.php)$`) and UI directories (`app/`, `components/`, `pages/`, `views/`, `templates/`, `client/`, `web/`, `frontend/`, `ui/`, plus repo-specific UI dirs identified by Scoping).
   - Any match → not backend-only.
   - No matches but uncertainty (config files affecting render, shared utilities used by both backend and UI) → ask the user.
   - Default on uncertainty: **do not skip** UI/UX (running it unnecessarily is cheap; skipping it incorrectly is expensive).

2. **Dispatch QA subagent.** Read `agents/qa.md` for the role prompt. Invoke a subagent with:
   - The ticket, AC, and approved plan.
   - The full diff.
   - The mode parameter: `backend` / `ui` / `mixed` per the diff (this is QA's mode, not the backend-only flag — even a mixed change runs QA in mixed mode).
   - The path/URL of the running app or service.
   - Browser tooling (Playwright MCP) for UI mode; HTTP tooling for backend mode.
   - The role-prompt content from `agents/qa.md`.
   Wait for the QA report.

3. **If QA returns BUGS FOUND**, route through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **QA re-runs the full behavior pass**.

4. **When QA returns CLEAN**, run the self-improvement extraction pass on QA findings.

5. **If backend-only flag is set: skip UI/UX. Otherwise, dispatch UI/UX subagent.** Read `agents/ui-ux.md` for the role prompt. Invoke a subagent with:
   - The ticket and approved plan.
   - The full diff.
   - The mode parameter: `parity` (personal workflow with React reference) or `consistency` (job workflow OR personal workflow without React reference).
   - For `parity`: paths/URLs to **both** the production app and the React reference app.
   - For `consistency`: path/URL to the production app.
   - Browser tooling (Playwright MCP).
   - The role-prompt content from `agents/ui-ux.md`.
   Wait for the UI/UX report.

6. **If UI/UX returns FINDINGS**, route through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **UI/UX re-runs scoped to affected states**.

7. **When UI/UX returns CLEAN** (or is skipped), run the self-improvement extraction pass on UI/UX findings (or skip the UI/UX pass if skipped). Advance to Ship.

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
- Claiming visual parity / consistency without `browser_evaluate` extraction.
- Using the `superpowers:executing-plans` fallback path and skipping `superpowers:requesting-code-review` before advancing to Review — that path has no other end-of-feature review.
- Letting `superpowers:finishing-a-development-branch` present its 4-option prompt to the user instead of returning to this skill's Review phase.
- Merging the PR before the user explicitly approves.

If any of these is true: stop, name the violation, and recover before continuing.
