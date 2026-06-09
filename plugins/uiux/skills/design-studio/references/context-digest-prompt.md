# Context Digest Prompt

Use this template before design-studio work. The output should be a compact project summary, not a file dump.

Inputs:

- `<project-root>`: absolute path to the project root.
- `<app-root>`: absolute path to the React reference app.
- `<task-summary>`: one-line summary of the current task.

Prompt:

```markdown
Produce a compact context digest for design-studio work.

Inputs:
- Project root: <project-root>
- Reference app root: <app-root>
- Task summary: <task-summary>

Read only what is needed from:
- DESIGN.md
- brand-voice.md
- PRD.md
- theme/global CSS
- component directories
- route registry
- package.json

Return this exact structure:

## Design Tokens
- Colors:
- Spacing:
- Typography:
- Radii:
- Shadows:
- Motion:

## Components
- ComponentName: purpose; variants; notable props.

## Routes
- path -> page; audience/role if implied.

## Brand Voice
- 3 to 5 actionable bullets, or None.

## PRD Slice
- Only requirements, flows, entities, or rules relevant to <task-summary>, or None.

## Visual Signals
- 3 to 5 file-derived bullets about color, spacing, type, density, shape, and motion.

## Dependencies
- Only dependencies that shape UI work.

## Mismatches
- Source disagreements, or None.

## Missing
- Expected missing artifacts, or None.

Rules:
- Keep the whole digest under 1200 tokens.
- Do not include code snippets, full file inventories, or implementation chatter.
- Do not invent missing facts.
```

After the digest, resolve `Missing` and `Mismatches` before changing the design system. Re-run the digest only when source artifacts change or the task scope materially shifts.
