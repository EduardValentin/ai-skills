# Dispatch → User Briefing Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encode a uniform briefing protocol so main agent always bridges subagent context → user context before any dispatch-→-user handoff (the failure mode observed during PR #6's execution).

**Architecture:** Two skill-file edits in `skills/ticket-start/`. `SKILL.md` gains a new top-level section (`## Dispatch → user briefing protocol`) defining the principle and four handoff-type content checklists, plus seven per-site cues across existing dispatch steps and two new red flags. `bug-fix-loop.md` gains one cue at the user-intervention-principle section. No subagent role-prompt changes — existing reports already carry the substance the briefing needs.

**Tech Stack:** Markdown skill files only. No scripts, no new artifact files.

**Spec reference:** `docs/superpowers/specs/2026-05-12-dispatch-user-briefing-protocol-design.md`. Read it before starting Task 1.

---

## Plan-level decisions locked

These were settled in the brainstorm and recorded in the spec:

1. **Scope:** all seven dispatch-→-user handoffs in the workflow (Setup clarification, Brainstorm dispatch, Architect re-dispatch, Reviewer FINDINGS, Security FINDINGS, QA BUGS FOUND, UI/UX FINDINGS, bug-fix-loop architectural intervention).
2. **Structure:** central section in `SKILL.md` + brief per-site cues at each dispatch step. Detail lives once; cues remind at each site.
3. **No subagent role-prompt changes.** Existing reports already include rationale/alternatives/tradeoffs/severity/location/suggested-fix. Main agent's job is to relay.
4. **No new artifact files.** Briefings live in the conversation transcript as user-facing messages at handoff moments.
5. **No mode gating.** The protocol applies at every dispatch-→-user handoff regardless of workflow, mode, or phase.
6. **bug-fix-loop.md cue location:** the user-intervention-principle section (where main agent stops and surfaces a judgment call to the user). The architectural-tier handling loops back into Brainstorm where Brainstorm step 2's cue applies.

---

## File structure (what changes)

**Modified files (canonical location):**

| File | Change | Size |
|---|---|---|
| `skills/ticket-start/SKILL.md` | (a) New top-level section `## Dispatch → user briefing protocol` between `## Self-Improvement Loop` and `## Implementation Standards`. (b) Seven per-site cues across Setup step 6, Brainstorm step 2, Brainstorm step 3, Review step 2, Security step 2, Verify step 3, Verify step 6. (c) Two new red flags appended to the existing Red Flags list. | medium (new section ~70 lines + ~30 lines of small edits + 2 red flags) |
| `skills/ticket-start/bug-fix-loop.md` | One cue appended to the `## User intervention principle (always-on)` section. | tiny (+2 lines) |

**Unchanged files:**
- `agents/scoping.md`, `agents/architect.md`, `agents/reviewer.md`, `agents/security.md`, `agents/qa.md`, `agents/ui-ux.md`, `agents/openai.yaml` — no role-prompt changes.
- `self-improvement.md`, `job-workflow.md`, `personal-workflow.md`, `react-parity.md`, `verification.md` — orthogonal.
- `scripts/extract-element-style.browser.js` — unchanged.

**Sync to install dirs:** each modification syncs to `~/.codex/skills/ticket-start/` and `~/.claude/skills/ticket-start/` in the same task (per AGENTS.md rule 2).

---

## Tasks

### Task 1: Add the central `## Dispatch → user briefing protocol` section to `SKILL.md`

**Files:**
- Modify: `skills/ticket-start/SKILL.md` — single edit inserting the new section
- Sync: both install dirs

- [ ] **Step 1: Insert the new section between `## Self-Improvement Loop` and `## Implementation Standards`**

Use the `Edit` tool. Find this exact block in `skills/ticket-start/SKILL.md`:

```
## Self-Improvement Loop

After **each** auditor agent (Reviewer, Security, QA, UI/UX) returns a CLEAN report (or after a CHANGES-REQUIRED report becomes CLEAN through the bug-fix loop), run the rule-extraction pass per `self-improvement.md`. That file defines:
- Rule promotion bar (pattern-based, high-cost, declarative, non-stylistic, non-duplicate).
- Repo-specific vs universal classification.
- Destinations: repo `AGENTS.md` (separate commit, same PR) for repo-specific; both `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` (kept in sync) for universal.
- Mandatory user-approval gate per rule.

## Implementation Standards
```

Replace with:

```
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
```

- [ ] **Step 2: Verify the new section landed correctly**

