---
name: frontend-pr-test
description: Use when asked to test or verify a frontend pull request against a ticket, bug report, acceptance criteria, PR notes, or blocked PR metadata
---

# Frontend PR Test

## Overview

Test the user-visible contract. PR notes, ticket criteria, focused tests, and browser evidence must agree before verification.

**Core principle:** Blocked metadata is not absent metadata. If PR or ticket details cannot be read, stop and resolve that gap before inferring from the diff.

## Requires

- Ability to inspect repository files, changed files, and available PR or ticket metadata. If private metadata is blocked by authentication, an unavailable PR host capability, network failure, missing CLI, or unavailable connector, treat that as a blocker: ask the user to restore access, provide the missing PR/ticket details, or point to an authenticated local interface.
- Ability to execute shell commands and start the frontend app as the repository or user specifies.
- Browser acceptance capability. Prefer a native browser or screenshot tool; otherwise use browser automation through the shell. If neither is available, collect commands, routes, and expected checks, then ask the user for visual confirmation.
- Optional read-only subagent support for scoping. If unavailable, perform the same scoping locally after metadata is available.

## When to Use

Use for frontend PR testing, bug-fix verification, browser acceptance testing, PR review support, and "click around" requests tied to a ticket. Do not use for implementation-only work or QA without a PR/ticket anchor.

## Required Flow

1. Always fetch the latest PR branch and base branch updates before starting test setup, then confirm the local checkout includes the branch state being verified.
2. Inspect ticket and PR metadata before diff-derived scoping or browser testing. Prefer authenticated APIs, CLIs, or connectors if web login blocks PR details.
3. If PR or ticket metadata cannot be read, stop before browser testing and explain the blocker. Ask the user to fix access, provide the PR notes/testing instructions, or identify an authenticated local source. Do not infer PR testing instructions from the diff as a substitute.
4. Extract PR testing instructions. If present, follow them first and map them to ticket criteria.
5. If metadata was read successfully and PR testing instructions are absent or vague, dispatch a read-only scoping subagent before browser testing. It must inspect the diff, ticket, changed files, UI entry points, setup, data needs, and focused tests. If subagents are unavailable, state that and do the same scoping locally before starting the UI.
6. Start the app exactly as the repo or user specifies, including requested environment flags.
7. Use the browser for acceptance behavior. Stop for manual login if authentication appears.
8. Isolate the scenario: enable only the relevant module, panel, toggle, layer, filter, or mode.
9. If a visual target is hard to hit, screenshot, estimate coordinates or landmarks, then hover/click and verify rendered content.
10. Run focused tests near the changed code, but never substitute passing tests for browser acceptance.
11. Report pass/fail per criterion, commands, data gaps, and server status.

## Quick Reference

| Situation | Required move |
| --- | --- |
| Before testing starts | Fetch latest PR branch and base branch updates |
| PR host metadata is blocked or unavailable | Stop; ask for access, PR notes, or an authenticated local source |
| PR metadata was read and has explicit testing instructions | Execute them first; cover missed ticket criteria |
| PR metadata was read but has no useful testing instructions | Scope from diff and ticket before UI testing |
| User supplies missing PR notes in chat | Proceed from those notes and report the metadata source |
| Login appears in the app | Stop and ask the user to log in manually |
| No obvious data appears | Change minimum filters/date/state to find representative data |
| Target is ambiguous | Screenshot, estimate coordinates, verify output |
| One criterion fails | Report failure; do not polish a "pass" narrative |

## Scoping Subagent Prompt

```text
Inspect available PR metadata, ticket, and changed files only. Do not edit.
Return affected workflows, criteria, UI entry points, setup, data needs,
focused tests, and risks where unit tests may not prove browser behavior.
If PR or ticket metadata is blocked, stop and report the missing source.
```

## Evidence Standard

For each criterion, capture reproducible evidence: URL/route, active state, interaction, observed UI text or behavior, and focused test output. If partial, name the unverified criterion.

## Red Flags

- "Bitbucket/GitHub/GitLab is unavailable, so I will infer from the diff"
- "The diff is clear enough to replace PR notes"
- "I can proceed best-effort and mention metadata was blocked later"
- "Ticket details are available, so PR metadata is optional"

All of these mean stop before browser testing and resolve the metadata gap.

## Common Mistakes

| Mistake | Fix |
| --- | --- |
| "PR host unavailable" | Stop; blocked metadata is not absent metadata |
| "No PR instructions" | Say this only after PR metadata was actually read |
| "Unit tests passed" | Still perform browser acceptance |
| "Diff is clear enough" | Use the diff for risks only after metadata is available |
| "Nothing to hover/click" | Adjust minimal state to find representative data |
| "Several features were open" | Reduce to the smallest scenario |
| "Happy path passed" | Cover each ticket variant |
