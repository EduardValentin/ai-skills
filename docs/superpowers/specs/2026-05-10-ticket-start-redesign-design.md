# Ticket-Start Redesign — Design Spec

**Date:** 2026-05-10
**Status:** Approved design, pending implementation plan
**Skill being redesigned:** `ticket-start` (lives at `codex/skills/ticket-start/` today; will exist at `claude/skills/ticket-start/` after this redesign)

## 1. Goals and non-goals

### Goals

Produce the highest-quality software the workflow can deliver per ticket. Specifically:

- **Performant** — performance is a first-class concern owned by the Reviewer agent.
- **Secure** — security is a first-class concern owned by a dedicated Security agent.
- **Maintainable / scalable / extendable** — owned by the Reviewer agent.
- **Free of bugs** — owned by the QA agent (behavior) and UI/UX agent (visual + accessibility), backed up by TDD on the implementation path.
- **Self-improving** — recurring findings from auditor agents become codified rules in repo and user-level instruction files, so the next session starts from a higher baseline.

### Non-goals

- Not changing where user dialogue happens. Brainstorming and plan approval remain conversations between the **main agent** and the user. No subagent runs human dialogue.
- Not auto-applying global rules. Every edit to repo `AGENTS.md`, `~/.claude/CLAUDE.md`, or `~/.codex/AGENTS.md` requires explicit user approval.
- Not changing the existing `superpowers:subagent-driven-development` + `superpowers:test-driven-development` per-task review loop on the implement path. Those continue to govern Implement.
- Not introducing backward-compatibility shims. The existing `ticket-start` skill is rewritten in place; there are no external consumers to preserve.
- Not building infrastructure for stale-rule pruning. Rules added via the self-improvement loop are not auto-expired. Periodic review is a separate workflow.

## 2. Workflow shape

The current skill has six phases: Setup → Brainstorm → Plan → Implement → Verify → Ship. The new design splits the single Verify phase into three explicit, gated phases (Review, Security, Verify) and introduces a hybrid orchestrator pattern where the main agent dispatches specialized subagents for every responsibility outside human dialogue and plan-writing.

### Phase order

```
Setup → Brainstorm → Plan → Implement → Review → Security → Verify → Ship
                                            │        │         │
                                        Reviewer Security  QA → UI/UX
                                                          (UI/UX skipped
                                                          on backend-only)
```

Every transition is a **gate**. Main agent does not advance until the prior gate's evidence is gathered.

### Hybrid orchestrator: who owns what

| Responsibility | Owner | Why |
|---|---|---|
| User-facing dialogue (clarifications, brainstorm, plan approval, ship approval) | Main agent | A subagent cannot run human conversation without either bouncing every reply back through main (no context savings) or losing main's visibility into the design reasoning |
| Plan writing (`superpowers:writing-plans`) | Main agent | The plan writer needs to have been *in* the brainstorm |
| Phase gating, dispatch, report synthesis, closeout report | Main agent | This is the orchestrator's job |
| The "stop and ask the human" principle | Main agent | At any phase, if main hits a judgment call, blocker, or ambiguity that exceeds its authority, it pauses and surfaces — workflow halts for user intervention |
| Repo/pattern survey | Scoping subagent | Heavy reads belong off the main agent's window |
| Solution design with tradeoffs | Architect subagent | Sharper output from a tightly-scoped role-prompt; reusable across other workflows |
| Per-task implementation with TDD | Existing `superpowers:subagent-driven-development` | Already battle-tested |
| End-of-feature code review | Reviewer subagent (`superpowers:requesting-code-review`) | Already exists, repurposed |
| Security audit | Security subagent | Distinct skill profile; runs on already-clean code |
| Behavior testing | QA subagent | Distinct skill profile; owns acceptance-criteria verification against the running app/service |
| Visual + accessibility verification | UI/UX subagent | Distinct skill profile; runs only when there are visual changes |

The main agent is **thin but not empty**: it carries judgment, the human conversation, and orchestration. Subagents handle the deep work that would otherwise blow the main agent's context window.

## 3. Agent roster

Each agent is a self-contained role with a single mandate. Inputs and outputs are explicit so handoffs are clean.

### 3.1 Scoping (Setup phase)

