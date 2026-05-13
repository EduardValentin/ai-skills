# Pre-Architect Understanding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a proactive pre-Architect understanding dialogue to Setup (new step 7), trim Setup steps 1-2 to workflow-specific bits, and split the misnamed "Brainstorm" phase into `Solution Exploration` + `Brainstorm` — so Architect proposes against richer context and each phase contains exactly one type of activity.

**Architecture:** Two skill-file edits. `skills/ticket-start/SKILL.md` gains Setup step 7 (proactive pre-Architect user dialogue with auto-trigger wording), gets its Setup steps 1-2 trimmed, has its `## Brainstorm` section split into `## Solution Exploration` + `## Brainstorm`, has its Overview prose + Phase Order block updated for the 9-phase order, and has its briefing-protocol handoff type 1 wording broadened to cover both reactive (step 6) and proactive (step 7) user dialogues. `skills/ticket-start/agents/architect.md` gains one new input bullet (the pre-Architect brainstorm summary).

**Tech Stack:** Markdown skill files only. No scripts, no new artifact files, no new subagents.

**Spec reference:** `docs/superpowers/specs/2026-05-13-pre-architect-understanding-design.md`. Read it before starting Task 1.

---

## Plan-level decisions locked

Settled in the brainstorm and recorded in the spec:

1. **Setup step placement:** new step 7 after Clarifications (step 6). Setup becomes 7 steps.
2. **Setup steps 1-2:** trimmed to workflow-specific discipline only (drop reminders about host-platform defaults).
3. **Phase rename:** `Brainstorm` (today, 4 steps) splits into `Solution Exploration` (1 step — Architect dispatch) and `Brainstorm` (3 steps — user-facing convergence + on-demand re-dispatch + convergence-not-plan-approval). Phase order becomes 9 phases.
4. **On-demand Architect re-dispatch** lives in the new `Brainstorm` phase, not in `Solution Exploration`. The trigger fires during the user dialogue; the instruction lives where its trigger lives.
5. **Architect role prompt** gains exactly one new input bullet (the pre-Architect brainstorm summary). No other changes to Architect's role prompt; no changes to other subagent role prompts.
6. **Auto-trigger discipline:** both Setup step 7 and Brainstorm step 1 use intent-language wording that auto-fires `superpowers:brainstorming` via its description. No explicit "Run X" invocations in the prose. Today's explicit "Run `superpowers:brainstorming`" wording (which didn't fire on the originating ticket) is replaced with intent-language.
7. **No mode gating.** Setup step 7 runs for every ticket regardless of workflow (job/personal) or UI/UX mode (parity/consistency).
8. **No new artifacts.** Brainstorm summary lives in the dispatch payload to Architect, ephemeral.

---

## File structure (what changes)

**Modified files:**

| File | Change | Size |
|---|---|---|
| `skills/ticket-start/SKILL.md` | (a) Overview prose: phase list 8→9 phases. (b) Phase Order block: ASCII art + numbered list 8→9 phases. (c) Setup step 1: trim. (d) Setup step 2: trim. (e) Setup step 7: NEW (~25 lines). (f) Split `## Brainstorm` into `## Solution Exploration` + `## Brainstorm`. (g) Briefing-protocol handoff type 1 wording: broaden to cover both reactive (step 6) and proactive (step 7) dialogues. | medium-large (~70 lines net change across 7 edits) |
| `skills/ticket-start/agents/architect.md` | One new input bullet appended to the Inputs section (the pre-Architect brainstorm summary). | tiny (~3 lines) |

**Unchanged files:** every other file in `skills/ticket-start/` (scoping.md, reviewer.md, security.md, qa.md, ui-ux.md, openai.yaml, bug-fix-loop.md, self-improvement.md, verification.md, job-workflow.md, personal-workflow.md, react-parity.md, scripts/extract-element-style.browser.js).

**Sync to install dirs:** every modification syncs to `~/.codex/skills/ticket-start/` and `~/.claude/skills/ticket-start/` in the same task (per AGENTS.md rule 2).

---

## Tasks

### Task 1: Trim Setup steps 1 and 2 in `SKILL.md`

**Files:**
- Modify: `skills/ticket-start/SKILL.md` — two Edit operations
- Sync: both install dirs

- [ ] **Step 1: Trim Setup step 1**

Use the `Edit` tool. Find this exact block:

```
1. **Worktree first.** Before reading the ticket body, before exploring code, create an isolated worktree from the freshest remote default branch. Do not work in the primary checkout. Identifying which workflow applies (Job vs Personal) requires only knowing the ticket's source system, not its contents — that minimal awareness is allowed before the worktree is in place.
   - Detect the upstream default branch (`main` or `master`).
   - `git fetch origin` to refresh remotes.
   - Base the new worktree off `origin/<default>`, not the local branch.
   - **REQUIRED SUB-SKILL:** `superpowers:using-git-worktrees` for the exact procedure and safety checks.
   - If `git fetch` fails, surface the blocker and stop. Do not silently fall back to a stale local branch.
```

Replace with:

```
1. **Worktree discipline.** REQUIRED SUB-SKILL: `superpowers:using-git-worktrees`. Base the worktree off `origin/<default>` (not the local branch). Halt on `git fetch` failure — do not fall back to stale local state.
```

