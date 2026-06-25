# Workflow Dispatch Tests

This directory covers whether an orchestration skill produces required workflow
actions after the parent skill body is loaded. It is separate from
`skill-trigger`, whose behavioral suite is the black-box installed-harness test
for whether a user request picks up a skill without injected context.

Keep workflow tests only when the behavior being tested is "skill X emits a
delegated request that the installed harness can auto-discover as skill Y." Do
not duplicate broad loaded-skill behavioral pressure tests here.

Scenario data, when needed, is colocated with the skill under test as
`skills/<skill-name>/tests/workflow-dispatch.toml`. The reusable runner and
black-box discovery helper stay in this directory.

## Static Contract

Run in CI:

```bash
python3 tests/contract.py --suite workflow-dispatch
```

The static contract is TOML-backed and checks only structural repository
expectations such as stale grouped workflow files being absent.

## Behavioral Dispatch

Run manually, nightly, or in a model-enabled CI job when colocated
`workflow-dispatch.toml` suites exist:

```bash
SKILL_TRIGGER_AGENT_COMMAND='python3 tests/codex_agent_command.py' \
  python3 tests/workflow-dispatch/behavioral_dispatch.py
```

The behavioral harness discovers colocated `workflow-dispatch.toml` files. Each
scenario gives the agent the loaded parent skill body and asks for a workflow
action ledger. This is a loaded-skill pressure test, not proof that the parent
skill was discovered by the installed harness. Parent-skill discovery belongs in
`tests/skill-trigger/trigger_harness.py`.

For downstream discovery coverage, workflow behavioral tests then send only the
emitted action rows for the handoff to the installed harness and assert that the
intended downstream skill is selected. `DISPATCH_REQUEST` rows are preferred when
present, but user-facing skill handoffs can use another action kind. The
downstream check does not provide a skill body, an `Available skills` list, or
any repo-built skill index. If the harness cannot discover the downstream skill
from the delegated request, the test fails.

Behavioral checks use a hybrid model:

- deterministic hard gates for `ACTION:` shape, required machine tokens,
  ordering invariants, configured response checks, and black-box downstream
  discovery;
- semantic judge rubrics for workflow quality, such as whether the parent stayed
  an orchestrator and whether delegated requests are self-contained.

The workflow agent command is reused as the judge by default.

Use the repo's `tests/codex_agent_command.py` shim for Codex-backed runs. It
defaults Codex invocations to `gpt-5.4-mini` with `low` reasoning, while still
allowing `CODEX_ACTOR_MODEL`, `CODEX_ACTOR_REASONING_EFFORT`,
`CODEX_TEST_MODEL`, and `CODEX_TEST_REASONING_EFFORT` overrides for the rare
scenario that needs more depth.
