# PR Body Workflow

## Output Contract

Use these sections in this order:

1. Summary of Changes
2. Automated Tests
3. Manual Verification
4. Technical Details only when explicitly requested or needed for multi-module or non-obvious logic

## Section Rules

### Summary of Changes

- Write concise bullets.
- Focus on user-facing behavior or externally observable API, workflow, operator, or system behavior.
- When ticket or conversation context names an affected user, workflow, or purpose, make that the first bullet before implementation details.
- Group related edits and omit review-irrelevant cleanup.

### Automated Tests

- Include automated test commands only.
- Use fenced code blocks with real line breaks.
- Prefer focused commands first, broader checks second.
- Write "Not specified." only when no reliable automated command can be inferred.

### Manual Verification

- Write concise, human-readable, command-backed steps. Preserve reliable setup, entry-point, request, query, script, or mock-control commands from the review context in fenced blocks.
- Exercise only the public or top-level entry point into the changed flow. Do not manually trigger downstream events, call private functions, or reach into helper code.
- Keep the application code path real. Mock only external I/O or service boundaries. For each mocked boundary, add a separate "Mocked external boundary:" line, name it, put any exact URL or path in a fenced block, explain why the mock is needed, and state what remains real.
- Do not include automated test runner commands here.

### Technical Details

- Include only when useful for review.
- Explain final code path, data flow, state transitions, persistence, migrations, jobs, or edge-case handling.
- Do not write a file-by-file changelog.

## Formatting Rules

- Use readable Markdown with blank lines between headings, lists, and code blocks.
- Use fenced code blocks, not inline code or embedded prose, for code-like values such as commands, request bodies, SQL, JSON, endpoints, URLs, file paths, query parameters, input values, output, or snippets.
- Add language hints to fenced blocks when known.
- Reserve inline code for short identifiers. Write UI labels and section names as plain prose or quoted text.
- Do not emit escaped newline text instead of real line breaks.
- Avoid agent-process phrases such as "I ran", "I was unable to run", "not tested locally", "verified with Playwright", or "screenshots captured".
- Use a platform-appropriate browser-opening command when one is supported; otherwise provide the URL and browser action without assuming a macOS-only command.

## Example Shape

````md
## Summary of Changes

- ...

## Automated Tests

```bash
npm test -- billing-export
npm run test:e2e -- billing-export.spec.ts
```

## Manual Verification

1. Start the app using the reliable setup command.
2. Open the changed public workflow in a browser or invoke its public entry point.
3. If an external dependency must be mocked, name the mocked boundary and explain what remains real.
4. Perform the reviewer action and confirm the visible state, response, persistence, generated artifact, or other observable result.
````
