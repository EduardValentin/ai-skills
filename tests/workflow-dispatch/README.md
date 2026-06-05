# Workflow Dispatch Tests

This directory covers whether an orchestration skill produces required workflow
actions after the skill body is loaded. It is separate from `skill-trigger`,
which only checks whether skill metadata gets selected.

## Static Contract

Run in CI:

```bash
python3 tests/workflow-dispatch/static_contract.py
```

The static contract verifies that the loaded skill body still contains the
required dispatch wording and does not reintroduce stale embedded-prompt
references.

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
prompt terms that describe the work.
