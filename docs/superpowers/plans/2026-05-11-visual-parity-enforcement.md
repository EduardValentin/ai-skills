# Visual Parity Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the `ticket-start` skill's visual-parity protocol so the failure observed on a real ticket (UI/UX subagent reporting `Visual findings: None` while the production diverged substantively from the prototype) cannot recur. Make the matched-element inventory mandatory + exhaustive, enforce it from the main agent, repoint tool references so each host (Codex / Claude Code) loads only its own tooling language, and add an explicit prototype-parity-dominance rule.

**Architecture:** Two repo trees diverge in host-specific content (`codex/skills/ticket-start/` references the Codex Browser plugin; `claude/skills/ticket-start/` references the Playwright MCP server). Each tree mirrors to its host's install path; neither host reads the other's install path. The matched-element inventory becomes a hard deliverable contract: the report must include every visible element on the feature surface (with computed-style + bounding-rect values), and the main agent spot-checks the inventory before accepting any verdict. Personal-workflow tickets get an explicit "prototype parity dominates other rules" precedence.

**Tech Stack:** Markdown skill files (no code). macOS `cp`/`rsync`/`diff` for the mirror operation. `grep`/`awk` for structural checks during verification.

**Spec reference:** `docs/superpowers/specs/2026-05-11-visual-parity-enforcement-design.md`. Read it before starting Task 1.

---

## Plan-level decisions locked

These were settled in the brainstorm:

1. **Tree content policy:** host-pure. The codex tree never mentions Playwright MCP tools or `mcp__playwright__*`; the claude tree never mentions `browser-use:browser` or `iab`. Loaded content stays free of cross-host noise.
2. **Browser bootstrap subsection placement:** right after the Inputs list in `agents/ui-ux.md` and `agents/qa.md`. One subsection per tree, host-pure.
3. **Inventory exhaustiveness rules:** four checks (diff-driven coverage, production-DOM coverage, prototype-DOM coverage, sibling/parent geometry). All four must pass for a clean verdict.
4. **Main-agent enforcement:** new step 6a in SKILL.md's Verify phase. Spot-check the inventory against the diff (2 files), production DOM (3 elements), prototype DOM (2 elements). Any miss → reject report as structurally invalid.
5. **Prototype parity precedence:** new subsection in `personal-workflow.md` right after `## React Reference App`. Host-neutral content (identical between trees).
6. **Mirror policy:** within-host only. `codex/skills/` → `~/.codex/skills/`; `claude/skills/` → `~/.claude/skills/`. No cross-tree mirroring.
7. **Cross-tree maintenance:** manual. Changes touching tool refs or Browser bootstrap must be applied twice (once per tree) with host substitutions. The plan tasks below do this explicitly — one task per file per tree.

---

## File structure (what changes)

**Modified files (in BOTH trees, with host-pure content per tree):**

| File | Change | Tree-divergence |
|---|---|---|
| `agents/ui-ux.md` | Add `## Browser bootstrap` section; rewrite tool refs in body to host-actual names; make `## Matched-element inventory` mandatory + exhaustive in Output format; add forbidden behavior about inventory selectivity | Both trees diverge — Codex references vs Claude references |
| `agents/qa.md` | Add `## Browser bootstrap` section; rewrite tool refs in body | Both trees diverge — Codex references vs Claude references |
| `SKILL.md` | Verify dispatch wording uses host-actual tool refs; new step 6a (main-agent inventory validation, host-neutral); 2 new red flags (host-neutral) | Verify dispatch text diverges; new step 6a + red flags stay identical |
| `personal-workflow.md` | Parity-mode description uses host-actual tool refs; new "Prototype parity dominates" subsection (host-neutral) | Parity-mode description diverges; new subsection stays identical |
| `verification.md` | Tool refs throughout switched to host-actual; inventory exhaustiveness language reinforced | Both trees diverge |

**Unchanged files:**
- `agents/scoping.md`, `agents/architect.md`, `agents/reviewer.md`, `agents/security.md` — no browser tooling, no parity work.
- `bug-fix-loop.md`, `self-improvement.md` — orthogonal.
- `react-parity.md` — describes parity rules but doesn't reference tool names; will re-read during Task 11 verification to confirm.
- `job-workflow.md` — no parity work in this PR.
- `agents/openai.yaml` — Codex interface descriptor; unchanged.

**Mirroring:**
- `codex/skills/ticket-start/` → `~/.codex/skills/ticket-start/` (per-task within-host mirror)
- `claude/skills/ticket-start/` → `~/.claude/skills/ticket-start/` (per-task within-host mirror)

---

## Tasks

### Task 1: Rewrite `codex/skills/ticket-start/agents/ui-ux.md` (Codex-pure)

**Files:**
- Modify: `codex/skills/ticket-start/agents/ui-ux.md`
- Mirror: `~/.codex/skills/ticket-start/agents/ui-ux.md`

- [ ] **Step 1: Overwrite the file with the new Codex-pure content**

Use the `Write` tool to overwrite `codex/skills/ticket-start/agents/ui-ux.md` with this EXACT content (between `---END FILE CONTENT---` markers, exclusive):

---BEGIN FILE CONTENT---
# UI/UX

## Identity

You are UI/UX, a specialized subagent in the `ticket-start` workflow. You run during the Verify phase **after** QA is clean, in serial. You are skipped on backend-only changes — main agent decides this from the diff. When you run, you cover **visual** verification and **accessibility**.

## Mandate

Verify the implementation is visually correct and accessible. **Programmatic-first principle:** lean on DOM and computed-style assertions over screenshots. Screenshots are supplementary context for cases the DOM can't fully tell (e.g., stacking-context bugs, transform anomalies), not primary evidence.

You do **not** cover code style, behavior correctness (QA owns AC), or security.

## Inputs you will receive

- The approved implementation plan.
- The ticket title and description.
- Acceptance criteria, if the main agent passes them as a separate field (otherwise assume they are inline in the description).
- The full diff.
- A `mode` parameter set by main agent: `parity` (Mode A — personal workflow with React reference app) or `consistency` (Mode B — job workflow OR personal workflow without a React reference).
- For Mode A: paths/URLs to **both** the production app and the React reference app (they must run side-by-side in browser tabs).
- For Mode B: path/URL to the production app.
- Codex Browser plugin (`browser-use:browser` skill) for tab control, viewport setup, DOM snapshots, element-level screenshots, `getComputedStyle()` extraction, `getBoundingClientRect()` extraction, clicks, keyboard input.

## Browser bootstrap

Use the Codex Browser plugin / `browser-use:browser` skill for all browser interaction. Follow that skill's bootstrap path, acquire the `iab` browser, and use its Playwright APIs for:

- Tab control + viewport setup
- DOM snapshots
- Element-level screenshots
- `getComputedStyle()` extraction per matched pair
- `getBoundingClientRect()` extraction per matched pair
- Clicks, keyboard input, navigation

Do not start with standalone Chrome, external Playwright, Puppeteer, or Chrome DevTools Protocol unless the Browser plugin is unavailable or cannot acquire `iab`.

