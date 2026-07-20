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

The manifest pins a digest of the complete normalized Docker balanced-network
rule set. Actors retain that broad tool access, but preflight fails if a rule,
resource, or wildcard is added, removed, or changed without an intentional pin
update.

Follow the [Docker Sandboxes setup guide](https://docs.docker.com/ai/sandboxes/get-started/),
then authenticate Codex on the host before creating workers:

```bash
sbx login
sbx secret set -g openai --oauth
```

- A command creates at most one reusable actor worker per concurrency slot.
- Before creation, the runner proves the invocation-specific worker name is
  absent. If creation times out after the sandbox appears, it removes that
  proven invocation-owned sandbox and verifies absence. If identity lookup is
  temporarily unavailable, the unresolved cleanup target and its staging root
  remain recorded for a later verified cleanup attempt.
- Judges use a separate worker pool and never receive the actor skill catalog.
- Every case receives a fresh unprivileged Linux user and group, staged skill
  projection, workspace, `CODEX_HOME`, XDG state, temporary directory, and
  ephemeral harness session. The previous identity, processes, and writable
  temporary residue are removed before worker reuse. SysV IPC owned or created
  by the retiring UID, POSIX queues, and shared-memory residue are also removed
  and verified. The
  reset fails closed unless every `/proc/sysvipc` table is readable and
  `/dev/mqueue` is proven to be an `mqueue` mount; an unverifiable worker is
  removed instead of reused.
- After the actor command completes, the runner terminates any process still
  owned by that case identity before it collects request or artifact evidence.
  Failure to quiesce the case removes the worker and invalidates the attempt.
- Durable results stay outside the actor mount. Judges receive only the
  sanitized artifacts needed for grading.
- A failed reset fails the case and removes the affected worker instead of
  silently reusing uncertain state.
- Workers and their private Docker resources are removed when the command ends.

Preflight checks every named Docker diagnostic, a valid pinned template digest
prefix, the complete network-policy digest, host-proxied OAuth, and a real
write/read/delete cycle in the durable result root. When selected cases need
HTTP fixtures, preflight also starts the pinned sidecar, proves private control
state is actor-inaccessible, and verifies unauthenticated control requests are
denied before any model call.

Each worker receives one invocation-owned staging root, mounted at the same
absolute path inside the microVM. The canonical repository, durable result
directory, host home, and another worker's staging root are never mounted.
Actor projections contain only `SKILL.md`, `scripts/`, `references/`, and
`assets/`; `evals/` and all grading material remain host-side.

Codex authentication is managed by the Docker Sandboxes host proxy. The runner
does not copy `~/.codex`, `auth.json`, API keys, browser sessions, or other
private host state into a worker. A fresh case home contains only the sandbox's
non-secret proxy configuration and credential placeholder. The case identity
cannot read the immutable proxy source or access the worker-private Docker
socket.

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
The target must exist in the runner-created projection before Codex starts; a
file created by the actor during the run cannot become activation evidence.
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
Every authored expectation represents one required call by default; finite
`times` values declare repeated calls. The runner verifies the complete call
sequence before grading, so missing, extra, repeated, and out-of-order requests
fail. Failed verification still preserves the bounded, redacted requests that
were observed for review. Unmatched requests fail and are never forwarded to
production. A fixture may declare at most 128 total expected calls.

Authored expectations are validated offline against the version-matched
vendored MockServer schema. Repository policy permits only static
`httpResponse` or `httpError` actions with restrained exact request matchers;
forwarding, callbacks, executable templates, generated responses, and file
bodies are rejected. Delays, relaxed body matching, and unbounded repetition
are also rejected. Every expectation requires a non-empty exact method, path,
and `Host` matcher. Before upload, the runner Java-regex-quotes authored request
strings so regex metacharacters remain literal and enables MockServer's exact
case matching for methods and paths. This keeps fixture files
declarative and prevents them from becoming code or an alternate path to
production.

MockServer's control API is protected by a worker-specific asymmetric JWT key.
The private signing key remains in runner memory, while the public JWK, short
lived control token, expectations, request history, and private CA files remain
runner-only. The actor can reach the loopback data plane but cannot read or
mutate control state. Only the generated public CA is copied into the case; its
fingerprint must differ from MockServer's pinned bundled CA and from every
other active worker CA.

The control token is refreshed before post-run request collection. Persisted
fixture evidence keeps bounded method, host, path, header-name, query, and body
metadata only; every durable scalar is bounded and high-confidence or `FAKE_`
credential values are redacted.

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

Each invocation creates one collision-safe result workspace outside the
repository. Its `attempts/` directory contains a separate collision-safe
workspace for every declared run:

```text
summary.md
benchmark.json
attempts/<attempt>/attempt.json
attempts/<attempt>/outputs/response.md
attempts/<attempt>/transcript.md
attempts/<attempt>/execution_trace.jsonl
attempts/<attempt>/timing.json
attempts/<attempt>/grading.json
```

The runner writes the immutable, schema-validated `attempt.json` before external
execution. It anchors run identity, variant membership, contribution policy,
required variants, and comparisons. Failed attempts preserve available
response, transcript, normalized trace, and timing without inventing a grade.

The generated `grading.json` records every assertion result, concrete evidence,
and judge model/reasoning metadata. A human may add a complete
`manual_grading.json` with the same schema; generated output remains unchanged.
Aggregate preserved results offline with:

```bash
python3 scripts/ai_skills.py evals aggregate \
  --results-dir <invocation-result-directory> \
  --grade-source judge|manual|both
```

Aggregation rejects undeclared, partial, failed, mismatched, or unbalanced
attempts. It reports judge and manual summaries separately when `both` is used;
the complete manual grade is the effective override for the command outcome.
Exit `0` means all contributing effective grades passed, exit `1` means a
trusted contributing assertion failed, and exit `2` means the result set is
invalid or untrustworthy.

Harness-native `error` and `turn.failed` messages are forwarded in bounded form
for diagnosis rather than reclassified into a repository-specific error
taxonomy.

Codex JSONL is parsed in memory. Durable traces retain normalized lifecycle,
command-name, exit-status, usage, and exact skill-read evidence without raw
command output, thread identifiers, hidden reasoning, or full skill bodies.

## Runtime Integration Checks

Routine runtime tests use a fake `sbx` process boundary and run under
`validate ci-all`. The real Docker Sandboxes smoke is separately opt-in:

```bash
AI_SKILLS_RUN_MODEL_INTEGRATION=1 \
  python3 -m unittest \
  tests.integration.eval_runtime.test_docker_sandboxes_smoke \
  tests.integration.eval_runtime.test_fixture_proxy_smoke
```

Run it only after explicit user approval. It invokes Codex with saved
host-proxied authentication and may incur model usage. The smoke verifies the
pinned runtime, disposable case identities, actor reuse and reset, with-skill
versus without-skill pickup, a separate skill-free judge worker, authenticated
fixture control, production-shaped HTTPS interception, unmatched-request
denial, shell-only proxy routing, and complete teardown. The environment
variable is an additional guard against accidental discovery; setting it is
not itself approval.

## Runtime Maintenance

Changes to Docker Sandboxes, the Codex or template pin, case reset behavior,
fixture proxying, or judge isolation require corresponding test and documentation
updates. Report the relevant model-backed integration command, but do not run it
without explicit user approval.
