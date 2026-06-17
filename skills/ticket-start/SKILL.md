---
name: ticket-start
description: Use when the user asks to start, work on, build, or implement one standalone Jira or Linear ticket, not an Epic, parent-with-children scope, or ticket set. Also use for progress/status on a ticket already being handled by this workflow. Covers job and personal-project tickets through MCP or REST API fallback. Do not use for multi-ticket workflow intake, code review, planning-only, QA-only, PR verification, PR summary, debugging-only, or ticket lookup tasks.
---

# Ticket Start
## Purpose

Use this skill as the main-agent workflow for working one implementation ticket from intake to final report. The main agent stays the user-facing orchestrator: it gathers ticket facts, brainstorms requirements/design with the user, gets approval, routes execution and verification work, reconciles returned reports, and keeps the user informed.

Prefer delegated work for implementation, independent review, QA verification, UI/UX verification, focused fixes, and PR verification. Use reusable native agents when available: `code-mapper` for codebase scoping, `implementation-worker` for implementation, `code-reviewer` for independent implementation review, `security-reviewer` for security review, `qa-verifier` for behavior verification, and `uiux-verifier` for visual/accessibility verification. QA verification is mandatory for every implementation with executable behavior: backend-only, job-only, event-model, script, and integration changes still route through `qa-verifier`; automated checks and reviewer/security approval never satisfy QA. If required delegated capability is unavailable, tell the user before replacing it with inline work.

If the runtime exposes a delegated/native-agent capability but its tool policy blocks use until the user explicitly asks for subagents or delegation, treat that delegated capability as unavailable for the current phase. Stop and ask for the needed authorization, or report the blocker. Do not continue with inline scoping, implementation, review, QA, UI/UX verification, or PR readiness as a silent substitute.

A personal project uses GitHub for code versioning and Linear for ticket tracking. A job project uses Bitbucket for code versioning and Jira for ticket tracking.

For UI-facing or mixed tickets, UI/UX verification depends on project type:
- Personal projects / Linear tickets: verify the production app matches the runnable reference app for the changed user-visible surfaces and every visually meaningful changed state.
- Job projects / Jira tickets: verify visual consistency with the rest of the application and similar existing elements, especially sizing, spacing, component usage, typography, state styling, and interaction patterns.

Full workflow summaries that mention UI/UX verification must preserve both project-type rules above, even when the current ticket only uses one of them.

## When To Use
- The user asks to start, work on, build, or implement one standalone ticket.
- The user gives one standalone Jira ticket or Linear issue ID as part of an implementation-work request.
- The user asks for progress or status on a ticket already being handled here.

Do not use for Epics, parent tickets with children requested as one scope, multi-ticket workflow intake, pure planning, debugging-only tasks, standalone code review, or refactors with no ticket.

