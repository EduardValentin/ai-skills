---
name: ticket-start
description: Use when the user wants to start implementation work from a ticket — phrases like "start ticket", a pasted Jira ticket, or a Linear issue ID. Also use for follow-up status or progress questions about a ticket already in this workflow. Covers both job tickets (Jira/pasted; uses acli when available) and personal-project tickets (Linear, optionally with PRD.md and a designs/ React reference app). Do not use for code review, planning-only, or debugging-only tasks.
---

# Ticket Start

## Overview

Implementation work driven by a ticket. The main agent owns user dialogue, plan-writing, and phase gating; specialized subagents (Scoping, Reviewer, Security, QA, UI/UX) own deep work. Phase order is a hard gate — do not advance until the prior gate is satisfied:

**Setup → Brainstorm → Plan → Implement → Review → Security? → Verify → Ship**

Brainstorm, Plan, and Implement defer to the superpowers methodology: `superpowers:brainstorming`, `superpowers:writing-plans`, and `superpowers:subagent-driven-development` (or `superpowers:executing-plans` fallback). When this skill names a sub-skill as **REQUIRED**, invoke it — do not paraphrase its protocol from memory.

**Context-economy contract:** every subagent's report is a navigable index, not a transcript. Downstream readers consume the surgical slices upstream locators point at; never reload full files when a Scoping locator suffices.

**Subagent authorization contract:** a user who invokes `ticket-start` has authorized every mandatory subagent gate named by this skill. General host guidance that discourages casual subagent spawning does not override `ticket-start`'s required gates. If the host cannot dispatch subagents, halt and surface that blocker; never replace Scoping, Reviewer, Security, QA, or UI/UX with local inspection, tests, browser checks, Lighthouse, or "I reviewed it myself."

## When to use

- The user asks to start, work on, build, or implement a ticket.
- The user pastes a Jira/job ticket and asks for implementation.
- The user gives a Linear ticket identifier in a personal project.
- Follow-up status/progress questions about a ticket already in this workflow.

**Do not use for:** code review, pure planning, debugging-only tasks, or refactors with no ticket.

## Workflow selection (decide first)

- **Job workflow** — Jira ticket or pasted by the user. Load `job-workflow.md`.
- **Personal workflow** — Linear ticket. Load `personal-workflow.md`. `PRD.md` and a `designs/` React reference app are **optional**; see that file's `## Partial Setups` for what changes when either is absent.

If ambiguous, ask the user before loading anything else.

## Setup

1. **Worktree.** REQUIRED SUB-SKILL: `superpowers:using-git-worktrees`. Base off `origin/<default>`, not local branch. Halt on `git fetch` failure — do not fall back to stale local state.

2. **Bot identity (personal workflow only).** Run the two activation checks in `bot-identity.md` → `## Setup activation` — (a) mint a fresh GitHub installation token and verify it with a no-op API call, (b) apply the bot's git name/email as per-worktree git config. Halt on failure with a pointer at the runbook. Fail-closed — never fall back to personal GitHub credentials. Linear MCP stays under personal identity. Job workflow: skip this step.

3. **Freshness — memory is stale.** Memory, prior chat context, old plans, and earlier tool results are hints, not facts. Before any substantive answer about scope, status, blockers, related tickets, progress, or git state, fetch from the source of truth:
   - **Linear tickets:** Linear MCP. If related/blocking/duplicate/parent/child tickets matter, read each.
   - **Job/Jira tickets:** prefer `acli jira workitem view <KEY> --json` (see `job-workflow.md`); fall back to user paste only on `acli` failure.
   - **Repo state:** inspect branch, working tree, diffs, recent commits, PR metadata.
   - **Repo docs/code:** re-read from disk before citing or depending.
   - If a source is unavailable, say what could not be verified. Do not fill from memory.

4. **Workflow-specific reading.** Read the workflow file selected above and gather the facts it points at. Stop when the relevant facts are gathered.

5. **Dispatch Scoping subagent** (`agents/scoping.md`). Forward: ticket title/description/AC, repo `AGENTS.md` / `CLAUDE.md`, and (personal workflow) the scoped slices of `PRD.md` / `designs/`. Subagent context does not inherit the main session's auto-loaded files — explicit forwarding is required. The returned report is the definitive map of the relevant code surface; do not re-read full files later when a Scoping locator points at the slice you need.

6. **Clarify before brainstorming if needed.** If AC are missing/vague/not testable, or Scoping surfaces a conflict between the ticket and existing architecture, brief the user with the Scoping evidence (`path:line`) and ask before continuing. See `## Briefing rule`.

