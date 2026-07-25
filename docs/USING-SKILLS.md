# Using The Skills

This repository publishes portable Agent Skills. The open-source
[`skills` CLI](https://github.com/vercel-labs/skills) discovers every valid
`SKILL.md` in the repository and installs selected skills into a supported
agent's skill directory. `npx` downloads and runs that CLI; this repository
does not implement the installer.

## Requirements

- Node.js with `npx`
- Codex, Claude Code, or another Agent Skills-compatible client
- Any skill-specific requirement shown in its `compatibility` frontmatter

Review third-party skill contents before installation. Skills may instruct an
agent to execute bundled scripts or use external tools.

## Discover And Install

Skill metadata communicates readiness and requirements:

| Status | What to expect |
| --- | --- |
| `public-ready` | Portable without special local configuration |
| `config-required` | Needs the environment or config-path variables named in `compatibility` |
| `local-required` | Needs the local collaborators or capabilities named in `compatibility` |
| `experimental` | Installable, but its behavior is still being refined |

Status does not hide a skill from installation. Inspect `compatibility` and
prefer selecting only the capabilities configured on the target machine.

List the available skills without installing them:

```bash
npx skills add EduardValentin/ai-skills --list
```

Install globally for Codex:

```bash
npx skills add EduardValentin/ai-skills -g -a codex
```

Install globally for Claude Code after confirming the Codex installation:

```bash
npx skills add EduardValentin/ai-skills -g -a claude-code
```

The group folders in `skills/` organize the source repository; they are not
installation bundles. Select one or more skills by name:

```bash
npx skills add EduardValentin/ai-skills \
  -g -a codex \
  --skill ticket-writing \
  --skill feature-work-planning
```

Use `--skill '*'` for a non-interactive all-skills selection. Without
`--skill`, the CLI presents its normal interactive selection flow.

## Update And Remove

Use the installer's standard commands:

```bash
npx skills update -g
npx skills remove <skill-name> -g -a codex
```

See the [`skills` CLI documentation](https://www.skills.sh/docs/cli) for its
current options and supported agents.

## Native Agents

Files under `agents/` are native Codex or Claude agent definitions, not Agent
Skills. They are intentionally delivered separately:

```bash
python3 scripts/sync_native_agents.py push
python3 scripts/sync_native_agents.py check
```

`push` writes each selected definition to both `~/.codex/agents/` and
`~/.claude/agents/`, then adds or updates its generated registration block in
`~/.codex/config.toml`. `check` is read-only and verifies all three locations.
Use command filters when only selected manifest agents should be synchronized.

The repository copy is canonical. Do not edit an installed skill or generated
agent copy because a later install or sync can replace it.

## Diagnose A Codex Install

Maintainers can compare this repository with active Codex skill roots using a
read-only diagnostic:

```bash
scripts/ai-skills check-local-installs --harness codex
```

It reports missing, stale, duplicate, malformed, and attributable extra
repository skills. It never repairs local state. In the contribution workflow,
run it only after pull-request creation has been explicitly approved.

## Next Steps

- Read [Creating skills](CREATING-SKILLS.md) to add or change a skill.
- Read [Evaluation](EVALUATION.md) to understand how skill behavior and pickup
  are assessed.
