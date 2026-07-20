# AI Skills

Portable [Agent Skills](https://agentskills.io/) and reusable native agents for
Codex and Claude Code. Skills are organized by group under `skills/`; canonical
native-agent prompts and delivery metadata live under `agents/`.

## Install

List the available skills, then install all or select individual skills for
Codex:

```bash
npx skills add EduardValentin/ai-skills --list
npx skills add EduardValentin/ai-skills -g -a codex
```

After confirming the Codex installation, install the desired skills for Claude
Code separately:

```bash
npx skills add EduardValentin/ai-skills -g -a claude-code
```

Use `--skill <name>` one or more times to make a non-interactive selection, or
`--skill '*'` to select every skill.

Update or remove global installs with the standard CLI:

```bash
npx skills update -g
npx skills remove <skill-name> -g -a codex
```

## Native Agents

Native agents are delivered separately from public skills:

```bash
python3 scripts/sync_native_agents.py push
python3 scripts/sync_native_agents.py check
```

## Validate

Run the deterministic repository gate with:

```bash
python3 scripts/ai_skills.py validate ci-all
```

See the [documentation index](docs/INDEX.md), [skill specification](docs/SPEC.md),
and [testing guide](docs/TESTING.md) for repository policy and opt-in evaluation
commands.
