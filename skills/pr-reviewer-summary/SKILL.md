---
name: pr-reviewer-summary
description: Use when asked for a PR description, summary of changes, testing instructions, reviewer notes, or prompts like "Generate a summary of changes for this PR" after finishing ticket or PR work in any codebase.
---

# PR Reviewer Summary

Generate a full PR body in Markdown that helps a reviewer understand what changed, why it matters, and how to verify it quickly. Build the draft from the current branch diff, changed files, recent commits, and the surrounding user conversation or ticket context. Describe the final shipped state only, not the sequence of iterations, discarded approaches, or intermediate fixes that happened during development.

## Workflow

1. Gather the review context.
   Inspect the current branch diff against the normal review base for the repository. Review the changed files, recent commits, and the user conversation that led to the work. Use ticket details if they are available.
2. Identify the reviewer-visible story.
   Distill the change into the smallest set of user-facing or externally observable outcomes that matter for review. Ignore refactors, renames, formatting, test-only changes, or small cleanups unless they materially affect behavior or the review path.
3. Collapse iteration history into final-state behavior.
   Do not narrate how the feature evolved during development. Do not mention earlier versions, retries, back-and-forth changes, or the order in which fixes landed unless that history is required for safe review of migrations or irreversible behavior changes. Describe only the final behavior and the final implementation shape the reviewer needs to evaluate.
4. Decide whether to include technical detail.
   Always include `## Summary of Changes` and `## Manual Testing`. Include `## Technical Details` only when the user explicitly asks for it or when the change spans multiple modules, subsystems, or non-obvious logic boundaries.
5. Write the PR body in Markdown only.
   Return a ready-to-paste PR description, not notes about how you produced it.

## Section Rules

### `## Summary of Changes`

- Write concise bullets at a high level.
- Focus on user-facing behavior, workflow changes, visible UI states, or externally observable system behavior.
- Group related edits into a single reviewer-relevant point.
- Abstract away low-level implementation details.
- Omit minor or review-irrelevant edits.
- Describe the end result only, not the path taken to get there.
- Prefer outcome language such as what now works, what changed for the user, or what a reviewer should notice.
- If there is no direct UI impact, describe the observable behavior change at the API, operator, or workflow level instead of padding with internal-only details.

### `## Manual Testing`

- Write a numbered list.
- Include preconditions when needed, such as login state, feature flags, seed data, permissions, or environment setup.
- Walk the reviewer through the flow step by step with enough detail that they do not need to infer missing navigation or setup.
- Prefer click-by-click instructions for product changes.
- For non-UI work, provide equally explicit command-by-command or request-by-request verification steps.
- Cover the primary happy path and any materially changed states, branches, or regressions that the diff makes reviewer-relevant.
- Include expected results inline when they help the reviewer confirm success.

### `## Technical Details`

- Include this section only when it is warranted by the rules above.
- Explain the code path step by step.
- Connect the implementation choices to the surrounding architecture so the reviewer understands why the approach fits the codebase.
- Highlight module boundaries, data flow, state transitions, persistence changes, migrations, background jobs, or edge-case handling when they are central to the review.
- Explain the final technical design, not the chronological history of experiments or revisions.
- Stay concrete without turning the section into a file-by-file changelog.

## Output Shape

Use these headings exactly when they are present:

```md
## Summary of Changes

- ...

## Manual Testing

1. ...

## Technical Details

1. ...
```

## Quality Bar

- Optimize for reviewer speed and clarity.
- Prefer a small number of high-signal bullets over exhaustive coverage.
- Make reasonable inferences from the diff and context when necessary.
- Call out assumptions briefly only when missing context could change how the reviewer validates the work.
- Avoid phrases that imply iteration history, such as "initially", "then", "later", "after feedback", or "we also changed this again", unless that sequence is essential to understanding a migration or rollout risk.
- Keep the writing neutral, concrete, and easy to skim.
