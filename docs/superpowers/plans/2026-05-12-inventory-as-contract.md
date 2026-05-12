# Inventory-as-Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the matched-element inventory a cross-phase contract — built by Scoping (prototype side) + Plan (production-side mapping) + main agent at Verify dispatch (stitched table), supplied to UI/UX as input, and cross-checked by step 6a — activated only in parity mode (personal workflow + runnable React reference app).

**Architecture:** Six skill-file edits in `skills/ticket-start/`. No new subagents, no new scripts, no persistent inventory artifact. Scoping gains a `## Prototype elements relevant to this feature` section. `SKILL.md` gains a Plan-phase guidance item (Element mapping blocks in tasks) and a Verify-phase pre-dispatch step (construct the expected inventory). Step 6a is rewritten to cross-check expected vs verified. `agents/ui-ux.md` is restructured so Mode A's role narrows from discovery+verification to verification of a supplied inventory. `personal-workflow.md` and `verification.md` get small updates pointing at the contract.

**Tech Stack:** Markdown skill files (no code). The inventory is constructed inline by main agent at dispatch using shell + grep + markdown reasoning — no helper script in v1 (deferred per spec §7; re-evaluate after the first parity-mode ticket exercises the contract in practice).

**Spec reference:** `docs/superpowers/specs/2026-05-12-inventory-as-contract-design.md`. Read it before starting Task 1.

---

## Plan-level decisions locked

These were settled in the brainstorm and recorded in the spec:

1. **Format:** phase reports own their slices; main agent stitches the inventory table at dispatch. No persistent `inventory.md` file. The expected inventory travels in the dispatch payload to UI/UX; the verified inventory lives in the UI/UX report.
2. **Granularity:** JSX-declaration rows on each side. UI/UX expands each row to its rendered DOM atoms and runs `getComputedStyle()` + `getBoundingClientRect()` per atom inside the row.
3. **Scope:** implementation-scoped only. Rows for elements the diff adds or modifies, plus their prototype counterparts. Adjacent-element drift is reportable as a UI/UX finding but not an inventory row.
4. **Activation gate:** personal workflow + runnable React reference app (parity mode). Inactive in consistency mode and job workflow.
5. **No helper script in v1.** Per AGENTS.md rule 3, non-trivial logic should live in scripts. The inventory-construction logic is non-trivial but the cost of extracting it before we know its shape is higher than the benefit. Revisit after the first parity-mode ticket runs.
6. **No fallback from parity-with-contract to discovery-mode UI/UX.** If construction fails, halt and surface the blocker.

---

## File structure (what changes)