## Core Rules
- Memory and prior chat are hints, not source of truth. Re-read the ticket, repo, branch, PR, and relevant docs before making substantive decisions.
- Use the ticket-system MCP first. If MCP is unavailable, use the ticket system's REST API.
- Start work in a fresh worktree based on fetched `origin/main`. Fetch first; do not base ticket work on local `main`, the current branch, or a stale ref.
- Treat "start working", "coding part only", "code it", branch instructions, branch clarification, and investigation permission as permission to begin this workflow, not permission to code.
- In every pre-approval response or workflow summary, explicitly state that branch choice, worktree setup, draft diff knowledge, investigation progress, internal status plans, checklists, update plans, and working notes are not approval of the spec/design or implementation plan.
- Before spec and plan approval, limit code-adjacent work to fact gathering, freshness/setup, and `code-mapper` delegated scoping. Do not validate draft changes, run implementation tests, recommend repairs, edit product/test files, or treat an existing draft worktree as approval.
- When responding to "start working", "coding part only", feature-branch directions, or similar pre-approval implementation language, explicitly block product-code edits and test edits in the main session before both approvals, then route to delegated scoping if needed and iterative requirements/design alignment with a visible open-questions ledger before spec/design approval.
- Keep the main session focused on orchestration and user decisions. Do not quietly turn it into the implementer, code reviewer, QA verifier, UI/UX verifier, security reviewer, or PR/ticket mutator.
- The scoping handoff is incomplete unless it states that the ticket-start request authorizes `code-mapper`, local main-session scoping is not a substitute, returned scoping evidence drives later brainstorming, and user questions are limited to unresolved unknowns.
- Branch choice, investigation progress, internal checklists, status plans, working notes, and update plans never replace explicit user approval of the written spec/design and implementation plan.
- Keep delegated requests self-contained: ticket facts, acceptance criteria, approved decisions, relevant repo instructions, scope locators, constraints, expected checks, PR expectations, and output expectations.
- Treat specialized-agent reports as compact evidence, not transcripts. Carry forward locators and summaries so later agents can read surgically.
- Full workflow summaries must not stop at intake, approval gates, or generic "delegated execution." Include this minimum checklist:
  - artifact and repo freshness: repo instructions, relevant PRD/design/reference slices, git state, branches, PRs, recent commits, fetched `origin/main`, and fresh worktree verification
  - delegated-context packet: ticket and acceptance criteria, parent context, approved decisions, approved plan, artifact slices, scope/codebase locators, branch state, constraints, expected checks, PR expectations, and output expectations
  - execution contract: the execution phase follows `coordinate-ticket-execution` while `ticket-start` remains the main current-session coordinator
  - named agents and order: `implementation-worker`, `code-reviewer`, `security-reviewer` or explicit skip, `qa-verifier`, `uiux-verifier` or explicit skip, aggregate findings, scoped fixes, affected reruns, PR creation or blocker, PR readiness verification, final handoff
  - verifier fallback: QA and UI/UX verifier requests must return `CANNOT_VERIFY` with reason and missing capability when they lack required tooling or access
  - PR readiness gate: not allowed while implementation, independent review, security review or skip, manual/runtime QA evidence, UI/UX or skip, scoped fixes, or necessary reruns are missing, unresolved, or not explicitly blocked/out of scope
  - UI/UX project rules: personal/Linear compares changed production UI against the runnable reference app; job/Jira checks visual consistency with the rest of the application and similar existing elements

## Step 1 - Gather Facts
1. Identify the ticket source and workflow type: job/Jira ticket or personal/Linear ticket.
2. Read the current ticket from the ticket-system MCP, or from the ticket system's REST API when MCP is unavailable. Capture title, description, acceptance criteria, links, status, dependencies, and ambiguity. Any intake summary must name those captured fields and state that MCP/API intake happens before brainstorming, planning, or downstream execution.
3. If the ticket is a child issue, subtask, story under an Epic, or otherwise linked into a parent hierarchy, read the parent tickets or Epic descriptions too. Carry forward the parent problem statement, goals, constraints, and acceptance context that explain why the child ticket exists.
4. Read nearby repo instructions and workflow references. For personal projects, check `PRD.md` when the ticket or unit of work adds or changes business rules. Check `designs/` or reference apps only when the ticket adds or modifies UI components that have a corresponding reference surface or component. Read only the relevant slices.
5. Inspect current git state, branches, existing PRs, and recent commits relevant to the ticket.
6. Create or verify the ticket worktree from freshly fetched `origin/main`; halt if freshness cannot be established.
7. After ticket, parent, artifact, and repo intake, the immediate next step is delegated codebase scoping with `code-mapper`, before brainstorming or planning. State that the ticket request authorizes the dispatch, local scoping is not a substitute, returned scoping evidence drives later brainstorming, and user questions are limited to unknowns the sweep could not resolve. Ask `code-mapper` to cover affected files/surfaces, schemas, secret conventions, event models, configs, tests, prior implementation history, risks, and verification surfaces. Include the ticket title, description, acceptance criteria, dependencies, repo instructions, and known constraints.

## Step 2 - Align Requirements And Design
Open with a short briefing grounded in the ticket, delegated scoping report, and current repo: what is known, what code evidence resolved, what remains ambiguous, likely affected surfaces, relevant designs or product docs, and any conflicts. In that briefing, explicitly state that brainstorming questions are based on returned scoping evidence and limited to unknowns the codebase sweep could not resolve.

Run a user-facing brainstorming session until the agent and user share a concrete understanding of the work, boundaries, and success criteria. This is mandatory and non-negotiable. Keep the discussion grounded in the ticket, parent context, approved artifacts, PRD/design slices, and current codebase facts.

