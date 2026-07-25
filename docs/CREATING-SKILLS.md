# Creating Skills

This guide is the authoring contract for skills in this repository. Start with
the public [Agent Skills specification](https://agentskills.io/specification),
then apply the repository policies below.

## Start With A Coherent Capability

A skill should teach a reusable procedure that adds knowledge or behavior the
agent would not reliably supply on its own. Base it on real tasks, corrections,
domain constraints, and failure cases. Keep related work together, but avoid a
scope so broad that the skill activates for unrelated requests.

Choose a lowercase, hyphenated name and place the skill under the most useful
subject group:

```text
skills/<group>/<skill>/
├── SKILL.md
├── scripts/                 optional executable runtime code
├── references/              optional on-demand instructions
├── assets/                  optional templates and resources
└── evals/
    ├── evals.json           required behavior cases
    ├── triggers.json        required pickup cases
    └── fixtures/            optional case inputs
```

The skill root may contain only these entries. Do not add empty directories,
placeholder files, generated output, or test infrastructure. Tests for
non-trivial bundled scripts belong under `tests/runtime/<suite>/`.
Do not use installer-omitted names anywhere in a skill tree:
`metadata.json`, `.git/`, `__pycache__/`, or `__pypackages__/`.
This applies to contained directory symlinks as well as physical directories.
Group and skill directory names must also avoid the public discovery exclusions
`node_modules`, `.git`, `dist`, `build`, and `__pycache__`.

## Write The Frontmatter

Every `SKILL.md` starts with strict YAML frontmatter:

```yaml
---
name: example-skill
description: >-
  Use when a user needs a specific outcome, including the important intents
  and near-neighbor wording that should activate this skill.
compatibility: >-
  Requires EXAMPLE_CONFIG_PATH. Uses the `related-skill` skill when available;
  otherwise returns a standalone draft.
metadata:
  status: config-required
  allows_tool_references: "true"
---
```

The public specification requires `name` and `description`. It also defines
optional `license`, `compatibility`, `metadata`, and experimental
`allowed-tools` fields. The repository additionally requires
`metadata.status`, using one of:

| Status | Meaning |
| --- | --- |
| `public-ready` | Portable without special local configuration |
| `config-required` | Requires a named environment or config-path variable |
| `local-required` | Requires documented local collaborators or capabilities |
| `experimental` | Installable but still being refined |

All statuses receive the same structural, trigger, and behavior coverage
requirements. A failing experimental skill is fixed rather than exempted.

Set `metadata.allows_tool_references: "true"` when the skill names tools,
harnesses, native agents, or other skills. In that case, `compatibility` must
state what is required and what happens when the collaborator is unavailable.
Use only `"true"` or `"false"` because metadata values are strings.
Do not define `metadata.internal`; the public installer reserves it for
excluding skills from normal discovery, so repository skills reject it.

## Write For Progressive Disclosure

The agent initially sees only a skill's name and description. Write the
description around user intent: what the skill does and when it should be used.
Include important near-neighbor phrases without making the scope universal.

When selected, the complete `SKILL.md` enters context. Keep it concise and
procedural:

1. State the scope and boundaries.
2. Give the normal workflow in execution order.
3. Make fragile operations and approval points explicit.
4. Include concrete fallbacks and non-obvious failure handling.
5. Define outputs only as tightly as the task requires.

Move conditional or detailed material into focused files under `references/`
and say exactly when to read each file. Keep references shallow and use paths
relative to the skill root, such as `references/api-errors.md`. Local links and
symlinks must remain inside the skill. Contained directory aliases are allowed
only when their directory graph is acyclic. Do not prefix bundled paths with a
checkout, home, drive, or other absolute location.

The upstream guides provide useful additional advice:

- [Best practices](https://agentskills.io/skill-creation/best-practices)
- [Optimizing descriptions](https://agentskills.io/skill-creation/optimizing-descriptions)
- [Using scripts](https://agentskills.io/skill-creation/using-scripts)

## Bundle Runtime Material

Place reusable executable logic in `scripts/`. A script should be
self-contained or document its dependencies, support non-interactive use,
provide useful `--help` and errors, and emit structured output when another
program will consume it. Make executable files executable in Git.

Keep every script and configuration helper needed by a skill inside that skill
folder, even when another skill needs similar logic. This preserves portable,
independent installation. Never hardcode personal filesystem paths or real
credentials. Authored credential-shaped test values begin with `FAKE_`.

Use `assets/` for templates or resources used as inputs or outputs. Use
`references/` for material an agent reads. A behavior case must exercise real
bundled material whenever the skill contains scripts, references, or assets.

## Define Behavior Cases

Every skill has `evals/evals.json`. A case describes a realistic task, success
in human-readable terms, and semantic assertions:

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": "handles-missing-record",
      "prompt": "Use the available example command to inspect account 42 and prepare the requested report.",
      "expected_output": "A complete report that identifies the missing record and recommends the supported recovery path.",
      "assertions": [
        "The report distinguishes a missing record from an authorization failure.",
        "The recovery recommendation follows the supported workflow."
      ],
      "files": [
        "fixtures/handles-missing-record/inputs/bin/example"
      ],
      "checks": []
    }
  ]
}
```

Actor prompts must read like ordinary user tasks. Do not tell the actor that it
is being evaluated or reveal expected results, assertions, grading rules,
fixture mechanics, or sandbox internals. When a case declares an executable
under `inputs/bin/`, the runner adds that directory to `PATH`; name the command
normally in the prompt. Expected output and assertions remain runner-only.

Ordinary owner phrasing such as "my repository" is allowed only when the case
declares contained actor inputs or HTTP initialization that establish its
isolated data boundary. Without those resources, private-state wording fails
validation. Explicit `live`, `production`, `real`, `private`, or `logged-in`
resource requests always fail, and fixtures never contain real credentials or
private sessions.

Use semantic assertions for meaning and quality. Avoid exact prose matching.
The approved deterministic checks cover only hard contracts:
`file_exists`, `path_absent`, `json_schema`, `exit_code`,
`no_secret_patterns`, and `response_protocol`.

## Define Trigger Cases

Every skill also has `evals/triggers.json`:

```json
{
  "skill_name": "example-skill",
  "queries": [
    {
      "id": "specialized-request",
      "query": "Can you diagnose why this account export has incomplete rows?",
      "should_trigger": true
    },
    {
      "id": "nearby-general-request",
      "query": "Can you explain what a CSV row is?",
      "should_trigger": false
    }
  ]
}
```

Include at least one realistic positive and one near-miss negative. Near-miss
negatives should share vocabulary with the skill while genuinely requiring a
different capability. Run counts are CLI configuration and do not belong in
the file.

## Add Fixtures Only When Needed

Most cases need no fixture. When a case requires files, commands, service
responses, or other controlled state, create only that case's material under
`evals/fixtures/<eval-id>/`. See [Evaluation](EVALUATION.md#fixtures-and-integrations)
for CLI shims, HTTP(S), GraphQL, WebSocket, certificate, and local-tooling
patterns.

Outside `evals/evals.json`, `evals/triggers.json`, and optional fixture files,
do not create skill-specific test artifacts.

## Machine-Enforced Reference

The prose above explains how to author a skill. These checked-in contracts are
the exact source of truth for limits and accepted shapes:

- [`evals.schema.json`](../schemas/ai-skills/evals.schema.json)
- [`triggers.schema.json`](../schemas/ai-skills/triggers.schema.json)
- [`frontmatter.py`](../scripts/ai_skills_lib/frontmatter.py)
- [repository policy checks](../scripts/ai_skills_lib/static_checks/policy.py)
- [topology checks](../scripts/ai_skills_lib/static_checks/topology.py)
- [content checks](../scripts/ai_skills_lib/static_checks/content.py)

The main enforced bounds are:

| Contract | Bound |
| --- | --- |
| Skill name | 1-64 lowercase letters, numbers, and single hyphens; unique and equal to the folder name |
| Description | Non-empty, at most 1,024 characters |
| Compatibility | Optional unless required by status; at most 500 characters |
| Behavior file | UTF-8 JSON, at most 2 MiB, with 1-128 cases |
| Behavior case | Path-safe ID up to 64 characters; prompt up to 16 KiB; expected output up to 8 KiB |
| Assertions | 1-64 per case, each up to 4 KiB |
| Inputs and checks | At most 64 of each per case; canonical contained paths up to 512 characters |
| Deterministic schemas | At most 256 KiB each and 512 KiB total per case |
| Fixture file | Regular file at most 4 MiB below its exact case root |
| Trigger file | 1-128 queries with path-safe IDs and prompts up to 16 KiB |

Unknown skill-root entries, broken, escaping, or cyclic directory symlinks,
empty directories, `.gitkeep` placeholders, non-executable files under
`scripts/`, personal paths, private-key blocks, and high-confidence credential
literals fail validation.
When bundled runtime material exists, at least one behavior case must name and
exercise it. MockServer definitions have their own exact matcher, static action,
finite repetition, and total-call rules described in [Evaluation](EVALUATION.md).

## Validate The Skill

Run the deterministic gate while authoring:

```bash
scripts/ai-skills validate ci-all
```

Model-backed trigger and behavior runs cost model usage and require explicit
user approval. They are described in [Evaluation](EVALUATION.md).

Before submitting a skill, confirm:

- The name, directory, description, frontmatter, and relative references pass.
- Installable references and assets contain no credential literals; fake
  credential values use the `FAKE_` prefix.
- Runtime material is self-contained and its dependencies are documented.
- Collaborators have an explicit availability and fallback contract.
- Behavior prompts are realistic and evaluation-blind.
- Assertions measure observable outcomes without requiring fixed prose.
- Trigger cases cover both intended pickup and a meaningful near miss.
- Fixtures expose only the interfaces the actor needs.
- `validate ci-all` passes.
