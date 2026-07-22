# AI Skills

A public collection of portable [Agent Skills](https://agentskills.io/) for
Codex, Claude Code, and other compatible agents. The repository also contains
reusable native-agent prompts and a validation and evaluation framework for
maintaining skill quality.

Skills are organized by subject under `skills/`. Each skill is independently
installable and keeps its instructions, scripts, references, assets, and eval
definitions together.

## Quick Start

List the available skills:

```bash
npx skills add EduardValentin/ai-skills --list
```

Review each selected skill's status and `compatibility` requirements. This
repository includes experimental, configuration-dependent, and local-tooling
skills. Install all skills globally for Codex, or select individual skills when
prompted:

```bash
npx skills add EduardValentin/ai-skills -g -a codex
```

For repository development, install Python 3.11 or newer and the test
dependencies, then run the deterministic validation gate:

```bash
python3 -m pip install -r requirements-test.txt
python3 scripts/ai_skills.py validate ci-all
```

## Documentation

- [Using the skills](docs/USING-SKILLS.md) covers installation, selection,
  updates, removal, and native agents.
- [Creating skills](docs/CREATING-SKILLS.md) defines the portable skill and
  repository contracts.
- [Evaluation](docs/EVALUATION.md) explains behavior evals, trigger evals,
  fixtures, judges, grading, and result review.
- [Architecture](docs/ARCHITECTURE.md) explains repository components and the
  Docker Sandboxes runtime.
- [Contributing](docs/CONTRIBUTING.md) covers setup, validation, and pull-request
  expectations.
- [Documentation index](docs/INDEX.md) maps readers to the right guide.