```bash
grep -q "^## Dispatch → user briefing protocol$" skills/ticket-start/SKILL.md && echo "Section header ✓"
grep -q "the user must enter the dialogue with the same context the subagent had" skills/ticket-start/SKILL.md && echo "Principle statement ✓"
grep -q "^### Handoff type 1 — Scoping → user clarification" skills/ticket-start/SKILL.md && echo "Type 1 ✓"
grep -q "^### Handoff type 2 — Architect → Brainstorm dialogue" skills/ticket-start/SKILL.md && echo "Type 2 ✓"
grep -q "^### Handoff types 3–6 — Auditor" skills/ticket-start/SKILL.md && echo "Types 3-6 ✓"
grep -q "^### Handoff type 7 — Bug-fix loop architectural intervention" skills/ticket-start/SKILL.md && echo "Type 7 ✓"
grep -q "^### Forbidden behaviors (briefing-specific)" skills/ticket-start/SKILL.md && echo "Briefing-forbidden subsection ✓"
```
All seven must pass.

- [ ] **Step 3: Sync to install dirs**

```bash
cp skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
cp skills/ticket-start/SKILL.md ~/.claude/skills/ticket-start/SKILL.md
diff -q skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
diff -q skills/ticket-start/SKILL.md ~/.claude/skills/ticket-start/SKILL.md
```
Both `diff -q` calls must produce no output.

- [ ] **Step 4: Commit**

