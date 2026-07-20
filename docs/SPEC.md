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

`evals/triggers.json` declares the exact skill name and a `queries` array. Each
query has a unique path-safe `id`, a non-whitespace `query`, and boolean
`should_trigger`. Every skill has at least one positive query and one near-miss
negative query. Do not put run counts or other runner configuration in the
file. It must be a contained non-symlink regular file and must pass the shared
high-confidence secret checks before any model-backed setup.

Model actors receive a generated runtime projection containing only
`SKILL.md`, `scripts/`, `references/`, and `assets/`. Runtime material must not
reference `evals/`; definitions, expected results, assertions, trigger answers,
and judge context stay outside actor mounts. Only explicitly declared files
below the current case's `evals/fixtures/<eval-id>/inputs/` directory may be
copied into its actor workspace. Both those files and an optional
`mockserverInitialization.json` are bound to that exact case fixture root;
sibling skill or case fixtures are invalid. Judges receive no skill catalog.

HTTP(S) fixture initialization files must pass the pinned official MockServer
schema and repository safety policy. Use only static `httpResponse` or
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

Model-backed invocations preserve results outside the repository. Each run is
listed in an immutable invocation manifest, then declared by its own
`attempt.json` before execution. Those declarations own the exact attempt set,
run identity, and generic aggregation policy. Aggregation requires every
declared attempt, required variant, timing record, and requested grade source to
be complete and mutually consistent. A complete manual grade overrides the
generated grade when manual or both sources are requested, without replacing
the generated artifact. Repeated trigger attempts declare their query-level
threshold, configured run count, and ordinal in immutable aggregation metadata.
Aggregation rejects missing, duplicate, or injected attempts and run ordinals;
the benchmark preserves each run and reports observed trigger rate by skill.
Aggregate exit codes are `0` for pass, `1` for a
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
