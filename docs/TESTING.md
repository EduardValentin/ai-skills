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
skill installations. Official conformance is preflighted exactly once by the
shared repository validation phase.

Deterministic executable tests live in named suite directories directly below
`tests/runtime/`. Each suite must contain at least one regular `test_*.py`
module. When `tests/runtime/` exists, root-level files, symlinks, hidden entries,
empty suites, and an empty runtime root fail instead of producing a vacuous
success. A missing runtime root is a successful no-op only while the repository
has no deterministic runtime suites.

## Local Install Diagnostic

After explicit approval for pull-request creation, inspect Codex's active local
skills with:

```bash
python3 scripts/ai_skills.py check-local-installs --harness codex
```

This machine-specific command is not part of `validate ci-all`. It is strictly
read-only and returns `0` when every repository skill has one current active
install, `1` for missing, stale, duplicate, malformed, or attributed-extra
installs, and `2` for invalid invocation or environment state. It reads
`$CODEX_HOME/skills` (defaulting to `$HOME/.codex/skills`) and
`$HOME/.agents/skills`. Whole-root and per-skill aliases are deduplicated only
when descriptor identity proves that they target another configured active
root or skill.

When `XDG_STATE_HOME` is configured, lock attribution comes only from
`$XDG_STATE_HOME/skills/.skill-lock.json`; otherwise it comes from
`$HOME/.agents/.skill-lock.json`. Only integer lock versions `3` or newer can
prove repository ownership. Root enumeration, lock/frontmatter reads, and
content hashing are bounded, special files are rejected without blocking, and
unrelated third-party skill content is not opened. A linked worktree and its
main checkout are treated as equivalent local sources only when matching Git
common-directory metadata proves the relationship. Repository skill discovery
uses a diagnostic-local no-follow descriptor adapter: it requires a regular
`SKILL.md`, parses only bounded stable bytes, and retains the exact source
manifest for comparison. Repository identifiers and Git metadata are derived
through the same anchored repository descriptor used by discovery; root,
common-directory, and proven main-checkout identities are rechecked before the
inspection returns. Git path/config reads are bounded before allocation, and a
single aggregate entry budget spans every source and installed manifest,
including zero-byte files. This does not replace or weaken shared core
validation.

## Model-Backed Testing

Behavior and trigger evaluation are opt-in:

```bash
python3 scripts/ai_skills.py validate evals --harness codex
python3 scripts/ai_skills.py validate triggers --harness codex
python3 scripts/ai_skills.py validate all --harness codex
```

Model-backed commands select every skill by default. Trigger runs accept
`--skill <name>`, `--query <id>`, `--runs 1|2|3`,
`--max-concurrency 1|2|3|4`, and `--results-dir <external-path>`.
Behavior runs accept `--skill <name>`, `--case <id>`,
`--max-concurrency 1|2|3|4`, and `--results-dir <external-path>`.
Complete runs accept `--skill <name>`, trigger repetition through
`--runs 1|2|3`, the same concurrency choices, and one shared result root. They
run the trigger and behavior suites through one preflighted runtime rather than
performing duplicate preflight calls.

These commands run only after explicit user approval. Before the first model
call, the CLI prints actor and judge run counts, preflight calls, concurrency,
and the durable result directory. Every attempted run is preserved; the runner
does not hide instability with automatic retries. The durable result path is
printed again on every success or failure after a workspace has been created.
Full offline static validation must pass before model-backed setup begins. The
runner loads definitions once, freezes the exact selected attempts, and writes
their invocation manifests before preflight. Declared actor inputs, fixture
initialization, and runner-only schemas are materialized and hash-frozen at
that boundary; execution never reopens their authored files. `validate all`
prepares both sub-runs before its single shared preflight and does not reload
definitions between trigger and behavior execution.

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
  absent and creates a unique 256-bit ownership marker in host staging. If
  creation returns an unknown sandbox identity, the runner adopts it only after
  reading and matching that exact marker from the candidate. If creation times
  out after the sandbox appears, it removes that proven invocation-owned
  sandbox and verifies absence. When an interrupted create has no authoritative
  completion or cancellation result, empty listings never prove absence; its
  exact target, ownership marker, and staging remain until the sandbox is
  positively identified and removed.
