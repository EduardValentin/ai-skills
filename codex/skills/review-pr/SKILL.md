---
name: review-pr
description: Review pull requests and branch diffs against a ticket, acceptance criteria, branch naming, changed files, tests, and risk areas. Use when Codex is asked to help review a PR, audit a diff before merge, verify a branch satisfies a ticket such as ABC-123, find blockers before approval, check checklist coverage, or identify missing tests and security/performance/maintainability issues with findings-first output and proposed fixes.
disable-model-invocation: true
metadata:
  ai-skills-category: procedural
  ai-skills-invocation: manual
---

# Review PR

## Workflow

1. Read the nearest applicable repository instructions before reviewing code. Start with the closest `AGENTS.md`. Then inspect only the minimum additional repo-specific files that matter, such as `CONTRIBUTING.md`, `CLAUDE.md`, review docs, or PR templates.
2. Require the ticket ID and ticket description before starting. If either is missing, ask for it.
3. Extract the acceptance criteria, checklist items, constraints, and explicit non-goals from the ticket description. If acceptance criteria are missing or too vague to evaluate, stop and ask for them.
4. Resolve [scripts/pr_review_preflight.py](scripts/pr_review_preflight.py) relative to this skill directory, then run it while your working directory is the target repository root. Pass `--ticket-id <TICKET-ID>`. If the user already specified a base branch, also pass `--base-branch <branch>`. If the script cannot be run, perform the same checks manually.
5. If the current branch name does not contain the ticket ID, stop the review. Read the available branches, identify the ones that contain the ticket ID, and propose the most likely branch to switch to. Do not begin the substantive review until the branch is corrected.
6. Use the preflight output or manual inspection to determine the review base branch, changed files, changed tests, and nearby instruction files.
7. Review in this order:
   - diff overview and file inventory
   - changed tests and test gaps
   - acceptance-criteria and checklist coverage
   - reuse opportunities and existing repo patterns
   - deep read of the risky changed files and the minimum adjacent code needed for confidence
8. Load [references/review-rubric.md](references/review-rubric.md) and apply it during the review.
9. Report findings first, ordered by severity.

## Preconditions

- Refuse to start the substantive review until all of these exist:
  - ticket ID
  - ticket description
  - acceptance criteria or equivalent explicit success conditions
  - the correct branch containing the ticket ID
  - the diff or a way to inspect it
- Treat repository instructions as binding review context. If repo instructions conflict with generic review preferences, follow the repo instructions and note the conflict.
- Treat every checklist item in the ticket description as required scope unless the user explicitly says otherwise.
- Flag any mismatch between the implemented scope and the ticket scope.
- Flag any code path that changes behavior but lacks appropriate tests.

## Branch Validation

- Prefer the helper script at [scripts/pr_review_preflight.py](scripts/pr_review_preflight.py) for branch and diff preflight.
- Otherwise read `git branch --all` and `git branch --show-current`.
- Compare the current branch name with the ticket ID.
- If the branch does not match:
  - stop the review
  - list the candidate branches that contain the ticket ID
  - propose the exact checkout command
  - wait for the user to switch or confirm before continuing
- Treat branch mismatch as a hard stop, not as a finding inside the review.

## Severity And Approval

- Use these labels:
  - `Blocker`: do not approve
  - `Major`: do not approve
  - `Minor`: non-blocking improvement
  - `Follow-up`: valid improvement that should be split into another ticket or a later PR
- Treat `Blocker` and `Major` as approval blockers.
- Do not promote a concern to a finding unless you can support it with concrete evidence from the diff, surrounding code, tests, or explicit ticket requirements.
- If evidence is incomplete, move the item to `Open Questions / Clarifications` instead of presenting it as a finding.

## Review Priorities

- Find correctness issues, regressions, broken acceptance criteria, security risks, and missing tests first.
- Then judge maintainability, clean code, reuse, and performance.
- Search for existing repo patterns, utilities, hooks, helpers, and abstractions before flagging duplication or proposing new abstractions.
- Ask follow-up questions about load or usage only when a credible performance hotspot exists and the answer materially affects the recommendation.
- Prefer the smallest safe recommendation for in-scope fixes.
- Separate larger architectural improvements into follow-up ticket suggestions when they materially exceed scope.

## Output Format

- Present findings first, ordered `Blocker`, `Major`, `Minor`, `Follow-up`.
- For each finding:
  - include the severity label and a short title
  - include clickable absolute file and line references
  - explain at a high level why the issue matters
  - propose a high-level fix
  - include a small code example only when the suggested change is clear and stays under roughly 100 lines
- After findings, include:
  - open questions or clarifications
  - a short summary covering:
    - what must change now before approval
    - what may be split into a separate ticket because it is materially out of scope or too large for the PR
- If any `Blocker` or `Major` findings exist, say the PR should not be approved yet.
- If there are no findings, say so explicitly and still call out residual risks or testing gaps.

## Codex-Specific Review Behavior

- Use `::code-comment{...}` for line-specific findings when the current surface supports inline review comments.
- Keep each code-comment range tight.
- Mirror the same finding in the chat response so the review remains readable outside the inline UI.
- Use absolute file references in the chat response so they are clickable.
- Keep the explanation technical and concise. Use one paragraph for why the issue is a problem and one paragraph for the proposed solution.
- When a concern lacks enough evidence for a code comment, keep it in the `Open Questions / Clarifications` section instead of emitting an inline finding.

## Review Heuristics

- Prefer existing repo patterns, helpers, and abstractions over inventing new ones.
- Flag duplicated logic when an existing reusable function or pattern likely already covers it.
- Treat untested behavior changes as findings, not as optional polish.
- Flag security issues even when the ticket does not mention security explicitly.
- Flag incomplete ticket or checklist coverage even when the code quality is otherwise good.
- State explicitly when a recommendation is a follow-up architectural improvement rather than a must-fix PR issue.
- Keep feedback high signal. Do not pad the review with trivial style nits.

## Focus Areas

- Use [references/review-rubric.md](references/review-rubric.md) for the detailed review checklist.
- Apply the clean code rules from the rubric aggressively when they affect readability, maintainability, or blast radius.
- Escalate performance concerns only when the changed code touches a plausible hot path or introduces an obvious cost pattern.
- Call out maintainability concerns when future changes would likely require scattered edits outside the feature's natural boundary.
- Use [scripts/pr_review_preflight.py](scripts/pr_review_preflight.py) whenever possible to standardize branch validation, base-branch detection, diff inventory, and changed-test discovery.