## Brainstorm

**REQUIRED SUB-SKILL: `superpowers:brainstorming`.** A single relentless interview between main agent and the user. Alternatives are surfaced inside this dialogue, not by a separate Architect role.

1. **Open with a Scoping-grounded briefing.** Per `## Briefing rule` (Scoping → user), surface entry points, target module, prototype elements (if any), and any conflicts Scoping flagged. The user must enter the dialogue with the same context Scoping built.

2. **Run a relentless interview.** Cover every dimension the ticket and AC don't already settle:
   - **Intent** — what does success look like for the user?
   - **Constraints** — areas of code to avoid, performance bars, prior decisions to honor.
   - **Design preferences** — UX, copy, animation, edge-state behavior, accessibility.
   - **Edge cases and failure modes.**
   - **Non-goals** — what is explicitly out of scope.

3. **Surface alternatives — mandatory.** Before treating any direction as converged, put at least one credible alternative on the table, even if only to dismiss it. The brainstorm summary must record `"considered X via approach B because [reason], but [reason it's worse]"`. If you cannot generate an alternative, dispatch a focused research subagent ad-hoc for that question — do not skip.

4. **Anti-collapse rule.** A single user answer is not convergence. An early user implementation preference is an **input** to the dialogue, not its endpoint. Before exiting:
   - Restate the chosen direction across every dimension covered (intent, mechanism, edge cases, non-goals, alternatives considered).
   - Ask the user to confirm each explicitly.
   - "Yes, do it" / "approved" / "go ahead" / similar is approval of the **approach**, not approval of the plan. They are separate artifacts — the plan still has to be written and re-approved.

5. **Output: brainstorm summary.** A written artifact passed to `superpowers:writing-plans`. Captures intent, mechanism, constraints, alternatives considered (with dismissal rationale), non-goals, and any open questions for the planner.

## Plan

1. **REQUIRED SUB-SKILL: `superpowers:writing-plans`.** Produce a written plan from the brainstorm summary. The plan is a distinct artifact — not a verbal summary, not the brainstorm transcript, not a mental model.

2. **Parity-mode UI tickets** (personal workflow with a runnable React reference app under `designs/`) — each plan task that adds or modifies a visible element includes an `**Element mapping:**` block in its body declaring (a) the prototype counterpart via reference to a `## Prototype elements relevant to this feature` row from the Scoping report, and (b) the planned production `file:line` for the new/changed JSX declaration. Tasks that don't add/modify visible elements omit this block. Main agent uses these mappings at Verify dispatch (step 4a) to build the expected matched-element inventory passed to UI/UX.

   ```
   **Element mapping:**
   - Prototype: Scoping row `designs/components/Hero/Eyebrow.tsx:8` (`<span class="eyebrow">`)
   - Planned production: `web/src/components/Hero/Eyebrow.tsx:12` (new `<span class="eyebrow">`)
   ```

3. Show the plan as `superpowers:writing-plans` directs. Wait for **explicit user approval of the plan itself** before any code.

4. **No code between brainstorm convergence and plan approval.** Not exploratory edits, not scaffolding, not "drafting what the plan would say in code." File edits are off-limits until the plan exists and the user has explicitly approved it.

## Implement

1. **Personal workflow:** move the Linear ticket to **In Progress** immediately after plan approval, before any code (per `personal-workflow.md`).

2. **REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`** (auto-bakes TDD + per-task spec + code-quality review), or **`superpowers:executing-plans`** for a parallel session. Let those skills run.

3. **Two overrides this skill adds:**
   - On the `superpowers:executing-plans` fallback path, invoke `superpowers:requesting-code-review` after the final task and before Review — that path has no other end-of-feature review.
   - When superpowers reaches `superpowers:finishing-a-development-branch`, accept its test-pass check but do **not** present its 4-option prompt (merge / PR / keep / discard). Return to this skill's Review phase. Ship replaces those options.

## Review

1. **Dispatch Reviewer subagent** (`agents/reviewer.md`). Forward: full diff (`git diff origin/<default>..HEAD`), ticket + AC + approved plan, chosen brainstorm direction + rationale from the brainstorm summary, repo `AGENTS.md`, Scoping report, role prompt. Local code inspection is useful preparation, but it does not satisfy this gate.

2. **If CHANGES REQUIRED**, brief the user (per `## Briefing rule`) and route through `bug-fix-loop.md`.

3. **When CLEAN**, run the self-improvement extraction pass (per `self-improvement.md`). Advance.

## Security (judgment-triggered)

