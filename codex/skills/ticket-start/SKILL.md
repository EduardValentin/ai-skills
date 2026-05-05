---
name: ticket-start
description: Use when the user wants to start implementation work from a ticket — phrases like "start ticket", a pasted Jira ticket, or a Linear issue ID. Also use for follow-up status or progress questions about a ticket already in this workflow. Covers both job tickets (Jira/pasted) and personal-project tickets (Linear with PRD.md and a designs/ React reference app). Do not use for code review, planning-only, or debugging-only tasks.
---

# Ticket Start

## Overview

Implementation work driven by a ticket. The skill enforces a strict phase order: setup → brainstorm → plan → implement → verify → ship. Brainstorm, Plan, and Implement defer to the superpowers methodology — the relevant skills auto-trigger from their own descriptions; ticket-start only adds explicit overrides where its workflow diverges. Workflow- and phase-specific detail files are loaded only when they apply, to keep context lean.

## When To Use

- The user asks to start, work on, build, or implement a ticket.
- The user pastes a Jira/job ticket and asks for implementation.
- The user gives a Linear ticket identifier in a personal project.
- Follow-up status/progress questions about a ticket already in this workflow.

**Do not use for:** code review, pure planning, debugging-only tasks, or refactors with no ticket.

## Workflow Selection (Decide First)

Choose one before reading any detail file:

- **Job workflow** — ticket comes from Jira or is pasted by the user. Read `job-workflow.md`.
- **Personal workflow** — ticket comes from Linear; project has `PRD.md` and a `designs/` reference app. Read `personal-workflow.md`. Also read `react-parity.md` if `designs/` is a runnable React app.

If the workflow is ambiguous, ask the user before loading anything else.

## Phase Order (Hard Gates)

Each phase is a gate. Do not advance until the prior gate is satisfied. Each named sub-skill below is **REQUIRED** — invoke it, do not paraphrase its workflow.

1. **Setup** — see "Setup" below.
2. **Brainstorm** — `superpowers:brainstorming`. Converge on a solution with the user. Do not draft a plan until the brainstorm has converged or the remaining decisions are explicitly called out for user approval. **When the brainstorm converges, the next required action is Phase 3 (Plan), not implementation.** A "yes, do it" at the end of the brainstorm authorizes you to write the plan, not to write code.
3. **Plan** — `superpowers:writing-plans`. Produce a written implementation plan from the brainstorm outcome. The plan is a distinct artifact produced by that sub-skill — not a verbal summary of the brainstorm, not the brainstorm transcript itself, and not a mental model in your head. Show the plan to the user as `superpowers:writing-plans` directs. Wait for explicit user approval of the *plan itself* before writing any code.

   **Design approval is not plan approval.** When the brainstorm converges and the user says "yes, do it," "approved," "go ahead," or similar, that is approval of the *approach*. It is not approval of the plan. The plan still has to be written by `superpowers:writing-plans` and re-approved as its own artifact. Do not collapse the two.

   **No code between brainstorm convergence and plan approval.** Not exploratory edits. Not scaffolding. Not "drafting what the plan would say in code." Not small or obvious changes. Not "let me just sketch the structure." If you have started writing code without an approved written plan from `superpowers:writing-plans`, you are in the Recovery protocol below — go there immediately.
4. **Implement** — execute the approved plan using the superpowers methodology. The relevant skills (`superpowers:subagent-driven-development` for in-session work, `superpowers:executing-plans` for a parallel session, with `superpowers:test-driven-development` and per-task spec + code-quality review baked into the subagent-driven path) auto-trigger from their own descriptions; let them. Two overrides this skill adds:
   - On the `superpowers:executing-plans` fallback path, explicitly invoke `superpowers:requesting-code-review` after the final task and before advancing to Verify — that path has no other end-of-feature review.
   - When superpowers' flow reaches `superpowers:finishing-a-development-branch`, accept its test-pass check but do not present its 4-option prompt (merge locally / PR / keep / discard) to the user. Return to ticket-start's Verify phase instead. Ship replaces options 1–4 with the PR + Linear-transition flow defined below.