```bash
git add skills/ticket-start/SKILL.md
git commit -m "$(cat <<'EOF'
ticket-start: add Dispatch → user briefing protocol section to SKILL.md

Introduces a new top-level section in SKILL.md that codifies the rule
main agent must follow at every dispatch-→-user handoff in the
workflow: brief the user on the subagent's substance BEFORE asking
for input, a decision, or a choice. The user must enter the dialogue
with the same context the subagent had.

The section defines four handoff types with per-type content checklists:

  1. Scoping → user clarification (Setup) — quoted conflict + path:line
     evidence + the clarification being asked.
  2. Architect → Brainstorm dialogue — recommended approach + rationale,
     alternatives + tradeoffs, open questions with motivating context,
     Scoping pointers.
  3-6. Auditor (Reviewer/Security/QA/UI/UX) → fix decision — findings
     with severity/location/description, suggested fix, complexity tier,
     architectural tradeoff (when applicable).
  7. Bug-fix loop architectural intervention — types 3-6 content +
     architectural tradeoff before user decides on direction.

Plus a briefing-specific forbidden-behaviors subsection.

Per-site cues at each dispatch step land in Task 2; bug-fix-loop.md
cue lands in Task 3.

Spec: docs/superpowers/specs/2026-05-12-dispatch-user-briefing-protocol-design.md
§4.1.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add seven per-site cues and two red flags to `SKILL.md`

**Files:**
- Modify: `skills/ticket-start/SKILL.md` — nine Edit operations (7 cues + 2 red flags)
- Sync: both install dirs

- [ ] **Step 1: Setup step 6 — append briefing cue**

Use the `Edit` tool. Find this exact block:

```
6. **Clarifications.** If acceptance criteria are missing, vague, or not testable, stop and ask before continuing. If the Scoping report surfaces a conflict between the ticket and existing architecture, surface the conflict before brainstorming. Ask concise clarifying questions when material ambiguity remains after Scoping.
```

Replace with:

```
6. **Clarifications.** If acceptance criteria are missing, vague, or not testable, stop and ask before continuing. If the Scoping report surfaces a conflict between the ticket and existing architecture, surface the conflict before brainstorming. Ask concise clarifying questions when material ambiguity remains after Scoping. Before asking the user any clarifying question, brief per `## Dispatch → user briefing protocol` (handoff type 1: Scoping → user clarification).
```

- [ ] **Step 2: Brainstorm step 2 — rewrite for explicit briefing**

Use the `Edit` tool. Find this exact block:

```
2. **Run `superpowers:brainstorming` with the user.** Use the Architect's proposals as the starting material. Standard one-question-at-a-time dialogue. Converge on a chosen direction.
```

Replace with:

```
2. **Brief per `## Dispatch → user briefing protocol` (handoff type 2: Architect → Brainstorm dialogue), then run `superpowers:brainstorming` with the user.** Brief BEFORE the first brainstorming question — present the Architect's recommended approach + rationale, alternatives + tradeoffs, and any open questions with their motivating context, as a single message. Only after this synthesis is in the user's view, start the standard one-question-at-a-time dialogue. Converge on a chosen direction.
```

- [ ] **Step 3: Brainstorm step 3 — append re-dispatch briefing cue**

Use the `Edit` tool. Find this exact block:

```
3. **On-demand re-dispatch.** If a follow-up architectural question arises mid-brainstorm that the original proposals didn't cover, re-dispatch the Architect with the focused question (per `agents/architect.md`'s follow-up handling) and bring the answer back into the conversation.
```

Replace with:

```
3. **On-demand re-dispatch.** If a follow-up architectural question arises mid-brainstorm that the original proposals didn't cover, re-dispatch the Architect with the focused question (per `agents/architect.md`'s follow-up handling) and bring the answer back into the conversation. When you bring the re-dispatched Architect's answer back, brief the user on what the Architect found (recommended adjustment + rationale + any new tradeoffs) before continuing the brainstorming dialogue.
```

- [ ] **Step 4: Review step 2 — rewrite for briefing cue**

Use the `Edit` tool. Find this exact line in the Review section:

```
2. **If Reviewer returns CHANGES REQUIRED**, route through `bug-fix-loop.md`.
```

Replace with:

```
2. **If Reviewer returns CHANGES REQUIRED**, brief the user per `## Dispatch → user briefing protocol` (handoff types 3–6: auditor → fix decision) before routing through `bug-fix-loop.md`.
```

- [ ] **Step 5: Security step 2 — rewrite for briefing cue**

Use the `Edit` tool. Find this exact line in the Security section:

```
2. **If Security returns CHANGES REQUIRED**, route through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **Reviewer + Security re-run on the full diff**.
```

Replace with:

```
2. **If Security returns CHANGES REQUIRED**, brief the user per `## Dispatch → user briefing protocol` (handoff types 3–6: auditor → fix decision) before routing through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **Reviewer + Security re-run on the full diff**.
```

- [ ] **Step 6: Verify step 3 (QA) — rewrite for briefing cue**

Use the `Edit` tool. Find this exact line in the Verify section:

```
3. **If QA returns BUGS FOUND**, route through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **QA re-runs the full behavior pass**.
```

Replace with:

```
3. **If QA returns BUGS FOUND**, brief the user per `## Dispatch → user briefing protocol` (handoff types 3–6: auditor → fix decision) before routing through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **QA re-runs the full behavior pass**.
```

- [ ] **Step 7: Verify step 6 (UI/UX) — rewrite for briefing cue**

Use the `Edit` tool. Find this exact line in the Verify section:

```
6. **If UI/UX returns FINDINGS**, route through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **UI/UX re-runs scoped to affected states**.
```

Replace with:

```
6. **If UI/UX returns FINDINGS**, brief the user per `## Dispatch → user briefing protocol` (handoff types 3–6: auditor → fix decision) before routing through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **UI/UX re-runs scoped to affected states**.
```

- [ ] **Step 8: Append two new red flags to the Red Flags list**

Use the `Edit` tool. Find this exact block:

```
- UI/UX returns a verified inventory with rows that have blank `font-*`, `color/bg`, `box`, `layout`, `size`, or `verdict` cells. The DOM-evaluation work was skipped for those rows; reject the verdict at step 6a.
- Using the `superpowers:executing-plans` fallback path and skipping `superpowers:requesting-code-review` before advancing to Review — that path has no other end-of-feature review.
```

Replace with:

```
- UI/UX returns a verified inventory with rows that have blank `font-*`, `color/bg`, `box`, `layout`, `size`, or `verdict` cells. The DOM-evaluation work was skipped for those rows; reject the verdict at step 6a.
- Starting a brainstorming dialogue, a clarification question, or a fix-decision request to the user without first presenting the relevant subagent's synthesis (per `## Dispatch → user briefing protocol`). The user must enter the conversation with the same context the subagent had.
- Routing an auditor's findings through bug-fix-loop's architectural-intervention path without surfacing the architectural tradeoff to the user.
- Using the `superpowers:executing-plans` fallback path and skipping `superpowers:requesting-code-review` before advancing to Review — that path has no other end-of-feature review.
```

- [ ] **Step 9: Verify all seven cues + two red flags**

```bash
grep -q "Before asking the user any clarifying question, brief per .## Dispatch → user briefing protocol. (handoff type 1" skills/ticket-start/SKILL.md && echo "Setup cue ✓"
grep -q "^2\. \*\*Brief per .## Dispatch → user briefing protocol. (handoff type 2" skills/ticket-start/SKILL.md && echo "Brainstorm step 2 cue ✓"
grep -q "When you bring the re-dispatched Architect.s answer back, brief the user" skills/ticket-start/SKILL.md && echo "Brainstorm step 3 cue ✓"
grep -q "If Reviewer returns CHANGES REQUIRED\*\*, brief the user per" skills/ticket-start/SKILL.md && echo "Review cue ✓"
grep -q "If Security returns CHANGES REQUIRED\*\*, brief the user per" skills/ticket-start/SKILL.md && echo "Security cue ✓"
grep -q "If QA returns BUGS FOUND\*\*, brief the user per" skills/ticket-start/SKILL.md && echo "QA cue ✓"
grep -q "If UI/UX returns FINDINGS\*\*, brief the user per" skills/ticket-start/SKILL.md && echo "UI/UX cue ✓"
grep -q "Starting a brainstorming dialogue, a clarification question, or a fix-decision request" skills/ticket-start/SKILL.md && echo "Red flag 1 ✓"
grep -q "Routing an auditor.s findings through bug-fix-loop.s architectural-intervention path without surfacing" skills/ticket-start/SKILL.md && echo "Red flag 2 ✓"
```
All nine must pass.

- [ ] **Step 10: Sync to install dirs**

```bash
cp skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
cp skills/ticket-start/SKILL.md ~/.claude/skills/ticket-start/SKILL.md
diff -q skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
diff -q skills/ticket-start/SKILL.md ~/.claude/skills/ticket-start/SKILL.md
```
Both `diff -q` calls must produce no output.

- [ ] **Step 11: Commit**

```bash
git add skills/ticket-start/SKILL.md
git commit -m "$(cat <<'EOF'
ticket-start: SKILL.md adds 7 dispatch-site briefing cues + 2 red flags

