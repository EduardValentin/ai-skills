# Agent Instructions

This repository is the tracked source for personal AI skills and reusable
specialized agents. Keep a single canonical source for every skill and agent;
never edit installed or generated copies.

## Repository Rules

### Baseline and source layout

- Before creating a branch or worktree from `main`, fetch the remote and base
  it on the current `origin/main`.
- Skills use the strict source layout
  `skills/<group>/<skill>/SKILL.md`. Runtime dependencies needed by a skill
  belong inside that skill folder.
- A skill is self-contained. Bundled executable code belongs in its skill;
  duplicated bundled financial runtime code is allowed only for this approved
  self-contained-skill exception.
- Do not directly edit installed skills, generated artifacts, or caches.
- When skill layout, validation, installation, or testing behavior changes,
  update the relevant files under `docs/` and keep `docs/INDEX.md` accurate.

### Skill contract and validation

- Treat upstream Agent Skills requirements separately from this repository's
  stricter policy. The nested group layout, supported-root allowlist, status
  metadata, optional experimental eval files, and validation gates are
  repository policy, not claims about the public specification.
- Parse frontmatter with StrictYAML. Keep repository policy in the shared
  validator. Use the pinned official `skills-ref` conformance check through
  `scripts/ai-skills validate ci-all`; review the specification,
  documentation, tests, and verified source manifest before updating that pin.
- Keep the isolated CLI bound to the exact repository `scripts/` package.
  Never expose the repository root as a general dependency import path before
  static validation.
- Each skill root may contain only supported entries. Validate those entries
  statically by directory; reject unknown root directories, broken or escaping
  symlinks, directory symlink cycles, public-installer discovery or copy
  exclusions, empty directories, and `.gitkeep` placeholders without scanning
  arbitrary nested prose.
- Require the repository frontmatter and metadata fields. Set
  `metadata.allows_tool_references: "true"` when a skill references tools,
  harnesses, native agents, or other skills.
- Document required collaborators or fallbacks in `compatibility`. Validate
  retained skill names, and when a collaborator is required, cover both its
  present and absent behavior.
- Repository skills are experimental unless explicitly promoted. Experimental
  skills may omit `evals/` entirely. Any present `evals/` directory, and every
  non-experimental skill, requires both `evals/evals.json` and
  `evals/triggers.json`.
- Dispatch every `SKILL.md` read performed for specification alignment to a
  separate subagent, regardless of the current delegation depth. Return only
  the findings needed by the coordinating agent.

### Evaluation and test policy

- For authored trigger coverage, run each query once by default, or uniformly
  use `--runs 2` or `--runs 3`. Unanimous results are stable. Two of three
  meets the threshold only after investigating the failed run, adding complete
  validated manual grading for every attempt, and aggregating with the manual
  source; judge-only aggregation must reject it. Every other non-unanimous
  result fails. Preserve every discordant run;
  Codex activation requires an exact successful read of the installed
  `SKILL.md` through a trusted system reader, with returned bytes equal to the
  prepared installed skill. Derive that read from one complete actor lifecycle
  with matched command ID, trusted reader, zero exit status, successful command
  status, matched tool start/completion IDs, and no unknown, out-of-order, or
  duplicate events; enforce the same lifecycle during offline aggregation.
- Keep trigger files runner-free: `skill_name` matches the skill, query IDs are
  unique, every query has `query` and boolean `should_trigger`, and each trigger
  file includes positive and near-miss negative coverage. Require a contained
  non-symlink file and complete static validation before model-backed setup;
  negative pickup passes only after the expected installed path is proven.
- Never run `validate triggers`, `validate evals`, `validate all`, or real
  Docker Sandboxes/Codex integration smoke tests unless the user explicitly
  requests them. A skill change, review, implementation workflow, or PR request
  is not approval.
- Before requested model-backed runs, print run counts, preflight calls,
  concurrency, and the durable result path. Default concurrency is `2`;
  supported values are `1` through `4`. Hidden retries are forbidden; preserve
  every attempted run outside the repository. Declare the exact immutable
  invocation attempt set before preflight so aggregation can reject missing or
  injected runs. Keep generated result JSON within the shared writer/reader
  ceiling before preflight; deterministic schemas total at most 512 KiB per
  behavior case. Derive the captured-output entry allowance from the complete
  per-attempt artifact contract, and reserve final benchmark and summary
  capacity before accepting a completed attempt. Give each invocation a fresh
  random identity, carry it
  through every structured attempt artifact, and bind `attempt.json` into
  grading evidence. Bind every attempt to a variant-independent scenario
  digest; require all behavior arms or repeated trigger runs in one group to
  share that digest and their immutable contracts. Bind preflight capabilities
  to that exact invocation through the runner-owned receipt and exact adapter;
  do not add an unbound capabilities bypass. Pass the preflight-selected actor
  and judge model configurations explicitly into every request and reject
  configured metadata drift across the complete invocation. Treat persisted
  model fields as exact bound-request configuration, not independent
  backend-routing attestation.