- [ ] **Step 2: Trim Setup step 2**

Use the `Edit` tool. Find this exact line:

```
2. **Repository instructions.** Inside the worktree, read the nearest applicable `AGENTS.md` first, then load only the additional instruction files and project docs that materially affect the task.
```

Replace with:

```
2. **Subagent context discipline.** When dispatching subagents, explicitly forward `AGENTS.md` and any workflow-relevant project docs as inputs — subagent context does not always inherit the main session's auto-loaded files, and explicit forwarding is the host-agnostic discipline.
```

- [ ] **Step 3: Verify**

```bash
grep -q "^1\. \*\*Worktree discipline\.\*\* REQUIRED SUB-SKILL: .superpowers:using-git-worktrees" skills/ticket-start/SKILL.md && echo "Step 1 trimmed ✓"
grep -q "^2\. \*\*Subagent context discipline\.\*\* When dispatching subagents" skills/ticket-start/SKILL.md && echo "Step 2 trimmed ✓"
! grep -q "Before reading the ticket body, before exploring code, create an isolated worktree" skills/ticket-start/SKILL.md && echo "Old step 1 prose removed ✓"
! grep -q "Inside the worktree, read the nearest applicable" skills/ticket-start/SKILL.md && echo "Old step 2 prose removed ✓"
```
All four must pass.

- [ ] **Step 4: Sync to install dirs**

```bash
cp skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
cp skills/ticket-start/SKILL.md ~/.claude/skills/ticket-start/SKILL.md
diff -q skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
diff -q skills/ticket-start/SKILL.md ~/.claude/skills/ticket-start/SKILL.md
```
Both `diff -q` calls must produce no output.

- [ ] **Step 5: Commit**

```bash
git add skills/ticket-start/SKILL.md
git commit -m "$(cat <<'EOF'
ticket-start: trim Setup steps 1-2 to workflow-specific discipline

Today's Setup steps 1 and 2 mix workflow-specific discipline with
reminders about host-platform default behavior (worktree creation
via UI, AGENTS.md auto-load). Trim each to only the workflow-specific
content:

  - Step 1 "Worktree first" → "Worktree discipline": REQUIRED
    SUB-SKILL pointer, base-off-origin rule, halt-on-fetch-failure
    rule. Drops the "before reading the ticket body" sequencing
    reminder (handled at the agent-UI level) and the prose about
    workflow identification.
  - Step 2 "Repository instructions" → "Subagent context
    discipline": names the host-agnostic discipline of explicitly
    forwarding AGENTS.md to dispatched subagents. Drops the
    "read the nearest AGENTS.md" reminder (Claude Code auto-loads
    this; the discipline that matters in the workflow is forwarding
    it to subagents).

Spec: docs/superpowers/specs/2026-05-13-pre-architect-understanding-design.md
§5.1(c)-(d).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add Setup step 7 (pre-Architect understanding) to `SKILL.md`

**Files:**
- Modify: `skills/ticket-start/SKILL.md` — one Edit operation inserting the new step before `## Brainstorm`
- Sync: both install dirs

- [ ] **Step 1: Insert new Setup step 7**

Use the `Edit` tool. Find this exact block (end of step 6 → start of Brainstorm phase):

```
6. **Clarifications.** If acceptance criteria are missing, vague, or not testable, stop and ask before continuing. If the Scoping report surfaces a conflict between the ticket and existing architecture, surface the conflict before brainstorming. Ask concise clarifying questions when material ambiguity remains after Scoping. Before asking the user any clarifying question, brief per `## Dispatch → user briefing protocol` (handoff type 1: Scoping → user clarification).

## Brainstorm
```

Replace with:

```
6. **Clarifications.** If acceptance criteria are missing, vague, or not testable, stop and ask before continuing. If the Scoping report surfaces a conflict between the ticket and existing architecture, surface the conflict before brainstorming. Ask concise clarifying questions when material ambiguity remains after Scoping. Before asking the user any clarifying question, brief per `## Dispatch → user briefing protocol` (handoff type 1: Scoping → user dialogue).

7. **Pre-Architect understanding.** Before the Architect proposes a direction, explore user intent, constraints, and design preferences not captured in the ticket. Pursue a question-driven dialogue with the user covering: implicit preferences ("how should this feel?"), constraints not in the AC ("are there areas of the code we should avoid?"), domain-specific intuitions, design-language preferences, and any unknowns the ticket leaves open. Cover whatever ground the Architect would benefit from before generating proposals.

   Brief per `## Dispatch → user briefing protocol` (handoff type 1: Scoping → user dialogue) before the first question — surface the Scoping report's relevant findings (entry points, target module, prototype elements if any) so the user has the same context the Architect will get.

   Capture the outcome as a short **brainstorm summary** that will be passed to the Architect as a new input in Solution Exploration. The summary covers the user's stated intent, the constraints they surfaced, and any preferences they expressed.