- **Mandate:** Read-only repo and pattern survey for the feature in scope.
- **Inputs:** Ticket title and description; relevant `AGENTS.md` and `CLAUDE.md`; for personal workflow, the scoped slices of `PRD.md` and `designs/` that match the feature.
- **Outputs:** A scoped summary doc covering: entry points / feature boot path; target module or component; nearby reducers, services, fetchers, transformers, hooks, tests, shared utilities; existing implementations of similar behavior; project patterns to reuse; potential conflict points with existing architecture.
- **Forbidden:** Proposing solutions, making decisions, writing code.
- **Reused by:** Architect (primary consumer), main agent (during brainstorm).

### 3.2 Architect (Brainstorm input + bug-fix-loop)

- **Mandate:** Produce 2–3 candidate solution architectures with explicit tradeoffs.
- **Inputs:** Scoping summary; ticket; acceptance criteria; any prior architectural decisions surfaced by main.
- **Outputs:** Design proposals — for each: integration approach, data/state model, module boundaries, performance considerations, security surface, risks, why this is preferred or rejected. One recommended option called out.
- **Re-engagement:** Main agent re-dispatches the architect during brainstorm if a follow-up architectural question arises that wasn't covered. Also re-engaged in the bug-fix loop when a fix requires architectural change.
- **Forbidden:** Writing the implementation plan, writing code, running reviews, talking to the user directly.

### 3.3 Implementer (Implement phase)

- **Mandate:** Execute the approved plan task-by-task with TDD and per-task code review.
- **Mechanism:** Dispatched via existing `superpowers:subagent-driven-development`, which auto-triggers `superpowers:test-driven-development` and per-task code-quality review.
- **No changes** to this layer in this redesign — it is already well-tuned.

### 3.4 Reviewer (Review phase)

- **Mandate:** End-of-feature code review covering spec compliance, code quality, **maintainability, scalability, extensibility, and performance**.
- **Mechanism:** Existing `superpowers:requesting-code-review`, dispatched by main after Implement is clean.
- **Inputs:** Full diff; ticket and plan; relevant repo conventions from `AGENTS.md`.
- **Outputs:** Findings list categorized by severity (blocking / strong-recommend / nit); each finding has a clear declarative form so it can later feed the self-improvement loop.
- **Forbidden:** Security audit (separate phase), behavior testing (QA), visual checks (UI/UX).

### 3.5 Security (Security phase)

- **Mandate:** Security audit of the final diff after Reviewer signs off.
- **Inputs:** Full diff; relevant code paths; `AGENTS.md`; package manifests/lockfiles for dependency-risk analysis.
- **Mandate-area checklist:** Trust boundaries, authn/z, user-controlled input, validation, data exposure, persistence safety, file handling, redirects, external requests, privileged actions, sensitive logs, common attack vectors (injection, XSS, CSRF, SSRF, IDOR, broken access control, open redirects, path traversal, unsafe deserialization, secret leakage), insecure dependency versions, unsafe client-side trust.
- **Outputs:** Findings list with severity and remediation; "no findings" is a valid output.
- **Forbidden:** Code style review, behavior testing, visual checks.

### 3.6 QA (Verify phase, behavior pass)

- **Mandate:** Exhaustive behavior verification of the running implementation. **Owns acceptance-criteria verification.**
- **Inputs:** Running app or service; ticket and acceptance criteria; full diff context; backend-only flag (determines mode).
- **Mode A — backend / API / service change:** Start the affected service. Issue real requests against changed endpoints/jobs/handlers/consumers. Cover happy paths, input variation including boundaries, validation failures and error responses, auth/permission boundaries, state transitions, idempotency/retry/concurrency where the change touches them. Inspect response payloads, persisted state, emitted events, and logs against the AC.
- **Mode B — user-facing app / UI change:** Start the app on its dev server. Drive every state through the live browser (Playwright MCP): happy path, loading, empty, success, error, validation, hover/focus/active/disabled, expanded/collapsed, modal-open, navigation. Adversarial input (invalid values, rapid clicks, double submits, navigating mid-action). Cross-feature regression on adjacent flows. Responsive behavior at breakpoints and the widths immediately before/after each breakpoint.
- **Mode C — mixed:** Run A and B both.
- **Outputs:** Bug list with reproduction steps, severity, and (where determinable) suspected location; or "all clean."
- **Bug → fix loop trigger:** Any non-clean output from QA enters the bug-fix loop (Section 5).

### 3.7 UI/UX (Verify phase, visual pass)

