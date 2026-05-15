# AI Skills

This repository mirrors the current global skill folders for both Codex and Claude on this machine.

## Layout

- `codex/skills/` mirrors `/Users/trocaneduard/.codex/skills/`
- `claude/skills/` mirrors `/Users/trocaneduard/.claude/skills/`

## Purpose

Use this repository as the tracked source for your personal AI skills while keeping the installed global copies aligned with any changes made here.

## Testing

Run deterministic skill-trigger contracts with:

```bash
bash tests/skill-trigger/static-contract.sh
```

Behavioral trigger pressure tests are opt-in because they require an agent command:

```bash
SKILL_TRIGGER_AGENT_COMMAND='<command reading stdin>' \
  bash tests/skill-trigger/behavioral-pressure.sh
```
