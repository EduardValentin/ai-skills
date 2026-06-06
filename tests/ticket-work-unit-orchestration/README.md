# Ticket Work Unit Orchestration Tests

These focused tests cover the per-ticket / per-work-unit readiness ledger expected from the future `ticket-work-unit-orchestration` skill.

They are intentionally RED until that dedicated skill exists and defines the explicit ledger contract.

## Deterministic Contract

```bash
python3 tests/ticket-work-unit-orchestration/readiness_ledger_contract.py
```

## Behavioral Pressure

```bash
TICKET_WORK_UNIT_AGENT_COMMAND='<command reading stdin>' \
  python3 tests/ticket-work-unit-orchestration/readiness_ledger_behavioral_pressure.py
```