- **Mandate:** Visual parity / consistency + accessibility. Skipped on backend-only changes.
- **Programmatic-first principle:** Lean on DOM and computed-style assertions over screenshots. Screenshots are supplementary context for cases where the DOM does not tell the full story (e.g., visual regression caused by stacking contexts), not primary evidence.
- **Mode A — personal workflow with React reference app present:** Run the existing protocol in `verification.md` (Pass 1: visual parity with `browser_evaluate` extraction of computed styles + `getBoundingClientRect`, matched-element inventory, per-state coverage). The reference app in `designs/` is the source of truth.
- **Mode B — job workflow OR personal workflow without React reference:** No external reference. Mandate is **stylistic consistency against the rest of the app/page**. Verify icon sizing rhythm, typography scale, spacing rhythm, color tokens, border radii, shadow elevation, alignment grid — by extracting computed styles from the new/changed elements and comparing against existing sibling and analog elements in the same view. Flag deviations like "this icon is 16px when every other icon on the page is 14px" with the DOM evidence.
- **Accessibility:** Both modes additionally check semantic structure, ARIA roles where applicable, focus order, keyboard reachability, color contrast (WCAG AA at minimum), text alternatives for images and icons.
- **Outputs:** Parity / consistency / a11y report; or "all clean."

## 4. Phase-by-phase protocol

For each phase, what main does, what subagent returns, what the gating evidence looks like.

### 4.1 Setup

1. Worktree first via `superpowers:using-git-worktrees` (unchanged).
2. Read repo instructions inside the worktree (`AGENTS.md` then any project-specific instruction files).
3. Workflow selection (Job vs Personal) — decided from ticket source, not contents. Loads the corresponding workflow file.
4. **Ticket intake** (workflow-specific):
   - **Job:** Try `acli jira workitem view <KEY> --json` first. If `acli` is not on PATH, errors out, or returns auth failure, surface the error and prompt the user to paste the full ticket title and description. Do not proceed without the full ticket content.
   - **Personal:** Linear MCP as the source of truth (unchanged).
5. **Dispatch Scoping subagent** with ticket + repo instructions + scoped PRD/designs slices (personal workflow only). Wait for scoped summary.
6. Clarifications loop with user if AC are vague, missing, or conflict with existing architecture. **No advance to Brainstorm without clean AC and a scoping summary.**

### 4.2 Brainstorm

1. **Dispatch Architect subagent** with (ticket + scoping summary). Wait for design proposals.
2. Run `superpowers:brainstorming` with the user, using the architect's proposals as starting material. Standard one-question-at-a-time dialogue.
3. If a follow-up architectural question arises mid-brainstorm, **re-dispatch Architect** with a focused question and bring the answer back into the conversation.
4. Converge on a chosen direction. Brainstorm convergence is **not** plan approval — that's a separate gate.

### 4.3 Plan

1. Main agent writes the implementation plan via `superpowers:writing-plans`.
2. Plan presented to user; wait for explicit approval of the plan as its own artifact.
3. **No code is written between brainstorm convergence and plan approval.** Not exploratory edits, not scaffolding, not "sketching the structure."

### 4.4 Implement

1. **Personal workflow:** Move Linear ticket to `In Progress` immediately after plan approval, before any code.
2. Dispatch implementation via existing `superpowers:subagent-driven-development` (auto-triggers TDD + per-task code review).
3. On the `superpowers:executing-plans` fallback path, main explicitly invokes `superpowers:requesting-code-review` after the final task — that path lacks per-task review.
4. When superpowers' flow reaches `superpowers:finishing-a-development-branch`: accept its test-pass check; do **not** present its 4-option prompt to the user. Return control to ticket-start's Review phase.

### 4.5 Review

1. **Dispatch Reviewer subagent** with full diff + ticket + plan.
2. If findings exist, route them through the bug-fix loop (Section 5) before advancing.
3. When Reviewer is clean, run the **self-improvement extraction pass** on Reviewer findings (Section 6).
4. Advance to Security only when Reviewer is clean.

### 4.6 Security

1. **Dispatch Security subagent** with full diff + relevant code paths + manifests.
2. If findings exist, route them through the bug-fix loop. After fix, **Reviewer + Security re-run on the full diff** (per the locked re-review scope).
3. Run self-improvement extraction pass on Security findings.
4. Advance to Verify only when Security is clean.

### 4.7 Verify