Each dispatch-→-user handoff in SKILL.md gains a one-sentence cue
pointing at the central briefing protocol (added in the prior
commit). Sites:

  - Setup step 6 (Scoping → user clarification)
  - Brainstorm step 2 (Architect → Brainstorm dialogue, rewritten
    to brief BEFORE the first brainstorming question)
  - Brainstorm step 3 (Architect re-dispatch — brief on what the
    re-dispatch returned before continuing dialogue)
  - Review step 2 (Reviewer CHANGES REQUIRED → fix decision)
  - Security step 2 (Security CHANGES REQUIRED → fix decision)
  - Verify step 3 (QA BUGS FOUND → fix decision)
  - Verify step 6 (UI/UX FINDINGS → fix decision)

Two new red flags appended to the Red Flags list:

  - Starting a brainstorming dialogue, clarification question, or
    fix-decision request without first presenting the subagent's
    synthesis. The user must enter the conversation with the same
    context the subagent had.
  - Routing auditor findings through bug-fix-loop's architectural-
    intervention path without surfacing the architectural tradeoff.

bug-fix-loop.md cue (handoff type 7) lands in Task 3.

Spec: docs/superpowers/specs/2026-05-12-dispatch-user-briefing-protocol-design.md
§4.1.2 and §4.1.3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Add briefing cue to `bug-fix-loop.md`

**Files:**
- Modify: `skills/ticket-start/bug-fix-loop.md` — one Edit operation
- Sync: both install dirs

- [ ] **Step 1: Append briefing cue to the User intervention principle section**

Use the `Edit` tool. Find this exact block:

```
## User intervention principle (always-on)

At **any** point in the loop — not just at the cap — if the main agent hits a judgment call, blocker, ambiguity, or environmental issue that exceeds its authority to decide, the workflow **stops** and surfaces. The main agent does not guess on the user's behalf. Surfaces include:

- Conflict between two agents' findings (e.g., Reviewer suggests A, Security suggests not-A).
- Ambiguous classification of fix tier when the architectural impact is unclear after honest assessment.
- Environmental blocker that cannot be diagnosed from the session (e.g., dev server crashes with no obvious cause).
- A finding that requires changing the ticket's scope.
```

Replace with:

