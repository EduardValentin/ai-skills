# Pre-Architect understanding — design

**Status:** approved by user, ready for implementation plan
**Scope:** `skills/ticket-start/` only
**Depends on:** PR #6 (visual-parity enforcement + canonical-skill migration + inventory-as-contract + dispatch-user-briefing-protocol)
**Activation:** every ticket (job or personal, parity or consistency mode). No mode gating.

## 1. Problem statement

During PR #6's execution, a structural failure mode surfaced: the Architect subagent ran cold against the ticket + AC + Scoping report and produced candidate proposals before any user-facing brainstorm had taken place. The user expected a question-driven dialogue BEFORE the Architect was involved — to surface intent, constraints, and design preferences not captured in the ticket — and to only let the Architect propose against that enriched context.

Today's Setup phase has six steps. Step 6 (Clarifications) is reactive only — it fires when acceptance criteria are missing/vague/not testable OR when Scoping flags a `## Conflicts surfaced for main` item. On a well-specified ticket where AC is testable and Scoping found no conflicts, step 6 is a no-op and the workflow flows straight from Scoping → Brainstorm → Architect. That no-op-on-well-specified-tickets behavior was the failure mode: there can be plenty of implicit user context (preferences, intuitions, constraints not in the ticket) that Scoping doesn't surface because nothing's structurally wrong, and Architect therefore proposes against cold context.

Two consequences followed in practice:

1. **Architect's proposals were off-target** because they were built against incomplete context.
2. **The post-Architect brainstorm became "explain why none of these fit"** instead of "converge on the right one." On the originating ticket, the post-Architect brainstorm also didn't fire as a multi-turn dialogue — the user was simply presented with the options and asked to pick. Today's wording explicitly says "Run `superpowers:brainstorming` with the user" but in practice the skill did not auto-fire, and the dialogue degenerated into a single-question gate.

A related cleanup also surfaced during the design discussion: today's Setup steps 1 (Worktree first) and 2 (Repository instructions) mix workflow-specific discipline with reminders about behavior that's auto-loaded by the host platform. The workflow-specific bits are real but small; the reminder-about-defaults bits are pure overhead. Trimming them is in scope here because they live in the same Setup section as the new step.

A third related issue: the phase named "Brainstorm" in `SKILL.md` today contains three sub-steps — Architect dispatch (not a brainstorm), post-Architect brainstorm with user (IS a brainstorm), and on-demand Architect re-dispatch (not a brainstorm). Two out of three activities aren't brainstorms. Misnaming the phase obscures the workflow's shape.

## 2. Goals and non-goals

### Goals