- Invocation shutdown attempts every owned worker even when an earlier cleanup
  fails. Still-pending workers receive one final reconciliation by their exact
  recorded sandbox name and ID; cleanup never scans or removes by a broad name
  prefix. Unresolved sandbox or host-staging failures are reported together in
  one bounded, redacted diagnostic, and host staging is retained until sandbox
  removal is trustworthy.
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
- All case-writable paths share one verified tmpfs capped at 256 MiB and 32,768
  inodes. The case identity cannot create user or mount namespaces, access
  FUSE, or create mounts. Execution and export both fail closed if the case
  mount tree contains an unexpected nested or stacked mount, and seed/export
  copies never cross a filesystem boundary.
- Every case command enters a dedicated cgroup v2 leaf. Before IPC cleanup,
  evidence export, or worker reuse, the runner freezes that leaf, invokes
  `cgroup.kill`, and proves both `populated=0` and an empty `cgroup.procs`.
  Missing or ambiguous cgroup controls fail closed, remove the worker without
  exporting evidence, and invalidate the attempt.
- Durable results stay outside the actor mount. Judges receive only the exact,
  prevalidated artifacts needed for grading.
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
`assets/`; `evals/` and all grading material remain host-side. Before actor
execution, the complete catalog becomes root-owned and read-only. Its
`CODEX_HOME` parent is root-owned with sticky write permissions so Codex can
create its own state but the case user cannot rename or replace the root-owned
catalog entry. The case root is also root-owned and read-only, with actor-owned
writable child directories prepared in advance. Rename probes for the catalog,
`CODEX_HOME`, and case root must all fail before the model runs, anchoring the
projection path at the non-actor-writable worker mount root.

Codex authentication is managed by the Docker Sandboxes host proxy. The runner
does not copy `~/.codex`, `auth.json`, API keys, browser sessions, or other
private host state into a worker. A fresh case home contains only the sandbox's
non-secret proxy configuration and credential placeholder. Before transferring
those files to the case identity, the runner requires the byte-for-byte canonical
profile generated by the pinned Docker Sandboxes runtime: the fixed `sandboxd`
provider, `https://chatgpt.com/backend-api/codex` endpoint and provider settings,
and only the documented `{"OPENAI_API_KEY":"proxy-managed"}` auth placeholder.
Alternate comments, whitespace, ordering, suffixes, or any other byte fail before
decoding. The runner then parses both files against exact closed shapes so unknown
providers, headers, MCP/tool settings, security settings, fields, values, and
types also fail as defense in depth. A digest additionally prevents the canonical
profile from changing between cases; neither schema validation nor a first-seen
digest establishes baseline trust. The case identity cannot read the immutable
proxy source or access the worker-private Docker socket.

Actor commands can use the same OpenAI eval principal as Codex. This trust model
intentionally does not claim endpoint-level principal separation. When isolation
from a personal account matters, use a dedicated quota-limited eval principal.

Oracle isolation is a runner boundary, not a claim that committed public files
are confidential. Expected outputs, assertions, trigger answers, schemas,
grades, and fixture control data are omitted from actor prompts, projections,
workspaces, and mounts. Actors intentionally keep the pinned normal network
policy so integration behavior remains realistic. A deliberately adversarial
skill could still fetch files that are publicly available from the repository
origin; preventing that would require private held-out evals or restrictive
egress and is outside this network-enabled evaluation threat model.

Paired with-skill and without-skill runs use the same harness version, model
settings, worker policy, tools, network policy, fixtures, and prompt. The skill
projection is the intentional difference. The with-skill actor receives the
complete retained repository catalog. The without-skill actor receives the same
catalog with only the target skill removed, so collaborator and competing-skill
behavior remains realistic.

## Behavior Evals

Each skill defines behavior scenarios in `evals/evals.json`. The actor produces
normal user-facing work while the runner captures response, transcript, command
events, generated artifacts, and timing. Deterministic checks assess hard
artifact contracts. A separately isolated LLM judge grades semantic assertions
from exact evidence that has passed the runner's bounded secret checks.

Every case has a path-safe `id`, actor-facing `prompt`, runner-only
`expected_output`, at least one semantic `assertion`, optional declared input
`files`, and optional deterministic `checks`. The actor receives only the
prompt, installed runtime skill projections, and declared files. Expected
output, assertions, schemas, proxy expectations, grades, and trigger answers
remain runner-side.