## Brainstorm
```

Note: the existing handoff-type-1 reference in step 6 is updated from "Scoping → user clarification" to "Scoping → user dialogue" — Task 4 broadens the handoff-type-1 wording to cover both reactive (step 6) and proactive (step 7) dialogues, and this rename is the consistent label.

- [ ] **Step 2: Verify**

```bash
grep -q "^7\. \*\*Pre-Architect understanding\.\*\* Before the Architect proposes a direction" skills/ticket-start/SKILL.md && echo "Step 7 present ✓"
grep -q "explore user intent, constraints, and design preferences" skills/ticket-start/SKILL.md && echo "Intent-language trigger ✓"
grep -q "pre-Architect.*brainstorm summary" skills/ticket-start/SKILL.md && echo "Brainstorm-summary reference ✓"
grep -q "handoff type 1: Scoping → user dialogue" skills/ticket-start/SKILL.md && echo "Step 6 + 7 use updated handoff-type-1 label ✓"
! grep -q "handoff type 1: Scoping → user clarification" skills/ticket-start/SKILL.md && echo "Old handoff-type-1 label removed from step 6 ✓"
```
All five must pass.

(The handoff-type-1 description in the central briefing-protocol section still uses the old "Scoping → user clarification" wording at this point; Task 4 updates that. The grep above only checks the per-site cue references, not the central section.)

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
ticket-start: add Setup step 7 — pre-Architect understanding dialogue

New Setup step 7 codifies a proactive question-driven dialogue with
the user BEFORE the Architect proposes a direction. Today's step 6
(Clarifications) is reactive only — it fires when AC is missing or
Scoping flagged a conflict. Step 7 is proactive content gathering:
explore implicit user intent, constraints, design preferences, and
unknowns the ticket doesn't capture. Always runs (no mode gating).

The step's wording uses intent-language matching superpowers:
brainstorming's trigger description ("explore user intent...
design preferences") so the skill auto-fires without an explicit
"Run X" invocation in the prose. This is a deliberate departure
from today's explicit-but-non-firing wording in Brainstorm step 2,
which Task 3 also reworks.

The step produces a "brainstorm summary" — a short markdown
synthesis of stated intent, constraints, and preferences — that
becomes a new input bullet on Architect's role prompt (Task 5 adds
the bullet). Ephemeral, not a persistent artifact file.

The handoff-type-1 references on both step 6 and step 7 use the
broadened label "Scoping → user dialogue" (covering both reactive
and proactive cases). Task 4 updates the central handoff-type-1
description to match.

Spec: docs/superpowers/specs/2026-05-13-pre-architect-understanding-design.md
§5.1(e).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Split `## Brainstorm` into `## Solution Exploration` + `## Brainstorm` (with Overview + Phase Order updates)

**Files:**
- Modify: `skills/ticket-start/SKILL.md` — three Edit operations
- Sync: both install dirs

- [ ] **Step 1: Update the Overview paragraph's phase list**

Use the `Edit` tool. Find this exact string in the Overview paragraph:

```
The skill enforces a strict phase order with explicit gates: Setup → Brainstorm → Plan → Implement → Review → Security → Verify → Ship.
```

Replace with:

```
The skill enforces a strict phase order with explicit gates: Setup → Solution Exploration → Brainstorm → Plan → Implement → Review → Security → Verify → Ship.
```

- [ ] **Step 2: Update the Phase Order block (ASCII art + numbered list)**

Use the `Edit` tool. Find this exact block:

```
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
```

Replace with:

```
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
```

- [ ] **Step 3: Replace the `## Brainstorm` section with `## Solution Exploration` + `## Brainstorm`**

Use the `Edit` tool. Find this exact block (the entire current Brainstorm section, from `## Brainstorm` through step 4):

```
## Brainstorm

1. **Dispatch Architect subagent.** Load the role prompt from `agents/architect.md`. Invoke a subagent with:
   - The ticket and AC.
   - The Scoping report.
   - The repo's `AGENTS.md` / `CLAUDE.md`.
   - The role-prompt content from `agents/architect.md`.
   Wait for the Architect's proposals (2–3 candidate solutions with tradeoffs, per the role-prompt's output format).

2. **Brief per `## Dispatch → user briefing protocol` (handoff type 2: Architect → Brainstorm dialogue), then run `superpowers:brainstorming` with the user.** Brief BEFORE the first brainstorming question — present the Architect's recommended approach + rationale, alternatives + tradeoffs, and any open questions with their motivating context, as a single message. Only after this synthesis is in the user's view, start the standard one-question-at-a-time dialogue. Converge on a chosen direction.

3. **On-demand re-dispatch.** If a follow-up architectural question arises mid-brainstorm that the original proposals didn't cover, re-dispatch the Architect with the focused question (per `agents/architect.md`'s follow-up handling) and bring the answer back into the conversation. When you bring the re-dispatched Architect's answer back, brief the user on what the Architect found (recommended adjustment + rationale + any new tradeoffs) before continuing the brainstorming dialogue.

4. **Convergence is not plan approval.** When the brainstorm converges and the user says "yes, do it," "approved," "go ahead," or similar, that is approval of the *approach*. It is **not** approval of the plan. The plan still has to be written by `superpowers:writing-plans` and re-approved as its own artifact. Do not collapse the two.
```

Replace with:

```
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
```

Note the key changes:
- Old step 2's "then run `superpowers:brainstorming`" is replaced with "then explore the Architect's proposals with the user via a question-driven dialogue" (auto-trigger wording).
- The Architect dispatch in the new `## Solution Exploration` section gains a new input bullet: the pre-Architect brainstorm summary.
- The on-demand re-dispatch moves into the new `## Brainstorm` section as step 2 (where its trigger fires).