**Run Security whenever the change has any plausible security surface.** The bar to skip is *"no plausible security surface,"* not *"looks safe."* When in doubt, run. Main agent decides — there is no allowlist.

Plausible surfaces include — non-exhaustively — auth/session, user input handling, data exposure, persistence, redirects, file handling, external requests, privileged actions, third-party deps, sensitive logging, and any change to **what users can see or do that they otherwise couldn't**. Soft signals count: a feature that reveals whether an email is already registered on the site has a security surface (account enumeration) and qualifies.

Calibration:
- **Skip:** CSS-only spacing fix; prose copy change; internal helper rename with no surface change; asset swap with no new request.
- **Run:** any new request handler; any new dependency; any change to who-sees-what; any state change tied to user input; any new redirect or external request; any file-handling change.

When skipped, record the skip rationale in the closeout report.

1. **Dispatch Security subagent** (`agents/security.md`). Forward: full diff, ticket + AC, package manifests / lockfiles, repo `AGENTS.md`, Scoping + Reviewer reports (Reviewer's out-of-scope flags for Security feed in here), role prompt. Local threat modeling is useful preparation, but it does not satisfy this gate when Security is required.

2. **If CHANGES REQUIRED**, brief the user and route through `bug-fix-loop.md`. Per the loop, after the fix lands, **Reviewer + Security re-run on the full diff**.

3. **When CLEAN (or skipped)**, run the self-improvement pass on Security findings (skip the pass if Security was skipped). Advance.

## Verify

1. **Determine backend-only flag.** Walk the diff:
   - `git diff --name-only origin/<default>..HEAD`.
   - Match against UI extensions (`\.(tsx|jsx|vue|svelte|html|css|scss|sass|less|styl|ejs|pug|hbs|erb|twig|liquid|jinja|blade\.php)$`) and UI directories (`app/`, `components/`, `pages/`, `views/`, `templates/`, `client/`, `web/`, `frontend/`, `ui/`, plus repo-specific UI dirs identified by Scoping).
   - Any match → not backend-only.
   - Uncertain (config files affecting render, shared utilities used by both) → ask the user. Default on uncertainty: **do not skip** UI/UX (running it unnecessarily is cheap; skipping it incorrectly is expensive).

2. **Dispatch QA subagent** (`agents/qa.md`). Forward: ticket + AC + plan, full diff, QA mode (`backend` / `ui` / `mixed` from diff), path/URL of the running app, live-browser automation for UI mode (HTTP tooling for backend), role prompt. Local test runs, manual browser checks, and endpoint probes are evidence for QA to use, not substitutes for the QA report.

3. **If BUGS FOUND**, brief the user and route through `bug-fix-loop.md`. Per the loop, after the fix lands, **QA re-runs the full behavior pass**.

4. **When QA CLEAN**, run the self-improvement pass on QA findings.

4a. **Parity mode only — construct the expected matched-element inventory before UI/UX dispatch.** (Skip in consistency mode; UI/UX discovers as today.) Parity mode = personal workflow with a runnable React reference app under `designs/`.

   Combine:
   - Scoping's `## Prototype elements relevant to this feature` rows.
   - Each plan task's `**Element mapping:**` block.
   - Actual post-diff production `file:line`s, resolved by walking `git diff --name-only` for touched UI files and locating each plan-declared JSX declaration (e.g., `grep -n` on a stable selector like `class="..."` or `data-testid="..."` from the mapping).

   Produce a markdown table — column order matches `agents/ui-ux.md` → `## Output format`:

   | Pair | Prototype selector | Production selector | font-* | color/bg | box | layout | size | verdict |

   Per row at dispatch:
   - `Pair`: prototype:line ↔ production:line locator pair (or `(none)` on the deliberately one-sided side per the plan).
   - `Prototype selector` / `Production selector`: JSX-derivable selector hint (component name, `data-testid`, stable class).
   - `font-*` through `size` and `verdict`: **blank** — UI/UX fills via DOM evaluation.

   If construction fails (Scoping's prototype section unparsable, a plan element-mapping block can't be matched to a Scoping row, or the production-side lookup returns nothing), halt with `cannot dispatch UI/UX in parity mode — expected inventory could not be constructed` and name the specific error. Do not fall back to discovery-mode UI/UX in parity mode.

5. **Dispatch UI/UX subagent** (`agents/ui-ux.md`) unless backend-only flag is set. Forward: ticket + plan, full diff, mode (`parity` for personal workflow with React reference, `consistency` otherwise), running URLs (both production and reference in parity mode), the expected inventory table (parity only — UI/UX fills the verdict and computed-style cells, doesn't discover from scratch), live-browser automation, role prompt. Local accessibility scans, screenshots, Lighthouse, or visual comparison notes are evidence for UI/UX to use, not substitutes for the UI/UX report and inventory validation.

6. **If FINDINGS**, brief the user and route through `bug-fix-loop.md`. Per the loop, after the fix lands, **UI/UX re-runs scoped to affected states**.

6a. **Validate UI/UX's matched-element inventory before accepting any verdict.**

   **Parity mode** (expected inventory was supplied at 4a):
   - Every expected row appears in the verified inventory.
   - Every verified row has non-blank `font-*`, `color/bg`, `box`, `layout`, `size`, and `verdict` cells. Blank = DOM-evaluation work was skipped for that row.
   - Spot-check: sample 2 rows whose file appears in the diff and 2 rows from the prototype enumeration; each must be present with non-blank cells.
   - `MISSING` (production side) is accepted only when the plan marked the element as not-implemented-this-ticket; otherwise a `MISSING` is a finding.
   - Any failure → report is **structurally invalid**. Reject and re-dispatch UI/UX with the specific gaps named.

   **Consistency mode** (no expected inventory):
   - Confirm a `## Matched-element inventory` section exists.
   - From the diff, pick 2 changed UI files; their rendered elements must appear in the inventory.
   - From the running production app, sample 3 visible elements on the feature surface; each must appear.
   - Any miss → structurally invalid. Reject and re-dispatch with the specific missing elements named.

   Do not accept "I checked the major elements" or "the rest match by inspection" as substitutes for filled rows.

7. **When UI/UX CLEAN (or skipped) and inventory validation passes**, run the self-improvement pass on UI/UX findings (skip the pass if UI/UX was skipped). Advance to Ship.

## Ship

0. **Ship preflight — mandatory before any Ship mutation.** Before opening a PR, marking a PR ready, moving a ticket to review, merging, closing, or otherwise signaling "ready," build a readiness ledger from the actual completed phase outputs:
   - Reviewer: CLEAN report present.
   - Security: CLEAN report present, or skipped with a concrete "no plausible security surface" rationale.
   - QA: CLEAN report present.
   - UI/UX: CLEAN report and inventory validation present, or skipped with backend-only rationale.
   - Self-improvement: extraction pass completed for each auditor that ran; skipped only where the skill permits skipping.
   - Bug-fix loop: no active unresolved findings; iterations consumed recorded.

   If any ledger row is missing, **do not perform any Ship action**. Return to the earliest missing gate and complete it first. Local verification, green CI, clean merge state, manual browser checks, or local review do not satisfy missing ledger rows.

1. **Personal workflow:** after Ship preflight passes, open the PR with `gh`, then move the Linear ticket to **In Review** per `personal-workflow.md`. Do not merge or close.
2. **Job workflow:** after Ship preflight passes, follow the team's PR conventions from repository instructions.
   - If the repository uses Bitbucket PRs and the work requires reading PR metadata, reading or posting comments, or merging via the REST API, treat that portion as Bitbucket PR REST work.
3. Wait for the user's explicit approval before merging.
4. **Personal workflow:** after merge, move the Linear ticket to its completed state per `personal-workflow.md`.
5. **Job workflow:** after merge, follow the team's post-merge convention if specified in repo instructions; otherwise stop and surface what remains manual.
6. If PR creation, ticket transition, merge, or any Ship step cannot be completed, say exactly what failed and what remains manual.

## Bug-fix loop

When any auditor (Reviewer / Security / QA / UI/UX) returns a non-clean verdict, route through `bug-fix-loop.md`. That file defines complexity tiers, per-agent re-review scope, the 3-iteration cap with intervention report, the always-on user-intervention principle, and sequencing rules.

## Self-improvement loop

After each auditor returns CLEAN (or becomes CLEAN through the bug-fix loop), run the rule-extraction pass per `self-improvement.md`. That file defines the promotion bar (pattern-based, high-cost, declarative, non-stylistic, non-duplicate), repo-vs-universal classification, destinations (repo `AGENTS.md` for repo-specific; both `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` for universal, kept in sync), and the mandatory user-approval gate per rule.

## Briefing rule

When the workflow dispatches a subagent and then asks the user for input, decision, or choice, **the user must enter the dialogue with the same context the subagent had.** Brief in a single message before the first question.

| Trigger | Brief with |
|---|---|
| Scoping → user (Setup clarify, or Brainstorm opener) | Scoping's relevant findings (entry points, target module, prototype elements if any). For conflicts: quoted finding + `path:line` evidence. The question framed against that evidence. |
| Auditor → fix decision (Reviewer / Security / QA / UI/UX) | Findings, one per line (severity, `path:line`, one-line description). Suggested fix. Complexity tier the bug-fix loop assigned. For architectural complexity: the tradeoff as options the user can weigh. |

**Forbidden:** asking the user to pick an option they haven't seen, answer a clarifying question without its motivating context, or approve a fix without naming the finding.

## Implementation standards

Smallest safe diff that satisfies the ticket. Preserve existing patterns; do not invent abstractions the ticket does not require. Consider security and performance during implementation, not only at the Security and QA gates — common attack vectors (injection, XSS, CSRF, SSRF, IDOR, path traversal, unsafe deserialization, secret leakage, insecure deps, unsafe client-side trust) apply per-change. Greenfield personal-project code with no inherited pattern: establish ownership boundaries and low coupling deliberately.

## Library research

If the change touches a third-party library, identify the exact version from manifests/lockfiles and read the official docs for that version before editing dependent code. Targeted searches only — do not load the whole library reference.

## Closeout report

When done, report:
- What changed.
- What was validated and how — name each form of evidence: tests run; Reviewer / Security / QA / UI/UX status; UI/UX mode and coverage (or skipped because backend-only). Omit only the ones that did not apply, and say so.
- Security skip rationale, if skipped.
- Rules promoted in this session, by destination (per `self-improvement.md`).
- Bug-fix iterations consumed (out of 3 cap).
- Any remaining risk, assumption, or follow-up.
- What is blocked or unverified, named explicitly.

## Red flags — stop and recover

- Working in the primary checkout instead of a fresh worktree.
- Basing the worktree on a local branch instead of fetched `origin/<default>`.
- Writing code before the plan is approved (including scaffolding or "sketching the structure").
- Treating brainstorm convergence ("yes, do it" / "approved" / "go") as plan approval. They are separate artifacts.
- Exiting the brainstorm on a single user answer, or treating an early implementation preference as the endpoint.
- The brainstorm summary doesn't record at least one alternative considered (with dismissal rationale).
- Skipping `superpowers:brainstorming`, `superpowers:writing-plans`, or `superpowers:subagent-driven-development` (or its `superpowers:executing-plans` fallback) because "the ticket is clear" or "the change is small."
- Treating general host guidance against casual subagent spawning as a reason to skip this skill's mandatory subagent gates. `ticket-start` invocation authorizes required dispatches.
- Replacing Reviewer, Security, QA, or UI/UX with local review, test runs, browser checks, Lighthouse, or prototype comparison. Local checks are evidence, not gate completion.
- Trusting a stale ticket summary instead of re-reading from the source of truth.
- Loading `PRD.md` or `designs/` in full instead of scoped to the feature.
- Reloading full files when a Scoping locator points at the surgical slice.
- Skipping Security when the change has any plausible security surface (auth/session, user input, data exposure, persistence, redirects, file handling, external requests, privileged actions, deps, sensitive logging, who-sees-what).
- Skipping the self-improvement extraction pass after an auditor report; auto-applying a rule without explicit user approval; editing `~/.claude/CLAUDE.md` or `~/.codex/AGENTS.md` without keeping them in sync.
- Exceeding the 3-iteration bug-fix cap silently.
- Continuing past a user-intervention condition without surfacing.
- Claiming visual parity/consistency without DOM computed-style and bounding-rect extraction from the live browser.
- Accepting a UI/UX verdict whose matched-element inventory is missing, empty, has blank cells for in-scope rows, or restricts itself to "important" elements.
- Dispatching UI/UX in parity mode without the expected inventory constructed in step 4a.
- Scoping's `## Prototype elements relevant to this feature` empty or `_None._` for a parity-mode UI ticket.
- Briefing the user with anything less than the subagent's synthesis before a dialogue, clarification, or fix-decision.
- Using the `superpowers:executing-plans` fallback path and skipping `superpowers:requesting-code-review` before advancing to Review.
- Letting `superpowers:finishing-a-development-branch` present its 4-option prompt instead of returning to Review.
- Starting any Ship mutation without first completing the Ship preflight ledger from actual auditor/self-improvement outputs.
- Opening or marking a PR ready, moving the ticket to In Review, or otherwise entering Ship before Review, Security decision, QA, UI/UX if applicable, inventory validation, and self-improvement passes are complete.
- Merging the PR before the user explicitly approves.

If any of these is true: stop, name the violation, and recover before continuing.
