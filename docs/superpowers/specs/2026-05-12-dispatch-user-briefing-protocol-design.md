# Dispatch → user briefing protocol — design

**Status:** approved by user, ready for implementation plan
**Scope:** `skills/ticket-start/` only
**Depends on:** PR #6 (`ticket-start: harden visual parity enforcement after observed failure`)
**Activation:** every dispatch-→-user handoff in the workflow. No mode gating.

## 1. Problem statement

A real-world failure observed during PR #6's execution: in the Brainstorm phase, main agent dispatched the Architect subagent, received the report, then ran `superpowers:brainstorming` with the user — but presented "pick an option" to the user without first briefing the user on **what the options were**, **what tradeoffs the Architect captured**, or **what context motivated the open questions the Architect surfaced**. The user "had nothing to work with."

`SKILL.md`'s Brainstorm step 2 says:

> Run `superpowers:brainstorming` with the user. Use the Architect's proposals as the starting material.

"Use the Architect's proposals as the starting material" is doing too much work in one phrase. An LLM main agent can — and apparently did — interpret it as "internally consult the proposals, then ask the user to choose", skipping the briefing entirely.

The same structural failure mode exists at every other dispatch-→-user handoff in the workflow:

1. **Setup step 6** — Scoping returns with conflicts surfaced, main asks user to clarify.
2. **Brainstorm step 2** — Architect returns proposals, main runs brainstorming dialogue. *(The observed case.)*
3. **Brainstorm step 3** — Architect re-dispatched mid-brainstorm, answer brought back.
4. **Review step 2** — Reviewer returns CHANGES REQUIRED → bug-fix-loop.
5. **Security step 2** — same shape as Review.
6. **Verify step 3** — QA returns BUGS FOUND → bug-fix-loop.
7. **Verify step 6** — UI/UX returns FINDINGS → bug-fix-loop.
8. **bug-fix-loop architectural complexity** — explicit user intervention for architectural fixes.

At every one of these handoffs, main agent owns a context the user does not have (the subagent's findings, rationale, alternatives, tradeoffs, open questions), and the bridge from subagent context → user context is currently under-specified. The user is asked to participate in a decision whose substance they haven't seen.

## 2. Goals and non-goals

### Goals

- Make the bridge from subagent context → user context **explicit, mandatory, and named** at every dispatch-→-user handoff in the workflow.
- Codify a single principle ("the user must enter the dialogue with the same context the subagent had") with **per-handoff-type content checklists** so the rule is uniform but the briefing content is appropriate to each handoff.
- Localise the rule in one place in `SKILL.md` (a new top-level section) plus a one-sentence cue at each dispatch site so dispatch steps stay self-documenting.
- Preserve all existing protocol from PR #6 (visual-parity hardening, canonical-skill migration, inventory-as-contract). The briefing protocol is additive — it adds a rule wherever main agent already hands off to the user; it does not remove or restructure existing behavior.

### Non-goals

- No changes to subagent role prompts (`agents/scoping.md`, `agents/architect.md`, `agents/reviewer.md`, `agents/security.md`, `agents/qa.md`, `agents/ui-ux.md`). Their existing output formats already include the substance the briefing needs (rationale, alternatives, tradeoffs, severity, location, suggested fix); the protocol just makes main agent relay it.
- No new subagent. Main agent does the briefing in its own context, drawing from the subagent's report.
- No persistent briefing artifact. The briefing is a user-facing message at the handoff moment; it lives in the conversation transcript only.
- No mode gating. The protocol applies to every dispatch-→-user handoff regardless of workflow (job vs personal), mode (parity vs consistency), or phase. The handoff types adapt the content; the principle stays constant.
- No change to `superpowers:brainstorming` or any other `superpowers:*` skill. The briefing happens BEFORE `superpowers:brainstorming` is invoked.

## 3. Architectural decisions

Two decisions settled during brainstorming:

| Decision | Choice | Alternative rejected | Why |
|---|---|---|---|
| **Scope** | Wide — all seven dispatch-→-user handoffs covered by one general principle. | Narrow (just Brainstorm step 2); Medium (Brainstorm + four auditor handoffs only) | The failure mode is structural — an LLM orchestrator skipping the bridge work between subagent context and user context. A point fix doesn't prevent the same failure recurring at other handoffs, and the consequences are worst at the auditor handoffs (where the user's fix decisions get made). Wide scope costs one extra commit; the protection is durable. |
| **Structure** | Central section + brief per-site cues. | Per-step inline expansion (rule repeated 7×); central section with no per-site cues | Per-step inline expansion duplicates the rule and makes future tightening expensive. Central section without per-site cues relies on the LLM to remember a global rule while reading a local step — exactly the kind of context-bridging failure this project is trying to prevent. The hybrid keeps the rule localized (one place to update) while keeping every dispatch step self-documenting about its briefing obligation. |