```
## User intervention principle (always-on)

At **any** point in the loop — not just at the cap — if the main agent hits a judgment call, blocker, ambiguity, or environmental issue that exceeds its authority to decide, the workflow **stops** and surfaces. The main agent does not guess on the user's behalf. Surfaces include:

- Conflict between two agents' findings (e.g., Reviewer suggests A, Security suggests not-A).
- Ambiguous classification of fix tier when the architectural impact is unclear after honest assessment.
- Environmental blocker that cannot be diagnosed from the session (e.g., dev server crashes with no obvious cause).
- A finding that requires changing the ticket's scope.

When surfacing to the user, brief per `SKILL.md` → `## Dispatch → user briefing protocol` (handoff type 7: bug-fix loop architectural intervention) before asking the user to decide on direction. Present the relevant finding(s), the auditor's suggested fix if any, and the architectural tradeoff main agent sees, so the user can weigh in with the same context main agent has.
```

- [ ] **Step 2: Verify the cue landed**

```bash
grep -q "When surfacing to the user, brief per .SKILL.md. → .## Dispatch → user briefing protocol. (handoff type 7" skills/ticket-start/bug-fix-loop.md && echo "Bug-fix-loop cue ✓"
```
Must pass.

- [ ] **Step 3: Sync to install dirs**

```bash
cp skills/ticket-start/bug-fix-loop.md ~/.codex/skills/ticket-start/bug-fix-loop.md
cp skills/ticket-start/bug-fix-loop.md ~/.claude/skills/ticket-start/bug-fix-loop.md
diff -q skills/ticket-start/bug-fix-loop.md ~/.codex/skills/ticket-start/bug-fix-loop.md
diff -q skills/ticket-start/bug-fix-loop.md ~/.claude/skills/ticket-start/bug-fix-loop.md
```
Both `diff -q` calls must produce no output.

- [ ] **Step 4: Commit**

```bash
git add skills/ticket-start/bug-fix-loop.md
git commit -m "$(cat <<'EOF'
ticket-start: bug-fix-loop.md cues briefing protocol at user-intervention

Appends a sentence to the User intervention principle (always-on)
section: when the loop surfaces a judgment call to the user, main
agent briefs per SKILL.md's Dispatch → user briefing protocol
(handoff type 7) before asking for direction. Present finding(s),
suggested fix (if any), and architectural tradeoff so the user has
the same context main agent has.

This closes the last dispatch-→-user handoff in the workflow: every
user-facing decision in ticket-start now has an explicit briefing
obligation, with content defined in SKILL.md's central section.

Spec: docs/superpowers/specs/2026-05-12-dispatch-user-briefing-protocol-design.md
§4.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Lint + cross-reference verification

**Files:**
- Verify (read-only): `skills/ticket-start/SKILL.md`, `skills/ticket-start/bug-fix-loop.md`, both install dirs
- No commit (verification only)

- [ ] **Step 1: All seven dispatch sites have briefing cues**

```bash
echo "=== Setup step 6 ===" && grep -q "Before asking the user any clarifying question, brief per .## Dispatch → user briefing protocol. (handoff type 1" skills/ticket-start/SKILL.md && echo "✓" || echo "✗"
echo "=== Brainstorm step 2 ===" && grep -q "^2\. \*\*Brief per .## Dispatch → user briefing protocol. (handoff type 2" skills/ticket-start/SKILL.md && echo "✓" || echo "✗"
echo "=== Brainstorm step 3 ===" && grep -q "When you bring the re-dispatched Architect.s answer back, brief the user" skills/ticket-start/SKILL.md && echo "✓" || echo "✗"
echo "=== Review step 2 ===" && grep -q "If Reviewer returns CHANGES REQUIRED\*\*, brief the user per" skills/ticket-start/SKILL.md && echo "✓" || echo "✗"
echo "=== Security step 2 ===" && grep -q "If Security returns CHANGES REQUIRED\*\*, brief the user per" skills/ticket-start/SKILL.md && echo "✓" || echo "✗"
echo "=== Verify step 3 (QA) ===" && grep -q "If QA returns BUGS FOUND\*\*, brief the user per" skills/ticket-start/SKILL.md && echo "✓" || echo "✗"
echo "=== Verify step 6 (UI/UX) ===" && grep -q "If UI/UX returns FINDINGS\*\*, brief the user per" skills/ticket-start/SKILL.md && echo "✓" || echo "✗"
echo "=== bug-fix-loop.md user-intervention cue ===" && grep -q "When surfacing to the user, brief per .SKILL.md. → .## Dispatch → user briefing protocol. (handoff type 7" skills/ticket-start/bug-fix-loop.md && echo "✓" || echo "✗"
```
Expected: every line ends `✓`.

- [ ] **Step 2: Central section is reachable from every cue**

