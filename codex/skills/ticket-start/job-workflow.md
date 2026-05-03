# Job Workflow

Use when the ticket comes from Jira or is pasted by the user. Loaded by `SKILL.md` during the Setup phase. Return to `SKILL.md` for phase ordering, standards, and closeout.

## Ticket Intake

1. Require the full ticket title and full description before starting. The description must include acceptance criteria and any implementation context the user has. If any of these are missing, stop and ask.
2. Do not accept a partial summary when the full title or description is required to implement safely. Stale or excerpted retellings are not current truth.
3. Extract and restate:
   - acceptance criteria
   - constraints
   - explicit context the user provided
   - non-goals, if present
   - open ambiguities that could change the implementation

## Clarifications

- Ask concise clarifying questions whenever the ticket leaves material ambiguity. Prefer a short focused set over broad brainstorming.
- If acceptance criteria are missing, vague, or not testable, stop and ask before continuing.
- If the ticket conflicts with repository instructions or existing architecture, surface the conflict before implementation.

## Architecture Research

Gather only the minimum code context needed to understand the current architecture and the implementation path. Prefer:

- the entry point or feature boot path
- the target module or component
- nearby reducers, services, fetchers, transformers, hooks, tests, or shared utilities that define the current pattern
- existing implementations of similar behavior in the repo

Reuse existing project patterns before inventing new abstractions. Aim for the smallest safe diff that satisfies the ticket cleanly.

## Hand-off To Brainstorm

When the ticket is concrete enough and the architecture findings are gathered, return to `SKILL.md` and proceed to the Brainstorm gate (`superpowers:brainstorming`).
