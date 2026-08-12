---
name: writing-tests
description: >-
  Use when writing, configuring, or maintaining backend or frontend tests, or
  choosing between unit, integration, and end-to-end coverage.
metadata:
  status: experimental
  allows_tool_references: "false"
---

# Writing Tests

## Overview

Tests follow the pyramid: many unit tests covering the edge cases of a unit,
fewer integration tests covering the crucial flows against real infrastructure,
fewest end-to-end tests covering only the most crucial business flows.

Test what the application is expected to do now — never the shape it used to
have.

## Before Writing A Test

1. Decide which layer the behavior belongs to.
2. For integration or end-to-end, first determine whether the project is already
   set up for that type — existing suites, containers, runner configuration, run
   scripts.
3. If that setup does not exist, **stop and ask before scaffolding it.**
4. If the project already has a pattern for that type, follow it rather than
   inventing one.

## Quick Reference

| | Unit | Integration | End-to-end |
|---|---|---|---|
| Volume | many | fewer | fewest |
| Mocks | external dependencies | none | none |
| Act through | the unit's public surface | an application entry point | the deployed application |
| Assert | returned values and interactions | real persisted state | real persisted state |

## Rules For Every Test

- **One scenario per test.** Several scenarios in one case hide which behavior
  broke and make the test hard to read and evolve.
- **Arrange, Act, Assert.** Expectations live only in Assert, never in Arrange
  or Act.
- Extract duplicated Arrange code into shared test utilities.
- Never test an intermediate migration state — for example, never assert a file
  is gone from its old folder after a restructure.
- Never test for the absence of something that no longer exists as a concept,
  such as a removed argument.
- Never use the CI pipeline to validate a concern the application should
  validate.
- No flakiness. Synchronous code has no excuse for it; genuinely asynchronous
  behavior gets a sensible timeout.

## Unit Tests

Cover the flows and edge cases of the implemented feature comprehensively, with
external dependencies mocked.

The code under test must **receive** its dependencies. Global state that is hard
to mock is an architecture failure — flag it instead of working around it in the
test. Typical cases: reading a file straight from a path or file pointer instead
of receiving the file or a reader; using the global clock instead of an injected
clock.

## Integration Tests

Start the real application container and run against it, with its dependencies
really deployed. No mocks, and no plumbing that risks deviating from the
deployed application.

Act only through an entry point — an API endpoint, a websocket, an asynchronous
listener. Never write an integration test against an intermediate component such
as a repository or a service; the flow started at the entry point covers those.
Assert the resulting persisted state, such as rows in the real database.

If the project runs its integration infrastructure with Testcontainers, read
`references/testcontainers.md` before writing or changing the setup. Skip that
file entirely for any other integration setup.

## End-To-End Tests

The most crucial business flows only. Same Arrange-Act-Assert structure, one
scenario per case, with as much setup as possible in reusable utilities.

## Frontend Tests

Two categories, kept in separate files named by the project's existing
convention:

- **Unit** — JavaScript functions and presentational components in isolation.
- **Frontend integration** — the composition of multiple components, where Act
  dispatches flows with side effects across the application, including API
  requests.

Mock API requests made by components under test with a request-interception
layer such as Mock Service Worker.

## Rationalizations

| Excuse | Reality |
|---|---|
| "I'll cover both cases in one test" | One scenario per test. Merged cases hide which behavior broke. |
| "The global clock/file read is fine, I'll just patch it" | Patching global state hides an architecture failure. Flag it. |
| "A quick mock keeps the integration test simple" | A mocked integration test proves nothing about the deployed application. |
| "I'll test the repository directly, it's the same flow" | It is not. Act through an entry point. |
| "There's no integration setup, I'll add one quickly" | Scaffolding a test type is a decision for the owner. Ask first. |
| "A short sleep fixes the failing assertion" | That is manufactured flakiness. Fix the wait or the sync assumption. |
| "Let me assert the old code path is gone" | Removed concepts are not testable behavior. |
