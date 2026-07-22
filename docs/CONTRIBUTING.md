# Contributing

Contributions should leave skills portable, independently installable, and
covered by the repository's generic validation and evaluation framework.

## Set Up The Repository

Use Python 3.11 or newer. Install the pinned development dependencies:

```bash
python3 -m pip install -r requirements-test.txt
```

Before starting a branch or worktree from `main`, fetch the remote and base the
work on the current `origin/main`.

## Choose The Change Surface

- Skill instructions and runtime files belong in
  `skills/<group>/<skill>/`.
- Behavior and pickup definitions belong in that skill's `evals/` directory.
- Generic validation and evaluation behavior belongs in
  `scripts/ai_skills_lib/`.
- Shared behavior used by more than one runner belongs in a core or shared
  library module.
- Non-trivial bundled-script tests belong in a named suite under
  `tests/runtime/`.
- Generic harness tests belong under `tests/ai_skills/` and automatically
  discover skills where appropriate.
- Native-agent prompts and delivery metadata belong under `agents/`.

Do not add per-harness skill sources, generated install copies, or
skill-specific test harness modules. A skill's only test definitions are
`evals/evals.json`, `evals/triggers.json`, and any files needed by their cases.

## Develop A Skill

Follow [Creating skills](CREATING-SKILLS.md). In particular:

1. Keep the Agent Skills contract and repository policy distinct.
2. Keep runtime dependencies inside the skill.
3. Add realistic behavior and trigger coverage for every skill status.
4. Keep actor prompts evaluation-blind.
5. Use deterministic checks only for hard artifact contracts.
6. Add case-local fixtures only when the scenario needs them.

## Run Deterministic Checks

The routine pull-request gate is:

```bash
python3 scripts/ai_skills.py validate ci-all
```

It runs:

- repository and skill topology checks;
- strict frontmatter and local policy checks;
- pinned `skills-ref` conformance;
- eval, trigger, fixture, reference, and secret validation;
- generic unit tests under `tests/ai_skills/`;
- deterministic bundled-script suites under `tests/runtime/`.

It does not start Docker Sandboxes, call a model, inspect local skill installs,
or use personal credentials.

Use narrower commands while iterating:

```bash
python3 scripts/ai_skills.py validate static
python3 scripts/ai_skills.py validate runtime
```

## Model-Backed Checks

Do not run `validate triggers`, `validate evals`, `validate all`, or the real
integration smoke tests unless the user explicitly requests that run. These
commands may consume model quota and saved Docker Sandboxes authentication.

When approved, prefer a filtered first run and inspect the printed attempt
count and result path before execution:

```bash
python3 scripts/ai_skills.py validate triggers \
  --harness codex --skill <skill-name> --runs 1

python3 scripts/ai_skills.py validate evals \
  --harness codex --skill <skill-name> --case <case-id>
```

Default model-backed concurrency is `2`; supported values are `1` through `4`.
There are no hidden retries. Review every failed or discordant attempt in the
external result directory. See [Evaluation](EVALUATION.md) for the complete
workflow and manual grading.

## Pull Requests And Local Installs

Before opening or updating a pull request, run only the deterministic gate
unless the user separately approved model-backed evaluation.

After the user explicitly approves pull-request creation, run the read-only
Codex install diagnostic:

```bash
python3 scripts/ai_skills.py check-local-installs --harness codex
```

Report missing, duplicate, or stale repository skills. Do not sync or repair
the user's install automatically.

## Native Agents

After changing canonical native-agent prompts or their manifest, update and
verify installed definitions with:

```bash
python3 scripts/sync_native_agents.py push
python3 scripts/sync_native_agents.py check
```

Skills and native agents have separate source and delivery paths.

## Keep Documentation Current

Update the relevant guide whenever behavior changes:

- installation and consumption: `USING-SKILLS.md`;
- skill authoring rules: `CREATING-SKILLS.md`;
- tests, fixtures, grading, or result review: `EVALUATION.md`;
- module boundaries, trust boundaries, or runtime lifecycle: `ARCHITECTURE.md`;
- contributor workflow or gates: this guide.

Keep `README.md` concise and point readers to these guides instead of repeating
their content.

## Runtime Maintenance

Changes to `config/eval-runtime.json`, Docker Sandboxes, Codex, MockServer,
network policy, worker reset, fixture proxying, evidence handling, or judge
isolation require focused deterministic tests and updates to both
`ARCHITECTURE.md` and `EVALUATION.md`.

Report the relevant real integration command in the pull request, but do not
run it without explicit user approval.
