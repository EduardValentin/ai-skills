# Ticket Work Unit Orchestration Tests

These focused tests cover the per-ticket / per-work-unit readiness ledger expected from `ticket-work-unit-orchestration`.

## Behavioral Pressure

```bash
TICKET_WORK_UNIT_AGENT_COMMAND='<command reading stdin>' \
  python3 tests/ticket-work-unit-orchestration/readiness_ledger_behavioral_pressure.py
```