## 4. File-by-file changes

Two files change in the canonical `skills/ticket-start/` tree. Both sync to `~/.codex/skills/ticket-start/` and `~/.claude/skills/ticket-start/` in the same flow per AGENTS.md rule 2.

### 4.1 `skills/ticket-start/SKILL.md`

Three substantive additions:

#### 4.1.1 New top-level section: `## Dispatch → user briefing protocol`

Placement: between the existing `## Self-Improvement Loop` and `## Implementation Standards`. This sits the protocol with the other cross-cutting concerns (bug-fix loop, self-improvement loop) rather than burying it in a phase-specific section.

Body:

```
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
```

#### 4.1.2 Per-site cues (7 cues across existing dispatch steps)

Each dispatch-→-user handoff in the workflow gets a one-sentence cue pointing at the central section:

**Setup step 6 (Clarifications):** append after the existing content — "Before asking the user any clarifying question, brief per `## Dispatch → user briefing protocol` (handoff type 1: Scoping → user clarification)."

**Brainstorm step 2:** rewrite the whole step — "**Brief per `## Dispatch → user briefing protocol` (handoff type 2: Architect → Brainstorm dialogue), then run `superpowers:brainstorming` with the user.** Brief BEFORE the first brainstorming question — present the Architect's recommended approach + rationale, alternatives + tradeoffs, and any open questions with their motivating context, as a single message. Only after this synthesis is in the user's view, start the standard one-question-at-a-time dialogue. Converge on a chosen direction."

**Brainstorm step 3 (on-demand re-dispatch):** append after the existing content — "When you bring the re-dispatched Architect's answer back, brief the user on what the Architect found (recommended adjustment + rationale + any new tradeoffs) before continuing the brainstorming dialogue."

**Review step 2 (Reviewer FINDINGS):** rewrite — "**If Reviewer returns CHANGES REQUIRED**, brief the user per `## Dispatch → user briefing protocol` (handoff types 3–6: auditor → fix decision) before routing through `bug-fix-loop.md`."

**Security step 2 (Security FINDINGS):** rewrite with the same shape as Review step 2.

**Verify step 3 (QA BUGS FOUND):** rewrite with the same shape.

**Verify step 6 (UI/UX FINDINGS):** rewrite with the same shape.

#### 4.1.3 Two new red flags

Add to the existing Red Flags list:

- "Starting a brainstorming dialogue, a clarification question, or a fix-decision request to the user without first presenting the relevant subagent's synthesis (per `## Dispatch → user briefing protocol`). The user must enter the conversation with the same context the subagent had."
- "Routing an auditor's findings through bug-fix-loop's architectural-intervention path without surfacing the architectural tradeoff to the user."

### 4.2 `skills/ticket-start/bug-fix-loop.md`

One cue at the architectural-complexity branch (where the loop calls for user intervention):

"Before asking the user for architectural direction, brief per `SKILL.md` → `## Dispatch → user briefing protocol` (handoff type 7: bug-fix loop architectural intervention)."