- Add a **proactive pre-Architect understanding dialogue** to Setup as step 7. Run on every ticket; surface implicit user intent, constraints, and preferences before Architect proposes solutions.
- **Trim Setup steps 1 and 2** to only the workflow-specific discipline; remove the reminders about host-platform defaults.
- **Split the misnamed "Brainstorm" phase** into two phases: `Solution Exploration` (Architect's cold solution work) and `Brainstorm` (user-facing convergence dialogue, with on-demand Architect re-dispatch). Make each phase contain exactly one type of activity, accurately labeled.
- **Architect proposes against richer context.** The brainstorm summary from Setup step 7 becomes a new input bullet on Architect's role prompt.
- **Auto-trigger discipline.** Both the new Setup step 7 and the post-Architect Brainstorm phase use intent-language wording that auto-fires the brainstorming skill. No explicit `superpowers:brainstorming` invocations in the prose. This is a deliberate departure from today's "Run X" wording that failed to fire in practice.

### Non-goals

- No new subagent. The pre-Architect dialogue is main-agent + user, with the brainstorming skill auto-firing.
- No new artifact file. The brainstorm summary lives in the dispatch payload to Architect, ephemeral.
- No new scripts.
- No mode gating. The new step + new phase split apply to every ticket regardless of workflow.
- No fallback for auto-trigger failure. We trust the wording; if a future ticket shows the skill still doesn't fire, the fix is to iterate on wording, not add a `Skill` invocation back.
- No change to subagent role prompts beyond a single new input bullet on `agents/architect.md`. Scoping, Reviewer, Security, QA, UI/UX role prompts unchanged.

## 3. Architectural decisions

Six decisions settled during brainstorming, each with alternatives that were considered and rejected.

| Decision | Choice | Alternative rejected | Why |
|---|---|---|---|
| **Where the pre-Architect step lives** | Setup phase, new step 7 after Clarifications | New phase between Setup and Brainstorm; or expand Setup step 6 to absorb proactive brainstorm | Step 6 is a reactive guard (hard-stop on AC missing or Scoping conflict). Step 7 is proactive content gathering. Merging them conflates escalation conditions with content-gathering. Separating keeps each independently auditable. |
| **End condition of the pre-Architect brainstorm** | Deferred to `superpowers:brainstorming`'s own auto-trigger and convergence logic | Bounded N questions; or user-signal-to-proceed | The brainstorming skill already has its own convergence discipline. Not our job to re-implement; trust the skill. |
| **Relationship to today's post-Architect brainstorm** | Keep both — different jobs (intent first, options second) | Replace with single pre-Architect brainstorm; or conditionally skip post-Architect | (Replacement) loses the explicit "pick a direction" gate. (Conditional) needs main agent judgment that the briefing protocol just learned not to skip without user input. Keep both → intent first, then option convergence. |
| **What Architect receives as new input** | Brainstorm summary as a new input bullet on the Architect role prompt (ephemeral) | Inline into ticket/AC; or persistent artifact file | (Inline) blurs provenance — Architect can't tell what came from the ticket vs the user. (Persistent file) adds a lifecycle for an upstream signal that doesn't need long-term auditing. New input bullet matches the pattern used for the supplied inventory in UI/UX (PR #6). |
| **Setup steps 1–2** | Trim to workflow-specific bits | Keep as-is (defense in depth); drop entirely | The workflow-specific parts (worktree discipline, subagent context forwarding) are real and small. Drop loses them; keep mixes them with redundant reminders about host defaults. Trim keeps the workflow-specific content with less overhead. |
| **Phase naming for the old "Brainstorm" phase** | Split into two phases: `Solution Exploration` (Architect dispatch) and `Brainstorm` (user dialogue + on-demand re-dispatch) | Rename to "Direction" (one phase); or fold all of it into Setup | Splitting names each activity accurately. The on-demand re-dispatch lives in the Brainstorm phase because that's where its trigger fires (during the user dialogue). Solution Exploration is single-step but well-defined. |

## 4. Phase data flow

After this change, the workflow has 9 phases:

```
Setup → Solution Exploration → Brainstorm → Plan → Implement → Review → Security → Verify → Ship
```

**Setup phase (7 steps after this change):**

1. Worktree discipline (trimmed)
2. Subagent context discipline (trimmed)
3. Freshness — treat memory as stale (unchanged)
4. Workflow-specific reading (unchanged)
5. Dispatch Scoping subagent (unchanged)
6. Clarifications (reactive guard, unchanged)
7. Pre-Architect understanding (NEW — proactive user dialogue)

**Solution Exploration phase (1 step):**

1. Dispatch Architect subagent — with the brainstorm summary from Setup step 7 as a new input.

**Brainstorm phase (3 steps):**

1. Brief per `## Dispatch → user briefing protocol` (handoff type 2: Architect → Brainstorm dialogue), then explore the Architect's proposals with the user via a question-driven dialogue. Converge on a chosen direction.
2. On-demand Architect re-dispatch — if a follow-up architectural question arises during the dialogue, re-dispatch Architect with the focused question; brief the user on the re-dispatched answer before continuing.
3. Convergence is not plan approval. Approval of the *approach* is not approval of the plan; the plan still has to be written by `superpowers:writing-plans` and re-approved.

**Subsequent phases** (Plan, Implement, Review, Security, Verify, Ship): unchanged in content; renumbered in the Phase Order list (Plan = 4, Implement = 5, Review = 6, Security = 7, Verify = 8, Ship = 9).

### 4.1 Auto-trigger discipline (key design point)

Both Setup step 7 and Brainstorm step 1 deliberately describe the activity in language that matches `superpowers:brainstorming`'s trigger description ("creative work — creating features, building components, adding functionality, or modifying behavior; explores user intent, requirements and design before implementation"):

- Step 7 opens with **"explore user intent, constraints, and design preferences"** — direct echo of "explores user intent, requirements and design".
- Brainstorm step 1 opens with **"explore the Architect's proposals with the user via a question-driven dialogue"** — same echo, different starting material.

Neither step names `superpowers:brainstorming` explicitly. No `Skill` tool invocation in the prose. The skill fires via auto-trigger because the language matches its description.

**Acknowledged failure mode.** This design assumes the auto-trigger reliably fires. Today's Brainstorm step 2 says "Run `superpowers:brainstorming`" explicitly and still didn't fire on the originating ticket — there's evidence the auto-trigger pathway can fail. We're choosing to trust auto-trigger anyway because:
1. Explicit "Run X" wording didn't work either, so explicit invocation is not a working fix.
2. Intent-language wording is shorter and more honest about what should happen.
3. The brainstorming skill's description is well-suited to fire on workflow language ("creative work", "user intent", "design before implementation").

If a future ticket shows the skill still doesn't fire, the fix is to refine wording (sharpen the trigger match), not to add a `Skill` invocation back. This is a known risk for next-ticket validation, surfaced explicitly so it can be tested.

### 4.2 Invariants

- **Architect no longer proposes cold.** By the time Solution Exploration runs, Setup step 7 has surfaced the user's implicit context and packaged it for Architect. Today's failure mode (proposals miss because user context wasn't gathered) becomes structurally harder.
- **No explicit skill invocations in workflow prose.** All references to `superpowers:brainstorming` are replaced with intent-language descriptions. The using-superpowers infrastructure handles invocation.
- **Each phase contains one type of activity.** Solution Exploration is Architect work only. Brainstorm is user dialogue only (plus the re-dispatch trigger that bounces back to Architect work).

## 5. File-by-file changes

### 5.1 `skills/ticket-start/SKILL.md`

This file gets the bulk of the work. Several distinct edits:

**(a) Overview paragraph.** Update phase list from 8 to 9 phases:
> The skill enforces a strict phase order with explicit gates: Setup → Solution Exploration → Brainstorm → Plan → Implement → Review → Security → Verify → Ship.

**(b) Phase Order section.** The ASCII art and numbered list update to 9 phases. The numbered descriptions add/change for the affected phases:
- "2. **Solution Exploration** — Architect subagent dispatch (with the pre-Architect brainstorm summary as input). See 'Solution Exploration' below."
- "3. **Brainstorm** — user-facing convergence on Architect's proposals via a question-driven dialogue. See 'Brainstorm' below."
- Renumbering cascades: Plan = 4, Implement = 5, Review = 6, Security = 7, Verify = 8, Ship = 9.

**(c) Setup step 1 trimmed:**
> 1. **Worktree discipline.** REQUIRED SUB-SKILL: `superpowers:using-git-worktrees`. Base off `origin/<default>`, not a local branch. Halt on `git fetch` failure — do not fall back to stale local state.

**(d) Setup step 2 trimmed:**
> 2. **Subagent context discipline.** When dispatching subagents, explicitly forward `AGENTS.md` and any workflow-relevant project docs as inputs — subagent context does not always inherit the main session's auto-loaded files, and explicit forwarding is the host-agnostic discipline.

**(e) Setup step 7 (NEW):**
> 7. **Pre-Architect understanding.** Before the Architect proposes a direction, explore user intent, constraints, and design preferences not captured in the ticket. Pursue a question-driven dialogue with the user covering: implicit preferences ("how should this feel?"), constraints not in the AC ("are there areas of the code we should avoid?"), domain-specific intuitions, design-language preferences, and any unknowns the ticket leaves open. Cover whatever ground the Architect would benefit from before generating proposals.
>
>    Brief per `## Dispatch → user briefing protocol` (handoff type 1: Scoping → user dialogue) before the first question — surface the Scoping report's relevant findings (entry points, target module, prototype elements if any) so the user has the same context the Architect will get.
>
>    Capture the outcome as a short **brainstorm summary** that will be passed to the Architect as a new input in Solution Exploration. The summary covers the user's stated intent, the constraints they surfaced, and any preferences they expressed.

**(f) Old `## Brainstorm` section → split into two new sections:**

```
## Solution Exploration

1. **Dispatch Architect subagent.** Load the role prompt from `agents/architect.md`. Invoke a subagent with:
   - The ticket and AC.
   - The Scoping report.
   - The repo's `AGENTS.md` / `CLAUDE.md`.
   - The pre-Architect brainstorm summary from Setup step 7.
   - The role-prompt content from `agents/architect.md`.
   Wait for the Architect's proposals (2–3 candidate solutions with tradeoffs).

## Brainstorm

1. **Brief per `## Dispatch → user briefing protocol` (handoff type 2: Architect → Brainstorm dialogue), then explore the Architect's proposals with the user via a question-driven dialogue.** Brief BEFORE the first question — present the Architect's recommended approach + rationale, alternatives + tradeoffs, and any open questions with their motivating context, as a single message. Only after this synthesis is in the user's view, walk through the proposals with the user. Converge on a chosen direction.

2. **On-demand Architect re-dispatch.** If during the dialogue a follow-up architectural question arises that the original proposals didn't cover, re-dispatch the Architect with the focused question (per `agents/architect.md`'s follow-up handling). When you bring the re-dispatched Architect's answer back, brief the user on what the Architect found (recommended adjustment + rationale + any new tradeoffs) before continuing the dialogue.

3. **Convergence is not plan approval.** When the dialogue converges and the user says "yes, do it," "approved," "go ahead," or similar, that is approval of the *approach*. It is **not** approval of the plan. The plan still has to be written by `superpowers:writing-plans` and re-approved as its own artifact. Do not collapse the two.
```

(The wording in the new Brainstorm step 1 replaces "Run `superpowers:brainstorming` with the user" — an explicit skill invocation that didn't fire on the originating ticket — with intent-language ("explore the Architect's proposals with the user via a question-driven dialogue") that auto-fires the skill.)

**(g) Briefing protocol update (handoff type 1).** Today the central protocol section describes handoff type 1 as triggered when "Scoping returns with items under `## Conflicts surfaced for main` or with insufficient AC coverage." Update to acknowledge proactive use too:

> ### Handoff type 1 — Scoping → user dialogue (Setup)
>
> When Scoping returns and main agent dispatches a user dialogue — either reactively (Setup step 6: Scoping flagged a conflict, or AC is missing/vague/not testable) or proactively (Setup step 7: pre-Architect understanding):
>
> - The Scoping report's relevant findings (entry points, target module, prototype elements if any), as context for the user.
> - For reactive cases: the specific conflict or ambiguity quoted from the report + the `path:line` evidence.
> - The clarification or open question main agent is bringing to the dialogue.

Handoff types 2–7 unchanged.

### 5.2 `skills/ticket-start/agents/architect.md`

One new input bullet appended to the Inputs section:
> - **Pre-Architect brainstorm summary:** A short markdown synthesis of the user's stated intent, constraints, and preferences surfaced during Setup step 7. Treat this as authoritative on questions the ticket and AC don't cover — it captures what the user expects that wasn't written down.

No other changes to Architect's role prompt; the existing mandate / output format / forbidden behaviors all apply.

### 5.3 Files that don't change

- `agents/scoping.md`, `agents/reviewer.md`, `agents/security.md`, `agents/qa.md`, `agents/ui-ux.md`, `agents/openai.yaml`.
- `bug-fix-loop.md`, `self-improvement.md`, `verification.md`, `job-workflow.md`, `personal-workflow.md`, `react-parity.md`.
- `scripts/extract-element-style.browser.js`.

## 6. Activation, briefing-protocol interaction, edge cases

### 6.1 Activation gate

No mode gating. Setup step 7 always runs (every ticket, both job and personal workflows, both parity and consistency modes). Solution Exploration and Brainstorm both also always run.

The brainstorming skill's own auto-trigger decides whether to engage deeply or shallowly. On a trivial ticket where the user has nothing implicit to add, the dialogue converges in zero or one questions; on a substantive ticket it goes deeper. No special-casing.

### 6.2 Briefing-protocol interaction

The dispatch-user-briefing-protocol's handoff types (1–7) carry forward with one small wording update to handoff type 1 (see §5.1(g) above) to acknowledge it now fires on both reactive (step 6) and proactive (step 7) user dialogues.

Other handoff types unchanged:
- Handoff type 2 (Architect → Brainstorm dialogue) still applies at Brainstorm step 1.
- Handoff type 7 (bug-fix loop architectural intervention) unchanged.

### 6.3 Edge cases

- **User has nothing to add at step 7.** Brainstorming skill converges fast. Main agent writes a minimal summary ("no implicit context beyond the ticket — proceed"). Architect receives the minimal summary and works essentially as today, just with explicit "user confirmed no additional context" provenance.

- **Step 7's dialogue surfaces something that contradicts Scoping.** Main agent surfaces the contradiction explicitly to the user (per the existing user-intervention principle) and either re-dispatches Scoping with the focused question or notes the contradiction and proceeds with the user's stated preference. The contradiction must be resolved before advancing to Solution Exploration — Architect cannot run with conflicting inputs.

- **Step 7's dialogue surfaces architectural questions Architect should answer.** Discipline: don't skip ahead to Architect. Step 7 surfaces what the user wants; the "how to build it" questions are Architect's job and come back in Brainstorm. If the user genuinely needs Architect's analysis to articulate their preferences, surface that as a workflow blocker rather than silently re-ordering phases.

- **Trivial tickets** (one-line typo fix, comment update, README rename). Brainstorming skill converges fast or shallowly; Architect's proposals also become trivial; workflow proceeds quickly. No special-casing.

- **Auto-trigger doesn't fire.** Known risk (see §4.1). Mitigation: the wording is engineered to match the brainstorming skill's trigger description. If next-ticket validation shows the skill still doesn't fire reliably, refine wording (don't add explicit `Skill` invocations).

### 6.4 What we explicitly don't add

- No new subagent. Step 7 is main-agent + user dialogue, with the brainstorming skill auto-firing.
- No new artifact file. Brainstorm summary lives in the dispatch payload, ephemeral.
- No new scripts.
- No mode gating.
- No fallback for auto-trigger failure (per §4.1 reasoning).

## 7. Deferred to implementation plan

The following implementation details are deferred to the plan:

- **Exact format of the brainstorm summary** passed to Architect. Probably a short markdown block with subsections for "Stated intent," "Constraints," "Preferences." The plan will pin down the exact structure.
- **Exact ASCII-art diagram update** in the Phase Order section. The plan will specify the new diagram.
- **Renumbering of the Phase Order section's numbered list** (Plan = 4 → 4, etc., but the numbers ARE changing because Brainstorm is being split). The plan will spell out the renumbering.

## 8. Migration and scope

This is additive plus a phase rename. No behavioral change to Plan, Implement, Review, Security, Verify, or Ship phases (their numbering changes in the Phase Order index, but their content is unchanged). The rollback is reverting the PR.

In-flight tickets that were started before this change ships finish on the existing protocol. New tickets start under the new flow automatically once their Setup runs.

## 9. Why this is meaningful

This is the fifth round of hardening on the `ticket-start` workflow in this PR. Each round addresses a structural failure mode observed during the previous round's execution. The accumulated pattern:

1. **Visual-parity enforcement (round 1)** — UI/UX inventory was non-exhaustive in practice; protocol now mandates exhaustiveness.
2. **Canonical-skill migration (round 2)** — duplicated skill trees and product-name pollution; consolidated and made host-agnostic.
3. **Inventory-as-contract (round 3)** — UI/UX inventory construction was done at the last possible moment with stale context; moved upstream to Scoping + Plan + main-at-dispatch.
4. **Dispatch-user-briefing-protocol (round 4)** — main agent asked the user to make decisions with less context than the subagent had; codified briefing obligations at every dispatch-→-user handoff.
5. **Pre-Architect understanding (round 5 — this round)** — Architect proposed against cold context because no user brainstorm preceded it; added a proactive user dialogue at Setup step 7 and split the misnamed Brainstorm phase into Solution Exploration + Brainstorm.

The common shape across all five rounds: an upstream phase needed to surface or carry context that a downstream phase was reconstructing or guessing. The fix is always to move work upstream where context is freshest, and to make the handoff explicit so the downstream phase can't accidentally skip it.

After this round, the workflow has explicit contracts at every major dispatch boundary: Scoping → Architect (brainstorm summary), Architect → Plan (the chosen direction from the post-Architect Brainstorm), Plan → Implement (the approved plan), Implement → auditors (the diff + AC + plan), auditors → user-decision (briefing protocol), bug-fix loop → user (intervention principle + briefing). Each contract has a name, a format, and explicit obligations on both sides.
