---
name: pr-reviewer-summary
description: Use when asked for a PR description, summary of changes, testing instructions, reviewer notes, or prompts like "Generate a summary of changes for this PR" after finishing ticket or PR work in any codebase.
---

# PR Reviewer Summary

Draft a ready-to-paste Markdown PR body from reliable review context: branch diff or PR diff, changed files, recent commits, and available ticket or conversation context. If there is no diff, changed-file summary, or PR URL, ask for that context instead of inventing the PR body.

Describe only the final shipped state. Do not mention iteration history, false starts, agent process, tools used, screenshots, environment limits, or whether the agent personally tested the app.

## Output Contract

Output only the PR body. Use these sections in this order:

1. `## Summary of Changes`
2. `## Automated Tests`
3. `## Manual Verification`
4. `## Technical Details` only when explicitly requested or needed for multi-module or non-obvious logic

## Section Rules

### `## Summary of Changes`

- Write concise bullets.
- Focus on user-facing behavior or externally observable API, workflow, operator, or system behavior.
- Group related edits and omit review-irrelevant cleanup.

### `## Automated Tests`

- Include automated test commands only.
- Use fenced code blocks with real line breaks.
- Prefer focused commands first, broader checks second.
- Write `Not specified.` only when no reliable automated command can be inferred.

### `## Manual Verification`

- Include as many steps as the feature needs for meaningful manual verification.
- Exercise the real app or system against real dependencies whenever practical.
- Reserve mocks, fakes, stubs, or test-support toggles for dependencies that are hard to spin up, configure, or safely manipulate.
- When a manual step uses a mock, fake, stub, or test-support toggle, label it as a fallback and state why the real dependency is not practical for that check.
- Include manual reviewer actions, exact commands to run, and expected results.
- For UI work, include required setup commands, then short click/input steps.
- For API, CLI, job, database, or integration work, include exact manual commands, requests, queries, or scripts.
- Use fenced code blocks for commands, request bodies, SQL, JSON, or multi-line snippets.
- Do not include automated test runner commands here.

### `## Technical Details`

- Include only when useful for review.
- Explain final code path, data flow, state transitions, persistence, migrations, jobs, or edge-case handling.
- Do not write a file-by-file changelog.

## Formatting Rules

- Use readable Markdown with blank lines between headings, lists, and code blocks.
- Add language hints to fenced blocks when known, such as `bash`, `json`, `http`, or `sql`.
- Do not emit escaped newline text instead of real line breaks.
- Avoid agent-process phrases such as "I ran", "I was unable to run", "not tested locally", "verified with Playwright", or "screenshots captured".

````md
## Summary of Changes

- ...

## Automated Tests

```bash
npm test -- billing-export
npm run test:e2e -- billing-export.spec.ts
```

## Manual Verification

1. Start the app:

   ```bash
   npm run dev
   ```

2. Open the changed workflow, perform the reviewer action, and confirm the expected result.
3. Trigger the changed failure state:

   ```bash
   curl -X POST http://localhost:3000/api/example/fail
   ```

4. Confirm the visible error or changed state.
````
