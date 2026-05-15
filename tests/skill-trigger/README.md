# Skill Trigger Tests

This directory keeps global trigger coverage for canonical skills under `skills/`.

## Static Contract

Run in CI:

```bash
bash tests/skill-trigger/static-contract.sh
```

The static contract is deterministic. It verifies:

- every canonical `skills/*/SKILL.md` has at least one trigger scenario;
- every scenario references an existing canonical skill;
- the declared skill name matches its folder;
- descriptions start with `Use when`;
- scenario-specific trigger terms appear in the description or skill body;
- forbidden stale wording is absent.

## Behavioral Pressure

Run manually, nightly, or in a model-enabled CI job:

```bash
SKILL_TRIGGER_AGENT_COMMAND='<agent command that reads stdin>' \
  bash tests/skill-trigger/behavioral-pressure.sh
```

The behavioral harness sends each scenario to an agent with the current skill
index and asks it to return the skills it would load before acting. It fails if
the expected skill is missing or if the response repeats a known bad
rationalization.

Run one scenario:

```bash
SKILL_TRIGGER_SCENARIO=bitbucket-pr-ui-test \
SKILL_TRIGGER_AGENT_COMMAND='<agent command that reads stdin>' \
  bash tests/skill-trigger/behavioral-pressure.sh
```

## RED-GREEN-REFACTOR For Trigger Bugs

1. RED: add or update a row in `scenarios.tsv` that captures the missed trigger.
2. GREEN: update the skill description/body until the static contract passes.
3. REFACTOR: run the behavioral harness against an agent and tighten forbidden
   terms or prompt coverage if the agent still rationalizes past the skill.
