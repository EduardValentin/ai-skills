# Repository Skill Specification

Every installable skill follows the public
[Agent Skills specification](https://agentskills.io/specification) and the
additional repository rules below.

## Layout

Skills live at `skills/<group>/<skill>/SKILL.md`. A skill root may contain only
`SKILL.md`, `scripts/`, `references/`, `assets/`, and `evals/`. Keep executable
code and configuration helpers needed at runtime inside the skill. Do not add
installed copies, generated distributions, empty directories, or test-only
infrastructure to a skill.

## Skill Contract

- Use specification-compliant YAML frontmatter and a portable Markdown body.
- Use clean skill-relative paths; links and symlinks must remain inside the
  skill root.
- Set `metadata.allows_tool_references: "true"` when instructions mention a
  tool, harness, native agent, or another skill.
- Describe required collaborators, fallbacks, environment variables, and
  config-file path variables in `compatibility`.
- Avoid personal paths, private sessions, and credential literals. Authored
  fake credential values begin with `FAKE_`.

## Evaluation Contract

Every skill includes `evals/evals.json` and `evals/triggers.json`. Behavior
cases assess the work produced with and without the skill. Trigger cases assess
selection without preloading the target skill body into the prompt. Fixtures
are optional and belong under `evals/fixtures/<eval-id>/` only when a case needs
them.

`evals/evals.json` is a UTF-8 JSON file of at most 2 MiB. It declares the exact
`skill_name` and between 1 and 128 cases. Every case has a unique path-safe ID
of at most 64 characters, a non-empty actor prompt of at most 16 KiB,
runner-only expected output of at most 8 KiB, and 1 to 64 semantic assertions
of at most 4 KiB each. The combined prompt, expected output, and assertions for
one case may occupy at most 320 KiB when UTF-8 encoded. A case may declare at
most 64 input files and 64 deterministic checks. All declared paths are canonical
POSIX-relative paths of at most 512 characters; aliases such as `./x`, `a//b`,
and `a/../b` are invalid. Optional `files` must identify existing regular files
below that exact case's `fixtures/<eval-id>/inputs/` directory, and the actor
prompt must name each file by its staged workspace-relative path. Each fixture
file is limited to 4 MiB. Optional
deterministic checks are limited to `file_exists`, `path_absent`, `json_schema`,
`exit_code`, `no_secret_patterns`, and `response_protocol`; output paths are
relative and contained, and schemas remain runner-only below the exact case
fixture root. Runner schemas are JSON objects of at most 256 KiB and may use
only a bounded structural subset of JSON Schema. The subset permits ordinary
types, properties, items, required fields, enums, constants, numeric bounds,
and size bounds. It allows at most 512 schema nodes, depth 32, 128 acyclic
same-document references, and 64 materialized validation errors. External or
recursive references, regular-expression keywords, combinators, conditionals,
and advanced unbounded keywords are invalid. An `exit_code` check can require
only successful actor execution with `expected: 0`; a nonzero harness exit
makes the attempt untrustworthy. Do not use exact model-prose matching checks
such as `contains` or `not_contains`.

Behavior prompts must use explicit mocks or fixtures. Cases that request real
credentials, logged-in sessions, or live private account state are invalid.
Static validation conservatively rejects explicit owned or state-qualified
resource phrases unless that same resource is directly marked as fake, mock,
fixture, sandbox, simulation, or transcript data, or is directly negated.
Authors should make non-live intent explicit. Broader semantic dependence on
private state is assessed by judge and human review rather than an open-ended
static language classifier.

At least one behavior case must name and exercise real bundled runtime material
when the skill contains `scripts/`, `references/`, or `assets/`. Evals should
assess both the resulting work and any required collaborator dispatch that is
observable in preserved harness evidence.

`evals/triggers.json` declares the exact skill name and a `queries` array. Each
of its 1 to 128 queries has a unique path-safe `id` of at most 64 characters, a
non-whitespace UTF-8 `query` of at most 16 KiB, and boolean `should_trigger`.
Every skill has at least one positive query and one near-miss negative query.
Do not put run counts or other runner configuration in the file. One invocation
may select at most 128 queries and 384 trigger model calls. It must be a
contained non-symlink regular file and must pass the shared high-confidence
secret checks before any model-backed setup.

Model actors receive a generated runtime projection containing only
`SKILL.md`, `scripts/`, `references/`, and `assets/`. Runtime material must not
reference `evals/`; definitions, expected results, assertions, trigger answers,
and judge context stay outside actor mounts. Only explicitly declared files
below the current case's `evals/fixtures/<eval-id>/inputs/` directory may be
copied into its actor workspace. Both those files and an optional
`mockserverInitialization.json` are bound to that exact case fixture root;
sibling skill or case fixtures are invalid. Judges receive no skill catalog.
This runner-side isolation does not make eval files committed to a public
repository confidential from an intentionally adversarial network-enabled
skill.

Actor responses, traces, and captured outputs must remain exact to be eligible
for checks or judging. Approved fake values use the `FAKE_` prefix. Evidence
that contains a classified credential or would require truncation or redaction
is quarantined and makes the attempt untrustworthy; a redacted diagnostic must
not be treated as evaluated actor output. Before checks or judging, the exact
response, transcript, frozen trace, and every captured regular output selected
for judge evidence must each fit the 32 KiB UTF-8 artifact bound and must fit
together in the 512 KiB rendered judge prompt. Non-text evidence or any bound
failure invalidates the attempt; no value may be replaced, truncated, or
silently omitted to fit.

HTTP(S) fixture initialization files must pass the pinned official MockServer
schema and repository safety policy during static validation, before any
model-backed setup. They must be regular, non-symlink files in the exact case
fixture root. Use only static `httpResponse` or
`httpError` actions with fake data. Do not use forwarding, callbacks,
executable templates, delays, relaxed body matching, generated responses,
file-backed response bodies, or unbounded repetition. Every expectation needs
one non-empty exact method, path, and `Host` matcher. Each expectation is one
required call unless finite `times` declares a repeat count, and one case may
declare at most 128 total calls. The runner quotes authored request strings as
Java-regex literals and enables exact-case method/path matching before uploading
them to MockServer. The shared runner
owns authenticated control access, dynamic CA material, per-case reset,
complete ordered-call verification, bounded redacted request evidence, and
proxy environment injection.

Model-backed invocations preserve results outside the repository. The runner
loads definitions once, freezes the complete selected trigger and behavior
plans, and persists their immutable invocation manifests before runtime
preflight. Each run is then declared by its own `attempt.json` before execution.
Those declarations own the exact attempt set, run identity, and generic
aggregation policy; definitions are not reloaded after preflight. Aggregation
requires every declared attempt, required variant, timing record, and requested
grade source to be complete and mutually consistent. A complete manual grade
overrides the generated grade when manual or both sources are requested,
without replacing the generated artifact. Repeated trigger attempts declare
their query-level threshold, configured run count, and ordinal in immutable
aggregation metadata. Aggregation rejects missing, duplicate, or injected
attempts and run ordinals; the benchmark preserves each run and reports
observed trigger rate by skill. Aggregate exit codes are `0` for pass, `1` for a
trusted evaluated failure, and `2` for invalid or untrustworthy evidence.

The schemas and validation commands are documented in [Testing](TESTING.md).
Do not create additional skill-specific test artifacts. Non-trivial bundled
scripts may instead have deterministic repository tests under `tests/runtime/`.

## Validation

Run the deterministic repository gate with:

```bash
python3 scripts/ai_skills.py validate ci-all
```

Model-backed behavior and trigger runs are separate, opt-in operations and
require explicit user approval.

The machine-specific `check-local-installs --harness codex` command is separate
from repository validation. It is strictly read-only and compares repository
skills with active Codex roots using bounded, descriptor-anchored reads. Lock
ownership is accepted only from integer lock versions `3` or newer. A configured
`XDG_STATE_HOME` selects `skills/.skill-lock.json`; otherwise the diagnostic uses
`~/.agents/.skill-lock.json` under the injected `HOME`. The diagnostic discovers
repository skill roots, parses bounded `SKILL.md` bytes, and retains source
manifests through its own no-follow descriptor snapshot; shared core discovery
and validation remain unchanged. Local and remote source identifiers are derived
only after that repository descriptor is anchored. The descriptor identity and
any Git common-directory proof remain stable through inspection, Git metadata
is read with descriptor-based byte bounds, and one aggregate entry budget covers
all repository and installed manifests.