Actor input paths are relative to the skill's `evals/` directory and must stay
below `fixtures/<eval-id>/inputs/`. They are staged at the corresponding path
below the fresh actor workspace. Every fixture file is limited to 4 MiB in both
static validation and runtime preparation. After execution is quiescent, the
adapter preserves only regular files the actor created or changed. Unchanged
inputs are not copied into results. Both the initial and final workspace snapshots are
bounded before file reads by entry, directory, depth, per-file, and cumulative
byte limits; the cumulative and per-file caps use
`maximum_captured_output_bytes`. Fixed structural caps allow 2,048 entries, 256
directories including the workspace root, depth 32, and 256 changed output
files. Files are read through no-follow descriptors and mutation during capture
fails closed. Symlinks, special files, and an actor-created `response.md`
collision also fail the attempt. The runner owns `outputs/response.md` for the
final harness response. The full response must fit the durable 64 KiB policy
without truncation or redaction; otherwise the attempt is invalid before checks
or judging because those consumers would not see exact evidence. The same rule
applies to captured actor evidence: safe content, including approved `FAKE_`
values, remains exact. Evidence that contains a classified credential or needs
size-driven transformation is quarantined and invalidates the attempt; only a
bounded redacted diagnostic is retained, and transformed content is never
passed to checks or the judge as if it were the actor's output.

Before either deterministic checks or semantic judging, the runner prepares one
complete judge evidence map containing the response, transcript, frozen actor
trace, and every captured regular output. Each value must be exact UTF-8 text of
at most 32 KiB, and the complete rendered judge prompt must be at most 512 KiB.
Non-text output, per-artifact overflow, or aggregate overflow invalidates the
attempt before either consumer runs. The runner never substitutes a binary
placeholder, truncates a value, or drops a later artifact to make the prompt
fit; the failed attempt records only a bounded failure diagnostic and no grade.

Deterministic checks are deliberately narrow:

- `file_exists` requires one regular output-relative file.
- `path_absent` requires one output-relative path to be absent.
- `json_schema` validates one JSON output against a runner-only case schema.
- `exit_code` requires `expected: 0` and confirms successful actor harness
  execution. A nonzero harness exit invalidates the attempt instead of becoming
  an authored success condition.
- `no_secret_patterns` scans the final response and captured text outputs with
  the shared high-confidence secret registry.
- `response_protocol` requires strict JSON or JSONL and may apply a runner-only
  schema to the parsed response.

Runner-only schemas use the same bounded subset for `json_schema` and
`response_protocol`: at most 256 KiB, 512 nodes, depth 32, 128 acyclic local
references, and 64 materialized errors. Structural type/property/item rules,
required fields, enums, constants, numeric limits, and size limits are allowed.
External or recursive references, regex keywords, branching combinators,
conditionals, and advanced unbounded keywords fail static validation.

Semantic assertions are sent to a separate judge worker after deterministic
checks. The judge receives the expected result, assertion IDs and text, a list
of allowed evidence artifacts, and the exact prevalidated response, transcript,
normalized trace, and captured text outputs. It receives no skill
catalog, actor files, fixtures, shell environment, or writable actor workspace.
The judge runs read-only with shell, web search, remote plugins, and skill
dependency installation disabled. Immutable developer instructions identify
all artifact content as untrusted evidence and preserve the runner's grading
oracle. A runner-owned JSON Schema constrains the response at the Codex boundary;
the parser then requires every assertion exactly once and an allowed evidence
reference for every verdict. Malformed or failed judge output is preserved only
as bounded, redacted diagnostic evidence. There are no hidden actor or judge
retries.

Workflow skills may dispatch other skills or native agents. Their evals should
verify both the collaborator choice, when observable, and the final result.
Both variants must complete and receive valid grades. Only the with-skill grade
controls behavior-eval success; the without-skill grade and pass-rate delta are
comparison evidence and may legitimately pass or fail.

## Trigger Evals

Each skill defines pickup queries in `evals/triggers.json`. Trigger actors receive
the full retained public skill catalog but are not told which skill should be
selected. Positive and near-miss negative cases use the same result format as
behavior evals.

