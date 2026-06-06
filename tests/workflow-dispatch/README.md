# Workflow Dispatch Tests

This directory covers whether an orchestration skill produces required workflow
actions after the skill body is loaded. It is separate from `skill-trigger`,
which only checks whether skill metadata gets selected.

Keep workflow tests here when the behavior being tested is "skill X dispatches
or coordinates skill/capability Y." Group new Python tests by the skill under
test, for example:

```text
tests/workflow-dispatch/ticket-start/dispatch_scoping_skill_contract.py
tests/workflow-dispatch/ticket-start/dispatch_scoping_skill_behavioral_pressure.py
```

The root `scenarios.toml` harness is legacy coverage and remains supported.

## Static Contract

Run in CI:

```bash
python3 tests/workflow-dispatch/static_contract.py
```

The static contract verifies that the loaded skill body still contains the
required dispatch wording and does not reintroduce stale embedded-prompt
references. It also runs grouped `*_contract.py` tests under skill folders.

## Behavioral Dispatch

Run manually, nightly, or in a model-enabled CI job:

```bash
WORKFLOW_DISPATCH_AGENT_COMMAND='<agent command that reads stdin>' \
  python3 tests/workflow-dispatch/behavioral_dispatch.py
```

If `WORKFLOW_DISPATCH_AGENT_COMMAND` is unset, the harness falls back to
`SKILL_TRIGGER_AGENT_COMMAND`.

The behavioral harness gives the agent the loaded skill body and asks for a
workflow action ledger. It fails if the expected Scoping subagent dispatch is
missing, appears after downstream phases, or omits the required self-contained
prompt terms that describe the work. It also runs grouped
`*_behavioral_pressure.py` tests under skill folders.