Maintain and show a complete open-questions ledger before writing the spec/design. Use explicit headings for `Blocking decisions`, `Risky assumptions`, and `Non-blocking assumptions`, even when one section is empty. Phrase each blocking decision or risky assumption as a direct question, not only a noun label. Do not say you will show the ledger later when material unknowns are already known; show the current ledger in the response. Do not surface only the loudest blocker while silently carrying other unknowns into the spec or plan. After the user answers one question, update the ledger, rescan for remaining unknowns, and show the remaining questions before proceeding.

A single question, generic "any concerns?", or brief summary is not enough. When material unknowns exist, ask concrete follow-up questions for every blocking decision and risky assumption in the user-facing response. Do not list risky assumptions and defer asking about them later. Continue until every material unknown that could affect scope, data contracts, integration behavior, fallback behavior, schedules, acceptance criteria, or verification is resolved or explicitly approved as an assumption. After the material unknowns are answered, restate the shared understanding and remaining assumptions, then explicitly ask the user to confirm them before writing the spec/design. Do not promise to draft the spec immediately after the answers without that confirmation step.

After brainstorming, write a concise spec/design covering scope, non-goals, decisions, acceptance criteria, risks, and open questions. Ask the user to approve it. Do not route plan writing before that approval. Every brainstorming handoff must state that plan writing waits for spec/design approval, and execution, draft validation, product edits, and test edits wait for both spec/design approval and implementation-plan approval.

## Step 3 - Create And Approve The Spec And Plan
1. After the spec/design is approved, route implementation-plan writing from a self-contained context that names the approved spec, ticket context, parent context, relevant artifact slices, codebase scope, repo constraints, expected checks, and non-goals.
2. Present the implementation plan to the user and get explicit approval before coding starts. The plan must be concrete enough to route implementation and verification work.

Branch choice, investigation progress, internal status plans, checklists, and working notes do not count as approval.
Spec approval and implementation-plan approval are mandatory, non-negotiable gates. Do not implement, scaffold, mutate product code, edit tests, validate draft work, recommend implementation repairs, or route execution before both approvals.

## Step 4 - Execute The Approved Packet
After the user approves the spec and implementation plan, enter the execution phase using the approved execution packet and the shared `coordinate-ticket-execution` contract. The first execution-phase response must restate the compact packet fields: ticket facts, parent context, acceptance criteria, approved spec/design, approved implementation plan, artifact slices, scope locators, branch/worktree state, constraints, expected checks, PR expectations, and output expectations. Do not merely refer to "the approved packet." Before modifying product or test code, select and apply the execution capability from that packet; if it is unavailable, stop and report the blocker. Remain the main orchestrator in the current session. Coordinate implementation through `implementation-worker`, independent review through `code-reviewer`, security review through `security-reviewer` when applicable, QA through `qa-verifier`, UI/UX verification through `uiux-verifier` when applicable, scoped fixes, reruns, PR preparation, and final reporting through delegated work as needed. Do not name only the first implementation dispatch and leave later review, security, QA, UI/UX, fix, rerun, and PR-readiness gates implicit. Do not hand off main-ticket orchestration to another agent.

The approved execution packet must include the ticket facts, parent context, acceptance criteria, approved spec/design, approved implementation plan, relevant artifact slices, scope locators, branch/worktree state, constraints, expected checks, PR expectations, and completion-report requirements.

Respect this execution order:
1. Validate the approved execution packet.
2. Coordinate implementation through `implementation-worker` for the approved plan.
3. Coordinate independent review through `code-reviewer` against the ticket, acceptance criteria, approved plan, implementation evidence, and diff.
4. Coordinate security review through `security-reviewer` whenever the change has a plausible security surface. When summarizing this gate, do not say "security review or skip" without the condition: record a skip reason only when there is no plausible security surface.
5. Coordinate QA verification through `qa-verifier` against manual/runtime acceptance-criteria behavior in the running app, service, API, job, script, event flow, or integration. A change being backend-only, job-only, event-model-only, script-only, or not tied to a browser/API route is not a QA skip reason. Forward the executable surface, such as command, trigger, probe, seed data, logs, queues, stores, or integration path, so QA can exercise behavior. Automated checks, including unit tests, lint, type checks, and reviewer/security approval, are checks and do not count as QA evidence. If QA cannot verify because tooling, access, runtime, data, or dependencies are missing, it must return `CANNOT_VERIFY` with the reason and missing capability.
6. For UI-facing or mixed work, coordinate UI/UX verification through `uiux-verifier`. If UI/UX cannot verify because tooling or access is missing, it must return `CANNOT_VERIFY` with the reason and missing capability. For backend-only/non-UI work, record the skip reason.
7. Aggregate findings from independent review, security review or skip, QA, and UI/UX verification.
8. Coordinate scoped fixes for fixable findings.
9. Rerun the affected verification after fixes.
10. Repeat the finding, fix, and rerun loop until all required reports are clean, explicitly blocked, or explicitly out of scope.
11. Close execution with a gate note that states whether PR verification is allowed, blocked, or still waiting, and why.

