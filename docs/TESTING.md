# Testing

This repository keeps routine validation deterministic and reserves model-backed
testing for explicitly requested evaluation runs.

## Offline Validation

Run the complete pull-request gate with:

```bash
python3 scripts/ai_skills.py validate ci-all
```

This command checks the repository and skill contracts, eval and trigger JSON,
official Agent Skills conformance, and deterministic runtime tests. It does not
start Docker Sandboxes, invoke a model, use credentials, or inspect personal
skill installations.

## Model-Backed Testing

Behavior and trigger evaluation are opt-in:

```bash
python3 scripts/ai_skills.py validate evals --harness codex
python3 scripts/ai_skills.py validate triggers --harness codex
python3 scripts/ai_skills.py validate all --harness codex
```

These commands run only after explicit user approval. Before the first model
call, the CLI prints actor and judge run counts, preflight calls, concurrency,
and the durable result directory. Every attempted run is preserved; the runner
does not hide instability with automatic retries.

## Runtime Isolation

Model-backed runs use Docker Sandboxes and the pinned runtime in
`config/eval-runtime.json`.

Follow the [Docker Sandboxes setup guide](https://docs.docker.com/ai/sandboxes/get-started/),
then authenticate Codex on the host before creating workers:

```bash
sbx login
sbx secret set -g openai --oauth
```

- A command creates at most one reusable actor worker per concurrency slot.
- Judges use a separate worker pool and never receive the actor skill catalog.
- Every case receives a fresh staged skill projection, workspace, `CODEX_HOME`,
  and ephemeral harness session.
- Durable results stay outside the actor mount. Judges receive only the
  sanitized artifacts needed for grading.
- A failed reset fails the case and removes the affected worker instead of
  silently reusing uncertain state.
- Workers and their private Docker resources are removed when the command ends.

Codex authentication is managed by the Docker Sandboxes host proxy. The runner
does not copy `~/.codex`, `auth.json`, API keys, browser sessions, or other
private host state into a worker. A fresh case home contains only the sandbox's
non-secret proxy configuration and credential placeholder.

Paired with-skill and without-skill runs use the same harness version, model
settings, worker policy, tools, network policy, fixtures, and prompt. The skill
projection is the intentional difference.

## Behavior Evals

Each skill defines behavior scenarios in `evals/evals.json`. The actor produces
normal user-facing work while the runner captures response, transcript, command
events, generated artifacts, and timing. Deterministic checks assess hard
artifact contracts. A separately isolated LLM judge grades semantic assertions
from sanitized evidence.

Workflow skills may dispatch other skills or native agents. Their evals should
verify both the collaborator choice, when observable, and the final result.

## Trigger Evals

Each skill defines pickup queries in `evals/triggers.json`. Trigger actors receive
the full retained public skill catalog but are not told which skill should be
selected. Positive and near-miss negative cases use the same result format as
behavior evals.

For Codex, activation requires a successfully completed command that reads the
exact installed target `SKILL.md`. A mention in prose is not activation proof.
Queries run once by default; `--runs 2` and `--runs 3` apply the same repetition
to every selected query.

## Fixtures

Most cases need no custom fixture. When a case does, keep its authored inputs
under `evals/fixtures/<eval-id>/` and reference them from `evals/evals.json`.

Production-shaped private HTTP(S) integrations use the pinned MockServer image
inside each actor worker's private Docker daemon. The shared runner owns proxy
configuration, certificate trust, startup, verification, and cleanup. A warm
sidecar, worker-scoped CA, and pulled image may be reused within one CLI
invocation, but expectations, request history, and fixture files are reset and
verified for every case. Private CA material is deleted with the worker.
Unmatched requests fail and are never forwarded to production.

Fixture proxy and CA variables are set through Codex's shell environment policy,
so only commands launched by the actor receive them. The Codex client itself
keeps Docker Sandboxes' generated model-provider route and host-proxied OAuth.
Login-shell profile loading is disabled for eval cases so a profile cannot
replace the runner-owned command environment.

Use fake service data, GraphQL responses, WebSocket transcripts, CLI shims, and
ephemeral certificates where they fit better than HTTP proxying. Authored fake
credential values start with `FAKE_`. Never use real private sessions or copy
machine-specific tooling into a case workspace.

## Results And Grading

Runs write reviewable artifacts outside the repository:

```text
outputs/response.md
transcript.md
execution_trace.jsonl
timing.json
grading.json
benchmark.json
```

The generated `grading.json` records each assertion, pass or fail, and concrete
evidence. A human may add a complete `manual_grading.json` with the same shape;
generated judge output remains unchanged. Aggregation can then use judge,
manual, or both grade sources.

Harness-native `error` and `turn.failed` messages are forwarded in bounded form
for diagnosis rather than reclassified into a repository-specific error
taxonomy.

## Runtime Maintenance

Changes to Docker Sandboxes, the Codex or template pin, case reset behavior,
fixture proxying, or judge isolation require corresponding test and documentation
updates. Report the relevant model-backed integration command, but do not run it
without explicit user approval.
