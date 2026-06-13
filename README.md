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
python3 tests/contract.py
python3 tests/skill-trigger/static_contract.py
python3 tests/workflow-dispatch/static_contract.py
```

Behavioral/model-backed tests are opt-in because they require an agent command:

```bash
BEHAVIORAL_AGENT_COMMAND='python3 tests/codex_agent_command.py --role actor' \
SEMANTIC_JUDGE_AGENT_COMMAND='python3 tests/codex_agent_command.py --role judge' \
  python3 tests/behavioral_pressure.py

SKILL_TRIGGER_AGENT_COMMAND='python3 tests/codex_agent_command.py --role actor' \
SEMANTIC_JUDGE_AGENT_COMMAND='python3 tests/codex_agent_command.py --role judge' \
  python3 tests/skill-trigger/behavioral_pressure.py

WORKFLOW_DISPATCH_AGENT_COMMAND='python3 tests/codex_agent_command.py --role actor' \
SEMANTIC_JUDGE_AGENT_COMMAND='python3 tests/codex_agent_command.py --role judge' \
  python3 tests/workflow-dispatch/behavioral_dispatch.py
```

`tests/contract.py` discovers TOML contract suites colocated under
`skills/*/tests/contracts.toml`, `plugins/*/tests/contracts.toml`, and
repo-wide `tests/contracts/*.toml` files.

`tests/behavioral_pressure.py` discovers colocated
`skills/*/tests/behavioral.toml` and `plugins/*/skills/*/tests/behavioral.toml`
files, then runs each suite through the shared loaded-skill harness. Use
`--skill <skill-name>` or `--scenario <scenario-id>` for focused runs.

`skill-trigger` behavioral tests are black-box installed-harness tests: they do
not inject skill bodies or available-skill indexes, and they fail when the target
harness cannot discover the expected skill. `workflow-dispatch` behavioral tests
are loaded-parent-skill pressure tests; their downstream discovery checks also
call the installed harness without injecting a skill index.

Behavioral pressure tests use deterministic hard gates for protocol and
forbidden terms, then use a semantic judge for rubric-based behavior checks. Set
`SEMANTIC_JUDGE_AGENT_COMMAND` to use a separate judge; otherwise tests fall back
to the scenario's agent command.

The bundled `tests/codex_agent_command.py` shim runs `codex exec` with efficient
defaults: `gpt-5.4-mini` and `low` reasoning. Override `CODEX_ACTOR_MODEL`,
`CODEX_JUDGE_MODEL`, `CODEX_ACTOR_REASONING_EFFORT`, or
`CODEX_JUDGE_REASONING_EFFORT` only when a scenario genuinely needs a heavier
model.
