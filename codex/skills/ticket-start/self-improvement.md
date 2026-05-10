# Self-Improvement Loop

Loaded by the main agent after each auditor agent (Reviewer, Security, QA, UI/UX) returns its report — regardless of whether the report was CLEAN or routed through the bug-fix loop. This file defines how recurring lessons become codified rules.

## Trigger

After Reviewer, Security, QA, or UI/UX returns its report, main scans the report's `Patterns to codify next time` section. Each entry is a **candidate** for promotion to a rule.

## Rule promotion bar

A candidate becomes a proposed rule **only if all** of these are true:

- **Pattern-based** — applies to a class of changes, not just this one ticket.
- **High-cost if violated** — security risk, performance regression, maintainability tax, behavioral correctness, or accessibility impact.
- **Has a clear declarative form** — can be expressed as one or two sentences in instruction voice ("Always X" / "Never Y when Z").
- **Not stylistic preference alone** — taste-only items don't qualify.
- **Not already covered** — not an explicit duplicate or implicit consequence of an existing rule. Cross-check repo `AGENTS.md`, `~/.claude/CLAUDE.md`, and `~/.codex/AGENTS.md` before proposing.

A candidate that fails the bar is recorded in the closeout report under "Observed once, not promoted to a rule." Visibility without bloat.

## Classification: repo-specific vs universal

For each candidate that passes the bar, main classifies it:

- **Repo-specific** — the rule is tied to this codebase's architecture, naming conventions, framework choices, library versions, or domain rules. It would not apply to other projects. Example: "In this codebase, all API responses go through `responseShape.ts`'s `ok()`/`err()` helpers."
- **Universal** — the rule is broadly applicable across the user's projects, codebases, and stacks. It captures a lesson that transcends one repo. Example: "Always validate user-controlled input at the trust boundary before persistence, regardless of upstream validation."

When in doubt, classify as repo-specific. Universal promotions are higher stakes and the user should always be in the loop on them.

## Destinations

| Classification | Destination | Update mechanism |
|---|---|---|
| Repo-specific | Repo's `AGENTS.md` (the same file the worktree's repo uses) | Append in a **separate commit** in the same worktree, distinct from the feature commits. Same PR. |
| Universal | **Both** `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`, with the **same rule text**, in the **same flow** (both must update or neither does — keep Codex and Claude Code in sync) | Same separate commit in the same worktree if the universal rule is appended via the worktree; otherwise update both files atomically with separate-commit-style messages |

Codex's auto-managed `~/.codex/memories/` is **not** a destination — it is internal to Codex. We do not write to it.

## Approval gate

**Every** rule proposed by main agent requires **explicit user approval before any file is edited.** Rule by rule, yes/no/edit.

The approval gate is non-negotiable. Codifying global guidance from one ticket's findings is high-stakes; the user is always in the loop. Auto-applying rules is forbidden.

Procedure:

1. Main collects all candidates passing the bar from this ticket's auditor reports.
2. Main classifies each (repo-specific vs universal).
3. Main drafts each rule in destination-style voice (terse, declarative, matching existing rule formatting in the destination file).
4. Main presents the candidates as a list with: candidate text, destination, classification, source agent, source finding ID, rationale.
5. User responds yes/no/edit per candidate.
6. Approved rules are committed to their destinations in a separate commit. Rejected rules are recorded in the closeout report under "Considered, not promoted."
7. The closeout report enumerates every promoted rule with its destination.

## Style: matching destination file conventions

Before drafting, **read the destination file's existing rules** and match their style:
- Repo `AGENTS.md` may use bullet lists, numbered sections, or paragraph form.
- `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` may be empty (clean slate) or have user-curated content.

Match the existing style. If the file is empty, choose a clean format (e.g., bullets under topical headers) and stick with it for future entries.

## Drift tolerance and stale rules

This protocol does not include automatic stale-rule pruning. A rule added 6 months ago may no longer apply to the codebase. Periodic review is a separate workflow — not part of this skill. The closeout report notes "rules in this session" but does not audit pre-existing rules.

## Closeout report integration

The session's closeout report (produced by the main agent at end of Ship) includes a section:

```markdown
## Rules promoted in this session

### Repo-specific (added to <repo>/AGENTS.md, commit <sha>)
- <rule 1>
- <rule 2>

### Universal (added to ~/.claude/CLAUDE.md and ~/.codex/AGENTS.md, commit <sha>)
- <rule 1>

### Considered, not promoted
- <candidate 1> — reason: <one line>
```

This makes the self-improvement transparent and auditable.
