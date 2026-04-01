---
name: ticket-start
description: Start implementation work from a software ticket with a plan-first workflow. Use when the user wants to begin building a feature or fix from a ticket, especially when they say phrases such as "start ticket". Require the full ticket title and full ticket description before proceeding. Ask for missing acceptance criteria or implementation context, gather the minimum relevant repo context, research version-specific third-party documentation when needed, produce an implementation plan, and wait for explicit approval before making code changes. Do not use for code review, pure planning, or debugging-only tasks.
---

# Ticket Start

## Workflow

1. Confirm that the request is implementation work driven by a ticket. If the task is review, planning-only, or debugging-only, do not use this skill.
2. Require the full ticket title and the full ticket description before starting. The description must include acceptance criteria and any implementation context the user has. If any of these are missing, stop and ask for the missing details.
3. Extract and restate the important requirements:
   - acceptance criteria
   - constraints
   - explicit context
   - non-goals, if present
   - open ambiguities that could change the implementation
4. Ask concise clarifying questions before doing code changes whenever the ticket leaves material ambiguity. Prefer a short focused set of questions over broad brainstorming.
5. Read and follow repository-local instructions first. Start with the nearest applicable `AGENTS.md`, then load only the additional instruction files and project docs that materially affect the task.
6. Gather only the minimum code context needed to understand the current architecture and implementation path. Prefer:
   - the entry points or feature boot path
   - the target module or component
   - nearby reducers, services, fetchers, transformers, hooks, tests, or shared utilities that define the current pattern
   - existing implementations of similar behavior in the repo
7. Reuse existing project patterns before inventing new abstractions. Aim for the smallest safe diff that satisfies the ticket cleanly.
8. If the implementation touches a third-party library, identify the exact version used by the project from manifests or lockfiles, then read the official or primary documentation for that version before editing code that depends on it.
9. After ticket review, clarification, repo-instruction review, and code research, switch into a plan-first handoff:
   - summarize the current understanding
   - outline the proposed implementation steps
   - call out risks, assumptions, and test strategy
   - wait for explicit user approval before making any file edits or code changes
10. After approval, implement the plan, keep the diff minimal, and preserve or improve code quality.
11. After changes, run the relevant validation available in the project:
   - unit tests
   - integration tests, when applicable
   - lint or static checks, when present
12. If validation cannot be run, say exactly what could not be run and why.

## Ticket Requirements

- Treat the ticket as the source of truth for scope.
- Do not accept a partial summary when the full ticket title or full description is required to implement safely.
- If acceptance criteria are missing, vague, or not testable, stop and ask for clarification.
- If the ticket conflicts with repository instructions or existing architecture constraints, surface the conflict before implementation.

## Research Rules

- Read broadly enough to understand the architecture, but keep context disciplined.
- Prefer targeted file discovery with existing repo patterns over large exploratory sweeps.
- Favor primary sources for library and framework behavior.
- Use internet research only when needed for unstable or version-sensitive information, especially third-party libraries, APIs, framework behavior, or current guidance.

## Planning Gate

- Do not start coding immediately after reading the ticket.
- Produce an implementation plan only after:
  - the ticket details are complete enough
  - clarifying questions have been answered
  - the relevant repo instructions have been read
  - the minimum necessary architecture research is done
- Treat this plan as a hard approval gate.
- Wait for an explicit user message approving the plan before making code changes.

## Implementation Standards

- Keep code readable, maintainable, and easy to reason about.
- Preserve or improve the repository's code quality standard. Do not degrade it to ship faster.
- Prefer simple, efficient solutions with clear control flow and low blast radius.
- Keep functions, modules, and components focused on a single responsibility.
- Preserve existing architecture unless the ticket truly requires change.
- Prefer small composable changes over cross-cutting rewrites.
- Consider performance as part of the solution, especially on hot paths, repeated work, unnecessary rendering, or avoidable network and memory cost.

## Validation And Closeout

- Run the smallest meaningful validation set that proves the change works and does not obviously regress quality.
- Prefer targeted tests first, then broader lint or test suites as appropriate for the repo.
- Report:
  - what was changed
  - what was validated
  - any remaining risk, assumption, or follow-up worth noting
