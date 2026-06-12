# Skill Trigger Tests

This directory keeps global trigger coverage for canonical skills under `skills/`
and plugin-packaged skills under `plugins/*/skills/`.

## Static Contract

Run in CI:

```bash
python3 tests/skill-trigger/static_contract.py
```

The static contract is deterministic. It verifies:

- every `skills/*/SKILL.md` and `plugins/*/skills/*/SKILL.md` has at least one trigger scenario;
- every scenario references an existing skill;
- the declared skill name matches its folder;
- descriptions start with `Use when`;
- forbidden stale wording is absent.

## Installed-Harness Behavioral Trigger

Run manually, nightly, or in a model-enabled CI job:

```bash
SKILL_TRIGGER_AGENT_COMMAND='python3 tests/codex_agent_command.py --role actor' \
SEMANTIC_JUDGE_AGENT_COMMAND='python3 tests/codex_agent_command.py --role judge' \
  python3 tests/skill-trigger/behavioral_pressure.py
```

The behavioral harness is a black-box installed-harness test. It sends only the
scenario's user request plus a reporting format to the target agent command. It
does not inject `SKILL.md` content, an `Available skills` list, or any repo-built
skill index.

This test fails if the installed harness cannot pick up the expected skill from
its real skill discovery mechanism. It also fails if the response repeats a
phrase listed in `response_forbidden_terms`.

The expected skill check is deterministic. The response is also evaluated by the
shared semantic judge to confirm the selected skill is relevant to the prompt,
the rationale comes from the prompt, and the agent did not perform the task. Set
`SEMANTIC_JUDGE_AGENT_COMMAND` to use a separate judge command; otherwise the
test falls back to `SKILL_TRIGGER_AGENT_COMMAND`.

The recommended Codex command shim defaults actor and judge calls to
`gpt-5.4-mini` with `low` reasoning so these simple selection checks do not
inherit a heavyweight local Codex profile. Use `CODEX_ACTOR_MODEL` or
`CODEX_JUDGE_MODEL` to opt into a stronger model for a specific run.

Run one scenario:

```bash
SKILL_TRIGGER_SCENARIO=bitbucket-pr-ui-test \
SKILL_TRIGGER_AGENT_COMMAND='python3 tests/codex_agent_command.py --role actor' \
SEMANTIC_JUDGE_AGENT_COMMAND='python3 tests/codex_agent_command.py --role judge' \
  python3 tests/skill-trigger/behavioral_pressure.py
```

## RED-GREEN-REFACTOR For Trigger Bugs

1. RED: add or update a `[[scenario]]` table in `scenarios.toml` that captures the missed trigger.
2. GREEN: update the skill description/body until the static contract passes.
3. REFACTOR: run the installed-harness behavioral trigger against an agent and
   tighten forbidden terms or prompt coverage if the agent still rationalizes
   past the skill.
