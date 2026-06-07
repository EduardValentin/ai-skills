# Workflow Dispatch Tests

This directory covers whether an orchestration skill produces required workflow
actions after the skill body is loaded. It is separate from `skill-trigger`,
which only checks whether skill metadata gets selected.

Keep workflow tests here when the behavior being tested is "skill X dispatches
or coordinates skill/capability Y." Group Python tests by the skill under test,
for example:

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
test verifies that the loaded skill body still contains required dispatch wording
and does not reintroduce stale embedded-prompt references.

## Behavioral Dispatch

Run manually, nightly, or in a model-enabled CI job:

```bash
WORKFLOW_DISPATCH_AGENT_COMMAND='<agent command that reads stdin>' \
  python3 tests/workflow-dispatch/behavioral_dispatch.py
```

If `WORKFLOW_DISPATCH_AGENT_COMMAND` is unset, the harness falls back to
`SKILL_TRIGGER_AGENT_COMMAND`.

The behavioral harness runs grouped `*_behavioral_pressure.py` tests under skill
folders. Each test gives the agent the loaded skill body and asks for a workflow
action ledger, then checks that the expected dispatch behavior appears.
