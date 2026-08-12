# Contributing

Contributions should leave skills portable, independently installable, and
compatible with the repository's generic validation and evaluation framework.

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
- Optional behavior and pickup definitions belong in that skill's `evals/`
  directory.
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
skill-specific test harness modules. When present, a skill's only test
definitions are `evals/evals.json`, `evals/triggers.json`, and files needed by
their cases.

## Develop A Skill

Follow [Creating skills](CREATING-SKILLS.md). In particular:

1. Keep the Agent Skills contract and repository policy distinct.
2. Keep runtime dependencies inside the skill.
3. Keep new skills experimental until realistic behavior and trigger coverage
   is ready; both files are required before promotion.
4. Keep actor prompts evaluation-blind.
5. Use deterministic checks only for hard artifact contracts.
6. Add case-local fixtures only when the scenario needs them.

## Run Deterministic Checks

The routine pull-request gate is:

```bash
scripts/ai-skills validate ci-all
```

It runs:

- repository and skill topology checks;
- bounded, stable `SKILL.md` discovery plus strict frontmatter and local policy
  checks under one shared repository entry-and-byte budget;
- pinned `skills-ref` conformance with Git provenance and source digest
  verification before the reviewed source is loaded;
- present eval, trigger, fixture, reference, asset, and secret validation;
- generic unit tests under `tests/ai_skills/`;
- deterministic bundled-script suites under `tests/runtime/`.

Topology and authored-file checks consume descriptor-backed snapshots for each
validated tree. Cached `SKILL.md` bytes and file identity are reverified after
static checks and again after official conformance. Eval JSON is accepted only
when the complete definition tree remains unchanged across all bounded reads.
The isolated CLI binds its own `scripts/` package directly without exposing the
repository root to dependency imports. Generic unit discovery uses the same
explicit `test*.py` pattern for package-marker preflight and pinned pytest
execution. The validated files are passed to pytest explicitly, including
files in otherwise skipped directory names, so both `unittest.TestCase` and
module-level pytest tests run.
Strict JSON rejects duplicate object keys and scans decoded strings so escapes
cannot hide credential patterns. Installable runtime files receive
high-confidence secret scanning and runner-only `evals/` reference checks,
including non-Markdown, binary, and non-UTF-8 files. Python multiline
assignment recovery is invoked only for relevant credential assignments and
must pass byte and token limits before AST parsing. Binary encoding views are
decoded and scanned one at a time under one shared finding and decoder budget.
Authored path components receive the same high-confidence credential checks;
diagnostics identify the pattern while keeping the component value redacted.
The curated assignment family includes common snake_case, environment-style,
camelCase, kebab-case, service-prefixed, and quoted inline-object credential
keys while retaining the documented fake-value exemptions. Local-install and
deterministic-test diagnostics apply the same redaction policy to failures,
paths, names, labels, and grouped issues.

It does not start Docker Sandboxes, call a model, inspect local skill installs,
or use personal credentials.

While iterating, `scripts/ai-skills validate conformance` runs only the pinned
`skills-ref` conformance phase, and `scripts/ai-skills validate static` runs
only repository policy. Neither replaces the `validate ci-all` gate.

Unit and bundled-script tests run from descriptor-copied temporary repository
snapshots. Every runtime suite receives a fresh snapshot, while all suites
still share one aggregate deadline. Runtime suites likewise execute their exact
validated `test*.py` file lists. Supported contained symlinks inside
installable skills are materialized as ordinary snapshot entries; directory
symlink cycles, test suites, executable inputs, escapes, and special files
remain rejected. Public-installer discovery exclusions are rejected at group
and skill boundaries, and installer-omitted entry names are rejected
recursively. Entry, byte, and depth limits apply, and nested unit-test
directories require package markers so discovery cannot silently skip them. An
empty unit suite or empty declared runtime suite fails instead of passing
vacuously. Generated Python and pytest caches remain ignored unless they
contain a `test*.py` module, which fails discovery instead of silently hiding
the test.

Test subprocesses receive an allowlisted environment with isolated home and
temporary directories. Stdout and stderr are captured as raw bytes with a
4 MiB limit per stream, scanned for high-confidence secrets, and emitted only
when safe. Each subprocess has its own process group so inherited descendants
are cleaned before validation continues. Exceeding the limit or producing
unsafe output fails the gate without printing the quarantined content.
These suites are reviewed repository code executed on the host. The snapshots,
environment filtering, limits, and process groups provide deterministic test
hygiene; they are not an adversarial sandbox and do not claim to contain code
that deliberately creates a new process session. Model-driven and other
untrusted execution belongs in Docker Sandboxes.

Use narrower commands while iterating:

```bash
scripts/ai-skills validate static
scripts/ai-skills validate runtime
```

## Model-Backed Checks

Do not run `validate triggers`, `validate evals`, `validate all`, or the real
integration smoke tests unless the user explicitly requests that run. These
commands may consume model quota and saved Docker Sandboxes authentication.

When approved, prefer a filtered first run and inspect the printed attempt
count and result path before execution:

```bash
scripts/ai-skills validate triggers \
  --harness codex --skill <skill-name> --runs 1

scripts/ai-skills validate evals \
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
scripts/ai-skills check-local-installs --harness codex
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
