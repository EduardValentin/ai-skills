# PR Review Rubric

Use this rubric after the preconditions in `SKILL.md` are satisfied.

## Approval Bar

- `Blocker` and `Major` findings mean the PR should not be approved yet.
- `Minor` findings are non-blocking improvements.
- `Follow-up` items are valid but should usually live in a separate ticket or later PR.
- If the evidence is not strong enough to support a finding, ask a question instead of issuing a finding.

## Severity Calibration

- `Blocker`:
  - broken or missing acceptance-criteria coverage
  - security vulnerabilities or unsafe trust boundaries
  - data loss, corruption, crashes, or high-confidence regressions
  - missing tests on critical or high-risk behavior changes
- `Major`:
  - meaningful but non-catastrophic acceptance-criteria gaps
  - likely regressions with credible supporting evidence
  - important maintainability problems that materially raise future change cost
  - avoidable performance risks on likely hot paths
  - weak or missing tests on meaningful changed behavior
- `Minor`:
  - worthwhile readability, structure, or reuse improvements that do not block approval
  - localized maintainability concerns with small blast radius
- `Follow-up`:
  - larger architectural improvements
  - broader cleanup or refactoring that exceeds ticket scope
  - valid ideas that should be tracked separately to avoid bloating the current PR

## Evidence Rule

- Ground every finding in concrete evidence from the diff, adjacent code, tests, repository instructions, or explicit ticket requirements.
- Prefer quoting the behavior and impact in your own words rather than making speculative claims.
- If you cannot show why the issue is likely real, downgrade it to an open question.
- Do not issue style-only findings unless they create a meaningful readability, maintainability, correctness, or performance problem.

## Deterministic Review Sequence

1. Read the nearest applicable repository instructions.
2. Confirm ticket ID, ticket description, acceptance criteria, and checklist items.
3. Run the preflight script or perform equivalent branch, base, and diff checks manually.
4. Inspect the changed file inventory before deep reading code.
5. Inspect changed tests and compare them to the changed behavior.
6. Map the diff to the acceptance criteria and checklist.
7. Search for existing helpers or patterns that the new code could reuse.
8. Deep-read only the risky changed files and the minimum surrounding code needed for confidence.
9. Emit findings in severity order, then open questions, then summary.

## Acceptance Criteria and Scope

- Compare the implemented behavior with every acceptance criterion.
- Compare the implementation with every checklist item in the ticket description.
- Flag missing scope, partially implemented scope, and scope that contradicts the ticket.
- Flag material overreach when the PR solves extra problems that should live in a separate ticket.
- State explicitly when a recommendation is outside the current ticket and should be split out.

## Testing

- Require unit tests for behavior changes unless the change is truly trivial and cannot regress meaningful behavior.
- Require integration tests when the change crosses module boundaries, service boundaries, async orchestration, or end-to-end user flows where unit tests alone are weak evidence.
- Distinguish clearly between:
  - no tests for changed behavior
  - tests exist but do not cover the real changed behavior
  - tests cover the happy path but miss failure, edge, or negative paths
  - integration coverage is missing where unit tests are not enough
- Flag tests that do not actually cover the changed behavior.
- Flag missing edge cases, failure-path assertions, and negative-path tests when those paths are relevant.
- Treat "manual testing only" as insufficient for meaningful logic changes unless the ticket explicitly justifies it.

## Security

- Inspect trust boundaries and untrusted input handling.
- Flag unsafe interpolation, injection risks, unsanitized rendering, insecure deserialization, or unsafe URL handling.
- Flag missing authorization or privilege checks.
- Flag sensitive data leaks in logs, responses, telemetry, or client-visible state.
- Flag insecure defaults, weak validation, and hidden assumptions about trusted callers.

## Clean Code

- Enforce single responsibility for methods, classes, and components.
- Allow orchestration functions to coordinate multiple steps, but still flag non-orchestrator units that mix multiple responsibilities.
- Suggest splitting code when one function, class, or component handles more than one clear responsibility.
- Prefer readability over cleverness unless performance clearly requires a denser approach.
- Flag unnecessary ternaries unless they are very simple and genuinely improve clarity.
- Flag functions or methods with more than 2-3 arguments and suggest using an object or struct-like parameter when appropriate.
- Prefer inverted conditionals and early returns when they reduce nesting and improve readability.
- Look for existing repo patterns, helpers, hooks, utilities, reducers, or services that could be reused instead of reimplemented.
- Prefer achieving more with less code when the simpler version preserves clarity and correctness.
- Suggest higher-effort design-pattern or architectural improvements only when they materially improve maintainability.

## Reuse

- Search for existing utilities, hooks, services, reducers, transformers, selectors, components, or helper functions before recommending new abstractions.
- Flag duplicated logic when reuse is likely practical and materially reduces code size or maintenance cost.
- Avoid forcing abstraction when the shared behavior is still too speculative or too small.

## Performance

- Be suspicious of nested loops, repeated linear scans, N+1 requests, unnecessary re-renders, repeated parsing or serialization, excessive temporary allocations, and obvious garbage-collection churn.
- Flag costly work inside hot render paths, tight loops, or repeated request handlers.
- Distinguish between proven bottlenecks and plausible hotspots.
- Ask the user about usage scale only when the answer materially changes whether the code is acceptable. Useful questions include:
  - how often the path runs
  - how many users or requests hit it
  - typical and worst-case data sizes
  - latency or throughput expectations
- Prefer small structural improvements first before suggesting larger rewrites.

## Maintainability

- Prefer designs with a small blast radius for future changes.
- Flag tight coupling between unrelated components, layers, or features unless there is a clear reason it is necessary.
- Flag feature implementations that require scattered edits outside the feature boundary for routine future changes.
- State explicitly when broader coupling is acceptable because the code is intentionally shared or reusable infrastructure.
- Prefer cohesive local abstractions over cross-cutting conditionals spread across the codebase.

## Response Template

For each blocking or important finding, aim for this shape:

1. Title with severity signal.
2. Clickable file reference using an absolute path and line.
3. Short technical paragraph explaining why the current code is risky, incorrect, incomplete, or hard to maintain.
4. Short technical paragraph describing the preferred fix.
5. Small code example only when the suggested patch is short and unambiguous.

After findings, include:

- open questions or clarifications
- a short summary of must-fix items now
- a short summary of follow-up items that deserve a separate ticket
