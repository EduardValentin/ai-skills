# Workflow Dispatch Tests

This directory covers whether an orchestration skill produces required workflow
actions after the parent skill body is loaded. It is separate from
`skill-trigger`, whose behavioral suite is the black-box installed-harness test
for whether a user request picks up a skill without injected context.

Keep workflow tests here when the behavior being tested is "skill X dispatches
or coordinates a downstream capability." Group Python tests by the skill under
test, for example:

```text
tests/workflow-dispatch/ticket-start/dispatch_scoping_contract.py
tests/workflow-dispatch/ticket-start/dispatch_scoping_behavioral_pressure.py
```

## Static Contract

Run in CI:

```bash
python3 tests/workflow-dispatch/static_contract.py
```

The static contract runs grouped `*_contract.py` tests under skill folders. Each
test guards against stale embedded-prompt references and hardcoded downstream
skill identifiers in parent/orchestrator skill prose. It also guards the
downstream discovery helper so it cannot rebuild or inject a skill index.

## Behavioral Dispatch

Run manually, nightly, or in a model-enabled CI job:

```bash
WORKFLOW_DISPATCH_AGENT_COMMAND='python3 tests/codex_agent_command.py --role actor' \
SEMANTIC_JUDGE_AGENT_COMMAND='python3 tests/codex_agent_command.py --role judge' \
  python3 tests/workflow-dispatch/behavioral_dispatch.py
```

If `WORKFLOW_DISPATCH_AGENT_COMMAND` is unset, the harness falls back to
`SKILL_TRIGGER_AGENT_COMMAND`.

The behavioral harness runs grouped `*_behavioral_pressure.py` tests under skill
folders. Each test gives the agent the loaded parent skill body and asks for a
workflow action ledger. This is a loaded-skill pressure test, not proof that the
parent skill was discovered by the installed harness. Parent-skill discovery
belongs in `tests/skill-trigger/behavioral_pressure.py`.

For downstream discovery coverage, workflow behavioral tests then send the
delegated request alone to the installed harness and assert that the intended
downstream skill is selected. The downstream check does not provide a skill body,
an `Available skills` list, or any repo-built skill index. If the harness cannot
discover the downstream skill from the delegated request, the test fails.

Behavioral checks use a hybrid model:

- deterministic hard gates for `ACTION:` shape, required machine tokens,
  forbidden downstream skill IDs, ordering invariants, and black-box downstream
  discovery;
- semantic judge rubrics for workflow quality, such as whether the parent stayed
  an orchestrator and whether delegated requests are self-contained.

Set `SEMANTIC_JUDGE_AGENT_COMMAND` to use a separate judge command. If unset,
the workflow agent command is reused as the judge.

Use the repo's `tests/codex_agent_command.py` shim for Codex-backed runs. It
defaults both actor and judge invocations to `gpt-5.4-mini` with `low` reasoning,
while still allowing `CODEX_ACTOR_MODEL`, `CODEX_JUDGE_MODEL`,
`CODEX_ACTOR_REASONING_EFFORT`, and `CODEX_JUDGE_REASONING_EFFORT` overrides for
the rare scenario that needs more depth.