When routing or relaying verifier work, require explicit rows such as `qa-verifier: CANNOT_VERIFY - <missing capability>` and `uiux-verifier: CANNOT_VERIFY - <missing capability>` when tooling or access is missing. If the main session has the required tooling, perform the needed verification there; otherwise report the blocker.

Track returned reports compactly enough to know what is implemented, reviewed, manually verified, fixed, rerun, clean, blocked, or explicitly out of scope. Do not route the ticket to PR verification until implementation, independent review, security review or skip, QA with manual/runtime evidence, UI/UX or skip, scoped fixes, and necessary reruns are resolved or explicitly blocked/out of scope.

Execution routing is incomplete unless it states that PR verification waits for those resolved, blocked, or out-of-scope reports and is not allowed while any required report is missing.

## Step 5 - PR Creation, Verification, And Handoff
When implementation, review, security review or skip, QA, UI/UX or skip, scoped fixes, and reruns are resolved, ensure a reviewable PR exists for the completed branch before the final ticket report. If no PR exists, the next gate is reviewer-facing PR preparation and source-control PR creation through the appropriate project workflow and identity; do not only report "PR missing." Carry the ticket context, approved spec and plan, implementation summary, verification evidence, risks, testing/checks, reviewer notes, and PR description needs into that PR preparation step. When describing this no-PR closing behavior, state that PR state is missing, PR readiness is not run, and after PR creation and PR readiness verification the normal final report must include the PR link, PR readiness result, ticket state, checks or remote status, and recommended next step. If PR creation is blocked, report that concrete blocker instead of presenting the ticket as complete.

After the PR exists or is identified, delegate a self-contained PR readiness verification request. Include the ticket, PR or branch, current known tracker/PR state, intended action, execution and verification summary, stale or missing PR metadata, and merge-approval status. When a tracker state is known, name the exact state in the readiness request rather than saying only "tracker state." PR creation alone is not ticket-start completion.

Relay the readiness result to the user. Do not merge, mark ready, update tickets, dismiss comments, or perform other source-control/tracker mutations inline while readiness is blocked or merge approval is absent.

## Final Report
End with a concise report:

- ticket, approved spec, and approved plan summary
- what was implemented
- what worked, what did not, and unresolved blockers
- implementation reports, self-review/review results, security review result or skip rationale, manual/runtime QA results, UI/UX results, and skipped rows with reasons
- plan-match or deviation findings from self-review/review, plus follow-up verification
- tests/checks/run evidence and remote check state
- PR link or PR-creation blocker, PR readiness result, ticket state, and recommended next step
- checks or remote status; if final handoff is blocked before a PR exists, still include PR blocker, PR readiness result as not run, ticket state, checks/remote status if known, and recommended next step

When describing correct closing behavior, explicitly state both cases: the successful final report includes the PR link, PR readiness result, ticket state, checks or remote status, and recommended next step; the blocked handoff includes the PR blocker, PR readiness result as not run, ticket state, checks or remote status if known, and recommended next step.

## Red Flags

Stop and recover when:

- ticket, repo, branch, PR, or requirement facts are stale or unavailable but would affect the decision
- spec approval or implementation-plan approval is skipped
- specialized-agent work is silently replaced by inline implementation, review, security review, QA, UI/UX verification, or PR/ticket mutation
- `qa-verifier` is skipped because work is backend-only, job-only, event-model-only, script-only, lacks a browser/API route, or has passing automated checks/reviewer approval
- PR verification is requested while required implementation, review, security review or skip, manual/runtime QA, UI/UX, finding, fix, or rerun reports are missing
- the final ticket report is prepared while no reviewable PR exists and no concrete PR-creation blocker is recorded
- merge or ticket completion is attempted without required checks and explicit user approval
