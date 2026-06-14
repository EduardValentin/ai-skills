# AI Skills

This repository tracks the canonical source for personal AI skills and reusable native agents used across Codex and Claude Code on this machine.

## Layout

- `skills/` contains canonical cross-agent skills.
- `agents/` contains canonical reusable specialized agents plus `manifest.toml`.
- `scripts/sync_skill.py` syncs skills into `/Users/trocaneduard/.codex/skills/` and `/Users/trocaneduard/.claude/skills/`.
- `scripts/sync_native_agents.py` generates native Codex and Claude Code agent definitions into `/Users/trocaneduard/.codex/agents/` and `/Users/trocaneduard/.claude/agents/`.
- `plugins/` contains plugin-packaged skill bundles and harness metadata.

## Purpose

Use this repository as the tracked source for your personal AI skills and specialized agents while keeping the installed global copies aligned with any changes made here.

Specialized agents are first-class reusable assets. Skills may request agents by name, but agents are not owned by a single skill.

## Native Agents

Native agents live in `agents/*.md` with delivery metadata in `agents/manifest.toml`.

Current reusable agents:

- `code-mapper` preloads `codebase-scope-map` for read-only locator-backed code maps.
- `implementation-worker` preloads `implement-unit-of-work` for approved implementation slices.
- `code-reviewer` reviews finished diffs against approved requirements and engineering quality.
- `security-reviewer` reviews diffs with plausible trust-boundary, auth, input, dependency, or data-exposure risk.
- `qa-verifier` preloads `qa-verification` for behavior verification against running surfaces.
- `uiux-verifier` preloads `ui-verification` for visual and accessibility verification.
- `ticket-execution-coordinator` preloads `coordinate-ticket-execution` for approved per-ticket execution packets, mainly from multi-ticket work.

`groups` in `agents/manifest.toml` are sync groups, not ownership boundaries. If an agent wraps or depends on a skill, include that skill name as a group so `python3 scripts/sync_skill.py push <skill-name>` also refreshes the native wrapper. `preload_skills` declares which skill is installed into the generated native agent.

Useful commands:

```bash
python3 scripts/sync_skill.py push <skill-name>
python3 scripts/sync_native_agents.py push --group <group-name>
python3 scripts/sync_native_agents.py check --group <group-name>
```

## Testing

The test stack has three layers.

### Deterministic Contracts

Run deterministic repo contracts with:

```bash
python3 tests/contract.py
python3 tests/contract_harness_contract.py
python3 tests/skill-trigger/static_contract.py
python3 tests/workflow-dispatch/workflow_harness_contract.py
```

Run deterministic sync tests with:

```bash
python3 scripts/test_sync_skill.py
python3 scripts/test_sync_native_agents.py
```

### Sync Rendering Tests

Sync tests verify that canonical repository files render into the expected
Codex and Claude Code install shapes without hand-maintained harness copies.

### Model-Backed Behavioral Tests

Behavioral tests are opt-in because they run an installed agent harness. Set one generic command that reads the prompt from stdin and prints the response:

```bash
SKILL_TRIGGER_AGENT_COMMAND='python3 tests/codex_agent_command.py' \
  python3 tests/behavioral_pressure.py

SKILL_TRIGGER_AGENT_COMMAND='python3 tests/codex_agent_command.py' \
  python3 tests/skill-trigger/behavioral_pressure.py

# Run this only when a skill has a colocated tests/workflow-dispatch.toml suite.
SKILL_TRIGGER_AGENT_COMMAND='python3 tests/codex_agent_command.py' \
  python3 tests/workflow-dispatch/behavioral_dispatch.py
```

All agent-driven behavioral suites use `SKILL_TRIGGER_AGENT_COMMAND`; suite
TOML files do not define separate command variables.

`tests/contract.py` discovers TOML contract suites colocated under
`skills/*/tests/contracts.toml`, `plugins/*/tests/contracts.toml`, and
repo-wide `tests/contracts/*.toml` files.

`tests/behavioral_pressure.py` discovers colocated
`skills/*/tests/behavioral.toml` and `plugins/*/skills/*/tests/behavioral.toml`
files, then runs each suite through the shared loaded-skill harness. Use
`--skill <skill-name>` or `--scenario <scenario-id>` for focused runs.
Actor-facing behavioral prompts must stay neutral: they may set safety
boundaries and scenario facts, but expected workflow behavior belongs in
criteria, judge context, or deterministic assertions.

`skill-trigger` behavioral tests are black-box installed-harness tests: they do
not inject skill bodies or available-skill indexes, and they fail when the target
harness cannot discover the expected skill.

`workflow-dispatch` behavioral tests are loaded-parent-skill pressure tests for
skills whose core behavior is choosing another skill route. Prefer colocated
`skills/<skill-name>/tests/behavioral.toml` coverage for ordinary workflow
behavior. Add workflow-dispatch suites only when route selection itself is the
behavior under test.

Behavioral pressure tests use deterministic hard gates for protocol and
forbidden terms, then use a semantic judge for rubric-based behavior checks. The
same `SKILL_TRIGGER_AGENT_COMMAND` is used for the scenario response and judge
unless a developer intentionally runs a separate judge override during local
debugging.

The bundled `tests/codex_agent_command.py` shim runs `codex exec` with efficient
defaults: `gpt-5.4-mini` and `low` reasoning. Override `CODEX_ACTOR_MODEL`,
`CODEX_ACTOR_REASONING_EFFORT`, `CODEX_TEST_MODEL`, or
`CODEX_TEST_REASONING_EFFORT` only when a scenario genuinely needs a heavier
model.