Placement: in whichever section of `bug-fix-loop.md` currently describes the architectural-complexity user-intervention path. The implementation plan will locate the exact insertion point during execution.

### 4.3 Files that don't change

- `agents/scoping.md`, `agents/architect.md`, `agents/reviewer.md`, `agents/security.md`, `agents/qa.md`, `agents/ui-ux.md` — their existing output formats already include the substance the briefing needs (rationale, alternatives, tradeoffs, severity, location, suggested fix). Main agent's job is just to relay it.
- `self-improvement.md`, `job-workflow.md`, `personal-workflow.md`, `react-parity.md`, `verification.md` — orthogonal.
- `scripts/extract-element-style.browser.js`, `agents/openai.yaml` — unchanged.

## 5. Activation, edge cases, what we don't add

### 5.1 Activation gate

The protocol applies to **every** dispatch-→-user handoff in the workflow. No mode gating, no workflow gating, no phase gating. The handoff types adapt the content per dispatch; the principle stays constant.

This is intentional. The failure mode is structural (LLM orchestrator skipping the bridge work between subagent context and user context); the structural fix has to be structural.

### 5.2 Edge cases

- **Architect re-dispatch mid-brainstorm.** Brainstorm step 3 allows main agent to re-dispatch the Architect with a focused question. When the answer comes back, the same briefing rule applies — main agent briefs the user on what the Architect found (recommended adjustment, rationale, new tradeoffs) before continuing the dialogue.

- **Trivial-complexity fixes from the bug-fix loop.** When `bug-fix-loop.md` assigns a trivial-complexity tier and routes the fix through Implementer without user input, no briefing is required (no user handoff). The protocol applies only at dispatch-→-user handoffs; dispatch-→-implementer handoffs are out of scope.

- **Backend-only Verify (UI/UX skipped).** No UI/UX dispatch, no UI/UX → user handoff. No briefing for UI/UX-related findings. QA's briefing rule still applies if QA returns BUGS FOUND.

- **Multiple findings in a single auditor report.** Brief on all findings, not a subset. Selectivity is forbidden in PR #6's visual-parity hardening; the same principle applies to the auditor-finding briefings.

- **Subagent re-dispatch after a fix lands.** When `bug-fix-loop.md`'s re-run rules apply (e.g., Reviewer + Security re-run on the full diff after a fix; UI/UX re-runs scoped to affected rows ∩ affected states), the briefing rule applies to the re-run reports too. Each re-run report → user handoff is a fresh briefing opportunity.

### 5.3 What we explicitly don't add

- **No new artifact files.** No `briefing.md` template, no persistent briefing log. The briefing is a user-facing message at the handoff moment.
- **No subagent role-prompt changes.** The existing reports already carry the substance the briefing needs. If a future change to a subagent's output format breaks the briefing's expected inputs, that future change owns the consistency-update.
- **No additional checks in the self-improvement loop.** The protocol's enforcement is upfront (red flags in `SKILL.md`) and at the auditor dispatch points (the per-site cues). Adding a self-improvement-loop check for "did main agent brief?" would be after-the-fact and likely lower-leverage than the upfront enforcement.

## 6. Why this is meaningful

The visual-parity hardening (PR #6's first commit set) prevented a class of UI/UX failures by mandating the matched-element inventory and the main-agent step 6a spot-check. The inventory-as-contract change (PR #6's third commit set) moved inventory construction upstream so UI/UX has a contract to verify rather than discover. Both fix specific failure modes by making the protocol's expectations explicit and structurally enforced.

This change fixes a different failure mode at a different layer: the LLM orchestrator skipping the bridge work between subagent context and user context. The bug is invisible from the workflow diagram — every dispatch-→-user step "works" in the sense that the user gets asked something — but the question is ill-formed because the user lacks the context to answer it.

The principle ("the user must enter the dialogue with the same context the subagent had") is one sentence; the protocol that operationalizes it is one new section in `SKILL.md` plus seven per-site cues. Cheap to add, durable in effect, and applies uniformly across every phase that involves user input.