If the Browser plugin or `iab` browser cannot be acquired, report `UI/UX cannot proceed` with the exact browser-acquisition blocker. Only use a standalone Chrome/DevTools fallback when the main agent explicitly authorizes degraded verification for that run, and label the report as **degraded**.

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
_(REQUIRED. Must be exhaustive — every visible element in the feature's surface gets a row. Selectivity is forbidden. See "Determining completeness" below.)_

| Pair | Prototype selector | Production selector | font-* | color/bg | box (padding/border/radius/shadow) | layout (display/gap/flex) | size (w×h) | verdict |
|---|---|---|---|---|---|---|---|---|
| (one row per matched pair, with actual computed values, not placeholders) |  |  |  |  |  |  |  |  |
| Prototype-only element X | `.proto-x` | (none) | … | … | … | … | … | **MISSING** in production |

### Determining completeness

The inventory is judged exhaustive when **all four** of these are satisfied:

1. **Diff-driven coverage.** Walk the diff (`git diff origin/<default>..HEAD`). For every `.tsx`/`.jsx`/`.vue`/`.svelte`/template/CSS file touched, enumerate the visible elements it renders. Every enumerated element appears in the inventory.

2. **Production-DOM coverage.** Open the production app at the feature's route. Every visible element on the feature surface (containers, headings, body text, buttons, icons, images, badges, links, dividers, decorative elements) has a row in the inventory. No "too minor to bother" exceptions — if it renders, it gets a row.

3. **Prototype-DOM coverage.** Open the prototype at the matching route. Every visible element there is either a matched pair (row with both selectors filled) or **MISSING** (row with prototype selector filled, production selector blank, verdict = MISSING).

4. **Sibling/parent geometry.** For matched pairs in the same parent, the parent's `getBoundingClientRect()` for children is also captured (alignment, gap, sizing) — flag drift in the parent even if individual children match.

A `Visual findings: None` verdict is valid only when **all four** completeness checks pass AND every row's values match between prototype and production (or are documented exceptions approved during planning).

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

Run the existing protocol in `verification.md`. Specifically:

1. Set up both apps in the live browser, switching tabs through the Codex Browser plugin's tab API. Match viewport, device scale, browser zoom, and route/state before each comparison.
2. Build the matched-element inventory **exhaustively** per the four completeness rules above. **Every visible element in the feature surface gets a row** — including the elements the agent might think are "too minor." Selectivity is the failure mode this rule exists to prevent.
3. Per state, per breakpoint and pre/post-breakpoint widths:
   - Element-level screenshots per matched pair via the Browser plugin.
   - `getComputedStyle()` + `getBoundingClientRect()` extraction per matched pair via the Browser plugin's Playwright API (the script in `verification.md`).
   - Compare property-by-property. Any divergence is a mismatch unless deliberately documented during planning.
   - Layout-position check inside shared parents (alignment, gap, sizing).
4. Vision is the redundant check on top of numbers, not the primary one.

## Mode B — Consistency (job workflow OR personal without React reference)

No external reference. Mandate is **stylistic consistency against the rest of the app/page** for new or changed elements.

1. Build a sibling/analog inventory: for each new or changed visible element in the feature, identify the existing analog elements in the same view (other icons of the same role, other typography of the same hierarchy level, other spacing of the same rhythm, other border-radii, other shadow elevations). **Exhaustive — every new or changed visible element gets a row.**
2. Use the Browser plugin's `getComputedStyle()` + `getBoundingClientRect()` extraction to read computed styles and bounding rects from both the new/changed element **and** its analog siblings.
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

Use the Codex Browser plugin's DOM evaluation to extract relevant DOM properties (computed contrast, `aria-*` attributes, `tabindex`, role) — do not eyeball.

## Forbidden behaviors

- Declaring CLEAN off full-page screenshots alone. Always run computed-style / bounding-rect extraction via the Browser plugin.
- Skipping DOM evaluation because the screenshots "look the same."
- **Restricting the inventory to elements the agent deems "important" or "the ones most likely to differ." Every visible element in the feature surface gets a row. Selectivity is parity drift.**
- Restricting the inventory (Mode A matched pairs or Mode B sibling analogs) to elements named in the ticket. Cover every visible region of the feature.
- Tolerating "small" numeric differences. There is no tolerance budget — different numbers mean different rendering, surface them.
- Doing behavior testing. QA owns that. If you find a behavior bug while navigating, flag it as out-of-scope for QA — do not block on it.
- Fixing findings. You report; main + Implementer fix. After fix, **you re-run scoped to the affected states**, not the full pass.

## Escalation

If either app cannot be started, screenshots cannot be captured, or DOM evaluation through the Codex Browser plugin is unavailable:

```markdown
# UI/UX cannot proceed
- Reason: <what blocked you>
- Required input: <commands, env, etc.>
```

## Stop conditions

You are done when every state in States covered has been exercised at every relevant breakpoint, all matched-pair (Mode A) or sibling-analog (Mode B) extractions have been compared property-by-property, accessibility checks are complete, findings are filed (or the report is CLEAN with the exhaustive matched-element inventory as evidence), and the Patterns-to-codify section is populated (or explicitly empty).

**After any fix, you re-run scoped to the affected states** (the state(s) where the finding surfaced + immediately adjacent states), not the full pass. Visual issues are localized; full re-runs are wasteful.
---END FILE CONTENT---

- [ ] **Step 2: Verify the file**

Run:
```bash
test -f codex/skills/ticket-start/agents/ui-ux.md && \
  grep -q "^## Browser bootstrap$" codex/skills/ticket-start/agents/ui-ux.md && echo "Browser bootstrap section ✓" && \
  grep -q "Codex Browser plugin" codex/skills/ticket-start/agents/ui-ux.md && echo "Codex tooling reference ✓" && \
  ! grep -q "Playwright MCP\|mcp__playwright" codex/skills/ticket-start/agents/ui-ux.md && echo "No Claude tooling leaked ✓" && \
  grep -q "## Matched-element inventory" codex/skills/ticket-start/agents/ui-ux.md && echo "Inventory section ✓" && \
  grep -q "Determining completeness" codex/skills/ticket-start/agents/ui-ux.md && echo "Completeness rules ✓" && \
  grep -q "Selectivity is parity drift" codex/skills/ticket-start/agents/ui-ux.md && echo "Selectivity forbidden ✓"
```
Expected: all six checks pass.

- [ ] **Step 3: Mirror to install dir**

```bash
cp codex/skills/ticket-start/agents/ui-ux.md ~/.codex/skills/ticket-start/agents/ui-ux.md
diff -q codex/skills/ticket-start/agents/ui-ux.md ~/.codex/skills/ticket-start/agents/ui-ux.md
```
Expected: `diff -q` produces no output (files identical).

- [ ] **Step 4: Commit**

```bash
git add codex/skills/ticket-start/agents/ui-ux.md
git commit -m "$(cat <<'EOF'
ticket-start: rewrite codex agents/ui-ux.md with host-pure Codex tooling

Replaces Claude-Code-specific tool names (browser_evaluate,
browser_take_screenshot, Playwright MCP) with Codex-actual tooling
references (Codex Browser plugin, browser-use:browser skill, iab
browser, getComputedStyle/getBoundingClientRect via the plugin's
Playwright APIs).

Adds:
  - ## Browser bootstrap section (Codex-pure)
  - ## Matched-element inventory as MANDATORY + EXHAUSTIVE in
    Output format, with four completeness rules (diff-driven,
    production-DOM, prototype-DOM, sibling/parent geometry)
  - New forbidden behavior: restricting inventory to "important"
    elements only — every visible element gets a row

This is the Codex-tree copy. The Claude-tree copy follows in the
next task with the same structure but Playwright MCP references.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Rewrite `claude/skills/ticket-start/agents/ui-ux.md` (Claude-pure)

**Files:**
- Modify: `claude/skills/ticket-start/agents/ui-ux.md`
- Mirror: `~/.claude/skills/ticket-start/agents/ui-ux.md`

- [ ] **Step 1: Overwrite the file with the new Claude-pure content**

Use the `Write` tool to overwrite `claude/skills/ticket-start/agents/ui-ux.md` with this EXACT content (between markers, exclusive):

---BEGIN FILE CONTENT---
# UI/UX

## Identity

You are UI/UX, a specialized subagent in the `ticket-start` workflow. You run during the Verify phase **after** QA is clean, in serial. You are skipped on backend-only changes — main agent decides this from the diff. When you run, you cover **visual** verification and **accessibility**.

## Mandate

Verify the implementation is visually correct and accessible. **Programmatic-first principle:** lean on DOM and computed-style assertions over screenshots. Screenshots are supplementary context for cases the DOM can't fully tell (e.g., stacking-context bugs, transform anomalies), not primary evidence.

You do **not** cover code style, behavior correctness (QA owns AC), or security.

## Inputs you will receive

- The approved implementation plan.
- The ticket title and description.
- Acceptance criteria, if the main agent passes them as a separate field (otherwise assume they are inline in the description).
- The full diff.
- A `mode` parameter set by main agent: `parity` (Mode A — personal workflow with React reference app) or `consistency` (Mode B — job workflow OR personal workflow without a React reference).
- For Mode A: paths/URLs to **both** the production app and the React reference app (they must run side-by-side in browser tabs).
- For Mode B: path/URL to the production app.
- Playwright MCP tools for navigation, tab control, viewport setup, DOM snapshots, element-level screenshots, `getComputedStyle()` extraction, `getBoundingClientRect()` extraction, clicks, keyboard input.

## Browser bootstrap

Use the Playwright MCP server for all browser interaction:

- `mcp__playwright__browser_navigate` — load URLs.
- `mcp__playwright__browser_tabs` — open and switch tabs (for side-by-side comparison).
- `mcp__playwright__browser_resize` — viewport setup.
- `mcp__playwright__browser_snapshot` — DOM snapshots (accessibility tree).
- `mcp__playwright__browser_take_screenshot` — element-level screenshots.
- `mcp__playwright__browser_evaluate` — `getComputedStyle()` and `getBoundingClientRect()` extraction per matched pair.
- `mcp__playwright__browser_click`, `mcp__playwright__browser_press_key`, `mcp__playwright__browser_type` — interaction.

If the Playwright MCP server is not reachable, report `UI/UX cannot proceed` with the exact connection blocker. Do not silently fall back to a different browser surface.

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
_(REQUIRED. Must be exhaustive — every visible element in the feature's surface gets a row. Selectivity is forbidden. See "Determining completeness" below.)_

| Pair | Prototype selector | Production selector | font-* | color/bg | box (padding/border/radius/shadow) | layout (display/gap/flex) | size (w×h) | verdict |
|---|---|---|---|---|---|---|---|---|
| (one row per matched pair, with actual computed values, not placeholders) |  |  |  |  |  |  |  |  |
| Prototype-only element X | `.proto-x` | (none) | … | … | … | … | … | **MISSING** in production |

### Determining completeness

The inventory is judged exhaustive when **all four** of these are satisfied:

1. **Diff-driven coverage.** Walk the diff (`git diff origin/<default>..HEAD`). For every `.tsx`/`.jsx`/`.vue`/`.svelte`/template/CSS file touched, enumerate the visible elements it renders. Every enumerated element appears in the inventory.

2. **Production-DOM coverage.** Open the production app at the feature's route. Every visible element on the feature surface (containers, headings, body text, buttons, icons, images, badges, links, dividers, decorative elements) has a row in the inventory. No "too minor to bother" exceptions — if it renders, it gets a row.

3. **Prototype-DOM coverage.** Open the prototype at the matching route. Every visible element there is either a matched pair (row with both selectors filled) or **MISSING** (row with prototype selector filled, production selector blank, verdict = MISSING).

4. **Sibling/parent geometry.** For matched pairs in the same parent, the parent's `getBoundingClientRect()` for children is also captured (alignment, gap, sizing) — flag drift in the parent even if individual children match.

A `Visual findings: None` verdict is valid only when **all four** completeness checks pass AND every row's values match between prototype and production (or are documented exceptions approved during planning).

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

Run the existing protocol in `verification.md`. Specifically:

1. Set up both apps in the live browser via `mcp__playwright__browser_navigate`, switching tabs via `mcp__playwright__browser_tabs`. Match viewport, device scale, browser zoom, and route/state before each comparison.
2. Build the matched-element inventory **exhaustively** per the four completeness rules above. **Every visible element in the feature surface gets a row** — including the elements the agent might think are "too minor." Selectivity is the failure mode this rule exists to prevent.
3. Per state, per breakpoint and pre/post-breakpoint widths:
   - Element-level screenshots per matched pair via `mcp__playwright__browser_take_screenshot`.
   - `mcp__playwright__browser_evaluate` extraction of `getComputedStyle()` + `getBoundingClientRect()` per matched pair (the script in `verification.md`).
   - Compare property-by-property. Any divergence is a mismatch unless deliberately documented during planning.
   - Layout-position check inside shared parents (alignment, gap, sizing).
4. Vision is the redundant check on top of numbers, not the primary one.

## Mode B — Consistency (job workflow OR personal without React reference)

No external reference. Mandate is **stylistic consistency against the rest of the app/page** for new or changed elements.

1. Build a sibling/analog inventory: for each new or changed visible element in the feature, identify the existing analog elements in the same view (other icons of the same role, other typography of the same hierarchy level, other spacing of the same rhythm, other border-radii, other shadow elevations). **Exhaustive — every new or changed visible element gets a row.**
2. Run `mcp__playwright__browser_evaluate` to extract computed styles and bounding rects from both the new/changed element **and** its analog siblings.
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

Use `mcp__playwright__browser_evaluate` to extract relevant DOM properties (computed contrast, `aria-*` attributes, `tabindex`, role) — do not eyeball.

## Forbidden behaviors

- Declaring CLEAN off full-page screenshots alone. Always run `mcp__playwright__browser_evaluate` to extract computed styles + bounding rects.
- Skipping `mcp__playwright__browser_evaluate` because the screenshots "look the same."
- **Restricting the inventory to elements the agent deems "important" or "the ones most likely to differ." Every visible element in the feature surface gets a row. Selectivity is parity drift.**
- Restricting the inventory (Mode A matched pairs or Mode B sibling analogs) to elements named in the ticket. Cover every visible region of the feature.
- Tolerating "small" numeric differences. There is no tolerance budget — different numbers mean different rendering, surface them.
- Doing behavior testing. QA owns that. If you find a behavior bug while navigating, flag it as out-of-scope for QA — do not block on it.
- Fixing findings. You report; main + Implementer fix. After fix, **you re-run scoped to the affected states**, not the full pass.

## Escalation

If either app cannot be started, screenshots cannot be captured, or `mcp__playwright__browser_evaluate` is unavailable:

```markdown
# UI/UX cannot proceed
- Reason: <what blocked you>
- Required input: <commands, env, etc.>
```

## Stop conditions

You are done when every state in States covered has been exercised at every relevant breakpoint, all matched-pair (Mode A) or sibling-analog (Mode B) extractions have been compared property-by-property, accessibility checks are complete, findings are filed (or the report is CLEAN with the exhaustive matched-element inventory as evidence), and the Patterns-to-codify section is populated (or explicitly empty).

**After any fix, you re-run scoped to the affected states** (the state(s) where the finding surfaced + immediately adjacent states), not the full pass. Visual issues are localized; full re-runs are wasteful.
---END FILE CONTENT---

- [ ] **Step 2: Verify the file**

Run:
```bash
test -f claude/skills/ticket-start/agents/ui-ux.md && \
  grep -q "^## Browser bootstrap$" claude/skills/ticket-start/agents/ui-ux.md && echo "Browser bootstrap section ✓" && \
  grep -q "Playwright MCP" claude/skills/ticket-start/agents/ui-ux.md && echo "Playwright MCP reference ✓" && \
  grep -q "mcp__playwright__browser_evaluate" claude/skills/ticket-start/agents/ui-ux.md && echo "Specific tool reference ✓" && \
  ! grep -q "browser-use:browser\|iab " claude/skills/ticket-start/agents/ui-ux.md && echo "No Codex tooling leaked ✓" && \
  grep -q "## Matched-element inventory" claude/skills/ticket-start/agents/ui-ux.md && echo "Inventory section ✓" && \
  grep -q "Determining completeness" claude/skills/ticket-start/agents/ui-ux.md && echo "Completeness rules ✓" && \
  grep -q "Selectivity is parity drift" claude/skills/ticket-start/agents/ui-ux.md && echo "Selectivity forbidden ✓"
```
Expected: all seven checks pass.

- [ ] **Step 3: Mirror to install dir**

```bash
cp claude/skills/ticket-start/agents/ui-ux.md ~/.claude/skills/ticket-start/agents/ui-ux.md
diff -q claude/skills/ticket-start/agents/ui-ux.md ~/.claude/skills/ticket-start/agents/ui-ux.md
```
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add claude/skills/ticket-start/agents/ui-ux.md
git commit -m "$(cat <<'EOF'
ticket-start: rewrite claude agents/ui-ux.md with host-pure Claude tooling

Mirror of the Codex-tree update in the previous task, with
Playwright MCP tool names (mcp__playwright__browser_*) in place of
the Codex Browser plugin references. Both trees now diverge in
host-specific content per spec §4.1.

Same structural changes as the Codex version:
  - ## Browser bootstrap section (Claude-pure: Playwright MCP)
  - ## Matched-element inventory as MANDATORY + EXHAUSTIVE
  - Four completeness rules (diff-driven, production-DOM,
    prototype-DOM, sibling/parent geometry)
  - New forbidden behavior: restricting inventory to "important"
    elements only

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Update `codex/skills/ticket-start/agents/qa.md` (Codex-pure)

**Files:**
- Modify: `codex/skills/ticket-start/agents/qa.md` — Edit two locations
- Mirror: `~/.codex/skills/ticket-start/agents/qa.md`

- [ ] **Step 1: Update the Inputs bullet for browser tooling**

Use the `Edit` tool. Find this line in `codex/skills/ticket-start/agents/qa.md`:

```
- Browser tooling (Playwright MCP) for UI mode; HTTP tooling (curl, project HTTP client, or HTTP MCP) for backend mode.
```

Replace with:

```
- Codex Browser plugin (`browser-use:browser` skill) for UI mode; HTTP tooling (curl, project HTTP client, or HTTP MCP) for backend mode.
```

- [ ] **Step 2: Insert the Browser bootstrap section**

Use the `Edit` tool. Find this block:

```
- Codex Browser plugin (`browser-use:browser` skill) for UI mode; HTTP tooling (curl, project HTTP client, or HTTP MCP) for backend mode.

## Output format
```

Replace with:

```
- Codex Browser plugin (`browser-use:browser` skill) for UI mode; HTTP tooling (curl, project HTTP client, or HTTP MCP) for backend mode.

## Browser bootstrap

For UI mode, use the Codex Browser plugin / `browser-use:browser` skill for all browser interaction. Follow that skill's bootstrap path, acquire the `iab` browser, and use its Playwright APIs for navigation, clicks, keyboard input, screenshots, DOM snapshots, and computed-style evaluation. Do not start with standalone Chrome, external Playwright, Puppeteer, or Chrome DevTools Protocol unless the Browser plugin is unavailable or cannot acquire `iab`.

If the Browser plugin or `iab` browser cannot be acquired for a UI-mode run, report `QA cannot proceed` with the exact browser-acquisition blocker. Only use a standalone Chrome/DevTools fallback when the main agent explicitly authorizes degraded verification for that run, and label the report as **degraded**.

## Output format
```

- [ ] **Step 3: Verify the file**

```bash
grep -q "Codex Browser plugin" codex/skills/ticket-start/agents/qa.md && echo "Codex tooling ✓"
grep -q "^## Browser bootstrap$" codex/skills/ticket-start/agents/qa.md && echo "Browser bootstrap section ✓"
! grep -q "Playwright MCP\|mcp__playwright" codex/skills/ticket-start/agents/qa.md && echo "No Claude tooling leaked ✓"
```
Expected: all three pass.

- [ ] **Step 4: Mirror to install dir**

```bash
cp codex/skills/ticket-start/agents/qa.md ~/.codex/skills/ticket-start/agents/qa.md
diff -q codex/skills/ticket-start/agents/qa.md ~/.codex/skills/ticket-start/agents/qa.md
```
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add codex/skills/ticket-start/agents/qa.md
git commit -m "$(cat <<'EOF'
ticket-start: switch codex agents/qa.md to Codex-pure browser tooling

Replaces "Playwright MCP" reference in Inputs with the Codex Browser
plugin / browser-use:browser skill. Adds a ## Browser bootstrap
section right after Inputs (host-pure: Codex only) instructing the
QA subagent to acquire the iab browser and use its Playwright APIs,
with a degraded-mode escape hatch authorized only by main.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Update `claude/skills/ticket-start/agents/qa.md` (Claude-pure)

**Files:**
- Modify: `claude/skills/ticket-start/agents/qa.md` — Edit two locations
- Mirror: `~/.claude/skills/ticket-start/agents/qa.md`

- [ ] **Step 1: Update the Inputs bullet for browser tooling**

Use the `Edit` tool. Find this line in `claude/skills/ticket-start/agents/qa.md`:

```
- Browser tooling (Playwright MCP) for UI mode; HTTP tooling (curl, project HTTP client, or HTTP MCP) for backend mode.
```

Replace with:

```
- Playwright MCP tools (`mcp__playwright__browser_*`) for UI mode; HTTP tooling (curl, project HTTP client, or HTTP MCP) for backend mode.
```

- [ ] **Step 2: Insert the Browser bootstrap section**

Use the `Edit` tool. Find this block:

```
- Playwright MCP tools (`mcp__playwright__browser_*`) for UI mode; HTTP tooling (curl, project HTTP client, or HTTP MCP) for backend mode.

## Output format
```

Replace with:

```
- Playwright MCP tools (`mcp__playwright__browser_*`) for UI mode; HTTP tooling (curl, project HTTP client, or HTTP MCP) for backend mode.

## Browser bootstrap

For UI mode, use the Playwright MCP server for all browser interaction:

- `mcp__playwright__browser_navigate` — load URLs.
- `mcp__playwright__browser_resize` — viewport setup.
- `mcp__playwright__browser_snapshot` — DOM snapshots.
- `mcp__playwright__browser_take_screenshot` — element-level screenshots.
- `mcp__playwright__browser_evaluate` — computed-style and bounding-rect extraction.
- `mcp__playwright__browser_click`, `mcp__playwright__browser_press_key`, `mcp__playwright__browser_type` — interaction.

If the Playwright MCP server is not reachable for a UI-mode run, report `QA cannot proceed` with the exact connection blocker. Do not silently fall back to a different browser surface.

## Output format
```

- [ ] **Step 3: Verify the file**

```bash
grep -q "Playwright MCP" claude/skills/ticket-start/agents/qa.md && echo "Playwright MCP ref ✓"
grep -q "^## Browser bootstrap$" claude/skills/ticket-start/agents/qa.md && echo "Browser bootstrap section ✓"
grep -q "mcp__playwright__browser_evaluate" claude/skills/ticket-start/agents/qa.md && echo "Specific tool ref ✓"
! grep -q "browser-use:browser\|iab " claude/skills/ticket-start/agents/qa.md && echo "No Codex tooling leaked ✓"
```
Expected: all four pass.

- [ ] **Step 4: Mirror to install dir**

```bash
cp claude/skills/ticket-start/agents/qa.md ~/.claude/skills/ticket-start/agents/qa.md
diff -q claude/skills/ticket-start/agents/qa.md ~/.claude/skills/ticket-start/agents/qa.md
```
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add claude/skills/ticket-start/agents/qa.md
git commit -m "$(cat <<'EOF'
ticket-start: switch claude agents/qa.md to Claude-pure browser tooling

Mirror of the Codex-tree QA update with Playwright MCP tool names
(mcp__playwright__browser_*) instead of Codex Browser plugin
references. Adds a ## Browser bootstrap section listing the specific
Playwright MCP tools the QA subagent uses for UI mode.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Update `codex/skills/ticket-start/SKILL.md` (Codex-pure Verify dispatch + new step 6a + red flags)

**Files:**
- Modify: `codex/skills/ticket-start/SKILL.md` — three Edit operations
- Mirror: `~/.codex/skills/ticket-start/SKILL.md`

- [ ] **Step 1: Update QA dispatch wording in Verify (step 2)**

Use the `Edit` tool. Find this line:

```
   - Browser tooling (Playwright MCP) for UI mode; HTTP tooling for backend mode.
```

Replace with:

```
   - Codex Browser plugin (`browser-use:browser` skill) for UI mode; HTTP tooling for backend mode.
```

- [ ] **Step 2: Update UI/UX dispatch wording in Verify (step 5)**

Use the `Edit` tool. Find this line:

```
   - Browser tooling (Playwright MCP).
```

Replace with:

```
   - Codex Browser plugin (`browser-use:browser` skill).
```

- [ ] **Step 3: Insert new step 6a (main-agent inventory validation) after UI/UX dispatch step 6**

Use the `Edit` tool. Find this block (the end of Verify step 6 → start of step 7):

```
6. **If UI/UX returns FINDINGS**, route through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **UI/UX re-runs scoped to affected states**.

7. **When UI/UX returns CLEAN** (or is skipped), run the self-improvement extraction pass on UI/UX findings (or skip the UI/UX pass if skipped). Advance to Ship.
```

Replace with:

```
6. **If UI/UX returns FINDINGS**, route through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **UI/UX re-runs scoped to affected states**.

6a. **Validate the UI/UX report's matched-element inventory before accepting any verdict.**

   - Confirm the report has a `## Matched-element inventory` section.
   - Spot-check exhaustiveness:
     - From the diff, pick 2 changed UI files. List their rendered elements. Each one must appear in the inventory.
     - From the running production app, sample 3 visible elements on the feature surface (one container, one text element, one interactive control). Each must appear in the inventory.
     - From the prototype, sample 2 visible elements. Each must appear either as a matched pair or as `MISSING` in the inventory.
   - If any sample is not in the inventory, the report is **structurally invalid**. Reject and re-dispatch UI/UX with the specific missing elements named.
   - Do not accept "I checked the major elements" or "the rest match by inspection" as substitutes for inventory rows.

7. **When UI/UX returns CLEAN** (or is skipped), and the inventory validation in step 6a has passed, run the self-improvement extraction pass on UI/UX findings (or skip the UI/UX pass if skipped). Advance to Ship.
```

- [ ] **Step 4: Update the Red Flags list — add two new entries + update the existing browser_evaluate one**

Use the `Edit` tool. Find this line in the Red Flags list:

```
- Claiming visual parity / consistency without `browser_evaluate` extraction.
```

Replace with:

```
- Claiming visual parity / consistency without DOM computed-style and bounding-rect extraction from the live browser.
- Accepting a UI/UX `CLEAN` verdict (or any verdict) whose Matched-element inventory section is missing, empty, or missing rows for elements visibly present on the feature surface.
- UI/UX subagent restricting the inventory to "important" elements instead of every visible element in the feature surface.
```

- [ ] **Step 5: Verify the file**

```bash
grep -q "Codex Browser plugin" codex/skills/ticket-start/SKILL.md && echo "Codex tooling refs ✓"
! grep -q "Playwright MCP\|browser_evaluate" codex/skills/ticket-start/SKILL.md && echo "No legacy tool refs ✓"
grep -q "^6a\. \*\*Validate the UI/UX report" codex/skills/ticket-start/SKILL.md && echo "Step 6a present ✓"
grep -q "Matched-element inventory section is missing" codex/skills/ticket-start/SKILL.md && echo "Red flag 1 present ✓"
grep -q "restricting the inventory to .important. elements" codex/skills/ticket-start/SKILL.md && echo "Red flag 2 present ✓"
```
Expected: all five pass.

- [ ] **Step 6: Mirror to install dir**

```bash
cp codex/skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
diff -q codex/skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
```
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add codex/skills/ticket-start/SKILL.md
git commit -m "$(cat <<'EOF'
ticket-start: harden codex SKILL.md Verify with inventory enforcement

Three changes:
  - QA and UI/UX dispatch in Verify phase reference the Codex Browser
    plugin (browser-use:browser) instead of "Playwright MCP" (the
    Claude-Code term that leaked into the Codex tree).
  - New step 6a — main agent validates the UI/UX report's
    Matched-element inventory before accepting any verdict. Sample
    spot-check: 2 files from diff, 3 elements from production, 2
    from prototype. Any miss → structurally invalid → reject and
    re-dispatch.
  - Two new red flags: accepting a CLEAN verdict with a missing/empty
    inventory, and UI/UX restricting inventory to "important"
    elements only.

The new step 6a + red flags are host-neutral (no tool refs), so the
Claude-tree copy carries them verbatim in the next task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Update `claude/skills/ticket-start/SKILL.md` (Claude-pure Verify dispatch + same step 6a + red flags)

**Files:**
- Modify: `claude/skills/ticket-start/SKILL.md` — three Edit operations
- Mirror: `~/.claude/skills/ticket-start/SKILL.md`

- [ ] **Step 1: Update QA dispatch wording in Verify (step 2)**

Use the `Edit` tool. Find this line:

```
   - Browser tooling (Playwright MCP) for UI mode; HTTP tooling for backend mode.
```

Replace with:

```
   - Playwright MCP tools (`mcp__playwright__browser_*`) for UI mode; HTTP tooling for backend mode.
```

- [ ] **Step 2: Update UI/UX dispatch wording in Verify (step 5)**

Use the `Edit` tool. Find this line:

```
   - Browser tooling (Playwright MCP).
```

Replace with:

```
   - Playwright MCP tools (`mcp__playwright__browser_*`).
```

- [ ] **Step 3: Insert new step 6a (identical to Codex tree — host-neutral content)**

Use the `Edit` tool. Find this block:

```
6. **If UI/UX returns FINDINGS**, route through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **UI/UX re-runs scoped to affected states**.

7. **When UI/UX returns CLEAN** (or is skipped), run the self-improvement extraction pass on UI/UX findings (or skip the UI/UX pass if skipped). Advance to Ship.
```

Replace with:

```
6. **If UI/UX returns FINDINGS**, route through `bug-fix-loop.md`. Per the loop's rules, after the fix lands, **UI/UX re-runs scoped to affected states**.

6a. **Validate the UI/UX report's matched-element inventory before accepting any verdict.**

   - Confirm the report has a `## Matched-element inventory` section.
   - Spot-check exhaustiveness:
     - From the diff, pick 2 changed UI files. List their rendered elements. Each one must appear in the inventory.
     - From the running production app, sample 3 visible elements on the feature surface (one container, one text element, one interactive control). Each must appear in the inventory.
     - From the prototype, sample 2 visible elements. Each must appear either as a matched pair or as `MISSING` in the inventory.
   - If any sample is not in the inventory, the report is **structurally invalid**. Reject and re-dispatch UI/UX with the specific missing elements named.
   - Do not accept "I checked the major elements" or "the rest match by inspection" as substitutes for inventory rows.

7. **When UI/UX returns CLEAN** (or is skipped), and the inventory validation in step 6a has passed, run the self-improvement extraction pass on UI/UX findings (or skip the UI/UX pass if skipped). Advance to Ship.
```

- [ ] **Step 4: Update the Red Flags list — same three changes as Codex tree**

Use the `Edit` tool. Find this line:

```
- Claiming visual parity / consistency without `browser_evaluate` extraction.
```

Replace with:

```
- Claiming visual parity / consistency without DOM computed-style and bounding-rect extraction from the live browser.
- Accepting a UI/UX `CLEAN` verdict (or any verdict) whose Matched-element inventory section is missing, empty, or missing rows for elements visibly present on the feature surface.
- UI/UX subagent restricting the inventory to "important" elements instead of every visible element in the feature surface.
```

- [ ] **Step 5: Verify the file**

```bash
grep -q "Playwright MCP" claude/skills/ticket-start/SKILL.md && echo "Playwright MCP refs ✓"
! grep -q "browser-use:browser\|iab " claude/skills/ticket-start/SKILL.md && echo "No Codex tooling leaked ✓"
grep -q "^6a\. \*\*Validate the UI/UX report" claude/skills/ticket-start/SKILL.md && echo "Step 6a present ✓"
grep -q "Matched-element inventory section is missing" claude/skills/ticket-start/SKILL.md && echo "Red flag 1 present ✓"
grep -q "restricting the inventory to .important. elements" claude/skills/ticket-start/SKILL.md && echo "Red flag 2 present ✓"
```
Expected: all five pass.

- [ ] **Step 6: Mirror to install dir**

```bash
cp claude/skills/ticket-start/SKILL.md ~/.claude/skills/ticket-start/SKILL.md
diff -q claude/skills/ticket-start/SKILL.md ~/.claude/skills/ticket-start/SKILL.md
```
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add claude/skills/ticket-start/SKILL.md
git commit -m "$(cat <<'EOF'
ticket-start: harden claude SKILL.md Verify with inventory enforcement

Mirror of Codex-tree update — QA and UI/UX dispatch reference
Playwright MCP tools (mcp__playwright__browser_*) instead of the
generic "Browser tooling (Playwright MCP)" wording.

Step 6a (main-agent inventory validation) and the two new red flags
are host-neutral and identical to the Codex-tree copy.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Update `codex/skills/ticket-start/personal-workflow.md` (Codex-pure tool refs + new parity-dominance section)

**Files:**
- Modify: `codex/skills/ticket-start/personal-workflow.md` — two Edit operations
- Mirror: `~/.codex/skills/ticket-start/personal-workflow.md`

- [ ] **Step 1: Update parity-mode description with Codex-pure tool refs**

Use the `Edit` tool. Find this line:

```
- **`parity`** — when `designs/` is a runnable React reference app. UI/UX runs the existing protocol in `verification.md`: matched-element inventory, computed-style + bounding-rect extraction via `browser_evaluate`, per-state coverage at all relevant breakpoints. Reference app is the absolute source of truth.
```

Replace with:

```
- **`parity`** — when `designs/` is a runnable React reference app. UI/UX runs the existing protocol in `verification.md`: matched-element inventory, computed-style + bounding-rect extraction via the Codex Browser plugin's Playwright APIs, per-state coverage at all relevant breakpoints. Reference app is the absolute source of truth.
```

- [ ] **Step 2: Insert the "Prototype parity dominates" section after `## React Reference App`**

Use the `Edit` tool. Find this block:

```
These are passed to the UI/UX subagent during Verify.

## Verification — Mode mapping for QA and UI/UX
```

Replace with:

```
These are passed to the UI/UX subagent during Verify.

### Prototype parity dominates all other rules

When the personal workflow has a runnable React reference app, **prototype visual parity is the highest-priority rule** for that ticket's visual surface. It overrides "use the design system's existing primitives" guidance, "match existing project patterns," and any other style heuristic.

If a production design-system primitive does not reproduce the prototype's visual exactly:

- **Right path:** add or extend the primitive so it matches the prototype. Surface the design-system gap during planning so the user can approve the new primitive.
- **Wrong path:** silently substitute a "close-enough" production primitive (e.g., translating a prototype `<span>+✔` eyebrow into a production `Badge` component with pill background and shadow). That is parity drift dressed up as design-system discipline.

When the prototype and the design system disagree, the prototype wins. The design system is a tool for achieving parity, not a replacement for it.

This rule exists because of an observed failure mode where this exact substitution happened and the UI/UX agent accepted it as "design-system compliant."

## Verification — Mode mapping for QA and UI/UX
```

- [ ] **Step 3: Verify the file**

```bash
grep -q "Codex Browser plugin's Playwright APIs" codex/skills/ticket-start/personal-workflow.md && echo "Codex tooling ref ✓"
! grep -q "browser_evaluate\b" codex/skills/ticket-start/personal-workflow.md && echo "Legacy tool ref removed ✓"
grep -q "Prototype parity dominates all other rules" codex/skills/ticket-start/personal-workflow.md && echo "Dominance section present ✓"
grep -q "parity drift dressed up as design-system discipline" codex/skills/ticket-start/personal-workflow.md && echo "Failure-mode language present ✓"
```
Expected: all four pass.

- [ ] **Step 4: Mirror to install dir**

```bash
cp codex/skills/ticket-start/personal-workflow.md ~/.codex/skills/ticket-start/personal-workflow.md
diff -q codex/skills/ticket-start/personal-workflow.md ~/.codex/skills/ticket-start/personal-workflow.md
```
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add codex/skills/ticket-start/personal-workflow.md
git commit -m "$(cat <<'EOF'
ticket-start: codex personal-workflow.md tool ref + parity-dominance rule

Two changes:
  - Parity-mode description in "Verification — Mode mapping" now
    references the Codex Browser plugin's Playwright APIs instead of
    the legacy "browser_evaluate" name.
  - New subsection "Prototype parity dominates all other rules"
    inserted after "## React Reference App". Names the observed
    failure mode (substituting design-system primitives for prototype
    elements) and resolves the precedence: prototype wins; the
    design system is a tool for achieving parity, not a replacement
    for it.

The new subsection is host-neutral content; the Claude-tree copy
carries it verbatim in the next task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Update `claude/skills/ticket-start/personal-workflow.md` (Claude-pure tool refs + same parity-dominance section)

**Files:**
- Modify: `claude/skills/ticket-start/personal-workflow.md` — two Edit operations
- Mirror: `~/.claude/skills/ticket-start/personal-workflow.md`

- [ ] **Step 1: Update parity-mode description with Claude-pure tool refs**

Use the `Edit` tool. Find this line:

```
- **`parity`** — when `designs/` is a runnable React reference app. UI/UX runs the existing protocol in `verification.md`: matched-element inventory, computed-style + bounding-rect extraction via `browser_evaluate`, per-state coverage at all relevant breakpoints. Reference app is the absolute source of truth.
```

Replace with:

```
- **`parity`** — when `designs/` is a runnable React reference app. UI/UX runs the existing protocol in `verification.md`: matched-element inventory, computed-style + bounding-rect extraction via `mcp__playwright__browser_evaluate`, per-state coverage at all relevant breakpoints. Reference app is the absolute source of truth.
```

- [ ] **Step 2: Insert the "Prototype parity dominates" section (identical to Codex tree)**

Use the `Edit` tool. Find this block:

```
These are passed to the UI/UX subagent during Verify.

## Verification — Mode mapping for QA and UI/UX
```

Replace with:

```
These are passed to the UI/UX subagent during Verify.

### Prototype parity dominates all other rules

When the personal workflow has a runnable React reference app, **prototype visual parity is the highest-priority rule** for that ticket's visual surface. It overrides "use the design system's existing primitives" guidance, "match existing project patterns," and any other style heuristic.

If a production design-system primitive does not reproduce the prototype's visual exactly:

- **Right path:** add or extend the primitive so it matches the prototype. Surface the design-system gap during planning so the user can approve the new primitive.
- **Wrong path:** silently substitute a "close-enough" production primitive (e.g., translating a prototype `<span>+✔` eyebrow into a production `Badge` component with pill background and shadow). That is parity drift dressed up as design-system discipline.

When the prototype and the design system disagree, the prototype wins. The design system is a tool for achieving parity, not a replacement for it.

This rule exists because of an observed failure mode where this exact substitution happened and the UI/UX agent accepted it as "design-system compliant."

## Verification — Mode mapping for QA and UI/UX
```

- [ ] **Step 3: Verify the file**

```bash
grep -q "mcp__playwright__browser_evaluate" claude/skills/ticket-start/personal-workflow.md && echo "Playwright MCP ref ✓"
! grep -qE 'via `browser_evaluate`' claude/skills/ticket-start/personal-workflow.md && echo "Legacy tool ref removed ✓"
grep -q "Prototype parity dominates all other rules" claude/skills/ticket-start/personal-workflow.md && echo "Dominance section present ✓"
grep -q "parity drift dressed up as design-system discipline" claude/skills/ticket-start/personal-workflow.md && echo "Failure-mode language present ✓"
```
Expected: all four pass.

- [ ] **Step 4: Mirror to install dir**

```bash
cp claude/skills/ticket-start/personal-workflow.md ~/.claude/skills/ticket-start/personal-workflow.md
diff -q claude/skills/ticket-start/personal-workflow.md ~/.claude/skills/ticket-start/personal-workflow.md
```
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add claude/skills/ticket-start/personal-workflow.md
git commit -m "$(cat <<'EOF'
ticket-start: claude personal-workflow.md tool ref + parity-dominance rule

Mirror of Codex-tree update. Parity-mode description uses
mcp__playwright__browser_evaluate (the Claude-pure tool name) instead
of the bare "browser_evaluate" reference.

The "Prototype parity dominates all other rules" subsection is
identical to the Codex-tree copy (host-neutral content).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Update `codex/skills/ticket-start/verification.md` (Codex-pure tool refs + reinforce inventory exhaustiveness)

**Files:**
- Modify: `codex/skills/ticket-start/verification.md` — multiple Edit operations
- Mirror: `~/.codex/skills/ticket-start/verification.md`

- [ ] **Step 1: Replace all body-text references to `browser_evaluate` with the Codex Browser plugin's Playwright API**

Use the `Edit` tool with `replace_all: true`. Find this exact string:

```
`browser_evaluate`
```

Replace with:

```
the Codex Browser plugin's `evaluate()` API
```

- [ ] **Step 2: Replace references to `browser_take_screenshot` similarly**

Use the `Edit` tool with `replace_all: true`. Find:

```
`browser_take_screenshot`
```

Replace with:

```
the Codex Browser plugin's screenshot API
```

- [ ] **Step 3: Replace references to `browser_tabs` similarly**

Use the `Edit` tool with `replace_all: true`. Find:

```
`browser_tabs`
```

Replace with:

```
the Codex Browser plugin's tab API
```

- [ ] **Step 4: Reinforce inventory exhaustiveness — add a callout near the matched-element inventory section**

Use the `Edit` tool. Find this block (the start of the matched-element inventory section in verification.md):

```
### Matched-element inventory (do this first)

Before any comparison, enumerate matched element pairs for the feature.
```

Replace with:

```
### Matched-element inventory (do this first)

**REQUIRED + EXHAUSTIVE.** Every visible element in the feature's surface gets a row. Selectivity is forbidden — "I checked the important ones" is parity drift. The completeness rules are detailed in `agents/ui-ux.md` → `## Determining completeness`; the four checks (diff-driven coverage, production-DOM coverage, prototype-DOM coverage, sibling/parent geometry) all apply here.

Before any comparison, enumerate matched element pairs for the feature.
```

- [ ] **Step 5: Verify the file**

```bash
! grep -q "browser_evaluate\|browser_take_screenshot\|browser_tabs" codex/skills/ticket-start/verification.md && echo "Legacy tool refs removed ✓"
grep -q "Codex Browser plugin" codex/skills/ticket-start/verification.md && echo "Codex tooling refs ✓"
grep -q "REQUIRED + EXHAUSTIVE" codex/skills/ticket-start/verification.md && echo "Inventory mandate present ✓"
grep -q "Selectivity is forbidden" codex/skills/ticket-start/verification.md && echo "Selectivity callout present ✓"
```
Expected: all four pass.

- [ ] **Step 6: Mirror to install dir**

```bash
cp codex/skills/ticket-start/verification.md ~/.codex/skills/ticket-start/verification.md
diff -q codex/skills/ticket-start/verification.md ~/.codex/skills/ticket-start/verification.md
```
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add codex/skills/ticket-start/verification.md
git commit -m "$(cat <<'EOF'
ticket-start: codex verification.md tool refs + exhaustive-inventory mandate

Replaces all body-text references to Claude-Code-specific tool names
(browser_evaluate, browser_take_screenshot, browser_tabs) with
Codex Browser plugin Playwright APIs. Adds an explicit
"REQUIRED + EXHAUSTIVE" callout at the start of the Matched-element
inventory section, with a pointer to ui-ux.md's "Determining
completeness" rules — so the exhaustiveness contract is enforced
in both the role-prompt and the protocol file.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Update `claude/skills/ticket-start/verification.md` (Claude-pure tool refs + same exhaustive-inventory mandate)

**Files:**
- Modify: `claude/skills/ticket-start/verification.md` — multiple Edit operations
- Mirror: `~/.claude/skills/ticket-start/verification.md`

- [ ] **Step 1: Update body-text references — keep Playwright MCP names**

The Claude-tree copy needs `browser_evaluate` to remain as `mcp__playwright__browser_evaluate` (the namespaced MCP tool). Use the `Edit` tool with `replace_all: true`. Find:

```
`browser_evaluate`
```

Replace with:

```
`mcp__playwright__browser_evaluate`
```

- [ ] **Step 2: Replace `browser_take_screenshot`**

Use the `Edit` tool with `replace_all: true`. Find:

```
`browser_take_screenshot`
```

Replace with:

```
`mcp__playwright__browser_take_screenshot`
```

- [ ] **Step 3: Replace `browser_tabs`**

Use the `Edit` tool with `replace_all: true`. Find:

```
`browser_tabs`
```

Replace with:

```
`mcp__playwright__browser_tabs`
```

- [ ] **Step 4: Reinforce inventory exhaustiveness — same callout as Codex tree**

Use the `Edit` tool. Find:

```
### Matched-element inventory (do this first)

Before any comparison, enumerate matched element pairs for the feature.
```

Replace with:

```
### Matched-element inventory (do this first)

**REQUIRED + EXHAUSTIVE.** Every visible element in the feature's surface gets a row. Selectivity is forbidden — "I checked the important ones" is parity drift. The completeness rules are detailed in `agents/ui-ux.md` → `## Determining completeness`; the four checks (diff-driven coverage, production-DOM coverage, prototype-DOM coverage, sibling/parent geometry) all apply here.

Before any comparison, enumerate matched element pairs for the feature.
```

- [ ] **Step 5: Verify the file**

```bash
grep -q "mcp__playwright__browser_evaluate" claude/skills/ticket-start/verification.md && echo "Playwright MCP evaluate ref ✓"
grep -q "mcp__playwright__browser_take_screenshot" claude/skills/ticket-start/verification.md && echo "Playwright MCP screenshot ref ✓"
grep -q "mcp__playwright__browser_tabs" claude/skills/ticket-start/verification.md && echo "Playwright MCP tabs ref ✓"
! grep -q "browser-use:browser\|iab " claude/skills/ticket-start/verification.md && echo "No Codex tooling leaked ✓"
grep -q "REQUIRED + EXHAUSTIVE" claude/skills/ticket-start/verification.md && echo "Inventory mandate present ✓"
```
Expected: all five pass.

- [ ] **Step 6: Mirror to install dir**

```bash
cp claude/skills/ticket-start/verification.md ~/.claude/skills/ticket-start/verification.md
diff -q claude/skills/ticket-start/verification.md ~/.claude/skills/ticket-start/verification.md
```
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add claude/skills/ticket-start/verification.md
git commit -m "$(cat <<'EOF'
ticket-start: claude verification.md tool refs + exhaustive-inventory mandate

Mirror of Codex-tree update with Playwright MCP namespaced tool names
(mcp__playwright__browser_*) in place of the bare browser_* names.

The "REQUIRED + EXHAUSTIVE" callout at the start of the matched-
element inventory section is host-neutral and identical to the
Codex-tree copy.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Lint + cross-tree symmetry verification

**Files:**
- Verify (read-only): every file in `codex/skills/ticket-start/` and `claude/skills/ticket-start/`

- [ ] **Step 1: Frontmatter validation on both SKILL.md copies**

```bash
for f in codex/skills/ticket-start/SKILL.md claude/skills/ticket-start/SKILL.md; do
  echo "=== $f ==="
  head -1 "$f" | grep -q '^---$' && echo "Frontmatter starts ✓"
  awk '/^---$/{n++; next} n==1{print}' "$f" | head -5
done
```
Expected: both files start with `---` and have valid YAML frontmatter (name + description).

- [ ] **Step 2: No-placeholder scan across both trees**

```bash
grep -rnE '\b(TBD|FIXME|XXX|implement later|fill in details)\b' \
  codex/skills/ticket-start/ claude/skills/ticket-start/ 2>/dev/null \
  | grep -v 'self-improvement.md' \
  || echo "no placeholders found ✓"
```
Expected: `no placeholders found ✓` (or empty grep output, which means no matches).

- [ ] **Step 3: Cross-reference resolution**

```bash
for tree in codex/skills/ticket-start claude/skills/ticket-start; do
  echo "=== $tree ==="
  missing=0
  for f in agents/scoping.md agents/architect.md agents/reviewer.md \
           agents/security.md agents/qa.md agents/ui-ux.md \
           bug-fix-loop.md self-improvement.md \
           job-workflow.md personal-workflow.md \
           react-parity.md verification.md \
           SKILL.md; do
    test -f "$tree/$f" || { echo "MISSING: $tree/$f"; missing=$((missing+1)); }
  done
  test "$missing" -eq 0 && echo "All cross-refs resolve ✓"
done
```
Expected: each tree reports "All cross-refs resolve ✓".

- [ ] **Step 4: Host-purity check — Codex tree has zero Claude tooling refs**

```bash
echo "=== Codex tree: no mcp__playwright or Playwright MCP refs ==="
! grep -rnE 'mcp__playwright|Playwright MCP' codex/skills/ticket-start/ \
  && echo "Codex tree host-pure ✓" \
  || echo "✗ Codex tree contains Claude tooling refs"
```
Expected: `Codex tree host-pure ✓`.

- [ ] **Step 5: Host-purity check — Claude tree has zero Codex tooling refs**

```bash
echo "=== Claude tree: no browser-use:browser or iab browser refs ==="
! grep -rnE 'browser-use:browser|iab browser|Codex Browser plugin' claude/skills/ticket-start/ \
  && echo "Claude tree host-pure ✓" \
  || echo "✗ Claude tree contains Codex tooling refs"
```
Expected: `Claude tree host-pure ✓`.

- [ ] **Step 6: Tree symmetry — expected divergences only**

```bash
diff -r --brief codex/skills/ticket-start/ claude/skills/ticket-start/
```
Expected output (multiple lines now — diverged files in both trees):
```
Files codex/skills/ticket-start/SKILL.md and claude/skills/ticket-start/SKILL.md differ
Files codex/skills/ticket-start/agents/qa.md and claude/skills/ticket-start/agents/qa.md differ
Files codex/skills/ticket-start/agents/ui-ux.md and claude/skills/ticket-start/agents/ui-ux.md differ
Only in codex/skills/ticket-start/agents: openai.yaml
Files codex/skills/ticket-start/personal-workflow.md and claude/skills/ticket-start/personal-workflow.md differ
Files codex/skills/ticket-start/verification.md and claude/skills/ticket-start/verification.md differ
```

This output is expected — the divergence is the intended host-pure design. Confirm only the five expected files diverge (plus the openai.yaml Codex-only file), no others.

- [ ] **Step 7: Install-path mirror sync**

```bash
diff -r --brief codex/skills/ticket-start/ ~/.codex/skills/ticket-start/ && echo "Codex install in sync ✓"
diff -r --brief claude/skills/ticket-start/ ~/.claude/skills/ticket-start/ && echo "Claude install in sync ✓"
```
Expected: both checks ✓ (no output from diff, just the "in sync" lines).

- [ ] **Step 8: No commit needed (verification only)**

This task produces no file changes. Any failed check means returning to the originating task (1–10) and fixing the source.

---

### Task 12: Closeout — push branch + create PR

**Files:**
- None directly; this task pushes the branch and opens the PR.

- [ ] **Step 1: Confirm working tree is clean**

```bash
git status
```
Expected: `nothing to commit, working tree clean`. All changes from Tasks 1–10 should already be committed individually.

- [ ] **Step 2: Confirm commit history**

```bash
git log --oneline origin/main..HEAD
```
Expected (order may vary by execution path):
```
<sha> ticket-start: claude verification.md tool refs + exhaustive-inventory mandate
<sha> ticket-start: codex verification.md tool refs + exhaustive-inventory mandate
<sha> ticket-start: claude personal-workflow.md tool ref + parity-dominance rule
<sha> ticket-start: codex personal-workflow.md tool ref + parity-dominance rule
<sha> ticket-start: harden claude SKILL.md Verify with inventory enforcement
<sha> ticket-start: harden codex SKILL.md Verify with inventory enforcement
<sha> ticket-start: switch claude agents/qa.md to Claude-pure browser tooling
<sha> ticket-start: switch codex agents/qa.md to Codex-pure browser tooling
<sha> ticket-start: rewrite claude agents/ui-ux.md with host-pure Claude tooling
<sha> ticket-start: rewrite codex agents/ui-ux.md with host-pure Codex tooling
<sha> ticket-start: clarify host-isolation loading model in visual-parity spec
<sha> ticket-start: tighten visual-parity spec to host-pure tree content
<sha> ticket-start: add visual-parity-enforcement design spec
```

13 commits total: 3 spec commits + 10 implementation commits.

- [ ] **Step 3: Push the branch**

```bash
git push -u origin ticket-start-visual-parity-enforcement
```
Expected: push succeeds, branch tracked.

- [ ] **Step 4: Create the PR**

```bash
gh pr create --title "ticket-start: harden visual parity enforcement after observed failure" --body "$(cat <<'EOF'
## Summary

After a real personal-workflow ticket shipped with substantial prototype-vs-production visual differences (eyebrow `<span>` → `Badge` pill, headline 48px → 72px, phone widget shell vs raw rounded story panel) and the UI/UX subagent reported "Visual findings: None," we tightened the protocol to make the failure mode structurally impossible.

Three substantive changes plus host-isolation polish:

- **Matched-element inventory is mandatory + exhaustive.** Every UI/UX report (including CLEAN verdicts) must include a `## Matched-element inventory` section with one row per matched pair, with actual computed-style values from `getComputedStyle()` and bounding rects from `getBoundingClientRect()`. Selectivity is forbidden — every visible element in the feature surface gets a row. Four completeness rules (diff-driven, production-DOM, prototype-DOM, sibling/parent geometry).
- **Main agent enforces the inventory shape.** New `SKILL.md` Verify step 6a spot-checks the inventory against the diff (2 files), running production (3 elements), and prototype (2 elements). Any miss → report is structurally invalid → reject and re-dispatch.
- **Prototype parity dominates other rules** in personal-workflow with a React reference. Explicit precedence rule — if the design system can't reproduce the prototype exactly, extend the design system; don't substitute a "close-enough" primitive. Named after the observed failure mode.
- **Host-pure tree content.** The codex tree references the Codex Browser plugin (`browser-use:browser` skill / `iab` browser); the claude tree references the Playwright MCP server (`mcp__playwright__browser_*`). Each tree contains only its own host's tooling language. When Codex loads the skill it never sees Playwright MCP references; when Claude Code loads it never sees Codex Browser plugin references.

Spec: `docs/superpowers/specs/2026-05-11-visual-parity-enforcement-design.md`. Plan: `docs/superpowers/plans/2026-05-11-visual-parity-enforcement.md`. 13 commits = 3 spec + 10 implementation.

## Test plan

This change is in skill files (markdown). The behavioral validation happens on the next personal-workflow ticket that exercises the parity pass. Until then:

- [ ] Lint passes (Task 11 in the plan).
- [ ] Both trees host-pure (no cross-host tool references — verified by grep in Task 11 step 4-5).
- [ ] Tree-symmetry check shows the expected 5 divergent files + openai.yaml only (Task 11 step 6).
- [ ] Install-path sync clean for both trees (Task 11 step 7).
- [ ] On the next personal-workflow ticket: confirm the UI/UX subagent produces the `## Matched-element inventory` section with non-trivial row count.
- [ ] On the same ticket: confirm the main agent's step 6a actually runs the spot-check and rejects an empty inventory (force-test by deliberately producing a UI/UX report with empty inventory and confirming main rejects).
- [ ] Re-run the failing GEN-86 ticket: confirm the same class of failure (substituted Badge components, missed phone-frame element, headline 48→72) would now be caught either by (a) the exhaustive inventory surfacing the differences or (b) the main agent rejecting an incomplete report.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

- [ ] **Step 5: Final summary to the user**

Produce a closeout summary covering:
- PR URL.
- Commits added (count: 13, range: from spec commit to last verification commit).
- Files modified per tree (5 files × 2 trees = 10 file modifications).
- Tree symmetry result (expected 5 host-pure divergences + openai.yaml).
- Install-path sync status (both clean).
- What is **not** verified by this plan: the runtime behavior on a real personal-workflow ticket. That's the next-time validation. Until then, the protocol is hardened at the skill-file level; whether the hardening actually changes agent behavior is empirical and only the next real ticket can confirm.
- Next steps for the user: review the PR, optionally test on a real personal-workflow ticket (or re-run GEN-86 with the updated skill to confirm the inventory catch).

---

## Self-review

### 1. Spec coverage

Mapping each spec section to a task that implements it:

- **§1 Problem statement + §2 Goals/non-goals** — captured in the plan header (Goal, Architecture). ✓
- **§3 Architectural decisions** — encoded across Tasks 1-10. Specifically: tree content policy (Tasks 1 vs 2, 3 vs 4, etc. — diverged trees), Browser bootstrap subsection (Tasks 1-4), inventory exhaustiveness (Tasks 1-2 + 9-10), main-agent fact-check (Tasks 5-6), prototype dominance (Tasks 7-8), mirror policy within-host (each task's mirror step). ✓
- **§4.1 Tool-language refactor** — Tasks 1-10 each use host-actual names. ✓
- **§4.2 Browser bootstrap subsection** — Tasks 1, 2, 3, 4 add it; Tasks 5, 6 update SKILL.md dispatch wording; Tasks 9, 10 update verification.md tool refs. ✓
- **§4.3 Exhaustive matched-element inventory** — Tasks 1, 2 add the mandatory section to ui-ux.md Output format; Tasks 9, 10 reinforce in verification.md. ✓
- **§4.4 Main-agent enforcement** — Tasks 5, 6 add step 6a + the two red flags. ✓
- **§4.5 Prototype parity dominance** — Tasks 7, 8 insert the new subsection. ✓
- **§4.6 Mirror policy** — every task's "mirror to install dir" step. Task 11 verifies install-path sync. ✓
- **§4.7 Cross-tree maintenance** — handled by the plan's structure (one task per file per tree). ✓
- **§5 File-by-file changes** — five files × two trees = 10 implementation tasks (Tasks 1-10). ✓
- **§6 Deferred to implementation plan** — addressed in plan-level decisions at the top of this plan. ✓
- **§7 Migration and scope** — addressed by the additive nature of every change (no deletions of files; rollback is reverting the PR). ✓

No spec gaps.

### 2. Placeholder scan

I searched the plan for: TBD, FIXME, XXX, "implement later," "fill in details," "Similar to Task N." The only `<placeholder>` style tokens are intentional substitution markers in the file content (e.g., `<ticket title>`, `<APP_ID>`) — same convention prior plans used. No real TBDs in instruction-bearing parts.

### 3. Type / name consistency

Cross-checked names used across tasks:

- File paths: `agents/ui-ux.md`, `agents/qa.md`, `SKILL.md`, `personal-workflow.md`, `verification.md` — consistent across Tasks 1-10 and Task 11 verification.
- Section names: `## Browser bootstrap`, `## Matched-element inventory`, `## Determining completeness` — consistent across Tasks 1, 2, 9, 10.
- Tool family names per tree: Codex tree uses "Codex Browser plugin", "browser-use:browser", "iab browser", "Playwright APIs"; Claude tree uses "Playwright MCP", "mcp__playwright__browser_*". Each tree's tasks (1/3/5/7/9 = codex; 2/4/6/8/10 = claude) consistently use the right family.
- Step numbering in SKILL.md: original Verify steps 1-7 stay 1-7; new step 6a inserts between 6 and 7. Consistent across Tasks 5, 6.
- Red-flag wording: identical strings used in Tasks 5 and 6.
- Parity-dominance subsection content: identical strings used in Tasks 7 and 8.

No inconsistencies found.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-11-visual-parity-enforcement.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best fit for this plan because each task is self-contained (one file in one tree per task) and the per-task review catches drift between the codex and claude versions of the same change before it propagates (e.g., a missing "Selectivity is parity drift" line in one tree but not the other).

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints. Faster wallclock; less context isolation between paired-tree changes.

**Which approach?**
