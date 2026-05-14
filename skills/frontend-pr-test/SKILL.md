---
name: frontend-pr-test
description: Use when asked to test or verify a frontend pull request against a ticket, bug report, acceptance criteria, or PR notes
---

# Frontend PR Test

## Overview

Test the user-visible contract. PR notes, ticket criteria, focused tests, and browser evidence must agree before verification.

## Requires

- Ability to inspect repository files, changed files, and available PR or ticket metadata. If private metadata is blocked by authentication, ask the user for the missing details or use an authenticated local interface if one is already available.
- Ability to execute shell commands and start the frontend app as the repository or user specifies.
- Browser acceptance capability. Prefer a native browser or screenshot tool; otherwise use browser automation through the shell. If neither is available, collect commands, routes, and expected checks, then ask the user for visual confirmation.
- Optional read-only subagent support for scoping. If unavailable, perform the same scoping locally before starting browser testing.

## When to Use

Use for frontend PR testing, bug-fix verification, browser acceptance testing, PR review support, and "click around" requests tied to a ticket. Do not use for implementation-only work or QA without a PR/ticket anchor.

## Required Flow

1. Always fetch the latest PR branch and base branch updates before starting test setup, then confirm the local checkout includes the branch state being verified.
2. Read ticket and PR metadata. Prefer authenticated APIs, CLIs, or connectors if web login blocks PR details.
3. Extract PR testing instructions. If present, follow them first and map them to ticket criteria.
4. If PR testing instructions are absent or vague, dispatch a read-only scoping subagent before browser testing. It must inspect the diff, ticket, changed files, UI entry points, setup, data needs, and focused tests. If subagents are unavailable, state that and do the same scoping locally before starting the UI.
5. Start the app exactly as the repo or user specifies, including requested environment flags.
6. Use the browser for acceptance behavior. Stop for manual login if authentication appears.
7. Isolate the scenario: enable only the relevant module, panel, toggle, layer, filter, or mode.
8. If a visual target is hard to hit, screenshot, estimate coordinates or landmarks, then hover/click and verify rendered content.
9. Run focused tests near the changed code, but never substitute passing tests for browser acceptance.
10. Report pass/fail per criterion, commands, data gaps, and server status.

## Quick Reference

| Situation | Required move |
| --- | --- |
| Before testing starts | Fetch latest PR branch and base branch updates |
| PR has explicit testing instructions | Execute them first; cover missed ticket criteria |
| PR has no useful testing instructions | Dispatch scoping subagent before UI testing |
| Login appears | Stop and ask the user to log in manually |
| No obvious data appears | Change minimum filters/date/state to find representative data |
| Target is ambiguous | Screenshot, estimate coordinates, verify output |
| One criterion fails | Report failure; do not polish a "pass" narrative |

## Scoping Subagent Prompt

```text
Read PR metadata, ticket, and changed files only. Do not edit.
Return affected workflows, criteria, UI entry points, setup, data needs,
focused tests, and risks where unit tests may not prove browser behavior.
```

## Evidence Standard

For each criterion, capture reproducible evidence: URL/route, active state, interaction, observed UI text or behavior, and focused test output. If partial, name the unverified criterion.

## Common Mistakes

| Mistake | Fix |
| --- | --- |
| "Unit tests passed" | Still perform browser acceptance |
| "No PR instructions" | Scope from diff and ticket with a subagent |
| "Nothing to hover/click" | Adjust minimal state to find representative data |
| "Several features were open" | Reduce to the smallest scenario |
| "Happy path passed" | Cover each ticket variant |
