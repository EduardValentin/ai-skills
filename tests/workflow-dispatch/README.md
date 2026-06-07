# Workflow Dispatch Tests

This directory covers whether an orchestration skill produces required workflow
actions after the skill body is loaded. It is separate from `skill-trigger`,
which checks whether skill metadata gets selected from the skill index.

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
test verifies that the loaded skill body still contains required dispatch wording,
does not reintroduce stale embedded-prompt references, and does not hardcode
downstream skill identifiers in parent/orchestrator skill prose.

## Behavioral Dispatch

Run manually, nightly, or in a model-enabled CI job:

```bash
WORKFLOW_DISPATCH_AGENT_COMMAND='<agent command that reads stdin>' \
  python3 tests/workflow-dispatch/behavioral_dispatch.py
```

If `WORKFLOW_DISPATCH_AGENT_COMMAND` is unset, the harness falls back to
`SKILL_TRIGGER_AGENT_COMMAND`.

The behavioral harness runs grouped `*_behavioral_pressure.py` tests under skill
folders. Each test gives the agent the loaded parent skill body and asks for a
workflow action ledger. The parent response should name capabilities and provide
self-contained delegated requests, not downstream skill identifiers.

For auto-discovery coverage, workflow behavioral tests then feed the delegated
request into a skill-index selection prompt and assert that the intended
downstream skill is selected there. This keeps the parent skill discovery-based:
the parent emits an intent-rich request, and skill selection happens from the
skill index.

Behavioral checks should tolerate non-deterministic model wording. Prefer
case-insensitive concept groups and forbidden anti-patterns over exact full-line
or full-response matches. Exact tokens are appropriate only when the prompt
explicitly requires a machine-readable token such as `DISPATCH_REQUEST`.
