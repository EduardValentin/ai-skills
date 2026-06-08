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
python3 tests/skill-trigger/static_contract.py
python3 tests/workflow-dispatch/static_contract.py
```

Behavioral/model-backed tests are opt-in because they require an agent command:

```bash
SKILL_TRIGGER_AGENT_COMMAND='<command reading stdin>' \
  python3 tests/skill-trigger/behavioral_pressure.py

WORKFLOW_DISPATCH_AGENT_COMMAND='<command reading stdin>' \
  python3 tests/workflow-dispatch/behavioral_dispatch.py
```

`skill-trigger` behavioral tests are black-box installed-harness tests: they do
not inject skill bodies or available-skill indexes, and they fail when the target
harness cannot discover the expected skill. `workflow-dispatch` behavioral tests
are loaded-parent-skill pressure tests; their downstream discovery checks also
call the installed harness without injecting a skill index.
