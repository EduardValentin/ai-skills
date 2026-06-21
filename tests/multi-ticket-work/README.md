# Multi-Ticket Work Tests

These focused tests cover the simplified `multi-ticket-work` contract: the main
agent gathers the full multi-ticket scope, sequences dependent work, dispatches
one ticket coordinator subagent per ticket or unit, and returns PRs in review order.

## Behavioral Pressure

```bash
SKILL_TRIGGER_AGENT_COMMAND='<command reading stdin>' \
  python3 tests/behavioral_pressure_harness.py --skill multi-ticket-work
```