1. Determine **backend-only flag** from the actual diff (Section 8). If uncertain, ask the user.
2. **Dispatch QA subagent.** QA selects mode from the change (A / B / C). Cover everything in QA's mandate (Section 3.6).
3. If QA finds bugs, route through bug-fix loop. After fix, **QA re-runs the full behavior pass** (regressions matter, so scoped re-runs are insufficient).
4. Run self-improvement extraction pass on QA findings.
5. **If backend-only flag is set: skip UI/UX. Otherwise, dispatch UI/UX subagent.** Mode determined by personal+React-reference vs everything else.
6. If UI/UX finds issues, route through bug-fix loop. After fix, **UI/UX re-runs scoped to affected states** (visual issues are localized; full re-runs are wasteful).
7. Run self-improvement extraction pass on UI/UX findings.
8. Advance to Ship only when QA is clean and UI/UX is clean (or skipped).

### 4.8 Ship

1. **Personal workflow:** Open PR with `gh`. Move Linear ticket to `In Review`.
2. **Job workflow:** Open PR per repo conventions.
3. Wait for explicit user approval before merging.
4. **Personal workflow:** After merge, move Linear ticket to its completed state.
5. **Job workflow:** After merge, follow team's post-merge convention from `AGENTS.md` if specified; otherwise stop and surface what remains manual.
6. Closeout report (Section 4.9).

### 4.9 Closeout report

Main agent reports:
- What changed.
- Each form of evidence gathered, named explicitly: tests run; API verification (job/backend); browser verification (job, user-facing); visual parity pass and behavior pass (personal+React); QA modes used; UI/UX mode used; Security audit clean.
- Any rules promoted to repo `AGENTS.md`, `~/.claude/CLAUDE.md`, or `~/.codex/AGENTS.md` during this session, with a one-line summary of each.
- Bug-fix iterations consumed (out of 3 cap).
- Remaining risk, assumption, or follow-up.
- Anything unverified or blocked, named explicitly.

## 5. Bug-fix loop

Triggered by any non-clean output from Reviewer, Security, QA, or UI/UX.

### 5.1 Three-tier complexity gating

Main agent classifies the fix:

| Tier | Definition | Path |
|---|---|---|
| **Trivial** | Typo, one-liner, mechanical change with no design implication | Straight to Implementer. No brainstorm, no plan, no architect |
| **Non-trivial, non-architectural** | Real change but doesn't alter the architecture of the solution | Main re-runs brainstorm + plan with the user. No architect involvement |
| **Architectural** | Fix changes the solution's architecture (modules, boundaries, data model, integration approach) | Main re-engages **Architect**, then re-runs brainstorm + plan (full initial loop) |

**Main agent decides classification.** When ambiguous, defaults to the higher tier (safer).

### 5.2 Re-review scope after a fix

| Agent | Scope of re-run |
|---|---|
| **Reviewer** | Full diff (original + fix). A fix can introduce regressions in the reviewed surface |
| **Security** | Full diff. Cross-cutting concerns require full audit |
| **QA** | Full behavior pass. A fix can introduce regressions in unrelated states |
| **UI/UX** | Scoped to affected states. Visual issues are localized; full re-runs are wasteful |

### 5.3 Iteration cap

- **Cap = 3 fix iterations.** After the third unresolved fix attempt, main agent stops and produces an intervention report:
  - What the persistent issues are
  - Why fixes didn't land
  - What user input or environment change could unblock the work
- This protects against runaway loops on genuinely hard problems.

### 5.4 User intervention principle

At **any** point — not just at the cap — if main agent hits a judgment call, blocker, ambiguity, environmental issue, or anything that exceeds its authority to decide, the workflow stops and surfaces. Main does not guess on the user's behalf.

## 6. Self-improvement loop

Triggered after **each** auditor agent (Reviewer, Security, QA, UI/UX) returns findings, regardless of whether those findings entered the bug-fix loop. The loop converts recurring lessons into codified rules.

### 6.1 Rule extraction protocol

1. Main agent scans the agent's findings for **patterns worth codifying** (filter in 6.2).
2. Main cross-checks against existing rules in repo `AGENTS.md`, `~/.claude/CLAUDE.md`, and `~/.codex/AGENTS.md` to avoid duplication.
3. Main drafts proposed rules in declarative voice ("Always X" / "Never Y when Z") matching the destination file's existing style.
4. Main classifies each proposed rule as **repo-specific** or **universal** based on whether it's tied to this codebase or applies across all the user's projects.
5. Main proposes rules to the user, listing destination, severity, and rationale per rule.
6. **User approves each rule individually** (yes / no / edit). No rule is written without explicit approval.
7. Approved rules are committed:
   - **Repo-specific** → repo `AGENTS.md`, as a **separate commit** in the same worktree (so the AGENTS.md change is in the same PR but a distinct commit, easy to review or revert independently of feature commits).
   - **Universal** → both `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`, with the **same rule text**, in the same flow. Both files must be updated for the rule to be considered live (so Codex and Claude Code stay in sync).
