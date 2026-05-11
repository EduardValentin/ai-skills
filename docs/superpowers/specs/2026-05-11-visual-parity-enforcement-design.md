# Visual Parity Enforcement — Design Spec

**Date:** 2026-05-11
**Status:** Approved design, pending implementation plan
**Branch:** `ticket-start-visual-parity-enforcement` (fresh, off `origin/main`; independent of PR #2 which is also still open)
**Predecessor specs:**
- `2026-05-10-ticket-start-redesign-design.md` (orchestrator redesign, merged)
- `2026-05-11-ticket-start-bot-identity-design.md` (bot identity work, on its own branch — orthogonal to this)

## 1. Problem statement

The orchestrator redesign defined a rigorous visual-parity protocol for the UI/UX subagent — matched-element inventory, programmatic `getComputedStyle()` + `getBoundingClientRect()` extraction per matched pair, "no tolerance budget" on numeric differences. The protocol was correct in spirit. **In practice, it failed on the first real personal-workflow ticket.**

Concretely observed:

- Prototype eyebrow row: plain `<span>` with checkmark + text, `14px / 500 / 20px / pad 0 / radius 0 / no bg`.
- Production: pill-shaped element inside a list, `16px / 600 / 24px / pad 4×10 / radius 9999 / pink-tinted bg / shadow / different parent gap`.
- Prototype headline: 48px. Production: 72px.
- Prototype widget shell: phone frame, 340×604, 4px border, 40px radius, big shadow. Production: raw rounded story panel, 320×569, 1px border, 24px radius.
- Section layout: prototype centered max-width flex; production full-width with internal grid.

The UI/UX subagent reported `Visual findings: None`. The main agent accepted that report and advanced to Ship.

### Self-diagnosed root causes (the Codex agent debugged itself)

1. **Subagent failure:** the UI/UX subagent did not extract computed styles for the matched inventory it was supposed to build. It did a looser visual/accessibility pass and reported no findings without producing the per-pair evidence the role-prompt required.
2. **Main agent failure:** main accepted a `Visual findings: None` verdict whose report did not contain the matched-element inventory or per-pair computed-style data the protocol mandates. There was no structural shape contract; "I checked" was accepted as proof.
3. **Tooling drift:** the role-prompts referenced Claude-Code-specific tool names (`browser_evaluate`, `browser_take_screenshot`, `browser_tabs`, Playwright MCP) that don't map cleanly onto Codex's `browser-use:browser` skill / in-app browser surface. Under Codex, the subagent drifted into "I inspected it in Chrome" instead of "I extracted every matched element."
4. **Design-system ambiguity:** the agent translated prototype `<span>+✔` eyebrows into the production `Badge` pill primitive on the rationale that the skill prefers shared design-system primitives. That decision conflicts with prototype parity but the skill did not declare a precedence rule.

## 2. Goals and non-goals

### Goals

Close the four root causes by tightening **what the role-prompts require** and **how the main agent enforces them** — not by adding more aspirational language. Specifically:

- **Structural evidence is mandatory.** Every UI/UX report — including `CLEAN` verdicts — must include a complete `## Matched-element inventory` section with per-pair computed-style and bounding-rect values. A report missing that section is structurally invalid and the main agent rejects it without accepting any verdict.
- **The inventory is exhaustive, not selective.** Every visible element in the feature's surface (in both prototype and production) gets a row. "Important elements only" is forbidden. The completeness criterion is enumerable and the main agent spot-checks it.
- **Tool references are host-neutral, with explicit per-host bootstrap.** The role-prompts describe capabilities (DOM evaluation, screenshots, snapshots, tab control). A small "Host-specific browser bootstrap" subsection names Codex's Browser plugin path and Claude Code's Playwright MCP path so the agent knows which tool surface to use without polluting the body with host-specific names.
- **Prototype parity dominates other rules** in personal workflow with a React reference. Explicit precedence rule — overrides design-system token preferences, "use existing primitives" guidance, and other style heuristics.

### Non-goals

- Not changing the phase order, agent roster, dispatch points, bug-fix loop, or self-improvement loop.
- Not changing the QA, Reviewer, Security, Scoping, or Architect role-prompts beyond the host-neutral tool wording.
- Not introducing a separate "auditor of the UI/UX agent" subagent. The fix is in the report shape contract + main-agent enforcement, not a new role.
- Not introducing pixel-diff screenshot comparison. DOM/computed-style extraction is the primary evidence; screenshots remain supplementary.
- Not changing how `verification.md` is loaded or which workflows trigger it.

## 3. Architectural decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Trust model | Evidence-shaped contract enforced by main agent | "Trust the agent's self-report" is what failed. The fix is to make the report mechanically falsifiable. |
| Inventory exhaustiveness | Every visible element on the feature surface | Selective inventories let the agent silently miss elements (eyebrow pill, phone frame). Exhaustive removes the option. |
| Inventory format | Markdown table with per-element computed-style + rect values | Compact, scannable, and a missing row is visible at a glance. Easier to enforce than free-form prose. |
| Host bootstrap | Capability-language in the body; named tool surfaces in a dedicated subsection | Keeps the role-prompt portable while still giving each host an explicit "use this tool" hook. |
| Precedence rule | Prototype parity > design-system primitives (for personal workflow with React reference) | Codex's self-diagnosis named this exact conflict. Without an explicit rule the agent will infer wrong. |
| Main-agent fact-check | Inventory shape + completeness spot-check before accepting any verdict | Closes the loop where main accepted a CLEAN without evidence. |
| New auditor subagent | **No** — fix is in shape contract, not a new role | Adding agents adds operational complexity without addressing the root cause (no contract). |
| Pixel-diff screenshots | **No** — DOM extraction remains primary | DOM extraction catches the failures we observed. Adding pixel-diff trades complexity for marginal coverage. |

## 4. The six concrete changes

### 4.1 Tool-language refactor (`agents/ui-ux.md`, `agents/qa.md`, `SKILL.md`)

Replace Claude-Code-specific tool names with capability descriptions throughout the body of the role-prompts and the SKILL.md dispatch instructions:

- `browser_evaluate` → "DOM evaluation" / "extract computed styles via `getComputedStyle()`"
- `browser_take_screenshot` → "element-level screenshot"
- `browser_snapshot` → "DOM snapshot"
- `browser_tabs` → "tab switching via the available browser tooling"
- "Playwright MCP" → "browser tooling"

Codex already wrote these patches correctly on its install-side. We pull them into the repo and propagate to the claude tree.

### 4.2 Host-specific browser bootstrap subsection

In `agents/ui-ux.md` (and `agents/qa.md`), add a subsection right after the Inputs list:

```markdown
### Host-specific browser bootstrap

When running under a specific host, use that host's primary browser surface before any fallback:

- **Codex.** If the `browser-use:browser` skill is available, follow its bootstrap path, acquire the `iab` browser, and use its Playwright APIs for tab control, viewport setup, screenshots, DOM snapshots, clicks, keyboard input, `getBoundingClientRect()`, and `getComputedStyle()` extraction. Do not start with standalone Chrome, external Playwright, Puppeteer, or Chrome DevTools Protocol unless the Browser plugin is unavailable or cannot acquire `iab`.
- **Claude Code.** Use the Playwright MCP server's tool family (`mcp__playwright__browser_navigate`, `mcp__playwright__browser_evaluate`, `mcp__playwright__browser_take_screenshot`, `mcp__playwright__browser_snapshot`, `mcp__playwright__browser_tabs`, etc.) for the same set of capabilities.

If the host's primary browser surface cannot be acquired, report `UI/UX cannot proceed` (or `QA cannot proceed`) with the exact browser-acquisition blocker. Only use a standalone Chrome/DevTools fallback when the main agent explicitly authorizes degraded verification for that run, and label the report as **degraded**.
```

### 4.3 Mandatory exhaustive matched-element inventory

In `agents/ui-ux.md` Output format, the `## Matched-element inventory` section becomes a hard requirement. Update the template:

```markdown
## Matched-element inventory
_(REQUIRED. Must be exhaustive — every visible element in the feature's surface gets a row. Selectivity is forbidden. See "Determining completeness" below.)_

| Pair | Prototype selector | Production selector | font-* | color/bg | box (padding/border/radius/shadow) | layout (display/gap/flex) | size (w×h) | verdict |
|---|---|---|---|---|---|---|---|---|
| (one row per matched pair, with actual computed values, not placeholders) |  |  |  |  |  |  |  |  |
| Prototype-only element X | `.proto-x` | (none) | … | … | … | … | … | **MISSING** in production |

### Determining completeness

The inventory is judged exhaustive when all four of these are satisfied:

1. **Diff-driven coverage.** Walk the diff (`git diff origin/<default>..HEAD`). For every `.tsx`/`.jsx`/`.vue`/`.svelte`/template/CSS file touched, enumerate the visible elements it renders. Every enumerated element appears in the inventory.

2. **Production-DOM coverage.** Open the production app at the feature's route. Every visible element on the feature surface (containers, headings, body text, buttons, icons, images, badges, links, dividers, decorative elements) has a row in the inventory. No "too minor to bother" exceptions — if it renders, it gets a row.

3. **Prototype-DOM coverage.** Open the prototype at the matching route. Every visible element there is either a matched pair (row with both selectors filled) or **MISSING** (row with prototype selector filled, production selector blank, verdict = MISSING).

4. **Sibling/parent geometry.** For matched pairs in the same parent, the parent's `getBoundingClientRect()` for children is also captured (alignment, gap, sizing) — flag drift in the parent even if individual children match.

A `Visual findings: None` verdict is valid only when all four checks pass AND every row's values match between prototype and production (or are documented exceptions approved during planning).
```

New forbidden behavior:

> Restricting the inventory to elements the agent deems "important" or "the ones most likely to differ." Every visible element gets a row. Selectivity is parity drift.

### 4.4 Main-agent enforcement in `SKILL.md` Verify phase

In `SKILL.md`'s Verify section, immediately after dispatching the UI/UX subagent and before branching on the verdict, add a structural-validity check:

```markdown
6a. **Validate the UI/UX report's matched-element inventory before accepting any verdict.**

- Confirm the report has a `## Matched-element inventory` section.
- Spot-check exhaustiveness:
  - From the diff, pick 2 changed UI files. List their rendered elements. Each one must appear in the inventory.
  - From the running production app, sample 3 visible elements on the feature surface (one container, one text element, one interactive control). Each must appear in the inventory.
  - From the prototype, sample 2 visible elements. Each must appear either as a matched pair or as `MISSING`.
- If any sample is not in the inventory, the report is **structurally invalid**. Reject and re-dispatch UI/UX with the specific missing elements named.
- Do not accept "I checked the major elements" or "the rest match by inspection" as substitutes for inventory rows.
```

Two new red flags:

- "Accepting a UI/UX `Visual findings: None` (or any verdict) whose Matched-element inventory section is missing, empty, or missing rows for elements visibly present on the feature surface."
- "UI/UX subagent restricting the inventory to 'important' elements instead of every visible element in the feature surface."

### 4.5 Prototype parity dominance rule (`personal-workflow.md`)

Add a new subsection right after `## React Reference App`:

```markdown
### Prototype parity dominates all other rules

When the personal workflow has a runnable React reference app, **prototype visual parity is the highest-priority rule** for that ticket's visual surface. It overrides "use the design system's existing primitives" guidance, "match existing project patterns," and any other style heuristic.

If a production design-system primitive does not reproduce the prototype's visual exactly:

- **Right path:** add or extend the primitive so it matches the prototype. Surface the design-system gap during planning so the user can approve the new primitive.
- **Wrong path:** silently substitute a "close-enough" production primitive (e.g., translating a prototype `<span>+✔` eyebrow into a production `Badge` component with pill background and shadow). That is parity drift dressed up as design-system discipline.

When the prototype and the design system disagree, the prototype wins. The design system is a tool for achieving parity, not a replacement for it.

This rule exists because of an observed failure mode where this exact substitution happened and the UI/UX agent accepted it as "design-system compliant."
```

Also update line 50 in `personal-workflow.md` (parity-mode description) to use capability language (replace `browser_evaluate` with "DOM evaluation").

### 4.6 Mirror everywhere

All changes propagate to:
- `codex/skills/ticket-start/` ← repo source of truth
- `claude/skills/ticket-start/` ← mirror (Claude Code tree)
- `~/.codex/skills/ticket-start/` ← Codex install path
- `~/.claude/skills/ticket-start/` ← Claude Code install path

Tree symmetry: only `agents/openai.yaml` is codex-only (unchanged convention).

## 5. File-by-file changes

### Files modified (in both `codex/` and `claude/` skill trees)

| File | Change |
|---|---|
| `agents/ui-ux.md` | (a) tool-language → capability descriptions; (b) new "Host-specific browser bootstrap" subsection; (c) `## Matched-element inventory` section becomes mandatory + exhaustive with completeness rules; (d) new forbidden behavior about selectivity. |
| `agents/qa.md` | (a) tool-language → capability descriptions; (b) new "Host-specific browser bootstrap" subsection (parallel to UI/UX). No other changes. |
| `SKILL.md` | (a) Verify step 6 — dispatch instruction wording host-neutral; (b) new step 6a — main-agent inventory validation + spot-check; (c) two new red flags. |
| `personal-workflow.md` | (a) parity-mode description wording host-neutral; (b) new subsection "Prototype parity dominates all other rules" after React Reference App section. |
| `verification.md` | (a) tool-language → capability descriptions; (b) reinforce inventory exhaustiveness language to match `agents/ui-ux.md`. |

### Files unchanged

- `agents/scoping.md`, `agents/architect.md`, `agents/reviewer.md`, `agents/security.md` — no browser tooling, no parity work.
- `bug-fix-loop.md`, `self-improvement.md` — orthogonal.
- `react-parity.md` — describes parity rules but doesn't reference tool names; reread during implementation to confirm but expect no edits.
- `job-workflow.md` — no parity workflow.
- `agents/openai.yaml` — Codex interface descriptor; unchanged.

### Mirroring requirements

Per the user's standing sync rule: every edit under `codex/skills/` mirrors to `~/.codex/skills/`; every edit under `claude/skills/` mirrors to `~/.claude/skills/`. After this PR, all four locations are byte-identical (modulo `agents/openai.yaml`).

## 6. Deferred to implementation plan

These are plan-level decisions, not design-level:

- Whether to include the codex install-side edits (already present in `~/.codex/skills/`) as a starting point and write on top, or to start fresh in the repo and overwrite the install path at mirror time. The latter is cleaner since the install path should always be a mirror, never a source of truth.
- Exact wording of the new "Host-specific browser bootstrap" subsection — Codex already wrote a Codex-specific version we can adapt.
- Exact wording of the new forbidden behavior and red-flag entries.
- Whether the completeness spot-check at main-agent's step 6a should always perform all three samples (diff, production, prototype) or whether it can short-circuit on the first miss.
- Test plan: how to validate the new enforcement actually works before merging. Options: (a) ship and trust the prior failure won't recur; (b) construct a synthetic UI/UX report that's deliberately incomplete and run through the main-agent validation logic by hand; (c) re-run the GEN-86 ticket end-to-end after merge and confirm the new enforcement catches the same class of failure.

## 7. Migration and scope

- **In scope:** edits to 5 skill files in both trees + mirroring to both install paths.
- **Out of scope:** GEN-86 itself (the ticket where the failure was observed). That ticket needs a real parity-correction pass — separate concern, separate work.
- **Backward compat:** Existing personal-workflow tickets re-run after merge will use the new protocol. No data migration. No breaking changes — the changes tighten existing requirements rather than introducing new dependencies.
- **Rollback path:** revert the PR. The skill returns to the pre-PR state with the looser protocol. The known failure mode reappears, but nothing else breaks.

## 8. Why this is a meaningful skill change worth a brainstorm pass

This is not "add more words to the role prompt." Three substantive design changes:

1. **Shape contract over self-report.** The matched-element inventory was a recommendation. Now it's a required deliverable whose absence the main agent can mechanically detect. This is the single highest-leverage change — it converts a soft expectation into a hard contract.

2. **Exhaustive vs selective.** "Some elements are checked" is the failure mode. "Every visible element gets a row" is enumerable and falsifiable. The user added this requirement explicitly during the brainstorm and it's what makes the inventory non-trivial.

3. **Explicit precedence.** When two rules conflict (parity vs design-system primitives), the skill picks a winner. The previous version implicitly let the agent decide, and the agent picked wrong. Explicit precedence removes that judgment call.

The tool-language patches Codex already wrote are necessary but not sufficient. Without changes 1–3 above, the same failure mode survives even with correct tool references.