The cues reference these anchors:
- `## Dispatch → user briefing protocol` (the section header)
- `(handoff type 1: Scoping → user clarification)` through `(handoff type 7: bug-fix loop architectural intervention)`

```bash
grep -q "^## Dispatch → user briefing protocol$" skills/ticket-start/SKILL.md && echo "Section header reachable ✓"
grep -q "^### Handoff type 1 — Scoping → user clarification" skills/ticket-start/SKILL.md && echo "Type 1 anchor ✓"
grep -q "^### Handoff type 2 — Architect → Brainstorm dialogue" skills/ticket-start/SKILL.md && echo "Type 2 anchor ✓"
grep -q "^### Handoff types 3–6 — Auditor" skills/ticket-start/SKILL.md && echo "Types 3–6 anchor ✓"
grep -q "^### Handoff type 7 — Bug-fix loop architectural intervention" skills/ticket-start/SKILL.md && echo "Type 7 anchor ✓"
```
Expected: every line ends `✓`.

- [ ] **Step 3: Red flags are in place**

```bash
grep -q "Starting a brainstorming dialogue, a clarification question, or a fix-decision request" skills/ticket-start/SKILL.md && echo "Red flag 1 ✓"
grep -q "Routing an auditor.s findings through bug-fix-loop.s architectural-intervention path without surfacing" skills/ticket-start/SKILL.md && echo "Red flag 2 ✓"
```
Expected: both pass.

- [ ] **Step 4: No-placeholder scan**

```bash
grep -rnE '\b(TBD|FIXME|XXX|implement later|fill in details)\b' skills/ticket-start/ 2>/dev/null \
  | grep -v 'self-improvement.md' \
  | grep -v 'No "TBD", no "n/a", no blank cells' \
  || echo "no placeholders found ✓"
```
Expected: `no placeholders found ✓` (or empty).

- [ ] **Step 5: Host-purity check**

```bash
grep -rnE 'mcp__playwright|Playwright MCP|browser-use:browser|iab |Codex Browser plugin|browser_evaluate|browser_take_screenshot|browser_tabs' skills/ticket-start/ 2>/dev/null \
  && echo "✗ host-purity violation" \
  || echo "host-pure ✓"
```
Expected: `host-pure ✓`.

- [ ] **Step 6: Install-path sync**

```bash
for f in $(find skills/ticket-start -type f | sed 's|^skills/ticket-start/||'); do
  diff -q "skills/ticket-start/$f" "$HOME/.codex/skills/ticket-start/$f"
  diff -q "skills/ticket-start/$f" "$HOME/.claude/skills/ticket-start/$f"
done
echo "(empty above = all in sync ✓)"
```
Expected: every `diff -q` produces no output.

- [ ] **Step 7: AGENTS.md self-review checklist**

```bash
echo "=== Agent tool names in prose (must be only natural English) ==="
grep -nE '\b(Read|Write|Edit|MultiEdit|str_replace|ask_user_input_v0|TodoWrite|WebFetch|WebSearch|Glob|Grep|Bash)\b' skills/ticket-start/*.md skills/ticket-start/agents/*.md 2>/dev/null \
  | grep -vE 'Read access|Read the|Read only|Read this|Reads|re-read|Re-read|Read-only|natural language'
echo "(only natural-English occurrences should remain)"
echo "=== Fallback chain + ## Requires still present in qa.md + ui-ux.md ==="
grep -l "Fallback chain" skills/ticket-start/agents/qa.md skills/ticket-start/agents/ui-ux.md
grep -l "^## Requires$" skills/ticket-start/agents/qa.md skills/ticket-start/agents/ui-ux.md
```
Expected: agent-tool-names grep produces only natural-English occurrences; both fallback-chain and Requires files listed.

- [ ] **Step 8: No commit (verification only)**

This task produces no file changes. If any check failed, return to Task 1, 2, or 3 and fix the source.

---

### Task 5: Update PR #6 description

**Files:**
- None directly. Edits PR #6 description on GitHub.

- [ ] **Step 1: Confirm working tree clean and commits are present**

```bash
git status
```
Expected: `nothing to commit, working tree clean`.

```bash
git log origin/main..HEAD --oneline | head -20
```
Expected: 4 new commits since the previous round (1 spec + 3 implementation tasks) on top of the existing branch history.

- [ ] **Step 2: Push the branch**

```bash
git push origin ticket-start-visual-parity-enforcement
```
Expected: push succeeds (or "Everything up-to-date" if commits were already pushed inline by previous flows).