5. **Verify** — see "Verify" below.
6. **Ship** — see "Ship" below.

## Setup (Always)

1. **Worktree first.** Before reading the ticket body, before exploring code, create an isolated worktree from the freshest remote default branch. Do not work in the primary checkout. Identifying which workflow applies (Job vs Personal) requires only knowing the ticket's source system, not its contents — that minimal awareness is allowed before the worktree is in place.
   - Detect the upstream default branch (`main` or `master`).
   - `git fetch origin` to refresh remotes.
   - Base the new worktree off `origin/<default>`, not the local branch.
   - **REQUIRED SUB-SKILL:** `superpowers:using-git-worktrees` for the exact procedure and safety checks.
   - If `git fetch` fails, surface the blocker and stop. Do not silently fall back to a stale local branch.

2. **Repository instructions.** Inside the worktree, read the nearest applicable `AGENTS.md` first, then load only the additional instruction files and project docs that materially affect the task.

3. **Freshness — treat memory as stale.** Memory, prior chat context, old plans, and earlier tool results are hints, not facts. Before any substantive answer about scope, status, blockers, related tickets, progress, PR readiness, or git state, fetch current facts from the source of truth:
   - **Linear tickets:** read the current ticket via Linear MCP. If blocked/blocking/related/duplicate/parent/child tickets matter, read each one too — do not infer from relation names or earlier context.
   - **Job/Jira tickets:** require the current full ticket content from the user. Stale summaries and previously pasted excerpts are not current truth.
   - **Repo state:** inspect the current branch, working tree, relevant diffs, recent commits, and PR metadata when relevant.
   - **Repo docs and code:** re-read from disk before citing or depending on them.
   - If a source of truth is unavailable, say what could not be verified. Do not fill the gap from memory.

4. **Workflow-specific reading.** Read the workflow file selected above. Stop when the relevant facts are gathered — do not push past the Brainstorm gate without them.

## Implementation Standards

Apply for every change:

- Smallest safe diff that satisfies the ticket. Reuse existing patterns; do not invent abstractions the ticket does not require.
- Preserve or improve the repository's code quality; never degrade it to ship faster.
- Keep functions, modules, and components single-responsibility. Preserve existing architecture unless the ticket truly requires change.
- Apply clean-code principles to every change regardless of workflow. In greenfield personal projects with no established pattern to inherit, additionally establish clear ownership boundaries, low coupling, and composable modules deliberately rather than improvising.
- Consider performance on hot paths, repeated work, unnecessary rendering, and avoidable I/O.
- Consider security on every change. Pay attention to trust boundaries, authn/z, user-controlled input, data exposure, persistence, file handling, redirects, external requests, privileged actions, and sensitive logs.
- Avoid common attack vectors: injection, XSS, CSRF, SSRF, IDOR, broken access control, open redirects, path traversal, unsafe deserialization, secret leakage, insecure dependencies, unsafe client-side trust.
- If secure behavior is ambiguous, surface the risk during planning and add targeted validation.

## Library Research

If the change touches a third-party library, identify the exact version from manifests/lockfiles, then read the official or primary documentation for that version before editing dependent code. Use targeted searches; do not load the whole library reference.

## Verify

1. Run the smallest meaningful validation set: targeted tests (including the tests written during Implement) first, then broader lint/test suites as appropriate. **All tests must pass** before continuing.
2. **Manual feature verification is required in every workflow.** Tests prove code correctness, not feature correctness — the implemented feature must be exercised against a running build before the work is called done.
   - **Personal workflow with a React reference app:** run the procedure in `verification.md`. Do not advance to Ship until both the visual parity pass and the behavior pass are clean.
   - **Job workflow:** run the Verification procedure in `job-workflow.md`. For backend/API/service changes, start the service and issue real requests against the changed surfaces. For user-facing changes, start the app on its dev server and exercise the feature in the live Playwright browser session. For mixed changes, do both. If the app or service cannot be started, stop and report the blocker — do not claim verification was completed.