- [ ] **Step 4: Verify**

```bash
grep -q "Setup → Solution Exploration → Brainstorm → Plan" skills/ticket-start/SKILL.md && echo "Overview phase list updated ✓"
grep -q "^## Solution Exploration$" skills/ticket-start/SKILL.md && echo "Solution Exploration section header ✓"
grep -c "^## Brainstorm$" skills/ticket-start/SKILL.md | grep -q "^1$" && echo "Exactly one ## Brainstorm section header ✓"
grep -q "pre-Architect.*brainstorm summary.*from Setup step 7" skills/ticket-start/SKILL.md && echo "Architect input bullet for brainstorm summary ✓"
grep -q "explore the Architect's proposals with the user via a question-driven dialogue" skills/ticket-start/SKILL.md && echo "Brainstorm step 1 auto-trigger wording ✓"
! grep -q "then run .superpowers:brainstorming. with the user" skills/ticket-start/SKILL.md && echo "Old explicit Run wording removed ✓"
grep -q "^9\. \*\*Ship\*\*" skills/ticket-start/SKILL.md && echo "Phase 9 numbering present ✓"
```
All seven must pass.

- [ ] **Step 5: Sync to install dirs**

```bash
cp skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
cp skills/ticket-start/SKILL.md ~/.claude/skills/ticket-start/SKILL.md
diff -q skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
diff -q skills/ticket-start/SKILL.md ~/.claude/skills/ticket-start/SKILL.md
```
Both `diff -q` calls must produce no output.

- [ ] **Step 6: Commit**

```bash
git add skills/ticket-start/SKILL.md
git commit -m "$(cat <<'EOF'
ticket-start: split Brainstorm phase into Solution Exploration + Brainstorm

The phase named "Brainstorm" in SKILL.md contained three sub-steps:
Architect dispatch (not a brainstorm), post-Architect user dialogue
(IS a brainstorm), and on-demand Architect re-dispatch (not a
brainstorm). Two out of three activities weren't brainstorms.

This commit splits the phase so each phase contains exactly one
activity type:

  - ## Solution Exploration (1 step) — Architect dispatch only.
    Gains a new input bullet: the pre-Architect brainstorm summary
    from Setup step 7 (added in the prior commit). Architect no
    longer proposes against cold context.

  - ## Brainstorm (3 steps) — user-facing convergence dialogue:
    1. Brief per handoff type 2, then explore Architect's
       proposals via question-driven dialogue. Replaces today's
       explicit "Run superpowers:brainstorming" wording with
       intent-language that auto-fires the skill — the explicit
       wording didn't fire on the originating ticket.
    2. On-demand Architect re-dispatch. Lives in Brainstorm
       because its trigger fires during the user dialogue.
    3. Convergence is not plan approval (moved from old step 4).

Overview prose updated to list 9 phases. Phase Order block
(ASCII art + numbered list) updated to 9 phases with Solution
Exploration as phase 2, Brainstorm as phase 3, and subsequent
phases renumbered (Plan=4, Implement=5, Review=6, Security=7,
Verify=8, Ship=9).

Spec: docs/superpowers/specs/2026-05-13-pre-architect-understanding-design.md
§5.1(a), §5.1(b), §5.1(f).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Broaden briefing-protocol handoff type 1 to cover both reactive and proactive dialogues

**Files:**
- Modify: `skills/ticket-start/SKILL.md` — one Edit operation
- Sync: both install dirs

- [ ] **Step 1: Update handoff-type-1 description in the central briefing-protocol section**

Use the `Edit` tool. Find this exact block:

```
### Handoff type 1 — Scoping → user clarification (Setup)

When Scoping returns with items under `## Conflicts surfaced for main` or with insufficient AC coverage and main agent needs the user to clarify:

- The specific conflict or ambiguity Scoping flagged, quoted from the report.
- The `path:line` evidence Scoping gave (so the user can drill in).
- The clarification main agent is asking for, framed against the surfaced conflict.
```

Replace with:

```
### Handoff type 1 — Scoping → user dialogue (Setup)

When Scoping returns and main agent dispatches a user dialogue — either reactively (Setup step 6: Scoping flagged a conflict, or AC is missing/vague/not testable) or proactively (Setup step 7: pre-Architect understanding):