- [ ] **Step 3: Update PR #6 description**

```bash
gh pr edit 6 --body "$(cat <<'EOF'
## Summary

This PR lands four coordinated changes to the `ticket-start` skill:

1. **Visual-parity enforcement** — after a real personal-workflow ticket shipped with substantial prototype-vs-production visual differences and the UI/UX subagent reported "Visual findings: None," we tightened the protocol to make the failure mode structurally impossible (mandatory + exhaustive inventory, four completeness rules, main-agent step 6a, prototype-parity dominance).

2. **Canonical-skill migration** — consolidated the legacy duplicated layout (`codex/skills/ticket-start/` + `claude/skills/ticket-start/`) into a single canonical `skills/ticket-start/`, per the AGENTS.md repo + authoring rules from PR #5. All product/tool references swapped to intent-level capability language; fallback chains added; non-trivial extraction logic moved to `scripts/`.

3. **Inventory-as-contract** — moved matched-element-inventory construction upstream from UI/UX into Scoping (prototype side) + Plan (production-side mapping) + main agent at Verify dispatch (stitched table). UI/UX's role narrows from discovery+verification to verification of a supplied inventory. Step 6a now cross-checks expected vs verified inventories. Activated only in parity mode.

4. **Dispatch → user briefing protocol** — codifies the rule that main agent must brief the user with a synthesis of the subagent's substance BEFORE asking for any input, decision, or choice. Applies uniformly to all seven dispatch-→-user handoff points in the workflow (Setup clarification, Brainstorm dispatch, Architect re-dispatch, Reviewer/Security/QA/UI/UX → fix decisions, bug-fix-loop architectural intervention). Closes the failure mode where main agent asked the user to pick between options the user had never seen.

### Dispatch-→-user briefing changes (this commit set)

- **`SKILL.md`** — new top-level section `## Dispatch → user briefing protocol` defining the principle + four handoff-type content checklists + briefing-specific forbidden behaviors.
- **`SKILL.md`** — seven per-site cues across Setup step 6, Brainstorm step 2 (rewritten), Brainstorm step 3, Review step 2, Security step 2, Verify step 3, Verify step 6.
- **`SKILL.md`** — two new red flags codifying the failure mode.
- **`bug-fix-loop.md`** — one cue in the User intervention principle section pointing at handoff type 7.

No subagent role-prompt changes; the existing reports already carry the substance the briefing needs.

### Self-review checklist (per AGENTS.md "Rules for Writing Cross-Agent Skills")

- [x] No specific agent tool names in prose.
- [x] Non-trivial logic in `scripts/`.
- [x] Fallback chain for live-browser capability documented in `agents/qa.md` and `agents/ui-ux.md`.
- [x] Required capabilities declared at the top of subagent role prompts.
- [ ] Skill has been run end-to-end on at least one target agent — empirical validation happens on the next ticket.
- [x] No copy of this skill exists for a different agent.
- [x] No adapter files (or `agents/openai.yaml` interpreted as one: 4 lines, well under 30).
- [x] Synced to both `~/.codex/skills/ticket-start/` and `~/.claude/skills/ticket-start/`.

### Specs and plans

- Visual-parity spec: `docs/superpowers/specs/2026-05-11-visual-parity-enforcement-design.md`.
- Visual-parity plan: `docs/superpowers/plans/2026-05-11-visual-parity-enforcement.md`.
- Inventory-as-contract spec: `docs/superpowers/specs/2026-05-12-inventory-as-contract-design.md`.
- Inventory-as-contract plan: `docs/superpowers/plans/2026-05-12-inventory-as-contract.md`.
- Dispatch-user-briefing-protocol spec: `docs/superpowers/specs/2026-05-12-dispatch-user-briefing-protocol-design.md`.
- Dispatch-user-briefing-protocol plan: `docs/superpowers/plans/2026-05-12-dispatch-user-briefing-protocol.md`.

## Test plan

This change is in skill files (markdown only). Behavioral validation happens on the next ticket. Until then:

- [x] Canonical tree is host-pure (zero product/tool-name hits).
- [x] All cross-refs resolve.
- [x] Install-path sync clean for both `~/.codex/skills/ticket-start/` and `~/.claude/skills/ticket-start/`.
- [x] AGENTS.md self-review checklist re-runs clean after each set of changes.
- [x] All seven dispatch-site briefing cues present in SKILL.md.
- [x] bug-fix-loop.md cue present at the User intervention principle section.
- [ ] On the next ticket: confirm main agent briefs the user on the Architect's proposals before starting the brainstorming dialogue.
- [ ] On the next ticket with auditor findings: confirm main agent briefs the user on findings + suggested fix + complexity tier before routing through `bug-fix-loop.md`.
- [ ] Force-test: deliberately produce an Architect report with multiple proposals and observe whether main agent presents the synthesis BEFORE the first brainstorming question.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR description updated successfully.

- [ ] **Step 4: Final summary to user**

Produce a short closeout summary covering:
- PR URL (still PR #6).
- Commits added in this round (4: 1 spec + 3 implementation tasks).
- Total commits on the branch.
- What is **not** verified by this plan: runtime behavior on a real ticket. The briefing protocol is hardened at the skill-file level; whether main agent actually changes its behavior is empirical and only the next real ticket can confirm.
- Next steps for the user: review PR #6, optionally test on a real ticket.

---

## Self-review

### 1. Spec coverage

Mapping each spec section to a task:

- **§1 Problem statement + §2 Goals/non-goals** — captured in the plan header (Goal, Architecture). ✓
- **§3 Architectural decisions** — encoded in Tasks 1-3. Scope (wide): all 7 dispatch points addressed (Tasks 2 + 3). Structure (central + per-site cues): Task 1 = central section; Task 2 = SKILL.md per-site cues; Task 3 = bug-fix-loop.md cue. ✓
- **§4.1.1 Central section** — Task 1 step 1. ✓
- **§4.1.2 Per-site cues** — Task 2 steps 1-7. ✓
- **§4.1.3 Two red flags** — Task 2 step 8. ✓
- **§4.2 bug-fix-loop.md touch** — Task 3 step 1. ✓
- **§4.3 Files that don't change** — no tasks for them by design. ✓
- **§5.1 Activation gate** — no gating; protocol applies everywhere. Built into the central section's wording in Task 1. ✓
- **§5.2 Edge cases** — covered by the central section's content (Architect re-dispatch is Brainstorm step 3's cue in Task 2; trivial fixes don't trigger user handoff so no cue; backend-only Verify naturally skips UI/UX so no cue; multi-finding briefings handled by handoff types 3-6's "one per line" format; re-run reports get fresh briefings because each handoff is a fresh briefing opportunity). ✓
- **§5.3 What we don't add** — no tasks add them by design. ✓
- **§6 Why this is meaningful** — captured in the plan header (Goal, Architecture). ✓

No spec gaps.

### 2. Placeholder scan

I searched the plan for: TBD, FIXME, XXX, "implement later," "fill in details," "Similar to Task N." The only `<placeholder>` style tokens are intentional substitution markers in file content (e.g., `<ticket title>`, `<one-line summary>`) — same convention as prior plans. No real TBDs in instruction-bearing parts.

### 3. Type / name consistency

Cross-checked names used across tasks:

- Section name: `## Dispatch → user briefing protocol` — used consistently in Task 1 (section header), Task 2 (all 7 cues), Task 3 (bug-fix-loop cue), Task 4 (verification grep).
- Handoff type labels: "handoff type 1" through "handoff type 7" — used consistently across the spec and all per-site cues.
- Section subheading names: `### Handoff type 1 — Scoping → user clarification`, `### Handoff type 2 — Architect → Brainstorm dialogue`, `### Handoff types 3–6 — Auditor (...) → fix decision`, `### Handoff type 7 — Bug-fix loop architectural intervention`, `### Forbidden behaviors (briefing-specific)` — used consistently in Task 1 and Task 4's reachability check.
- File paths: `skills/ticket-start/SKILL.md` and `skills/ticket-start/bug-fix-loop.md` — consistent across all tasks.
- Mirror paths: `~/.codex/skills/ticket-start/` and `~/.claude/skills/ticket-start/` — consistent.
- Dispatch step numbers in SKILL.md: Setup step 6, Brainstorm step 2, Brainstorm step 3, Review step 2, Security step 2, Verify step 3, Verify step 6 — matches the current numbering in SKILL.md (verified against the prior task's reads).

No inconsistencies found.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-12-dispatch-user-briefing-protocol.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, two-stage review (spec compliance + code quality), continuous execution. Best fit here: 3 implementation tasks, all small or medium (one of them has 9 substeps in one file — that's the heaviest), well-specified.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batched with checkpoints. Faster wallclock; less isolation between tasks.

**Which approach?**