**Modified files (canonical location after PR #6):**

| File | Change | Size |
|---|---|---|
| `skills/ticket-start/agents/scoping.md` | Add `## Prototype elements relevant to this feature` section to the report output format; extend mandate; extend forbidden behaviors. | small (+ ~10 lines) |
| `skills/ticket-start/SKILL.md` | Plan-phase: add item 1a (Element mapping blocks in parity-mode plan tasks). Verify-phase: add step 4a (construct expected inventory before UI/UX dispatch); update step 5 dispatch inputs; rewrite step 6a as cross-check; add 3 red flags. | medium (~50 lines added/changed) |
| `skills/ticket-start/agents/ui-ux.md` | New Inputs bullet (parity mode supplied inventory); Mandate clarification; Mode A protocol rewritten as per-row verification; Forbidden behaviors rephrased; Stop conditions updated for first-pass + bug-fix re-run. | large (full rewrite ~200 lines) |
| `skills/ticket-start/personal-workflow.md` | Corollary to "Prototype parity dominates" subsection; one-sentence note on parity-mode line under "Verification — Mode mapping". | small (+ ~6 lines) |
| `skills/ticket-start/verification.md` | Opening of `### Matched-element inventory (do this first)` updated for parity-mode contract; per-state procedure step 3 reworded ("verify the supplied inventory" vs "build the inventory"). | small (~8 lines changed) |

**Unchanged files:**
- `agents/qa.md`, `agents/architect.md`, `agents/reviewer.md`, `agents/security.md`, `agents/openai.yaml` — orthogonal.
- `bug-fix-loop.md` — row-level re-run scoping lives in `agents/ui-ux.md`'s stop conditions, not here.
- `self-improvement.md` — orthogonal.
- `job-workflow.md` — not parity mode.
- `react-parity.md` — philosophy doc.
- `scripts/extract-element-style.browser.js` — unchanged.

**Sync to install dirs:** every modification syncs to `~/.codex/skills/ticket-start/` and `~/.claude/skills/ticket-start/` in the same task (per AGENTS.md rule 2).

---

## Tasks

### Task 1: Update `agents/scoping.md` (add Prototype elements section)

**Files:**
- Modify: `skills/ticket-start/agents/scoping.md` — three edits
- Sync: `~/.codex/skills/ticket-start/agents/scoping.md` and `~/.claude/skills/ticket-start/agents/scoping.md`

- [ ] **Step 1: Add the new section to the output format**

Use the `Edit` tool. Find this block:

```
## Existing implementations of similar behavior
- `path:start-end` | `name(signature)` | one-line on what makes this analogous

## Project patterns to reuse
```

Replace with:

```
## Existing implementations of similar behavior
- `path:start-end` | `name(signature)` | one-line on what makes this analogous

## Prototype elements relevant to this feature
_(populate only when the project has a runnable React reference app under `designs/` and the ticket touches UI; otherwise emit `_None._`. One row per visible JSX declaration in the scoped designs/ slices.)_
- `designs/path:start-end` | component name or HTML element | accessible name / role / text content | one-line purpose

## Project patterns to reuse
```

- [ ] **Step 2: Extend the mandate paragraph**

Use the `Edit` tool. Find this line:

```
Produce a **navigable index** of the parts of this codebase relevant to the ticket. Read-only. Your output is the **only** place downstream agents (Architect, main during plan-writing, Implementer subagents during implementation) should need to learn *where* relevant code lives. After your report, no later agent should ever need to load a full file to find context — they should be able to read only the surgical slices your locators point at.
```

Replace with:

```
Produce a **navigable index** of the parts of this codebase relevant to the ticket. Read-only. Your output is the **only** place downstream agents (Architect, main during plan-writing, Implementer subagents during implementation) should need to learn *where* relevant code lives. After your report, no later agent should ever need to load a full file to find context — they should be able to read only the surgical slices your locators point at.

For tickets in projects with a runnable React reference app under `designs/` that touch UI, the `## Prototype elements relevant to this feature` section is **required** — an empty enumeration in this case is a Scoping failure, not a clean report. The downstream UI/UX subagent receives a pre-built matched-element inventory at Verify dispatch (per `SKILL.md`'s Verify step 4a), and that inventory is constructed from your prototype-element enumeration.
```

- [ ] **Step 3: Extend forbidden behaviors**

Use the `Edit` tool. Find this line:

```
- Inflating the report with unrelated code. Stay scoped to the feature.
```

Replace with:

```
- Inflating the report with unrelated code. Stay scoped to the feature.
- Emitting `_None._` for the `## Prototype elements relevant to this feature` section in a parity-mode UI ticket. If you cannot enumerate (composition is too dynamic, third-party components obscure rendered DOM from static reading), surface the limitation under `## Conflicts surfaced for main` instead — the workflow can then decide whether to degrade to consistency mode for this ticket.
```

- [ ] **Step 4: Verify the file**

Run:
```bash
grep -q "^## Prototype elements relevant to this feature$" skills/ticket-start/agents/scoping.md && echo "Section header ✓"
grep -q "populate only when the project has a runnable React reference app" skills/ticket-start/agents/scoping.md && echo "Section subtitle ✓"
grep -q "required.* an empty enumeration in this case is a Scoping failure" skills/ticket-start/agents/scoping.md && echo "Mandate extension ✓"
grep -q "Emitting .None. for the .. Prototype elements relevant" skills/ticket-start/agents/scoping.md && echo "Forbidden behavior added ✓"
```
Expected: all four pass.

- [ ] **Step 5: Sync to install dirs**

```bash
cp skills/ticket-start/agents/scoping.md ~/.codex/skills/ticket-start/agents/scoping.md
cp skills/ticket-start/agents/scoping.md ~/.claude/skills/ticket-start/agents/scoping.md
diff -q skills/ticket-start/agents/scoping.md ~/.codex/skills/ticket-start/agents/scoping.md
diff -q skills/ticket-start/agents/scoping.md ~/.claude/skills/ticket-start/agents/scoping.md
```
Expected: both `diff -q` calls produce no output.

- [ ] **Step 6: Commit**

```bash
git add skills/ticket-start/agents/scoping.md
git commit -m "$(cat <<'EOF'
ticket-start: scoping.md emits prototype-element enumeration in parity mode

Adds a new section to the Scoping subagent's output format:
## Prototype elements relevant to this feature. Populated only when
the project has a runnable React reference app under designs/ and
the ticket touches UI; otherwise emits _None._.

One row per visible JSX declaration in the scoped designs/ slices,
with designs/path:start-end, component or HTML element name,
accessible name/role, and one-line purpose. This enumeration feeds
the expected matched-element inventory that main agent constructs at
Verify dispatch.

Mandate extended: for parity-mode UI tickets, the section is
required. An empty enumeration is a Scoping failure, not a clean
report. If enumeration is structurally impossible (dynamic
composition, third-party components obscuring rendered DOM from
static reading), surface the limitation under "Conflicts surfaced
for main" so the workflow can decide whether to degrade to
consistency mode.

Spec: docs/superpowers/specs/2026-05-12-inventory-as-contract-design.md
§5.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Update `SKILL.md` Plan phase (Element mapping blocks)

**Files:**
- Modify: `skills/ticket-start/SKILL.md` — one edit in the Plan section
- Sync: both install dirs

- [ ] **Step 1: Insert new item 1a in the Plan section**

Use the `Edit` tool. Find this block:

```
## Plan

1. **`superpowers:writing-plans`.** Produce a written implementation plan from the brainstorm outcome. The plan is a distinct artifact produced by that sub-skill — not a verbal summary of the brainstorm, not the brainstorm transcript itself, and not a mental model in your head.
2. Show the plan to the user as `superpowers:writing-plans` directs. Wait for explicit user approval of the *plan itself* before writing any code.
```

Replace with:

```
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
```

- [ ] **Step 2: Verify the file**

```bash
grep -q "^1a\. \*\*For parity-mode UI tickets\*\*" skills/ticket-start/SKILL.md && echo "Item 1a present ✓"
grep -q "\\*\\*Element mapping:\\*\\* block" skills/ticket-start/SKILL.md && echo "Element mapping reference ✓"
grep -q "Scoping row .designs" skills/ticket-start/SKILL.md && echo "Example block ✓"
```
Expected: all three pass.

- [ ] **Step 3: Sync to install dirs**

```bash
cp skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
cp skills/ticket-start/SKILL.md ~/.claude/skills/ticket-start/SKILL.md
diff -q skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
diff -q skills/ticket-start/SKILL.md ~/.claude/skills/ticket-start/SKILL.md
```
Expected: both `diff -q` calls produce no output.

- [ ] **Step 4: Commit**

```bash
git add skills/ticket-start/SKILL.md
git commit -m "$(cat <<'EOF'
ticket-start: SKILL.md Plan phase requires Element mapping in parity mode

Adds item 1a to the Plan section: for parity-mode UI tickets, each
plan task that adds or modifies a visible element includes an
**Element mapping:** block declaring (a) the prototype counterpart
via reference to a Scoping prototype-element row, and (b) the planned
production file:line for the new/changed JSX declaration.

Tasks that don't add/modify visible elements omit the block.

Main agent uses these mappings at Verify dispatch (Task 3 introduces
step 4a) to construct the expected matched-element inventory passed
to UI/UX.

Spec: docs/superpowers/specs/2026-05-12-inventory-as-contract-design.md
§5.2 (Plan phase).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Update `SKILL.md` Verify phase (dispatch + step 6a + red flags)

**Files:**
- Modify: `skills/ticket-start/SKILL.md` — four edits in the Verify section + Red Flags list
- Sync: both install dirs

- [ ] **Step 1: Insert new step 4a (construct expected inventory) before step 5**

Use the `Edit` tool. Find this block:

```
4. **When QA returns CLEAN**, run the self-improvement extraction pass on QA findings.

5. **If backend-only flag is set: skip UI/UX. Otherwise, dispatch UI/UX subagent.** Load the role prompt from `agents/ui-ux.md`. Invoke a subagent with:
```

Replace with:

```
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
```

- [ ] **Step 2: Add the expected-inventory bullet to the UI/UX dispatch inputs in step 5**

Use the `Edit` tool. Find this block:

```
   - For `parity`: paths/URLs to **both** the production app and the React reference app.
   - For `consistency`: path/URL to the production app.
   - Live-browser automation (navigation, clicks, keyboard input, viewport control, DOM evaluation, element-level screenshots, tab control). See `agents/ui-ux.md` → `## Browser bootstrap` for the fallback chain when a native browser capability is missing.
   - The role-prompt content from `agents/ui-ux.md`.
   Wait for the UI/UX report.
```

Replace with:

```
   - For `parity`: paths/URLs to **both** the production app and the React reference app.
   - For `parity`: the **expected matched-element inventory** table constructed in step 4a. UI/UX's job in parity mode is to fill in the verdict and computed-style cells, not to discover the inventory from scratch.
   - For `consistency`: path/URL to the production app.
   - Live-browser automation (navigation, clicks, keyboard input, viewport control, DOM evaluation, element-level screenshots, tab control). See `agents/ui-ux.md` → `## Browser bootstrap` for the fallback chain when a native browser capability is missing.
   - The role-prompt content from `agents/ui-ux.md`.
   Wait for the UI/UX report.
```

- [ ] **Step 3: Rewrite step 6a as cross-check**

Use the `Edit` tool. Find this block:

```
6a. **Validate the UI/UX report's matched-element inventory before accepting any verdict.**

   - Confirm the report has a `## Matched-element inventory` section.
   - Spot-check exhaustiveness:
     - From the diff, pick 2 changed UI files. List their rendered elements. Each one must appear in the inventory.
     - From the running production app, sample 3 visible elements on the feature surface (one container, one text element, one interactive control). Each must appear in the inventory.
     - From the prototype, sample 2 visible elements. Each must appear either as a matched pair or as `MISSING` in the inventory.
   - If any sample is not in the inventory, the report is **structurally invalid**. Reject and re-dispatch UI/UX with the specific missing elements named.
   - Do not accept "I checked the major elements" or "the rest match by inspection" as substitutes for inventory rows.
```

Replace with:

```
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
```

- [ ] **Step 4: Add three new red flags to the Red Flags list**

Use the `Edit` tool. Find this block:

```
- UI/UX subagent restricting the inventory to "important" elements instead of every visible element in the feature surface.
- Using the `superpowers:executing-plans` fallback path and skipping `superpowers:requesting-code-review` before advancing to Review — that path has no other end-of-feature review.
```

Replace with:

```
- UI/UX subagent restricting the inventory to "important" elements instead of every visible element in the feature surface.
- Main agent dispatching UI/UX in parity mode without supplying the expected matched-element inventory constructed in step 4a.
- Scoping report's `## Prototype elements relevant to this feature` section is empty or `_None._` for a parity-mode UI ticket — surface this at Setup, do not proceed to Brainstorm.
- UI/UX returns a verified inventory with rows that have blank `font-*`, `color/bg`, `box`, `layout`, `size`, or `verdict` cells. The DOM-evaluation work was skipped for those rows; reject the verdict at step 6a.
- Using the `superpowers:executing-plans` fallback path and skipping `superpowers:requesting-code-review` before advancing to Review — that path has no other end-of-feature review.
```

- [ ] **Step 5: Verify the file**

```bash
grep -q "^4a\. \*\*In parity mode, construct the expected matched-element inventory" skills/ticket-start/SKILL.md && echo "Step 4a present ✓"
grep -q "expected matched-element inventory.. table constructed in step 4a" skills/ticket-start/SKILL.md && echo "Step 5 input bullet ✓"
grep -q "cross-check the verified inventory.* against the expected inventory" skills/ticket-start/SKILL.md && echo "Step 6a cross-check ✓"
grep -q "Main agent dispatching UI/UX in parity mode without supplying" skills/ticket-start/SKILL.md && echo "Red flag 1 ✓"
grep -q "Scoping report.s .. Prototype elements relevant.* is empty" skills/ticket-start/SKILL.md && echo "Red flag 2 ✓"
grep -q "UI/UX returns a verified inventory with rows that have blank" skills/ticket-start/SKILL.md && echo "Red flag 3 ✓"
```
Expected: all six pass.

- [ ] **Step 6: Sync to install dirs**

```bash
cp skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
cp skills/ticket-start/SKILL.md ~/.claude/skills/ticket-start/SKILL.md
diff -q skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
diff -q skills/ticket-start/SKILL.md ~/.claude/skills/ticket-start/SKILL.md
```
Expected: both `diff -q` calls produce no output.

- [ ] **Step 7: Commit**

```bash
git add skills/ticket-start/SKILL.md
git commit -m "$(cat <<'EOF'
ticket-start: SKILL.md Verify phase adopts inventory-as-contract

Four changes to the Verify phase:

- New step 4a (parity mode only) — main agent constructs the
  expected matched-element inventory before dispatching UI/UX.
  Combines Scoping's prototype-element enumeration + plan tasks'
  Element-mapping blocks + actual post-diff production file:lines
  from the touched UI files. Produces the same table shape as
  ui-ux.md's matched-element inventory but with verdict and
  computed-style cells blank for UI/UX to fill in. If construction
  fails, halt; no fallback to discovery-mode UI/UX in parity mode.

- Step 5 dispatch input list gains a bullet (parity mode only):
  "the expected matched-element inventory constructed in step 4a".

- Step 6a rewritten as a two-mode cross-check. In parity mode,
  cross-check verified vs expected (every expected row present,
  no blank cells, sampled rows confirmed). In consistency mode,
  today's diff + running-app spot-check still applies.

- Three new red flags: dispatching UI/UX in parity mode without
  supplying the inventory; Scoping's prototype-elements section
  empty for a parity-mode UI ticket; UI/UX verified inventory has
  blank cells (DOM-evaluation work was skipped).

Spec: docs/superpowers/specs/2026-05-12-inventory-as-contract-design.md
§5.2 (Verify phase).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Rewrite `agents/ui-ux.md` (verification-not-discovery in parity mode)

**Files:**
- Modify: `skills/ticket-start/agents/ui-ux.md` — full rewrite
- Sync: both install dirs

- [ ] **Step 1: Overwrite the file with the new content**

Use the `Write` tool to overwrite `skills/ticket-start/agents/ui-ux.md` with this EXACT content. The file body starts at `# UI/UX` and ends at `... full re-runs are wasteful.`. The content contains a nested triple-backtick code fence (the output-format example block); pass the body verbatim.

```
# UI/UX

## Identity

You are UI/UX, a specialized subagent in the `ticket-start` workflow. You run during the Verify phase **after** QA is clean, in serial. You are skipped on backend-only changes — main agent decides this from the diff. When you run, you cover **visual** verification and **accessibility**.

## Mandate

Verify the implementation is visually correct and accessible.

In **parity mode** (personal workflow with a runnable React reference app), main agent supplies an **expected matched-element inventory** at dispatch — a table of JSX declarations on the prototype side paired with their production counterparts, with verdict and computed-style cells blank. Your job is to verify each supplied row by running DOM evaluation against the live browsers and filling in those cells. You are not building the inventory; you are completing it.

In **consistency mode** (job workflow or personal workflow without a React reference), no inventory is supplied. You build a sibling/analog inventory yourself from the diff and the running production app.

In both modes: **programmatic-first principle** — lean on DOM and computed-style assertions over screenshots. Screenshots are supplementary context for cases the DOM can't fully tell (e.g., stacking-context bugs, transform anomalies), not primary evidence.

You do **not** cover code style, behavior correctness (QA owns AC), or security.

## Requires

- Ability to execute shell commands (start dev servers, run helper scripts).
- Ability to drive a live browser session — load URLs, switch tabs, set viewport, capture element-level screenshots, evaluate JavaScript against the DOM (to read `getComputedStyle()` and `getBoundingClientRect()`), click, type, press keys.
- Read access to both the production app and (in parity mode) the React reference app.

## Inputs you will receive

- The approved implementation plan.
- The ticket title and description.
- Acceptance criteria, if the main agent passes them as a separate field (otherwise assume they are inline in the description).
- The full diff.
- A `mode` parameter set by main agent: `parity` (Mode A — personal workflow with React reference app) or `consistency` (Mode B — job workflow OR personal workflow without a React reference).
- For Mode A: paths/URLs to **both** the production app and the React reference app (they must run side-by-side in browser tabs).
- For Mode A: the **expected matched-element inventory** table supplied by main agent at dispatch — one row per JSX declaration, with prototype + production file:lines populated, prototype + production selector hints populated, and verdict + computed-style cells blank. Treat the supplied rows as a contract: every row gets verified.
- For Mode B: path/URL to the production app.
- Live-browser automation (tab control, viewport setup, DOM snapshots, element-level screenshots, in-page JavaScript evaluation for `getComputedStyle()` and `getBoundingClientRect()`, clicks, keyboard input).

## Browser bootstrap

Visual + accessibility verification requires driving a live browser. Use whatever browser-automation capability the host agent provides — what matters is the capability, not the specific tool name.

**Fallback chain** when a preferred capability is missing:

1. **Native browser-automation capability** (preferred). Use the agent's built-in browser tool(s) for navigation, tab control, viewport sizing, element-level screenshots, and DOM evaluation. Prefer this when available.
2. **Playwright via shell.** If no native capability is available, drive a local Playwright install through the shell. For DOM evaluation, inject the contents of `scripts/extract-element-style.browser.js` (shipped with this skill) via Playwright's `page.evaluate(...)`. Capture screenshots with Playwright's element-level screenshot API.
3. **Manual confirmation (degraded).** If neither is available, render each relevant state to disk (HTML + any screenshot the platform can produce), describe the matched-element inventory you would have built, and ask the user to confirm visually. Label any verdict produced this way as **degraded**.

If even the manual fallback cannot be performed, do not silently substitute another approach. Report `UI/UX cannot proceed` with the exact blocker.

## Output format

```markdown
# UI/UX report — <ticket title>

## Verdict
- [ ] CLEAN — no findings, advance to Ship
- [ ] FINDINGS — at least one mismatch / a11y issue (see below)

## Mode used
- <parity | consistency>

## States covered
- <default | loading | empty | hover | focus | active | disabled | error | validation | success | expanded/collapsed | modal-open | navigation>
- For each: viewport widths exercised: <list, including pre/post-breakpoint widths>

## Matched-element inventory
_(In parity mode: this is the supplied inventory with the verdict and computed-style cells filled in by you. In consistency mode: this is the sibling/analog inventory you built per Mode B's rules. Either way, the table is exhaustive — every row gets verified and no rows are dropped without explanation.)_

| Pair | Prototype selector | Production selector | font-* | color/bg | box (padding/border/radius/shadow) | layout (display/gap/flex) | size (w×h) | verdict |
|---|---|---|---|---|---|---|---|---|
| (parity mode: one row per supplied JSX declaration, with computed values filled in. consistency mode: one row per new/changed element + its sibling analogs.) |  |  |  |  |  |  |  |  |
| Prototype-only element X | `.proto-x` | (none) | … | … | … | … | … | **MISSING** in production |

### Rows added beyond the supplied inventory
_(Parity mode only. If during verification you observe a visible element on the feature surface that wasn't in the supplied inventory, add it here with the same row format. Flag it explicitly — it represents a planning gap (Scoping or Plan missed it) that main agent should surface back to the user.)_
- `production:line` | element type | one-line description | suggested provenance gap (Scoping enumeration / Plan element-mapping block)

### Determining completeness — parity mode

In parity mode, completeness is **cross-checked against the supplied inventory**, not built from scratch:

1. **Every supplied row is verified.** All four computed-style columns (`font-*`, `color/bg`, `box`, `layout`), the `size` column, and the `verdict` column are filled with actual values from DOM evaluation. No "TBD", no "n/a", no blank cells.

2. **Production-DOM cross-check.** As you verify, observe whether the production app renders any visible elements on the feature surface that aren't in the supplied inventory. If so, those rows go in the "Rows added beyond the supplied inventory" section above — never silently dropped.

3. **Prototype-DOM cross-check.** Same in the other direction: if the prototype renders a visible element on the matching route that isn't in the supplied inventory, that's also a "Rows added beyond" entry. It means Scoping's prototype enumeration missed something.

4. **Sibling/parent geometry.** For matched pairs in the same parent JSX declaration, also capture the parent's `getBoundingClientRect()` for children (alignment, gap, sizing) — flag drift in the parent even if individual children match.

### Determining completeness — consistency mode

In consistency mode there's no supplied inventory. Today's exhaustive-enumeration rules apply:

1. **Diff-driven coverage.** Walk the diff. For every UI file touched, enumerate the visible elements it renders. Every enumerated element appears in the inventory.

2. **Production-DOM coverage.** Open the production app at the feature's route. Every visible element on the feature surface has a row.

3. **Sibling/analog coverage.** For each new or changed visible element, identify the existing analog elements in the same view and add rows for them too.

4. **Sibling/parent geometry.** Same as parity mode.

## Visual findings
_(severity rubric: **blocker** = parity/consistency miss that breaks brand or design-system fidelity, or makes the feature unusable. **major** = clearly noticeable mismatch in spacing, typography, color, or layout that a reasonable user or designer would flag. **minor** = sub-pixel or edge-case drift. Any finding flips the verdict to FINDINGS.)_
- **V1** | severity: <blocker / major / minor> | `selector` (production) ↔ `selector` (reference, if Mode A) | property / measurement diff | DOM evidence (computed-style snippet, getBoundingClientRect numbers) | suggested fix

## Accessibility findings
_(severity rubric: **blocker** = WCAG AA failure that locks out a user (e.g., missing keyboard reach, color contrast below 3:1 on UI components). **major** = WCAG AA gap with a workaround or intermittent failure. **minor** = best-practice deviation that doesn't violate AA.)_
- **A1** | severity: <blocker / major / minor> | `selector` | issue (semantic structure / ARIA / focus order / keyboard reach / contrast / alt text) | WCAG criterion | suggested fix

## Out-of-scope flags
- **O1** | `path:line` or `path:start-end` | <suspected behavior / code-quality / security issue> | flagged for: <QA / Reviewer / Security>

## Patterns to codify next time
_(candidates for the self-improvement loop)_
- <one-line declarative form> | rationale: <one sentence>
```

## Mode A — Parity (personal workflow with React reference app)

You are given the **expected matched-element inventory** as input. Run the existing protocol in `verification.md`, but the per-state procedure is now a per-row verification:

1. Set up both apps in the live browser, switching between tabs to compare side-by-side. Match viewport, device scale, browser zoom, and route/state before each comparison.

2. For each row in the supplied inventory, at every relevant breakpoint plus the widths immediately before and after each breakpoint switch:
   - Locate the rendered DOM atoms inside that row's JSX declaration's output in both browsers (the row's `Prototype selector` and `Production selector` cells hint at the selectors to use).
   - Capture an element-level screenshot per atom.
   - Evaluate the extraction snippet (`scripts/extract-element-style.browser.js`) against the DOM for each atom to read `getComputedStyle()` and `getBoundingClientRect()`.
   - Fill the row's `font-*`, `color/bg`, `box`, `layout`, `size` cells with the actual values.
   - Set the row's `verdict`: **MATCH** (every atom's properties agree), **DRIFT** (one or more atoms diverge), **MISSING** (production side doesn't render the expected atom — accepted only if the plan deliberately omitted it, otherwise a finding).
   - For each drifting atom inside a DRIFT row, file a finding (V1, V2, …) citing the specific atom and property.

3. Sibling/parent geometry: for rows sharing a parent JSX declaration, compare the parent's `getBoundingClientRect()` for children; file findings for alignment / gap / sizing drift.

4. **Cross-check production and prototype DOM during verification.** If you observe a visible element on the feature surface (in either browser) that isn't in the supplied inventory, add a row in the `### Rows added beyond the supplied inventory` section of your report. This is how Scoping/Plan enumeration gaps surface to main agent.

5. Vision is the redundant check on top of numbers, not the primary one.

## Mode B — Consistency (job workflow OR personal without React reference)

No external reference and no supplied inventory. Mandate is **stylistic consistency against the rest of the app/page** for new or changed elements.

1. Build a sibling/analog inventory: for each new or changed visible element in the feature, identify the existing analog elements in the same view (other icons of the same role, other typography of the same hierarchy level, other spacing of the same rhythm, other border-radii, other shadow elevations). **Exhaustive — every new or changed visible element gets a row.**

2. Evaluate `scripts/extract-element-style.browser.js` against the DOM to read computed styles and bounding rects from both the new/changed element **and** its analog siblings.

3. Compare. Any deviation without rationale is a finding (e.g., new icon at 16px when analogs are 14px; new heading at `font-weight: 500` when analogs are `font-weight: 600`).

4. Screenshots only as supplementary context, not primary evidence.

## Accessibility (both modes)

Always cover, regardless of mode:

- Semantic HTML structure (correct landmark elements, heading hierarchy).
- ARIA roles and labels where applicable. Don't add ARIA to elements with native semantics that already convey the same meaning.
- Focus order on tabbable elements. Visible focus indicator.
- Keyboard reachability of every interactive element. No keyboard traps.
- Color contrast (WCAG AA: 4.5:1 normal text, 3:1 large text and UI components).
- Text alternatives for images, icons-as-buttons, and other non-text content.

Evaluate JavaScript against the DOM to extract relevant properties (computed contrast, `aria-*` attributes, `tabindex`, role) — do not eyeball.

## Forbidden behaviors

- Declaring CLEAN off full-page screenshots alone. Always extract computed styles and bounding rects via DOM evaluation against the live browser.
- Skipping DOM evaluation because the screenshots "look the same."
- **Parity mode: skipping rows in the supplied inventory, or marking a row MATCH without filling the `font-*`, `color/bg`, `box`, `layout`, `size`, and `verdict` cells.** Every supplied row is a contract — every row gets verified.
- **Parity mode: silently dropping a visible element you observed in production or the prototype that wasn't in the supplied inventory.** Add it to `### Rows added beyond the supplied inventory` so main agent sees the planning gap.
- **Consistency mode: restricting the inventory to elements the agent deems "important" or "the ones most likely to differ." Every visible element in the feature surface gets a row. Selectivity is parity drift.**
- Restricting the inventory (Mode A matched pairs or Mode B sibling analogs) to elements named in the ticket. Cover every visible region of the feature.
- Tolerating "small" numeric differences. There is no tolerance budget — different numbers mean different rendering, surface them.
- Doing behavior testing. QA owns that. If you find a behavior bug while navigating, flag it as out-of-scope for QA — do not block on it.
- Fixing findings. You report; main + Implementer fix. After fix, **you re-run scoped to the affected rows and states**, not the full pass.

## Escalation

If either app cannot be started, screenshots cannot be captured, or DOM evaluation against the live browser is unavailable:

```markdown
# UI/UX cannot proceed
- Reason: <what blocked you>
- Required input: <commands, env, etc.>
```

## Stop conditions

**First-pass parity mode:** done when every supplied inventory row has filled `font-*`, `color/bg`, `box`, `layout`, `size`, and `verdict` cells; every drifting row has at least one corresponding finding (V1, V2, …); any rows observed in production or the prototype that weren't in the supplied inventory are listed in `### Rows added beyond the supplied inventory`; accessibility checks are complete; the Patterns-to-codify section is populated (or explicitly empty).

**First-pass consistency mode:** done when the sibling/analog inventory is exhaustive per Mode B's rules; computed-style + bounding-rect extractions have been compared property-by-property; accessibility checks are complete; the Patterns-to-codify section is populated (or explicitly empty).

**Bug-fix re-run, parity mode:** scope narrows to **affected rows ∩ affected states**. Affected rows are (a) rows that had findings on the previous pass, plus (b) rows whose production file:line changed because of the fix. Affected states are the state(s) where those rows render. Return a **delta verified inventory** containing only those rows; main agent merges the delta into the existing verified inventory and re-runs step 6a on the merged result. Re-run is done when every affected row's cells are updated and previously-drifting rows either report MATCH or a new finding that re-routes through `bug-fix-loop.md`.

**Bug-fix re-run, consistency mode:** scope is the affected states (the state(s) where the finding surfaced + immediately adjacent states), per today's protocol. Visual issues are localized; full re-runs are wasteful.
```

- [ ] **Step 2: Verify the file**

```bash
test -f skills/ticket-start/agents/ui-ux.md && \
  grep -q "^## Requires$" skills/ticket-start/agents/ui-ux.md && echo "Requires section ✓" && \
  grep -q "expected matched-element inventory.. table supplied by main agent at dispatch" skills/ticket-start/agents/ui-ux.md && echo "Supplied-inventory input bullet ✓" && \
  grep -q "verification-not-discovery\|Your job is to verify each supplied row" skills/ticket-start/agents/ui-ux.md && echo "Verification mandate ✓" && \
  grep -q "Rows added beyond the supplied inventory" skills/ticket-start/agents/ui-ux.md && echo "Provenance-gap subsection ✓" && \
  grep -q "Determining completeness . parity mode" skills/ticket-start/agents/ui-ux.md && echo "Parity-mode completeness ✓" && \
  grep -q "Determining completeness . consistency mode" skills/ticket-start/agents/ui-ux.md && echo "Consistency-mode completeness ✓" && \
  grep -q "Parity mode: skipping rows in the supplied inventory" skills/ticket-start/agents/ui-ux.md && echo "Parity-mode forbidden ✓" && \
  grep -q "Bug-fix re-run, parity mode.*affected rows . affected states" skills/ticket-start/agents/ui-ux.md && echo "Re-run scoping ✓" && \
  ! grep -qE 'mcp__playwright|Playwright MCP|browser-use:browser|Codex Browser plugin' skills/ticket-start/agents/ui-ux.md && echo "Host-pure ✓"
```
Expected: all nine checks pass.

- [ ] **Step 3: Sync to install dirs**

```bash
cp skills/ticket-start/agents/ui-ux.md ~/.codex/skills/ticket-start/agents/ui-ux.md
cp skills/ticket-start/agents/ui-ux.md ~/.claude/skills/ticket-start/agents/ui-ux.md
diff -q skills/ticket-start/agents/ui-ux.md ~/.codex/skills/ticket-start/agents/ui-ux.md
diff -q skills/ticket-start/agents/ui-ux.md ~/.claude/skills/ticket-start/agents/ui-ux.md
```
Expected: both `diff -q` calls produce no output.

- [ ] **Step 4: Commit**

```bash
git add skills/ticket-start/agents/ui-ux.md
git commit -m "$(cat <<'EOF'
ticket-start: ui-ux.md verifies a supplied inventory in parity mode

Restructures the UI/UX subagent's role around the inventory contract:
in parity mode, main agent supplies the expected matched-element
inventory at dispatch and UI/UX fills in the verdict + computed-style
cells per row. In consistency mode, UI/UX still builds the inventory
from scratch as before.

Substantive changes:

- New input bullet (parity mode): "the expected matched-element
  inventory table supplied by main agent at dispatch."
- Mandate paragraph: clarifies parity-mode role is verification of
  a supplied inventory, not discovery; consistency-mode unchanged.
- Mode A protocol rewritten as a per-row verification: locate the
  rendered atoms inside each supplied row, capture screenshots,
  evaluate the extraction snippet, fill the row's computed-style and
  verdict cells, file findings for drifting atoms.
- Output format adds "### Rows added beyond the supplied inventory"
  subsection. UI/UX uses it to flag visible elements observed in
  production or the prototype that weren't in the supplied inventory
  - these surface Scoping/Plan enumeration gaps back to main agent.
- "Determining completeness" splits into parity-mode (cross-check
  against the supplied inventory) and consistency-mode (today's
  exhaustive enumeration rules).
- Forbidden behaviors: new parity-mode entry "skipping rows in the
  supplied inventory or marking MATCH without filling cells";
  consistency-mode "Selectivity is parity drift" rule unchanged.
- Stop conditions: split into first-pass parity, first-pass
  consistency, bug-fix re-run parity (rows ∩ states scoping, returns
  delta inventory), bug-fix re-run consistency (today's state-based
  scoping).

Mode B (consistency) is unchanged in behavior. The two modes coexist
cleanly because the new contract activates only in parity mode.

Spec: docs/superpowers/specs/2026-05-12-inventory-as-contract-design.md
§5.3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Update `personal-workflow.md` (corollary + mode-mapping note)

**Files:**
- Modify: `skills/ticket-start/personal-workflow.md` — two small edits
- Sync: both install dirs

- [ ] **Step 1: Append corollary to "Prototype parity dominates" subsection**

Use the `Edit` tool. Find this block:

```
This rule exists because of an observed failure mode where this exact substitution happened and the UI/UX agent accepted it as "design-system compliant."

## Verification — Mode mapping for QA and UI/UX
```

Replace with:

```
This rule exists because of an observed failure mode where this exact substitution happened and the UI/UX agent accepted it as "design-system compliant."

**Corollary:** prototype enumeration in Scoping is mandatory in parity mode. The parity-dominance rule depends on having an authoritative list of what to maintain parity with; Scoping's `## Prototype elements relevant to this feature` section is that list. An empty section is a Scoping failure, not a clean report — see `agents/scoping.md` → forbidden behaviors.

## Verification — Mode mapping for QA and UI/UX
```

- [ ] **Step 2: Add a one-sentence note to the parity-mode line**

Use the `Edit` tool. Find this block:

```
- **`parity`** — when `designs/` is a runnable React reference app. UI/UX runs the existing protocol in `verification.md`: matched-element inventory, computed-style + bounding-rect extraction via DOM evaluation against the live browser, per-state coverage at all relevant breakpoints. Reference app is the absolute source of truth.
```

Replace with:

```
- **`parity`** — when `designs/` is a runnable React reference app. UI/UX runs the existing protocol in `verification.md`: matched-element inventory, computed-style + bounding-rect extraction via DOM evaluation against the live browser, per-state coverage at all relevant breakpoints. Reference app is the absolute source of truth. Main agent constructs the **expected matched-element inventory** at Verify dispatch (per `SKILL.md`'s Verify step 4a) from Scoping's prototype-element enumeration + the plan's `**Element mapping:**` blocks + the actual diff, and passes it to UI/UX as input.
```

- [ ] **Step 3: Verify the file**

```bash
grep -q "Corollary:.. prototype enumeration in Scoping is mandatory in parity mode" skills/ticket-start/personal-workflow.md && echo "Corollary present ✓"
grep -q "expected matched-element inventory.. at Verify dispatch" skills/ticket-start/personal-workflow.md && echo "Mode-mapping note present ✓"
```
Expected: both pass.

- [ ] **Step 4: Sync to install dirs**

```bash
cp skills/ticket-start/personal-workflow.md ~/.codex/skills/ticket-start/personal-workflow.md
cp skills/ticket-start/personal-workflow.md ~/.claude/skills/ticket-start/personal-workflow.md
diff -q skills/ticket-start/personal-workflow.md ~/.codex/skills/ticket-start/personal-workflow.md
diff -q skills/ticket-start/personal-workflow.md ~/.claude/skills/ticket-start/personal-workflow.md
```
Expected: both `diff -q` calls produce no output.

- [ ] **Step 5: Commit**

```bash
git add skills/ticket-start/personal-workflow.md
git commit -m "$(cat <<'EOF'
ticket-start: personal-workflow.md notes the parity inventory contract

Two additions:

- Corollary to the "Prototype parity dominates all other rules"
  subsection: prototype enumeration in Scoping is mandatory in parity
  mode. The parity-dominance rule depends on having an authoritative
  list of what to maintain parity with; Scoping's prototype-elements
  section is that list. Empty section = Scoping failure.

- One-sentence note on the parity-mode line under "Verification —
  Mode mapping": main agent constructs the expected matched-element
  inventory at Verify dispatch and passes it to UI/UX as input.

Spec: docs/superpowers/specs/2026-05-12-inventory-as-contract-design.md
§5.4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Update `verification.md` (parity-mode contract note + per-state procedure)

**Files:**
- Modify: `skills/ticket-start/verification.md` — two edits
- Sync: both install dirs

- [ ] **Step 1: Update opening of "Matched-element inventory (do this first)"**

Use the `Edit` tool. Find this block:

```
### Matched-element inventory (do this first)

**REQUIRED + EXHAUSTIVE.** Every visible element in the feature's surface gets a row. Selectivity is forbidden — "I checked the important ones" is parity drift. The completeness rules are detailed in `agents/ui-ux.md` → `## Determining completeness`; the four checks (diff-driven coverage, production-DOM coverage, prototype-DOM coverage, sibling/parent geometry) all apply here.

Before any comparison, enumerate matched element pairs for the feature. For every visible region — header, button, input, label, card, list item, icon, badge, link, divider, container — identify the matching element in both apps. Match by role, accessible name, text content, or `data-testid`. Record:
```

Replace with:

```
### Matched-element inventory (do this first)

**REQUIRED + EXHAUSTIVE.** Every visible element in the feature's surface gets a row. Selectivity is forbidden — "I checked the important ones" is parity drift.

In **parity mode**, the inventory is **supplied by main agent at Verify dispatch** (see `SKILL.md` → Verify step 4a). Your job is to verify each supplied row by running DOM evaluation against the live browsers and filling in the verdict + computed-style cells per row. If during verification you observe a visible element on either side that wasn't in the supplied inventory, add it to `### Rows added beyond the supplied inventory` in your report — it represents a Scoping/Plan enumeration gap, not a row to silently drop.

In **consistency mode**, you build the sibling/analog inventory yourself per `agents/ui-ux.md` → `## Determining completeness — consistency mode`.

The four completeness checks (diff-driven coverage, production-DOM coverage, prototype-DOM coverage, sibling/parent geometry) detailed in `agents/ui-ux.md` apply in both modes — they're built into the supplied inventory in parity mode and built by you in consistency mode.

Before any comparison, ensure the inventory is in hand (parity mode: supplied; consistency mode: built). For every visible region — header, button, input, label, card, list item, icon, badge, link, divider, container — identify the matching element in both apps (parity mode: per the supplied row; consistency mode: by inspection). Match by role, accessible name, text content, or `data-testid`. Record:
```

- [ ] **Step 2: Update per-state procedure step 3**

Use the `Edit` tool. Find this block:

```
3. **Programmatic style and layout extraction (REQUIRED).** For each matched pair, evaluate the extraction snippet at `scripts/extract-element-style.browser.js` against the DOM in both apps. The snippet returns a single JSON-serialisable object per element containing the computed-style and bounding-rect fields the matched-element inventory needs:
```

Replace with:

```
3. **Programmatic style and layout extraction (REQUIRED).** For each matched pair (parity mode: each supplied row; consistency mode: each row of the sibling/analog inventory you built), evaluate the extraction snippet at `scripts/extract-element-style.browser.js` against the DOM in both apps. The snippet returns a single JSON-serialisable object per element containing the computed-style and bounding-rect fields the matched-element inventory needs:
```

- [ ] **Step 3: Verify the file**

```bash
grep -q "In .\*parity mode.*, the inventory is .\*supplied by main agent at Verify dispatch" skills/ticket-start/verification.md && echo "Parity-mode supplied-inventory note ✓"
grep -q "Rows added beyond the supplied inventory" skills/ticket-start/verification.md && echo "Provenance-gap reference ✓"
grep -q "parity mode: each supplied row; consistency mode: each row of the sibling/analog inventory" skills/ticket-start/verification.md && echo "Per-state step 3 update ✓"
```
Expected: all three pass.

- [ ] **Step 4: Sync to install dirs**

```bash
cp skills/ticket-start/verification.md ~/.codex/skills/ticket-start/verification.md
cp skills/ticket-start/verification.md ~/.claude/skills/ticket-start/verification.md
diff -q skills/ticket-start/verification.md ~/.codex/skills/ticket-start/verification.md
diff -q skills/ticket-start/verification.md ~/.claude/skills/ticket-start/verification.md
```
Expected: both `diff -q` calls produce no output.

- [ ] **Step 5: Commit**

```bash
git add skills/ticket-start/verification.md
git commit -m "$(cat <<'EOF'
ticket-start: verification.md routes inventory by mode

Two updates to the matched-element inventory section:

- Opening note: in parity mode the inventory is supplied by main
  agent at Verify dispatch (per SKILL.md Verify step 4a); UI/UX
  verifies each supplied row and uses "Rows added beyond the
  supplied inventory" to flag enumeration gaps. In consistency mode,
  UI/UX builds the sibling/analog inventory itself.

- Per-state procedure step 3: clarifies that the per-pair extraction
  applies to "each supplied row" in parity mode and "each row of the
  sibling/analog inventory you built" in consistency mode.

The four completeness checks (diff-driven, production-DOM,
prototype-DOM, sibling/parent geometry) still apply in both modes -
they're built into the supplied inventory in parity mode and built
by UI/UX in consistency mode.

Spec: docs/superpowers/specs/2026-05-12-inventory-as-contract-design.md
§5.5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Lint + AGENTS.md self-review

**Files:**
- Verify (read-only): every file in `skills/ticket-start/`
- No commit (verification only)

- [ ] **Step 1: Frontmatter validation on SKILL.md**

```bash
head -1 skills/ticket-start/SKILL.md | grep -q '^---$' && echo "Frontmatter starts ✓" || echo "✗ Missing frontmatter"
awk '/^---$/{n++; next} n==1{print}' skills/ticket-start/SKILL.md | head -5
```
Expected: `Frontmatter starts ✓` and a valid `name:` + `description:` pair.

- [ ] **Step 2: No-placeholder scan**

```bash
grep -rnE '\b(TBD|FIXME|XXX|implement later|fill in details)\b' skills/ticket-start/ 2>/dev/null \
  | grep -v 'self-improvement.md' \
  || echo "no placeholders found ✓"
```
Expected: `no placeholders found ✓`.

- [ ] **Step 3: Cross-reference resolution**

```bash
missing=0
for f in agents/scoping.md agents/architect.md agents/reviewer.md \
         agents/security.md agents/qa.md agents/ui-ux.md \
         bug-fix-loop.md self-improvement.md \
         job-workflow.md personal-workflow.md \
         react-parity.md verification.md \
         SKILL.md scripts/extract-element-style.browser.js \
         agents/openai.yaml; do
  test -f "skills/ticket-start/$f" || { echo "MISSING: skills/ticket-start/$f"; missing=$((missing+1)); }
done
test "$missing" -eq 0 && echo "All cross-refs resolve ✓"
```
Expected: `All cross-refs resolve ✓`.

- [ ] **Step 4: Host-purity (no product/tool refs leaked)**

```bash
grep -rnE 'mcp__playwright|Playwright MCP|browser-use:browser|iab |Codex Browser plugin|browser_evaluate|browser_take_screenshot|browser_tabs' skills/ticket-start/ 2>/dev/null \
  && echo "✗ host-purity violation" \
  || echo "host-pure ✓"
```
Expected: `host-pure ✓`.

- [ ] **Step 5: Inventory-contract presence across files**

```bash
echo "=== scoping.md has Prototype elements section ==="
grep -q "^## Prototype elements relevant to this feature$" skills/ticket-start/agents/scoping.md && echo "✓" || echo "✗"
echo "=== SKILL.md Plan section has item 1a ==="
grep -q "^1a\. \*\*For parity-mode UI tickets\*\*" skills/ticket-start/SKILL.md && echo "✓" || echo "✗"
echo "=== SKILL.md Verify section has step 4a ==="
grep -q "^4a\. \*\*In parity mode, construct the expected matched-element inventory" skills/ticket-start/SKILL.md && echo "✓" || echo "✗"
echo "=== SKILL.md step 6a has the two-mode cross-check ==="
grep -q "cross-check the verified inventory.* against the expected inventory" skills/ticket-start/SKILL.md && echo "✓" || echo "✗"
echo "=== SKILL.md has the three new red flags ==="
grep -q "Main agent dispatching UI/UX in parity mode without supplying" skills/ticket-start/SKILL.md && echo "✓ (rf1)" || echo "✗ (rf1)"
grep -q "Scoping report.s .. Prototype elements relevant.* is empty" skills/ticket-start/SKILL.md && echo "✓ (rf2)" || echo "✗ (rf2)"
grep -q "UI/UX returns a verified inventory with rows that have blank" skills/ticket-start/SKILL.md && echo "✓ (rf3)" || echo "✗ (rf3)"
echo "=== ui-ux.md has supplied-inventory input bullet ==="
grep -q "expected matched-element inventory.. table supplied by main agent at dispatch" skills/ticket-start/agents/ui-ux.md && echo "✓" || echo "✗"
echo "=== ui-ux.md has Rows-added-beyond subsection ==="
grep -q "^### Rows added beyond the supplied inventory$" skills/ticket-start/agents/ui-ux.md && echo "✓" || echo "✗"
echo "=== ui-ux.md has bug-fix re-run parity scoping ==="
grep -q "Bug-fix re-run, parity mode.*affected rows . affected states" skills/ticket-start/agents/ui-ux.md && echo "✓" || echo "✗"
echo "=== personal-workflow.md has Corollary ==="
grep -q "Corollary:.. prototype enumeration in Scoping is mandatory in parity mode" skills/ticket-start/personal-workflow.md && echo "✓" || echo "✗"
echo "=== verification.md routes inventory by mode ==="
grep -q "In .\*parity mode.*, the inventory is .\*supplied by main agent at Verify dispatch" skills/ticket-start/verification.md && echo "✓" || echo "✗"
```
Expected: every line ends `✓`.

- [ ] **Step 6: Install-path sync**

```bash
for f in $(find skills/ticket-start -type f | sed 's|^skills/ticket-start/||'); do
  diff -q "skills/ticket-start/$f" "$HOME/.codex/skills/ticket-start/$f"
  diff -q "skills/ticket-start/$f" "$HOME/.claude/skills/ticket-start/$f"
done
echo "(empty above = all in sync ✓)"
```
Expected: every `diff -q` produces no output.

- [ ] **Step 7: AGENTS.md self-review checklist (re-run after the inventory-contract additions)**

```bash
echo "=== Agent tool names in prose (must be empty or only natural English) ==="
grep -nE '\b(Read|Write|Edit|MultiEdit|str_replace|ask_user_input_v0|TodoWrite|WebFetch|WebSearch|Glob|Grep|Bash)\b' skills/ticket-start/*.md skills/ticket-start/agents/*.md 2>/dev/null \
  | grep -vE 'Read access|Read the|Read only|Read this|Reads|re-read|Re-read|Read-only|natural language'
echo "=== Capability/fallback markers present in qa.md + ui-ux.md ==="
grep -l "Fallback chain" skills/ticket-start/agents/qa.md skills/ticket-start/agents/ui-ux.md
echo "=== ## Requires preconditions present in qa.md + ui-ux.md ==="
grep -l "^## Requires$" skills/ticket-start/agents/qa.md skills/ticket-start/agents/ui-ux.md
```
Expected: agent-tool-names grep produces only natural-English occurrences (manually inspect); both fallback-chain files listed; both Requires files listed.

- [ ] **Step 8: No commit (verification only)**

This task produces no file changes. If any check failed, return to the originating task (1–6) and fix.

---

### Task 8: Push branch + update PR description

**Files:**
- None directly. Pushes branch and edits PR #6.

- [ ] **Step 1: Confirm working tree clean**

```bash
git status
```
Expected: `nothing to commit, working tree clean`.

- [ ] **Step 2: Confirm commit history**

```bash
git log origin/ticket-start-visual-parity-enforcement..HEAD --oneline
```
Expected (order matches task execution):
```
<sha> ticket-start: verification.md routes inventory by mode
<sha> ticket-start: personal-workflow.md notes the parity inventory contract
<sha> ticket-start: ui-ux.md verifies a supplied inventory in parity mode
<sha> ticket-start: SKILL.md Verify phase adopts inventory-as-contract
<sha> ticket-start: SKILL.md Plan phase requires Element mapping in parity mode
<sha> ticket-start: scoping.md emits prototype-element enumeration in parity mode
<sha> ticket-start: add inventory-as-contract design spec
```
7 new commits on top of the canonical-migration commit.

- [ ] **Step 3: Push the branch**

```bash
git push origin ticket-start-visual-parity-enforcement
```
Expected: push succeeds.

- [ ] **Step 4: Update PR #6 description**

```bash
gh pr edit 6 --body "$(cat <<'EOF'
## Summary

This PR lands three coordinated changes to the `ticket-start` skill:

1. **Visual-parity enforcement** — after a real personal-workflow ticket shipped with substantial prototype-vs-production visual differences and the UI/UX subagent reported "Visual findings: None," we tightened the protocol to make the failure mode structurally impossible (mandatory + exhaustive inventory, four completeness rules, main-agent step 6a, prototype-parity dominance, three new red flags).

2. **Canonical-skill migration** — consolidated the legacy duplicated layout (`codex/skills/ticket-start/` + `claude/skills/ticket-start/`) into a single canonical `skills/ticket-start/`, in line with the AGENTS.md repo + authoring rules from PR #5. All product/tool references swapped to intent-level capability language; fallback chains added; non-trivial extraction logic moved to `scripts/`.

3. **Inventory-as-contract** — moved matched-element-inventory construction upstream from UI/UX into Scoping (prototype side) + Plan (production-side mapping) + main agent at Verify dispatch (stitched table). UI/UX's role narrows from discovery+verification to verification of a supplied inventory. Step 6a now cross-checks expected vs verified inventories. Activated only in parity mode (personal workflow + runnable React reference app).

### Inventory-as-contract changes (this commit set)

- **`agents/scoping.md`** — new `## Prototype elements relevant to this feature` section; required for parity-mode UI tickets, `_None._` otherwise.
- **`SKILL.md` Plan phase** — new item 1a requiring `**Element mapping:**` blocks in parity-mode plan tasks that touch visible elements.
- **`SKILL.md` Verify phase** — new step 4a constructs the expected inventory at dispatch; step 5 dispatch inputs gain a "supplied inventory" bullet; step 6a rewritten as a two-mode cross-check (parity: verified-vs-expected; consistency: today's spot-check); three new red flags.
- **`agents/ui-ux.md`** — Mandate clarifies parity-mode role is verification not discovery; Mode A protocol rewritten as per-row verification; output format gains `### Rows added beyond the supplied inventory` subsection (surfaces planning gaps back to main); Forbidden behaviors split by mode; Stop conditions split into first-pass + bug-fix re-run, with parity-mode re-runs scoped to **affected rows ∩ affected states** returning a delta inventory.
- **`personal-workflow.md`** — corollary to "Prototype parity dominates" subsection (Scoping enumeration is mandatory in parity mode); one-sentence note on parity-mode mode-mapping bullet pointing at the contract.
- **`verification.md`** — opening of the matched-element inventory section routes by mode; per-state procedure step 3 reworded.

### Self-review checklist (per AGENTS.md "Rules for Writing Cross-Agent Skills")

- [x] No specific agent tool names in prose (grep clean for `Read`/`Write`/`Edit`/etc. used as tool references).
- [x] Non-trivial logic in `scripts/`. (No new scripts in v3; inventory construction is main-agent reasoning at dispatch. Per spec §7, revisit after first parity-mode ticket exercises it in practice.)
- [x] Fallback chain for live-browser capability documented in `agents/qa.md` and `agents/ui-ux.md`.
- [x] Required capabilities declared at the top of subagent role prompts.
- [ ] Skill has been run end-to-end on at least one target agent — empirical validation happens on the next parity-mode ticket.
- [x] No copy of this skill exists for a different agent (canonical layout established in commit fc5ee37).
- [x] No adapter files (or `agents/openai.yaml` interpreted as one: 4 lines, well under 30).
- [x] Synced to both `~/.codex/skills/ticket-start/` and `~/.claude/skills/ticket-start/`.

### Specs and plans

- Visual-parity spec: `docs/superpowers/specs/2026-05-11-visual-parity-enforcement-design.md`.
- Visual-parity plan: `docs/superpowers/plans/2026-05-11-visual-parity-enforcement.md`.
- Inventory-as-contract spec: `docs/superpowers/specs/2026-05-12-inventory-as-contract-design.md`.
- Inventory-as-contract plan: `docs/superpowers/plans/2026-05-12-inventory-as-contract.md`.

## Test plan

This change is in skill files (markdown + one JS snippet). Behavioral validation happens on the next parity-mode ticket. Until then:

- [x] Canonical tree is host-pure (zero product/tool-name hits).
- [x] All cross-refs resolve.
- [x] Install-path sync clean for both `~/.codex/skills/ticket-start/` and `~/.claude/skills/ticket-start/`.
- [x] AGENTS.md self-review checklist re-runs clean after each set of changes.
- [ ] On the next parity-mode ticket: confirm Scoping produces a non-empty `## Prototype elements relevant to this feature` section.
- [ ] On the same ticket: confirm the plan's UI-touching tasks include `**Element mapping:**` blocks.
- [ ] On the same ticket: confirm main agent constructs the expected inventory at Verify dispatch and passes it to UI/UX.
- [ ] On the same ticket: confirm UI/UX returns a verified inventory with all cells filled, and step 6a's cross-check rejects any verdict where cells are blank.
- [ ] Force-test: deliberately produce a Scoping report with `_None._` in the prototype-elements section for a parity-mode UI ticket; confirm the workflow halts and surfaces the gap.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR description updated successfully.

- [ ] **Step 5: Final summary to user**

Produce a short closeout summary covering:
- PR URL (still PR #6).
- Commits added in this round (7: 1 spec + 6 implementation).
- Total commits on the branch.
- Activation behavior reminder: contract is inactive until the next parity-mode ticket goes through Setup with the new Scoping behavior.
- What is **not** verified by this plan: runtime behavior on a real parity-mode ticket. The protocol is hardened at the skill-file level; whether the contract actually changes agent behavior is empirical and only the next real ticket can confirm.
- Next steps for the user: review PR #6, optionally test on a real parity-mode ticket.

---

## Self-review

### 1. Spec coverage

Mapping each spec section to a task:

- **§1 Problem statement + §2 Goals/non-goals** — captured in the plan header (Goal, Architecture). ✓
- **§3 Architectural decisions** — encoded across Tasks 1-6. Format (C from Q1): main agent stitches at dispatch (Task 3, step 4a). Granularity (C from Q2): JSX-declaration rows on each side (Tasks 1, 3, 4 — Scoping enumeration is JSX-declaration; SKILL.md step 4a builds JSX-declaration rows; ui-ux.md verifies per-row). Scope (A from Q3): implementation-scoped only (Tasks 2, 4 — Plan element mappings; ui-ux.md's "Rows added beyond" flags planning gaps without making the inventory surface-scoped). ✓
- **§4 Phase data flow** — implemented end-to-end across Tasks 1 (Scoping), 2 (Plan), 3 (Verify dispatch + step 6a), 4 (UI/UX role). ✓
- **§4.1 Invariants** — supplied-inventory contract enforces them (Tasks 3, 4). ✓
- **§5 File-by-file changes** — Tasks 1-6 each implement one file's section. ✓
- **§6 Activation, bug-fix loop, edge cases** — activation gate built into Task 3 step 4a's first sentence ("Skip this step in consistency mode"); bug-fix re-run scoping is Task 4's Stop conditions update; edge cases are addressed in the construction-failure language of Task 3 step 4a and the "Rows added beyond" subsection in Task 4. ✓
- **§7 Deferred to implementation plan** — addressed in plan-level decision 5 ("No helper script in v1") and in the inventory-construction language of Task 3 step 4a. ✓
- **§8 Migration and scope** — purely additive; spec §8's "no behavioral change in job workflow or in personal-workflow tickets without a React reference app" is satisfied because every change is mode-gated. ✓

No spec gaps.

### 2. Placeholder scan

I searched the plan for: TBD, FIXME, XXX, "implement later," "fill in details," "Similar to Task N." The only `<placeholder>` style tokens are intentional substitution markers in file content (e.g., `<ticket title>`, `<path>`) — same convention as prior plans. No real TBDs in instruction-bearing parts.

### 3. Type / name consistency

Cross-checked names used across tasks:

- File paths: `agents/scoping.md`, `SKILL.md`, `agents/ui-ux.md`, `personal-workflow.md`, `verification.md` — consistent across Tasks 1-7.
- Section names: `## Prototype elements relevant to this feature` (Tasks 1, 3, 4, 5, 7); `## Matched-element inventory` (Tasks 3, 4, 6); `### Rows added beyond the supplied inventory` (Tasks 4, 6); `**Element mapping:**` block (Tasks 2, 3, 4 references); step number `4a` (Tasks 3, 5, 6); step number `6a` (Tasks 3, 7); item number `1a` (Tasks 2, 7).
- Verdict tokens: MATCH / DRIFT / MISSING used consistently in Tasks 3 (step 6a accepts MISSING when planned) and 4 (verdict definitions).
- Phrase consistency: "expected matched-element inventory" (Tasks 3, 4, 5, 7); "verified inventory" (Tasks 3, 4, 7); "supplied inventory" (Tasks 4, 6).

No inconsistencies found.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-12-inventory-as-contract.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, two-stage review per task (spec compliance + code quality), fast iteration. Best fit for this plan because each task is one file with self-contained edits; reviewers can spot drift early (e.g., a forgotten install-dir sync, or a section-name typo between tasks).

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batched with checkpoints. Faster wallclock; less isolation between tasks.

**Which approach?**