8. The closeout report lists every rule promoted in the session.

### 6.2 Rule promotion bar

A finding becomes a rule only if it satisfies **all** of:

- **Pattern-based** — applies to a class of changes, not just this one ticket.
- **High-cost if violated** — security risk, performance regression, maintainability tax, or behavioral correctness.
- **Has a clear declarative form** — can be expressed in one or two sentences as an instruction.
- **Not stylistic preference alone** — taste-only items don't qualify.
- **Not already covered** — explicit or implicit duplicates of existing rules don't qualify.

Findings that fail this bar are mentioned in the closeout report as "observed once, not promoted to a rule."

### 6.3 Rule destinations summary

| Rule type | Destination | Approval required |
|---|---|---|
| Repo-specific | Repo `AGENTS.md` (separate commit in same PR) | Yes, per rule |
| Universal | Both `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`, kept in sync | Yes, per rule |

Codex's auto-managed `~/.codex/memories/` is **not** a destination — it is internal to Codex and we do not write to it.

## 7. Job vs personal differentiation

The two workflows differ in exactly two places. Every agent's mandate and behavior is identical across both workflows except where the table below names the difference.

| Aspect | Job | Personal |
|---|---|---|
| Ticket platform | Jira via `acli jira workitem view <KEY> --json`; falls back to user paste if `acli` is missing or errors | Linear via Linear MCP (unchanged) |
| UI/UX reference source | None — UI/UX runs in stylistic-consistency mode (Section 3.7 Mode B) | If `designs/` is a runnable React app, UI/UX runs the `verification.md` parity protocol (Mode A); if `designs/` is missing, falls back to Mode B |
| Linear state transitions | N/A | `In Progress` at start of Implement; `In Review` at PR open; completed state on user-approved merge (unchanged) |
| Post-merge ticket convention | Per repo `AGENTS.md` if specified, else surface as manual | Move to completed Linear state |

Everything else — Scoping, Architect, Implementer, Reviewer, Security, QA's mandate, the bug-fix loop, the self-improvement loop, the file structure — is identical.

## 8. Backend-only detection

UI/UX is skipped only when the change is backend-only. Detection is **main agent's responsibility**, performed during Verify after Implement is complete.

### 8.1 Heuristic

Main agent walks the actual diff:

- **Backend-only candidates:** No files changed in UI directories or with UI extensions. UI extensions include `.tsx`, `.jsx`, `.vue`, `.svelte`, `.html`, `.css`, `.scss`, `.sass`, `.less`, `.styl`, server-side template files (`.ejs`, `.pug`, `.hbs`, `.erb`, `.twig`, `.liquid`, `.jinja`, `.blade.php`). UI directories include conventional `app/`, `components/`, `pages/`, `views/`, `templates/`, `client/`, `web/`, `frontend/`, `ui/`. Repo-specific UI directories (e.g., a `src/screens/`) are inferred from existing pattern.
- **Not backend-only:** Any file change to a UI extension or UI directory, OR any change that modifies rendered output indirectly (e.g., a server-side handler that emits HTML, a config that changes which template is rendered).

### 8.2 Ask-on-uncertainty

If main agent is uncertain whether a change affects rendered output (e.g., a backend file that produces UI strings, a config file that switches between UI behaviors, a shared utility used by both backend and UI), it **asks the user** before deciding to skip UI/UX.

The default on uncertainty is **do not skip** — running UI/UX unnecessarily is cheap; skipping it incorrectly is expensive.

## 9. File structure and mirroring

### 9.1 Skill directory structure (symmetric for Codex and Claude Code)

```
codex/skills/ticket-start/                          claude/skills/ticket-start/
├── SKILL.md                                        ├── SKILL.md          (Claude Code frontmatter)
├── job-workflow.md                                 ├── job-workflow.md
├── personal-workflow.md                            ├── personal-workflow.md
├── react-parity.md                                 ├── react-parity.md
├── verification.md                                 ├── verification.md
├── bug-fix-loop.md          ← NEW                  ├── bug-fix-loop.md          ← NEW
├── self-improvement.md      ← NEW                  ├── self-improvement.md      ← NEW
└── agents/                                         └── agents/
    ├── openai.yaml          ← Codex iface              ├── scoping.md           ← shared content
    ├── scoping.md           ← NEW (shared)             ├── architect.md         ← shared content
    ├── architect.md         ← NEW (shared)             ├── reviewer.md          ← shared content
    ├── reviewer.md          ← NEW (shared)             ├── security.md          ← shared content
    ├── security.md          ← NEW (shared)             ├── qa.md                ← shared content
    ├── qa.md                ← NEW (shared)             └── ui-ux.md             ← shared content
    └── ui-ux.md             ← NEW (shared)
```

