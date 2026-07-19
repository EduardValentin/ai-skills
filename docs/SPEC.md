# Repository Skill Specification

Every installable skill follows the public
[Agent Skills specification](https://agentskills.io/specification) and the
additional repository rules below.

## Layout

Skills live at `skills/<group>/<skill>/SKILL.md`. A skill root may contain only
`SKILL.md`, `scripts/`, `references/`, `assets/`, and `evals/`. Keep executable
code and configuration helpers needed at runtime inside the skill. Do not add
installed copies, generated distributions, empty directories, or test-only
infrastructure to a skill.

## Skill Contract

- Use specification-compliant YAML frontmatter and a portable Markdown body.
- Use clean skill-relative paths; links and symlinks must remain inside the
  skill root.
- Set `metadata.allows_tool_references: "true"` when instructions mention a
  tool, harness, native agent, or another skill.
- Describe required collaborators, fallbacks, environment variables, and
  config-file path variables in `compatibility`.
- Avoid personal paths, private sessions, and credential literals. Authored
  fake credential values begin with `FAKE_`.

## Evaluation Contract

Every skill includes `evals/evals.json` and `evals/triggers.json`. Behavior
cases assess the work produced with and without the skill. Trigger cases assess
selection without preloading the target skill body into the prompt. Fixtures
are optional and belong under `evals/fixtures/<eval-id>/` only when a case needs
them.

The schemas and validation commands are documented in [Testing](TESTING.md).
Do not create additional skill-specific test artifacts. Non-trivial bundled
scripts may instead have deterministic repository tests under `tests/runtime/`.

## Validation

Run the deterministic repository gate with:

```bash
python3 scripts/ai_skills.py validate ci-all
```

Model-backed behavior and trigger runs are separate, opt-in operations and
require explicit user approval.
