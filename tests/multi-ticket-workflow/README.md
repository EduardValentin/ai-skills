# Multi Ticket Workflow Tests

These focused tests cover the simplified `multi-ticket-workflow` contract: the
main agent gathers the multi-ticket scope, sequences dependent work, creates
approved execution packets, delegates ticket implementation, and returns PRs in
review order.

## Behavioral Pressure

```bash
SKILL_TRIGGER_AGENT_COMMAND='<command reading stdin>' \
  python3 tests/behavioral_pressure_harness.py --skill multi-ticket-workflow
```