- The Scoping report's relevant findings (entry points, target module, prototype elements if any), as context for the user.
- For reactive cases (step 6): the specific conflict or ambiguity quoted from the report + the `path:line` evidence Scoping gave (so the user can drill in).
- The clarification or open question main agent is bringing to the dialogue, framed against the surfaced conflict (reactive) or against the Setup-phase context (proactive).
```

- [ ] **Step 2: Verify**

```bash
grep -q "^### Handoff type 1 — Scoping → user dialogue (Setup)$" skills/ticket-start/SKILL.md && echo "Handoff type 1 renamed ✓"
grep -q "either reactively .Setup step 6.* or proactively .Setup step 7" skills/ticket-start/SKILL.md && echo "Handoff type 1 covers both cases ✓"
! grep -q "^### Handoff type 1 — Scoping → user clarification (Setup)$" skills/ticket-start/SKILL.md && echo "Old handoff-type-1 header removed ✓"
```
All three must pass.

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
ticket-start: broaden briefing handoff type 1 to cover proactive Setup step 7

The dispatch-user-briefing-protocol's handoff type 1 was originally
written for the reactive Setup step 6 (Clarifications) — it fired
only when Scoping flagged a conflict or AC was missing. With Setup
step 7 (pre-Architect understanding) added in Task 2, handoff type 1
now also fires proactively at the start of step 7's dialogue.

This commit updates the central handoff-type-1 description in the
## Dispatch → user briefing protocol section:

  - Renamed: "Scoping → user clarification" → "Scoping → user
    dialogue" (a broader label that covers both cases).
  - Expanded trigger: now fires reactively (step 6) or proactively
    (step 7).
  - Content list updated: the Scoping report's findings are surfaced
    as user context in both cases; the conflict-quote + path:line
    evidence is required for reactive cases; the clarification or
    open question framing applies to both.

Setup step 6 and step 7 already reference the new handoff-type-1
label "Scoping → user dialogue" (from Tasks 1-2); this commit
makes the central description match.

Spec: docs/superpowers/specs/2026-05-13-pre-architect-understanding-design.md
§5.1(g) and §6.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Add new input bullet to `agents/architect.md`

**Files:**
- Modify: `skills/ticket-start/agents/architect.md` — one Edit operation
- Sync: both install dirs

- [ ] **Step 1: Read the current `## Inputs you will receive` section**

```bash
grep -n "^## Inputs you will receive$" skills/ticket-start/agents/architect.md
sed -n "/^## Inputs you will receive$/,/^## /p" skills/ticket-start/agents/architect.md | head -25
```

Confirm the section exists and identify the last input bullet — that's where the new bullet will go.

- [ ] **Step 2: Append the new input bullet**

Use the `Edit` tool. Read the current Inputs section first to find the unique last-bullet text, then append the new bullet after it. The exact Edit operation depends on the current last-bullet wording in the file; use a find-string that's unique and ends with the last input bullet, and append the new bullet to the replace-string.

