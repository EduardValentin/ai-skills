# Agent Instructions

This repository is the tracked source for personal AI skills and reusable
specialized agents. Keep a single canonical source for every skill and agent;
never edit installed or generated copies.

## Repository Rules

### Baseline and source layout

- Before creating a branch or worktree from `main`, fetch the remote and base
  it on the current `origin/main`.
- Skills use the strict source layout
  `skills/<group>/<skill>/SKILL.md`. Do not create per-harness skill copies or
  repository-level runtime toolkits.
- A skill is self-contained. Bundled executable code belongs in its skill;
  duplicated bundled financial runtime code is allowed only for this approved
  self-contained-skill exception.
- Do not directly edit installed skills, generated artifacts, or caches.
- When skill layout, validation, installation, or testing behavior changes,
  update `docs/INDEX.md`, `docs/TESTING.md`, and `docs/SPEC.md`.

### Skill contract and validation

- Treat upstream Agent Skills requirements separately from this repository's
  stricter policy. The nested group layout, supported-root allowlist, status
  metadata, required eval files, and validation gates are repository policy,
  not claims about the public specification.
- Parse frontmatter with StrictYAML. Keep repository policy in the shared
  validator. Use the pinned official `skills-ref` conformance check through
  `python3 scripts/ai_skills.py validate ci-all`; review the specification,
  documentation, and tests before updating that pin.
- Each skill root may contain only supported entries. Validate those entries
  statically by directory; reject unknown root directories, broken or escaping
  symlinks, empty directories, and `.gitkeep` placeholders without scanning
  arbitrary nested prose.
- Require the repository frontmatter and metadata fields. Set
  `metadata.allows_tool_references: "true"` when a skill references tools,
  harnesses, native agents, or other skills.
- Document required collaborators or fallbacks in `compatibility`. Validate
  retained skill names, and when a collaborator is required, cover both its
  present and absent behavior.
- Every retained skill requires `evals/evals.json` and
  `evals/triggers.json`.

### Evaluation and test policy

- Trigger requirements are uniform regardless of status. Run each query once
  by default, or uniformly use `--runs 2` or `--runs 3`. Unanimous results are
  stable. Two of three meets the threshold only after investigating the failed
  run; every other non-unanimous result fails. Preserve every discordant run;
  hidden retries are forbidden. Codex activation requires an exact successful
  read of the installed `SKILL.md`.
- Never run `validate triggers`, `validate evals`, `validate all`, or real
  Docker/Codex integration smoke tests unless the user explicitly requests
  them. A skill change, review, implementation workflow, or PR request is not
  approval.
- Before requested model runs, print run counts, preflight calls, concurrency,
  and the durable result path. Default concurrency is `2`; supported values are
  `1` through `4`. Preserve every attempted run outside the repository.
- Create skill-local fixtures only when a case needs them, preferably at
  `evals/fixtures/<eval-id>/`, and reference them from `evals/evals.json`.
  For production-shaped private-integration HTTP(S), use
  `mockserverInitialization.json` with the shared fail-closed proxy. Otherwise
  use fake data, shims, transcripts, or specialized local fixtures instead of
  real credentials or private sessions.
- Model-backed runs use the shared Docker sandbox. Do not weaken mounts,
  credential isolation, resource limits, network policy, judge isolation,
  MockServer no-passthrough behavior, or cleanup without updating
  `docs/TESTING.md` and the harness tests.
- Runtime pins are immutable: no floating image tags, package ranges, or
  runtime-schema downloads. Changes to `config/eval-runtime.json`, the actor
  Dockerfile, or the vendored MockServer schema require `docs/TESTING.md` updates
  and a report of the recommended integration verification; the agent-backed
  suite still requires explicit user approval.
- `validate ci-all` is offline and includes `tests/ai_skills/` plus deterministic
  runtime tests. Real Docker/Codex/MockServer smoke tests belong under
  `tests/integration/eval_runtime/` and run only through model-backed preflight
  or an explicit integration command.
- Non-trivial bundled executable code may have deterministic tests under
  `tests/runtime/`. Keep tests and test-only dependencies outside installable
  skill folders. `validate runtime` is included by `validate ci-all`.
- Secret scanning distinguishes values from names: allow documented
  environment-variable identifiers, lookups, references, and recognized
  placeholders; reject private-key blocks and high-confidence credential
  literals. Authored fake credential values must start with `FAKE_`; never
  print matched values.
- Hard absence evidence is allowed for structural, security, artifact, and
  negative-trigger contracts. Do not use brittle absence assertions against
  model prose.
- Config-required skills document environment variables or config-file path
  variables in `compatibility`, avoid personal hardcoded paths, and keep each
  config-reading helper inside its skill folder.

### Native agents and PR checks

- Native agents are local and internal. Keep canonical prompts under `agents/`
  and delivery metadata in `agents/manifest.toml`; do not create per-harness
  source copies. Update them with:

  ```bash
  python3 scripts/sync_native_agents.py push
  python3 scripts/sync_native_agents.py check
  ```

- `python3 scripts/ai_skills.py validate ci-all` is the sole routine PR gate.
- Only after the user explicitly approves PR creation, run the read-only
  `python3 scripts/ai_skills.py check-local-installs --harness codex`
  diagnostic. Report duplicate, missing, or stale repository skills and never
  repair local state automatically.
