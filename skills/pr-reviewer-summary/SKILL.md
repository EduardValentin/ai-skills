---
name: pr-reviewer-summary
description: This skill should be used every time we create or update a PR description
---

# PR Reviewer Summary

Draft a ready-to-paste Markdown PR body from reliable review context: branch diff or PR diff, changed files, recent commits, and available ticket or conversation context. If there is no diff, changed-file summary, or PR URL, ask for that context instead of inventing the PR body.

Describe only the final shipped state. Do not mention iteration history, false starts, agent process, tools used, screenshots, environment limits, or whether the agent personally tested the app.

## Output Contract

Output only the PR body. Use these sections in this order:

1. Summary of Changes
2. Automated Tests
3. Manual Verification
4. Technical Details only when explicitly requested or needed for multi-module or non-obvious logic

## Section Rules

### Summary Of Changes

- Write concise bullets.
- Focus on user-facing behavior or externally observable API, workflow, operator, or system behavior.
- When ticket or conversation context names an affected user, workflow, or purpose, make that the first Summary bullet before implementation details.
- Group related edits and omit review-irrelevant cleanup.

### Automated Tests

- Include automated test commands only.
- Use fenced code blocks with real line breaks.
- Prefer focused commands first, broader checks second.
- Write "Not specified." only when no reliable automated command can be inferred.

### Manual Verification

- Write concise, human-readable, command-backed steps. Preserve reliable setup, entry-point, request, query, script, or mock-control commands from the review context in fenced blocks; for UI flows, include setup and, when inferable, a terminal command to open the public route before click/input steps and expected visible results.
- Exercise only the public or top-level entry point into the changed flow, such as the UI flow, API route, CLI command, job runner, handler, or top-level function touched by the PR; do not manually trigger downstream events, call private/internal functions, or reach into helper code.
- Keep the application code path real. Mock only external I/O or service boundaries the entry point depends on, such as API, network, filesystem, queue, clock, or ISO-provider calls. For each mocked boundary, include a separate "Mocked external boundary:" line, name the boundary, put any exact URL/path in a fenced block, explain why the mock is needed, and state what remains real.
- Do not include automated test runner commands here.

### Technical Details

- Include only when useful for review.
- Explain final code path, data flow, state transitions, persistence, migrations, jobs, or edge-case handling.
- Do not write a file-by-file changelog.

## Formatting Rules

- Use readable Markdown with blank lines between headings, lists, and code blocks.
- Use fenced code blocks, not inline code or embedded prose, for every code-like value, including single-line commands, request bodies, SQL, JSON, endpoint paths, URLs, file paths, query parameters, input values, terminal output, or snippets. Introduce each exact value with a short sentence, then place it in its own fenced block.
- Add language hints to fenced blocks when known, such as `bash`, `json`, `http`, or `sql`.
- Reserve inline code only for single-word identifiers such as short function, variable, package, flag, or command names.
- Write UI labels, button text, menu names, and section names as plain prose or quoted text, not inline code.
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

   ```bash
   open http://localhost:3000/example
   ```

3. If the real external dependency is impractical for reviewer verification, note the mocked boundary before the command. The changed entry point and application persistence still run normally.

   Mocked external boundary: example provider at:

   ```text
   http://localhost:4010
   ```

   Reason: the real provider cannot be safely forced into this response state during review.

4. Exercise the changed public entry point:

   ```bash
   curl -X POST http://localhost:3000/api/example \
     -H 'content-type: application/json' \
     --data '{"example":"value"}'
   ```

5. Confirm the visible state, response body, database row, generated file, or other reviewer-observable result.
````