Each file names its skill and contains uniquely identified queries with a
non-empty prompt and boolean `should_trigger`. It may contain 1 to 128 queries;
query IDs are at most 64 characters and each UTF-8 prompt is at most 16 KiB. At
least one positive and one near-miss negative query are required. Run counts are
CLI policy and never belong in the authored file. A selected invocation is
limited to 128 queries and 384 model calls. The file must be a contained
non-symlink regular file, and high-confidence credential literals fail before
workspace creation.

For Codex, activation requires a successfully completed command that reads the
exact installed target `SKILL.md`. A mention in prose is not activation proof.
The target must exist in the runner-created projection before Codex starts; a
file created by the actor during the run cannot become activation evidence.
Missing expected-path evidence is an execution error, including for negative
queries; failed setup cannot become a passing absence assertion.
Queries run once by default; `--runs 2` and `--runs 3` apply the same repetition
to every selected query. One, two, or three unanimous matching runs are stable.
Two of three enters a durable `pending_review` state and exits nonzero without
automatically generating `benchmark.json`. Every attempt remains available in
the result workspace; after the failed run is investigated, the existing
explicit aggregation command may apply the declared two-of-three threshold.
Every other non-unanimous result fails. Harness, timeout, and evidence errors
are reported separately and never averaged into the threshold.
Trigger grading is deterministic and cites exact normalized trace evidence; it
does not spend a separate judge call.

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
machine-specific tooling into a case workspace. Static prompt validation uses a
conservative lexical gate for explicit owned/live resources; qualify the exact
resource as fake, mock, fixture, sandbox, simulation, or transcript data. The
LLM judge and human review remain responsible for broader semantic private-state
concerns.

## Results And Grading

Each invocation creates one collision-safe result workspace outside the
repository. Its `attempts/` directory contains a separate collision-safe
workspace for every declared run:

```text
summary.md
benchmark.json
invocation.json
attempts/<attempt>/attempt.json
attempts/<attempt>/outputs/response.md
attempts/<attempt>/transcript.md
attempts/<attempt>/execution_trace.jsonl
attempts/<attempt>/timing.json
attempts/<attempt>/grading.json
```

Once a result workspace exists, `summary.md` is always written with the terminal
decision, including setup, preflight, execution, or aggregation errors and
available attempt artifact paths. `benchmark.json` is written only when the
complete declared attempt set can be aggregated as trustworthy evidence.

Before external execution, the runner writes schema-validated `invocation.json`
with the exact expected attempt set, then writes each immutable `attempt.json`
before its harness call. These declarations anchor run identity, variant
membership, contribution policy, required variants, comparisons, repetition
count, and ordinal. Aggregation rejects missing, injected, duplicate, or changed
attempt declarations. Failed attempts preserve available response, transcript,
normalized trace, and timing without inventing a grade.

The generated `grading.json` records every assertion result and concrete
evidence. Behavior grades include judge model/reasoning metadata; trigger grades
identify the deterministic trigger runner. A human may add a complete
`manual_grading.json` with the same schema; generated output remains unchanged.
Aggregate preserved results offline with:

```bash
python3 scripts/ai_skills.py evals aggregate \
  --results-dir <invocation-result-directory> \
  --grade-source judge|manual|both
```

Offline aggregation treats the supplied result directory as untrusted. It
accepts at most 1,024 declared attempts and scans at most 100,000 entries, 40
levels, and 256 MiB across the result tree. Parsed JSON files are limited to 4
MiB, depth 32, and 100,000 nodes. Symlinks, special files, excess or undeclared
entries, unstable reads, and mutations during aggregation fail closed.

Aggregation rejects undeclared, partial, failed, mismatched, or unbalanced
attempts. It reports judge and manual summaries separately when `both` is used;
the complete manual grade is the effective override for the command outcome.
Repeated trigger attempts preserve every run while applying the declared
runner threshold at query level. Every attempt records the configured run count
and its ordinal, and aggregation requires the exact complete run set before
applying that threshold. The trigger runner defers aggregation when a
two-of-three result is pending review and records the reason in `summary.md`;
the reviewer uses the same explicit offline aggregation command after
investigating the discordant run. Per-skill benchmark summaries include the
observed `trigger_rate` measurement, so actual pickup frequency remains visible
even when the expected positive or negative outcome passed.
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