Required new bullet text (must appear verbatim somewhere in the Architect role prompt's Inputs section after this edit):

```
- **Pre-Architect brainstorm summary:** A short markdown synthesis of the user's stated intent, constraints, and preferences surfaced during Setup step 7. Treat this as authoritative on questions the ticket and AC don't cover — it captures what the user expects that wasn't written down.
```

- [ ] **Step 3: Verify**

```bash
grep -q "\\*\\*Pre-Architect brainstorm summary:\\*\\* A short markdown synthesis" skills/ticket-start/agents/architect.md && echo "New input bullet present ✓"
grep -q "captures what the user expects that wasn't written down" skills/ticket-start/agents/architect.md && echo "Bullet body text complete ✓"
```
Both must pass.

- [ ] **Step 4: Sync to install dirs**

```bash
cp skills/ticket-start/agents/architect.md ~/.codex/skills/ticket-start/agents/architect.md
cp skills/ticket-start/agents/architect.md ~/.claude/skills/ticket-start/agents/architect.md
diff -q skills/ticket-start/agents/architect.md ~/.codex/skills/ticket-start/agents/architect.md
diff -q skills/ticket-start/agents/architect.md ~/.claude/skills/ticket-start/agents/architect.md
```
Both `diff -q` calls must produce no output.

- [ ] **Step 5: Commit**

```bash
git add skills/ticket-start/agents/architect.md
git commit -m "$(cat <<'EOF'
ticket-start: architect.md gains pre-Architect brainstorm-summary input

Appends one new input bullet to agents/architect.md's
## Inputs you will receive section:

- Pre-Architect brainstorm summary: short markdown synthesis of
  the user's stated intent, constraints, and preferences surfaced
  during Setup step 7. Authoritative on questions the ticket and
  AC don't cover.

The orchestrator (SKILL.md → ## Solution Exploration step 1) now
passes this summary as an input when dispatching Architect; this
commit makes the receiving side of the contract explicit on the
role-prompt side.

No other changes to Architect's role prompt: mandate, output
format, and forbidden behaviors all unchanged.

Spec: docs/superpowers/specs/2026-05-13-pre-architect-understanding-design.md
§5.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Lint + cross-reference verification

**Files:**
- Verify (read-only): every file in `skills/ticket-start/`
- No commit (verification only)

- [ ] **Step 1: Frontmatter validation**

```bash
head -1 skills/ticket-start/SKILL.md | grep -q '^---$' && echo "Frontmatter starts ✓"
awk '/^---$/{n++; next} n==1{print}' skills/ticket-start/SKILL.md | head -5
```
Expected: `Frontmatter starts ✓` followed by the YAML frontmatter (name + description).

- [ ] **Step 2: No-placeholder scan**

```bash
grep -rnE '\b(TBD|FIXME|XXX|implement later|fill in details)\b' skills/ticket-start/ 2>/dev/null \
  | grep -v 'self-improvement.md' \
  | grep -v 'No "TBD", no "n/a", no blank cells' \
  || echo "no placeholders found ✓"
```
Expected: `no placeholders found ✓`.

- [ ] **Step 3: Host-purity check**

```bash
grep -rnE 'mcp__playwright|Playwright MCP|browser-use:browser|iab |Codex Browser plugin|browser_evaluate|browser_take_screenshot|browser_tabs' skills/ticket-start/ 2>/dev/null \
  && echo "✗ host-purity violation" \
  || echo "host-pure ✓"
```
Expected: `host-pure ✓`.

- [ ] **Step 4: Inventory of inventory-as-contract structural checks (regression guard from PR #6 rounds 1-3)**

```bash
grep -q "^## Prototype elements relevant to this feature$" skills/ticket-start/agents/scoping.md && echo "scoping.md prototype-elements section ✓"
grep -q "^1a\. \*\*For parity-mode UI tickets\*\*" skills/ticket-start/SKILL.md && echo "Plan-phase item 1a ✓"
grep -q "^4a\. \*\*In parity mode, construct the expected matched-element inventory" skills/ticket-start/SKILL.md && echo "Verify step 4a ✓"
grep -q "^6a\. \*\*Validate the UI/UX report" skills/ticket-start/SKILL.md && echo "Verify step 6a ✓"
grep -q "^### Rows added beyond the supplied inventory$" skills/ticket-start/agents/ui-ux.md && echo "ui-ux.md rows-added-beyond subsection ✓"
```
Expected: every line ends `✓`.

- [ ] **Step 5: Dispatch-user-briefing-protocol structural checks (regression guard from PR #6 round 4)**

```bash
grep -q "^## Dispatch → user briefing protocol$" skills/ticket-start/SKILL.md && echo "Central briefing section ✓"
grep -q "^### Handoff type 1 — Scoping → user dialogue" skills/ticket-start/SKILL.md && echo "Handoff type 1 (renamed) ✓"
grep -q "^### Handoff type 2 — Architect → Brainstorm dialogue" skills/ticket-start/SKILL.md && echo "Handoff type 2 ✓"
grep -q "^### Handoff types 3–6 — Auditor" skills/ticket-start/SKILL.md && echo "Handoff types 3-6 ✓"
grep -q "^### Handoff type 7 — Bug-fix loop architectural intervention" skills/ticket-start/SKILL.md && echo "Handoff type 7 ✓"
grep -q "When surfacing to the user, brief per .SKILL.md. → .## Dispatch → user briefing protocol. (handoff type 7" skills/ticket-start/bug-fix-loop.md && echo "bug-fix-loop user-intervention cue ✓"
```
Expected: every line ends `✓`.

- [ ] **Step 6: This round's structural checks**

```bash
grep -q "^1\. \*\*Worktree discipline\.\*\*" skills/ticket-start/SKILL.md && echo "Setup step 1 trimmed ✓"
grep -q "^2\. \*\*Subagent context discipline\.\*\*" skills/ticket-start/SKILL.md && echo "Setup step 2 trimmed ✓"
grep -q "^7\. \*\*Pre-Architect understanding\.\*\*" skills/ticket-start/SKILL.md && echo "Setup step 7 NEW ✓"
grep -q "^## Solution Exploration$" skills/ticket-start/SKILL.md && echo "Solution Exploration section ✓"
grep -c "^## Brainstorm$" skills/ticket-start/SKILL.md | grep -q "^1$" && echo "Exactly one ## Brainstorm section ✓"
grep -q "Setup → Solution Exploration → Brainstorm → Plan" skills/ticket-start/SKILL.md && echo "9-phase order in Overview + Phase block ✓"
grep -q "^9\. \*\*Ship\*\*" skills/ticket-start/SKILL.md && echo "Phase numbering reaches Ship=9 ✓"
grep -q "Pre-Architect brainstorm summary" skills/ticket-start/agents/architect.md && echo "Architect role-prompt input bullet ✓"
```
Expected: every line ends `✓`.

- [ ] **Step 7: Install-path sync**

```bash
for f in $(find skills/ticket-start -type f | sed 's|^skills/ticket-start/||'); do
  d1=$(diff -q "skills/ticket-start/$f" "$HOME/.codex/skills/ticket-start/$f" 2>&1)
  d2=$(diff -q "skills/ticket-start/$f" "$HOME/.claude/skills/ticket-start/$f" 2>&1)
  [ -z "$d1" ] || echo "codex: $d1"
  [ -z "$d2" ] || echo "claude: $d2"
done
echo "(empty above = all in sync ✓)"
```
Expected: every `diff -q` produces no output.

- [ ] **Step 8: AGENTS.md self-review checklist (re-run)**

```bash
echo "=== Agent tool names in prose (only natural-English usage acceptable) ==="
grep -nE '\b(Read|Write|Edit|MultiEdit|str_replace|ask_user_input_v0|TodoWrite|WebFetch|WebSearch|Glob|Grep|Bash)\b' skills/ticket-start/*.md skills/ticket-start/agents/*.md 2>/dev/null \
  | grep -vE 'Read access|Read the|Read only|Read this|Reads|re-read|Re-read|Read-only|natural language|read only the surgical|read the ticket directly'
echo "(empty above = no tool-name leakage ✓)"
echo "=== Fallback chain + ## Requires preconditions present in qa.md + ui-ux.md ==="
grep -l "Fallback chain" skills/ticket-start/agents/qa.md skills/ticket-start/agents/ui-ux.md
grep -l "^## Requires$" skills/ticket-start/agents/qa.md skills/ticket-start/agents/ui-ux.md
```
Expected: agent-tool-names grep produces only natural-English occurrences; both fallback-chain and Requires files listed.

- [ ] **Step 9: No commit (verification only)**

This task produces no file changes. If any check failed, return to Task 1, 2, 3, 4, or 5 and fix.

---

### Task 7: Push branch + update PR description

**Files:**
- None directly. Pushes branch and edits PR #6.

- [ ] **Step 1: Confirm working tree clean and commits present**

```bash
git status
```
Expected: `nothing to commit, working tree clean`.

```bash
git log origin/ticket-start-visual-parity-enforcement..HEAD --oneline
```
Expected: 6 new commits since the previous round (1 spec + 5 implementation tasks: trim 1-2, add step 7, split Brainstorm, broaden handoff 1, architect input bullet).

- [ ] **Step 2: Push the branch**

```bash
git push origin ticket-start-visual-parity-enforcement
```
Expected: push succeeds.

- [ ] **Step 3: Update PR #6 description**

```bash
gh pr edit 6 --body "$(cat <<'EOF'
## Summary

This PR lands five coordinated changes to the `ticket-start` skill:

1. **Visual-parity enforcement** — UI/UX subagent inventory was non-exhaustive in practice; protocol now mandates exhaustiveness (mandatory + exhaustive inventory, four completeness rules, main-agent step 6a, prototype-parity dominance).

2. **Canonical-skill migration** — consolidated the legacy duplicated layout (`codex/skills/ticket-start/` + `claude/skills/ticket-start/`) into a single canonical `skills/ticket-start/`, per the AGENTS.md repo + authoring rules from PR #5. All product/tool references swapped to intent-level capability language; fallback chains added; non-trivial extraction logic moved to `scripts/`.

3. **Inventory-as-contract** — moved matched-element-inventory construction upstream from UI/UX into Scoping (prototype side) + Plan (production-side mapping) + main agent at Verify dispatch (stitched table). UI/UX's role narrows from discovery+verification to verification of a supplied inventory. Step 6a now cross-checks expected vs verified inventories. Activated only in parity mode.

4. **Dispatch → user briefing protocol** — codifies the rule that main agent must brief the user with a synthesis of the subagent's substance BEFORE asking for any input, decision, or choice. Applies uniformly to all seven dispatch-→-user handoff points in the workflow.

5. **Pre-Architect understanding** — Architect was proposing solutions cold (against ticket + AC + Scoping report only) before any user-facing brainstorm. This change adds a proactive pre-Architect dialogue at Setup step 7 to surface user intent, constraints, and preferences not captured in the ticket. The Architect now proposes against richer context (the brainstorm summary becomes a new input bullet). The old "Brainstorm" phase, which contained both Architect dispatch and user dialogue, splits into `Solution Exploration` (Architect dispatch only) + `Brainstorm` (user-facing convergence + on-demand re-dispatch). Setup steps 1-2 are also trimmed to workflow-specific bits. Phase order becomes 9 phases.

### Pre-Architect-understanding changes (this commit set)

- **`SKILL.md`** — Setup steps 1-2 trimmed; new Setup step 7 (pre-Architect understanding with auto-trigger wording for `superpowers:brainstorming`); old `## Brainstorm` section split into `## Solution Exploration` (1 step) + `## Brainstorm` (3 steps including on-demand re-dispatch); Overview prose + Phase Order block updated to 9 phases; briefing-protocol handoff type 1 broadened to cover both reactive (step 6) and proactive (step 7) dialogues.
- **`agents/architect.md`** — one new input bullet (the pre-Architect brainstorm summary).

No other skill files change. No new subagents, scripts, or artifact files.

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
- Pre-Architect-understanding spec: `docs/superpowers/specs/2026-05-13-pre-architect-understanding-design.md`.
- Pre-Architect-understanding plan: `docs/superpowers/plans/2026-05-13-pre-architect-understanding.md`.

## Test plan

This change is in skill files (markdown only). Behavioral validation happens on the next ticket. Until then:

- [x] Canonical tree is host-pure (zero product/tool-name hits).
- [x] All cross-refs resolve.
- [x] Install-path sync clean for both `~/.codex/skills/ticket-start/` and `~/.claude/skills/ticket-start/`.
- [x] AGENTS.md self-review checklist re-runs clean after each set of changes.
- [x] All seven dispatch-site briefing cues present in SKILL.md.
- [x] Setup step 7 (pre-Architect understanding) present with auto-trigger wording.
- [x] Brainstorm phase split into Solution Exploration + Brainstorm.
- [x] Architect role prompt receives pre-Architect brainstorm summary as new input.
- [ ] On the next ticket: confirm Setup step 7 fires as a multi-turn dialogue (not a single-question gate). Auto-trigger of \`superpowers:brainstorming\` is the load-bearing detail; observe whether it actually fires.
- [ ] On the next ticket: confirm Architect receives the brainstorm summary as input and references it in proposals' rationale.
- [ ] On the next ticket: confirm Brainstorm phase (post-Architect) also fires as a multi-turn dialogue, not a single "pick one" gate.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR description updated successfully.

- [ ] **Step 4: Final summary to user**

Produce a short closeout summary covering:
- PR URL (still PR #6).
- Commits added in this round (6: 1 spec + 5 implementation).
- Total commits on the branch.
- What is **not** verified by this plan: the auto-trigger mechanism. The wording is engineered to match `superpowers:brainstorming`'s trigger description, but empirical validation that the skill actually fires (as a multi-turn dialogue) only happens on the next real ticket. This is the known risk surfaced in the spec.
- Next steps for the user: review PR #6, run a real ticket to validate the auto-trigger.

---

## Self-review

### 1. Spec coverage

Mapping each spec section to a task:

- **§1 Problem statement + §2 Goals/non-goals** — captured in the plan header (Goal, Architecture). ✓
- **§3 Architectural decisions** — encoded across Tasks 1-5. Setup step placement (decision 1) = Task 2. Setup 1-2 trim (decision 5) = Task 1. End condition deferred to skill (decision 2) = built into Tasks 2 + 3 via auto-trigger wording. Relationship to post-Architect brainstorm (decision 3) = Task 3 keeps both, with the post-Architect one in the new Brainstorm phase. Architect input (decision 4) = Tasks 3 + 5. Phase naming (decision 6) = Task 3 (the phase split). ✓
- **§4 Phase data flow** — implemented across Tasks 1, 2, 3 (Setup → Solution Exploration → Brainstorm flow); Task 4 (briefing-protocol fits both step 6 and step 7); Task 5 (Architect's role-prompt side of the contract). ✓
- **§4.1 Auto-trigger discipline** — wording in Task 2 step 7 ("explore user intent, constraints, and design preferences") and Task 3 Brainstorm step 1 ("explore the Architect's proposals via a question-driven dialogue") match `superpowers:brainstorming`'s trigger description. No explicit `superpowers:brainstorming` invocations. ✓
- **§5 File-by-file changes** — Tasks 1-5 each implement one or more of the SKILL.md sub-edits or the architect.md edit. ✓
- **§6 Activation, briefing-protocol interaction, edge cases** — activation gate (no mode gating) built into Task 2's wording; handoff type 1 broadening in Task 4. Edge cases listed in spec apply at runtime; no code paths needed beyond what the wording covers. ✓
- **§7 Deferred to implementation plan** — exact brainstorm-summary format addressed in Tasks 2 + 3 + 5 (markdown synthesis covering intent/constraints/preferences); exact ASCII-art diagram update in Task 3 step 2. ✓
- **§8 Migration and scope** — additive plus phase rename; rollback is reverting the PR. No special migration code needed. ✓

No spec gaps.

### 2. Placeholder scan

I searched the plan for: TBD, FIXME, XXX, "implement later," "fill in details," "Similar to Task N." The only `<placeholder>` style tokens are intentional substitution markers in file content (e.g., `<ticket title>` in the briefing-protocol section already present in SKILL.md, not introduced by this plan). No real TBDs in instruction-bearing parts.

### 3. Type / name consistency

Cross-checked names used across tasks:

- Phase names: `Setup`, `Solution Exploration`, `Brainstorm`, `Plan`, `Implement`, `Review`, `Security`, `Verify`, `Ship` — consistent across Tasks 1-6.
- Step numbers in SKILL.md: Setup step 1 (Worktree discipline), step 2 (Subagent context discipline), step 6 (Clarifications, unchanged), step 7 (Pre-Architect understanding, NEW) — consistent across Tasks 1, 2.
- Phase numbering: Setup=1, Solution Exploration=2, Brainstorm=3, Plan=4, Implement=5, Review=6, Security=7, Verify=8, Ship=9 — consistent in Task 3.
- Handoff-type-1 label: "Scoping → user dialogue" — used in Tasks 2 (per-site cues at step 6 + step 7) and 4 (central description). Consistent.
- Brainstorm-summary terminology: "pre-Architect brainstorm summary" (referencing Setup step 7) — used in Tasks 2 (description in step 7), 3 (Architect input bullet in Solution Exploration), 5 (Architect role-prompt input bullet). Consistent across all three references.
- Auto-trigger wording: "explore user intent, constraints, and design preferences" (Task 2) and "explore the Architect's proposals with the user via a question-driven dialogue" (Task 3). Both match `superpowers:brainstorming`'s trigger description ("explores user intent, requirements and design before implementation").

No inconsistencies found.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-13-pre-architect-understanding.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, two-stage review per task (spec compliance + code quality), continuous execution. Best fit because Tasks 1-5 each touch one file with self-contained edits; per-task review catches drift between the sub-edits (e.g., a missed handoff-type-1 label update in step 6 or step 7 vs the central description update in Task 4).

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batched with checkpoints. Faster wallclock; less isolation.

**Which approach?**