The Codex tree has `agents/openai.yaml` as its platform-specific skill interface descriptor (existing convention). The Claude Code tree does **not** need an equivalent — Claude Code skills are defined entirely by SKILL.md frontmatter. Both trees share the same six `agents/<role>.md` role-prompt files (identical content).

### 9.2 Mirroring rule

Per the user's standing sync requirement (in `MEMORY.md`):
- Every edit under `codex/skills/` mirrors to `~/.codex/skills/` in the same flow.
- Every edit under `claude/skills/` mirrors to `~/.claude/skills/` in the same flow.

Both repo trees and both install paths must be updated together for any change in this skill.

### 9.3 Agent role-prompt content (shared, platform-agnostic)

Each `agents/<role>.md` is platform-agnostic content: identity, mandate, inputs expected, output format, forbidden behaviors, escalation rules. The same file content is consumed on both platforms.

**Dispatch mechanism differs by platform:**
- **Codex:** main agent invokes the role via Codex's skill/subagent mechanism, reading the role-prompt content and passing it as the subagent's instruction set. The exact Codex API and whether `agents/openai.yaml` needs extending to declare the subagents is a plan-level question (Section 10).
- **Claude Code:** main agent invokes the role via the `Agent` tool. The exact `subagent_type` choice — generic (`general-purpose`) with the role-prompt injected, or a custom agent definition placed in `~/.claude/agents/` and referenced by name — is a plan-level question (Section 10).

The role-prompts themselves contain no platform-specific content, so the same file ships on both platforms.

## 10. Deferred to implementation plan

These are deliberately not specified at the design level. They are operational details to nail down during `superpowers:writing-plans` and implementation:

- Exact subagent dispatch mechanics on each platform:
  - **Codex:** whether subagents are declared in `agents/openai.yaml`, in a separate per-agent YAML, or invoked ad-hoc via skill loading. Whether the existing `agents/openai.yaml` needs to be extended.
  - **Claude Code:** whether to use generic `general-purpose` `Agent` dispatch with the role-prompt injected at call time, or to ship custom agent definitions to `~/.claude/agents/` and reference them by `subagent_type`. The custom-agent route makes the agents named/reusable but adds an install-side artifact outside the skill folder.
- Exact handoff artifact formats per agent (free-form structured Markdown vs YAML vs JSON; whether reports go to disk or stay in-message).
- The diff-walking implementation for backend-only detection (which `git diff` invocation, how to handle renames, how to walk the file tree for UI directory inference).
- Where to file the per-session "rules considered but not promoted" log (closeout report only, or a persisted file).
- How `acli` errors are detected and categorized (auth vs network vs invalid key) for clean fallback messaging.
- Whether `agents/<role>.md` files should be physically shared via symlink, copied, or generated from a single source template.
- Whether the `bug-fix-loop.md` and `self-improvement.md` content lives inline in `SKILL.md` or as separate files (file structure above assumes separate; that's a default to revisit if the docs are short enough to inline).
- Migration strategy for the existing `codex/skills/ticket-start/SKILL.md` content during the rewrite (single sweep vs phased).

## 11. Migration and scope

- **In scope of this redesign:** Full rewrite of `codex/skills/ticket-start/`. Creation of mirror skill at `claude/skills/ticket-start/`. Mirroring of both to `~/.codex/skills/` and `~/.claude/skills/`. Creation of new files (`bug-fix-loop.md`, `self-improvement.md`, `agents/<role>.md` × 6). Update to `agents/openai.yaml` and creation of `agents/claude-code.yaml` for dispatch wiring.
- **Out of scope:** Changes to `superpowers:*` skills themselves. Changes to other skills in `codex/skills/` or `claude/skills/`. Pre-populating any `AGENTS.md` or `CLAUDE.md` content based on hypothetical rules (the self-improvement loop populates them organically over real ticket sessions).
- **No backward-compat concern:** The existing `ticket-start` skill is the only consumer. Rewriting it in place is safe.
