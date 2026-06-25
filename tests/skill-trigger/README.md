# Skill Trigger Tests

This directory keeps global trigger coverage for ability skills under `skills/`
and plugin-packaged skills under `plugins/*/skills/`.

Procedural skills are manually invoked workflows. Mark them with
`metadata.ai-skills-invocation: manual` and `disable-model-invocation: true`;
they must not have trigger scenarios.

## Static Contract

Run in CI:

```bash
python3 tests/skill-trigger/static_contract.py
```

The static contract is deterministic. It verifies:

- every ability skill has at least one trigger scenario;
- procedural/manual-invocation skills have no trigger scenarios;
- every scenario references an existing skill;
- the declared skill name matches its folder.

## Installed-Harness Behavioral Trigger

Run manually, nightly, or in a model-enabled CI job:

```bash
SKILL_TRIGGER_AGENT_COMMAND='python3 tests/codex_agent_command.py' \
  python3 tests/skill-trigger/trigger_harness.py
```

The behavioral harness is a black-box installed-harness test. It sends only the
scenario's user request plus a reporting format to the target agent command. It
does not inject `SKILL.md` content, an `Available skills` list, or any repo-built
skill index.

This test fails if the installed harness cannot pick up the expected skill from
its real skill discovery mechanism.

The expected skill check is deterministic. The response is also evaluated by the
shared semantic judge to confirm the selected skill is relevant to the prompt,
the rationale comes from the prompt, and the agent did not perform the task. The
same `SKILL_TRIGGER_AGENT_COMMAND` is used for that judge call.

The recommended Codex command shim defaults calls to `gpt-5.4-mini` with `low`
reasoning so these simple selection checks do not inherit a heavyweight local
Codex profile. Use `CODEX_ACTOR_MODEL` or
`CODEX_TEST_MODEL` to opt into a stronger model for a specific run.

Run one scenario:

```bash
SKILL_TRIGGER_SCENARIO=bitbucket-pr-ui-test \
SKILL_TRIGGER_AGENT_COMMAND='python3 tests/codex_agent_command.py' \
  python3 tests/skill-trigger/trigger_harness.py
```

## RED-GREEN-REFACTOR For Trigger Bugs

1. RED: add or update a `[[scenario]]` table in `scenarios.toml` that captures the missed trigger.
2. GREEN: update the skill description/body until the static contract passes.
3. REFACTOR: run the installed-harness behavioral trigger against an agent and
   tighten the positive semantic criteria if the agent still rationalizes past
   the skill.

Do this only for ability skills. For procedural skills, prove behavior with the
loaded-skill behavioral suites instead of installed-harness trigger tests.