- Create skill-local fixtures only when a case needs them, preferably at
  `evals/fixtures/<eval-id>/`, and reference them from `evals/evals.json`.
  For production-shaped private-integration HTTP(S), use
  `mockserverInitialization.json` with the shared fail-closed proxy. Otherwise
  use fake data, shims, transcripts, or specialized local fixtures instead of
  real credentials or private sessions. MockServer fixtures may use only
  static response/error actions; never add forwards, callbacks, executable
  templates, delays, relaxed matching, generated responses, file-backed
  response bodies, or unbounded repetition. Require exact non-empty method,
  path, and `Host` matchers; keep the total declared calls at or below the
  manifest limit. Every declared call is verified. Bind actor inputs and HTTP
  initialization to the exact current case fixture root. Keep MockServer
  sidecars case-scoped: prove every declared TLS subject with a real handshake,
  then destroy the sidecar and generated certificate state before worker reuse.
- Keep behavior definitions generic and runner-owned: actor prompts must not
  contain expected results, grading guidance, or unnecessary disclosure of
  evaluation, sandbox, fixture, mock, or shim mechanics. Describe available
  commands and data as ordinary task capabilities. Use semantic assertions for
  meaning and only the approved deterministic checks for hard artifact
  contracts. Declared inputs stay below the exact case `inputs/` directory;
  executable `inputs/bin/` collaborators are runner-added to the actor `PATH`;
  runner-only schemas and proxy expectations stay outside `inputs/`.
- Keep behavior variant identity runner-only. Never include `with_skill` or
  `without_skill` labels in judge controls or evidence, and require every
  behavior attempt in an aggregation group to share one judge-control digest.
- Model-backed runs use reusable Docker Sandboxes worker pools. Give every case
  a fresh actor projection, workspace, `CODEX_HOME`, and ephemeral harness
  session; keep actor and judge workers separate, keep real credentials in the
  host proxy, keep all case-writable state on the pinned aggregate tmpfs, and
  recycle a worker when reset verification fails. Judges remain skill-free,
  read-only, shell-free, web-free, and response-schema-bound; treat all actor
  evidence as untrusted. Do not weaken resource limits, mount isolation,
  network policy, oracle isolation, MockServer no-passthrough behavior, or
  cleanup without updating `docs/ARCHITECTURE.md`, `docs/EVALUATION.md`, and
  the harness tests.
- Runtime pins are immutable: no floating sandbox/template/image tags, package
  ranges, or runtime-schema downloads. Changes to `config/eval-runtime.json`,
  Docker Sandboxes or Codex pins, or the vendored MockServer schema require
  `docs/ARCHITECTURE.md` and `docs/EVALUATION.md` updates plus a report of the
  recommended integration verification; the agent-backed suite still requires
  explicit user approval.
- `validate ci-all` is deterministic, offline, and model-free. It includes
  `tests/ai_skills/` plus deterministic runtime tests. Real Docker
  Sandboxes/Codex/MockServer smoke tests belong under
  `tests/integration/eval_runtime/` and run only through model-backed preflight
  or an explicit integration command.
- Unit and runtime tests are reviewed repository code executed on the host.
  Their isolated environment, snapshots, output limits, and process groups are
  deterministic hygiene, not an adversarial sandbox. Keep untrusted or
  model-driven execution inside Docker Sandboxes.
- Non-trivial bundled executable code may have deterministic tests under
  `tests/runtime/`. Keep tests and test-only dependencies outside installable
  skill folders. Use one named directory per suite with at least one
  `test_*.py`; do not add root-level files, symlinks, hidden entries, or empty
  suites. Give each suite a fresh materialized repository snapshot while
  preserving the aggregate deadline. `validate runtime` is included by
  `validate ci-all`.
- Secret scanning distinguishes values from names: allow documented
  environment-variable identifiers, lookups, references, and recognized
  placeholders; reject private-key blocks and high-confidence credential
  literals. Authored fake credential values must start with `FAKE_`; never
  print matched values. Preserve safe actor evidence exactly; quarantine and
  fail an attempt when its evidence would require redaction instead of grading
  transformed content. Eval prompts always reject explicit actual, live,
  personal, private, production, real, or logged-in resource requests. Ordinary
  owner phrasing is allowed only when valid case-local inputs or HTTP
  initialization establish the non-production boundary, without requiring
  fixed disclosure prose in the actor prompt. Leave broader semantic
  private-state concerns to judge and human review.
- Hard absence evidence is allowed for structural, security, artifact, and
  negative-trigger contracts. Do not use brittle absence assertions against
  model prose.
- Manual grading may override judge-scored semantic assertions, but it must
  preserve deterministic assertion outcomes and evidence exactly.
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

- `scripts/ai-skills validate ci-all` is the sole routine PR gate.
- Only after the user explicitly approves PR creation, run the read-only
  `scripts/ai-skills check-local-installs --harness codex`
  diagnostic. Report duplicate, missing, or stale repository skills and never
  repair local state automatically.
