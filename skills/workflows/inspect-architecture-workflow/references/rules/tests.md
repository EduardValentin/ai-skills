# Tests as a component

The rules that treat tests as part of the architecture (R34 to R37): tests are the outermost
component, reach business rules through a testing API, are organized by behavior, and are designed
to falsify. Read this file when a review or audit touches test code, a testing API, a test-only
power in production code, or a plan's verification approach.

## Rules

### R34. Tests are the outermost component

**Tests are the outermost component: they depend inward, nothing depends on them, and they never
ship to production.** The suite imports what it verifies; no production unit imports a test,
fixture, test double, or test helper. Every kind of test, from developer tests to acceptance
suites, follows the same dependency rules. Tests build and run as their own unit, and the
production deployable carries no test code or test-only endpoints; in a repository holding several
packages, a separate package or an enforced folder excluded from the production artifact is
enough. Test-only powers (bypass security, force state, skip expensive resources) sit in a
separate testing component the production composition root never imports, not behind a flag or
environment check in production code. Tests that use those powers bypass authorization, so a small
separate set exercises the security adapters.

Check questions:
- Does any production unit import a test path?
- Does the production artifact contain test routes or a test-mode flag?
- Is authorization covered by tests that do not use the bypass?

Examples:
- Bad: `if (process.env.TEST_MODE) skipAuth()` in the production authorization adapter.
- Good: a `testing-api` package depends on the use cases' ports and is imported only by the test
  component and the test environment's composition root.

Not a finding when: `test-code-in-production-deployable`: the test-only code lives in a separate testing component that the production composition root never imports and the production artifact excludes, even though it sits in the same repository.

### R35. Test through a testing API

**Verify business rules through a testing API, never through volatile surfaces.** Screens,
navigation, login flows, and vendor paths are volatile. A suite that reaches rules through them
breaks on every small change and makes the system rigid, because developers stop changing it.
Provide one surface exposing every use case the UI can reach, with the same request and response
models, plus test-only powers: act as any role without a credential flow, short-circuit expensive
resources such as stores and vendors, and force a chosen state in one call instead of replaying a
workflow. That surface is an entry point of the test deployment, not an intermediate component. UI
end-to-end tests stay few and assert the UI itself, not business outcomes. Wide breakage from a
small change is an architecture defect, not test maintenance.

Check questions:
- For each business-rule assertion, what does the test pass through to reach the rule?
- Can a test reach its starting state in one call?
- After the recent UI or structural changes, how many tests changed while the asserted behavior did
  not?

Examples:
```ts
// bad: rule reached through login and navigation
await page.goto("/login"); await login(page); await page.click("#loans"); await page.click("#new");
expect(await page.textContent("#interest")).toBe("12.50");
// good: rule reached through the testing API
const r = await testApi.applyInterest({ loanId: seeded.loanId });
expect(r.interest).toBe("12.50");
```

Not a finding when: `rule-tested-through-volatile-surface`: the test asserts the screen itself, such as layout, navigation, or a widget's state, rather than a business outcome; `no-testing-api`: the code has no business rules beyond passing data between a screen and a store.

### R36. Organize tests by behavior

**Organize tests by behavior, so tests and production evolve independently.** A test class per
production class and a test method per method is structural coupling: renames, splits, and merges
force test changes with no behavior change. The unit under test is a behavior reached through its
public surface or the testing API. Over time tests grow more concrete and specific while
production grows more abstract and general; the test boundary lets production internals be
refactored without touching tests, and tests be consolidated without touching production.

Check questions:
- Does the test tree mirror the production tree file for file?
- Would extracting or merging a production class force tests to move?
- After the recent internal refactors, did tests change? After the last cleanup of the suite, did
  production change?

Examples:
- Bad: `InterestCalculator.test.ts` asserts `monthlyRate()` and `compound()` separately.
- Good: `loan-interest.test.ts` asserts `applyInterest` outcomes, so the class split is invisible,
  and a cleanup collapses many scenario tests into one data-driven table with no production edits.

Not a finding when: a test file shares a production file's name but asserts behavior through the public surface or the testing API.

### R37. Tests falsify, they do not prove

Guidance: advisory by default. Reported to the reviewers who own it.

**Tests falsify, they do not prove: design them into the plan.** A green suite means no test found
a defect. Each test targets a concrete way the code could be wrong, and the plan states, per
behavior, which defect the test catches and through which surface. Never write "tests pass,
therefore correct". A test that broke because structure changed while behavior did not falsified
nothing: count it as structural coupling. A humble unit that is hard to test is no evidence of
correctness either; keeping it thin limits what can go wrong in it. Tests not designed into the
system turn fragile, get discarded, and take their regression protection with them.

Check questions:
- Does each test name the wrong behavior it would catch?
- Does the plan name the verification surface per behavior?
- Does the review ask what the tests are coupled to?

Examples:
- Bad: `expect(sort([])).toEqual([])` as the only test, then "sort is verified".
- Good: "a 10-hour day pays 9 regular hours (catches the old cap); the report still counts 8
  (catches a shared helper); the use case runs against an in-memory store (catches a
  policy-to-detail import)."

Not a finding when: `tests-falsify-nothing`: a report mentions passing tests alongside evidence of which defect each test would catch; `plan-names-no-falsifying-tests`: the plan names the defect and the surface per behavior in each test's description rather than in a separate section.

## Conditions

| Id | Condition | Rule | Decided by | Severity | Defect |
|---|---|---|---|---|---|
| `production-imports-test` | A unit that is not a test depends on a test unit. | R34 | check | blocker | `production-depends-on-test` |
| `test-power-behind-flag` | Production code holds a test-only power behind a runtime flag or an environment check. | R34 | judgment | blocker | `production-depends-on-test` |
| `test-code-in-production-deployable` | Test-only routes or fixtures are included in the production deployable. | R34 | judgment | blocker | `production-depends-on-test` |
| `security-bypass-untested` | Tests use a security bypass and no separate tests cover authorization. | R34 | judgment | blocker | `security-bypass-untested` |
| `rule-tested-through-volatile-surface` | A business-rule assertion is reached through a screen, navigation, login, or vendor path. | R35 | judgment | blocker | `rule-tested-through-volatile-surface` |
| `no-testing-api` | Business rules exist and tests have no testing API or direct use-case boundary to reach them. | R35 | judgment | blocker | `no-testing-api` |
| `tests-mirror-production` | The test tree mirrors the production tree class for class, and internal refactors within {historyWindow} changed tests. | R36 | judgment | major | `tests-coupled-to-structure` |
| `tests-falsify-nothing` | Tests assert nothing a specific defect would falsify, or a report claims correctness because the tests pass. | R37 | judgment | minor | `tests-falsify-nothing` |
| `plan-names-no-falsifying-tests` | The plan does not name, per behavior, the defect its test would catch and the surface it runs through. | R37 | judgment | minor | `tests-falsify-nothing` |