3. **REQUIRED SUB-SKILL:** `superpowers:verification-before-completion` is the gate that governs every claim made about this work. Steps 1 and 2 produce the evidence VBC requires; do not assert the work is done until both are clean and the evidence has actually been gathered in this session — not recalled, not assumed, not extrapolated.

## Ship

1. **Personal workflow:** open the PR with `gh`, then move the Linear ticket to `In Review` per the transitions in `personal-workflow.md`. Do not merge or close the ticket.
2. **Job workflow:** follow the team's PR conventions from repository instructions.
3. Wait for the user's explicit approval before merging.
4. **Personal workflow:** after merge, move the Linear ticket to its completed state per `personal-workflow.md`.
5. **Job workflow:** after merge, follow the team's post-merge ticket convention if specified in repository instructions; otherwise stop and surface what remains manual rather than guessing the destination state.
6. If PR creation, ticket transition, merge, or any Ship step cannot be completed, say exactly what failed and what remains manual.

## Report

When done, report:
- What changed.
- What was validated and how — name each form of evidence explicitly: tests run, API verification (job, backend), browser verification (job, user-facing), visual parity pass and behavior pass (personal with React reference app). Omit only the ones that did not apply, and say so.
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
- Recovering from a skipped Plan gate with a softening "housekeeping note," "quick housekeeping," or "I got slightly ahead" instead of explicitly naming the violated gate, stopping, and following the Recovery protocol.
- Trusting a stale ticket summary instead of re-reading from the source of truth.
- Loading `PRD.md` or `designs/` in full instead of scoped to the feature.
- Claiming visual parity without running both apps in the browser.
- Claiming behavior is verified without exercising every relevant state and scenario.
- Declaring the feature done off the strength of unit/lint passing — the running app or service was never exercised end-to-end.
- Job workflow, backend change: declaring done without issuing real requests against the running service.
- Job workflow, user-facing change: declaring done without driving the feature in the live browser session.
- Using the `superpowers:executing-plans` fallback path and skipping `superpowers:requesting-code-review` before advancing to Verify — that path has no other end-of-feature review.
- Letting `superpowers:finishing-a-development-branch` present its 4-option prompt to the user instead of returning to this skill's Verify phase.
- Merging the PR before the user explicitly approves.

If any of these is true: stop, name the violation, and recover before continuing.

## Recovery — Skipped Phase Gate

If you discover that a phase gate was crossed — typical case: you started coding before the Plan was approved — do not paper over it. The honest recovery is the recovery.

1. **Stop immediately.** Do not finish the current file, do not "round out" the change, do not commit, do not push. Stopping mid-edit is correct.
2. **Name the violation explicitly to the user, in their words.** Example: "I skipped the Plan gate. I implemented after the brainstorm without writing a `superpowers:writing-plans` plan and getting your approval on it." Do not soften this into "housekeeping," "quick note," "I got slightly ahead," or "minor process detour" — those phrases are the rationalization, not the recovery. The user needs to know exactly which gate was skipped and why it matters.
3. **Decide with the user how to recover.** Two options, no third:
   - **Roll back** the uncommitted code if it was exploratory; then produce the plan from scratch via `superpowers:writing-plans`.
   - **Pause** and produce a plan via `superpowers:writing-plans` covering both what is already written and what remains. Mark the already-written portion explicitly in the plan so the user can see what they are retroactively approving.
4. **Resume only after explicit plan approval.** Do not continue under the assumption that "the design was already approved" — that assumption is the violation that got you here. The user must approve the *plan*, not the *recovery narrative*.

Skipped gates are recoverable. Pretending they did not happen is not. A clean acknowledgment of a skipped gate is more trustworthy than a smooth report of a clean run.
