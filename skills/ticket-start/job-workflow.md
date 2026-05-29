# Job Workflow

Use when the ticket comes from Jira or is pasted by the user. Loaded by `SKILL.md` once when the job workflow is selected. The Ticket Intake section applies during Setup. The Verification section is delegated to the QA and UI/UX subagents; this file specifies the review modes they receive in the job workflow. Return to `SKILL.md` for phase ordering, dispatch points, standards, verification fix loops, and Ship.

## Ticket Intake

Two intake paths, in priority order:

### 1. Atlassian CLI (preferred)

If the user provides a Jira issue key (e.g., `PROJ-1234`):

1. Detect availability:
   ```bash
   command -v acli && acli --version
   ```
   If both succeed, proceed.

2. Fetch the ticket:
   ```bash
   acli jira workitem view <KEY> --json
   ```
   Parse the returned JSON to extract title, description, acceptance criteria, comments, labels, priority, issue type, status, parent/subtasks.

3. If `acli` errors (auth failure, network, invalid key, missing permissions), surface the error verbatim and fall back to manual paste (path 2). Do not silently retry or guess.

### 2. Manual paste (fallback)

If `acli` is not on PATH, errors out, or the user is pasting a ticket directly:

1. Require the **full** ticket title and full description before starting. The description must include acceptance criteria and any implementation context the user has. If any of these are missing, stop and ask.
2. Do not accept a partial summary when the full title or description is required to implement safely. Stale or excerpted retellings are not current truth.

### Restate (both paths)

After intake, extract and restate to the user:

- acceptance criteria
- constraints
- explicit context the user provided
- non-goals, if present
- open ambiguities that could change the implementation

Then proceed to Scoping subagent dispatch as instructed by `SKILL.md`'s Setup phase.

## Verification — Mode Mapping For QA And UI/UX

The Verify phase is run by the QA and UI/UX subagents. This file specifies the review mode they receive in the job workflow.

### QA mode

Determined from the diff (main agent decides):

- **`backend`** — diff touches only backend / API / service files. QA runs Mode A (start the affected service, issue real requests against changed endpoints, inspect persisted state and logs against AC).
- **`ui`** — diff touches only user-facing app files. QA runs Mode B (start the dev server, drive every state via the live Playwright browser session against AC).
- **`mixed`** — diff touches both. QA runs Mode C (Mode A and Mode B both must be clean).

If the app or service cannot be started, QA escalates and the workflow stops on the user-intervention principle. Do not declare verified.

### UI/UX mode

For the job workflow, the UI/UX subagent always runs in **`consistency` mode**:

- No external reference (job apps in this workflow do not have a React reference app in `designs/`).
- Mandate is stylistic consistency against existing analog elements in the same view: icon sizing rhythm, typography scale, spacing rhythm, color tokens, border radii, shadow elevation, alignment.
- Programmatic-first: extract computed styles and bounding rects via DOM evaluation against the live browser. Screenshots are only supplementary context.
- Accessibility checks always apply.

UI/UX is **skipped** if main agent determines the change is backend-only (no UI files in the diff) per `SKILL.md`'s backend-only detection.

## Hand-off to Requirements/Design

When ticket intake and the Scoping subagent's report are both complete, return to `SKILL.md` and proceed to Requirements/Design. This file is no longer relevant until the Verify phase.
