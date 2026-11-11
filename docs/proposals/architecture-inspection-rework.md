# Architecture inspection rework proposal

Date: 2026-11-10  
Status: Draft for discussion; not an approved implementation plan  
Scope: `inspect-architecture-workflow`, its bundled analysis tools, and its architecture agents

## Purpose

Rework the skill into a focused reviewer of how changes affect application
maintainability. Use Clean Architecture as a source of principles while requiring
each recommendation to fit the application's needs and established decisions.

The central question should be:

> Does this change make the next reasonable change harder, and what is the
> smallest correction that prevents that?

The review should recognize both insufficient separation and excessive
separation. Keeping a small, understandable implementation should be a valid
outcome. Compliance with a particular arrangement of layers, interfaces, or
classes should not be sufficient justification for adding structure.

This document consolidates the discussion from October 27 through November 10,
2026. It distinguishes user feedback, observed limitations, and proposed
solutions. Writing this proposal does not approve changes to the skill or to an
application's architecture.

## Current responsibilities and mechanisms

The skill supports three modes: auditing a repository or area, reviewing a
written implementation plan, and reviewing a code change. It maintains a
committed architecture record, generates a dependency graph, dispatches agents,
and records findings, acceptances, and proposed improvements in a local ledger.

Its eight evaluation workflows cover:

| Workflow | Current concern |
| --- | --- |
| W1 | Dependency direction, interfaces, ownership, construction, and justified abstractions |
| W2 | Reasons to change, shared behavior, interfaces, inheritance, encapsulation, control flow, and mutation |
| W3 | Placement of business rules, application sequencing, and boundary data |
| W4 | Thin I/O adapters, presentation decisions, rendering, and storage access |
| W5 | Boundary justification, infrastructure independence, deferred choices, deployment topology, and development sequence |
| W6 | Component cohesion, cycles, stability, abstraction, change propagation, and release boundaries |
| W7 | Test boundaries, production isolation, behavioral access, and coupling to implementation structure |
| W8 | Enforced boundaries, published surfaces, forbidden dependencies, and code organization |

### Existing tools versus custom code

The table below describes the current JavaScript/TypeScript implementation,
not a required toolchain for projects using the reworked skill. The requested
direction is a technology-agnostic skill with project-owned adapters for both
metric collection and architectural enforcement.

| Mechanism | Responsibility |
| --- | --- |
| dependency-cruiser | Discovers source imports and dependency relationships |
| TypeScript compiler API | Provides syntax and type information used by the custom adapter |
| Git | Supplies versions, changed paths, renames, and file history |
| Node.js | Executes the bundled scripts |
| Custom language adapter | Runs extraction, interprets compiler facts, normalizes results, and reports unsupported or missing information |
| Custom `arch` commands | Apply classifications, construct and query the graph, calculate metrics, perform implemented deterministic assessments, and maintain artifacts |
| Coordinator | Establishes scope, maintains the model, prepares evidence, dispatches agents, consolidates results, and writes records |
| Code auditor | Reads source to propose classifications or answer targeted factual questions |
| Evaluator | Applies decision rules to supplied evidence and requests missing facts |

In the implementation examined during this discussion, automated assessments
cover selected W1 and W6 conditions. W2 and W3 have no dedicated deterministic
assessments. A precise condition is not necessarily automated: counting how many
interface members a consumer uses is still assigned to an agent today.

The language adapter currently supports JavaScript and TypeScript. Supporting
another language requires an adapter; a generic architectural rule does not
establish that its evidence can be extracted for every stack.

### Classification and evidence

The inspected project stores its model in `docs/architecture/model/`:

- `components.json`: component membership, tooling configuration, entry points,
  enforcement, and release information.
- `rules.json`: ordered layers and file-pattern classifications for kind, layer,
  and actors.
- `overrides.json`: individual file classifications that override general rules.
- `boundaries.json`: ports, shared shapes, and cohesion groups.

Agents establish the classifications. The initial audit seeds rules from
conventions and structure; code auditors classify uncovered modules from their
behavior. Subsequent graph generation applies an override or the first matching
rule. Tools do not infer business ownership or semantic responsibility merely by
parsing imports.

The model is reused and updated rather than recreated on each run. This means
complete classification coverage does not prove classification correctness.
Files covered by broad rules do not automatically receive individual source
inspection on every run.

During the October 28 inspection of `eli-coach-platform`, the saved model had 30
classification rules, no individual overrides, and empty actor lists throughout.
This is a dated observation, not a current audit of that application. It showed
why a graph can be fully classified yet lack evidence needed for actor-based
checks.

## Feedback and concerns collected

### 1. Make check groups self-contained

The user's concrete proposed direction is to define groups with:

- Explicit inputs, identifying exactly what comes from collected evidence.
- Explicit additional inputs when evidence must come from elsewhere.
- Steps tied to the rule being checked.
- Any necessary metadata.

The current separation between a numbered procedure and a condition table makes
the reader infer which steps establish which conditions. The mapping is not
necessarily one-to-one, and neither section alone clearly establishes coverage.

Rule prose and evaluation conditions also appear in separate files. The user
wants to avoid duplication; whether to consolidate the files remains open.

### 2. Separate structural review from development guidance

The user questioned R23's requirement to start ports in memory and the related
R26 requirement to sequence domain rules before frameworks, schemas, or screens.
These prescribe a development approach. Building a screen first does not itself
establish an architectural defect.

The proposed distinction is to retain assessment of infrastructure independence
and testability while treating domain-first delivery and initial in-memory
implementations as optional planning guidance.

The user also challenged R24's treatment of service splits. Once a microservice
decision has been made, a scoped implementation review should verify the chosen
architecture rather than automatically reopen the decision. Topology evaluation
belongs in an explicitly scoped design discussion or reassessment.

### 3. Make automation and agent judgment visible

The discussion repeatedly exposed a difference between a mechanically stated
criterion and a mechanically implemented check. Several inspections currently
require agents to count, search, and infer facts that tooling could partly
provide.

Each check should identify whether extraction and evaluation are automated,
agent-based, or mixed. A successful query with missing capabilities must not be
interpreted as proof that a violation is absent.

Possible tooling improvements discussed include interface-member usage,
substitution sites, implementation-specific type checks, public mutable data,
and mutation sites. These remain candidates, not a selected implementation scope.
Dynamic access, aliases, external calls, and semantic ownership limit what can be
decided reliably.

### 4. Clarify terminology and abstraction levels

| Term or wording | Concern from the discussion | Proposed clarification |
| --- | --- | --- |
| Gateway | The vocabulary and R22 use it for a business-owned port, while classification uses it for the infrastructure implementation | Use distinct names for the contract and implementation; decide whether `gateway` remains useful |
| Adapter | Its relationship to gateway and plugin is unclear | Define its concrete translation responsibility and make any specializations explicit |
| Plugin | Sometimes describes an external technology, sometimes its adapter | Reserve plugin architecture for the dependency and replaceability relationship, rather than another interchangeable component label |
| Many-formed component | Unclear shorthand | Say that the capability can have alternative implementations; do not imply several must be built |
| Device boundary | Explained by examples but not explicitly defined in the glossary | Define the separation between decisions and external interaction, including screens, storage, network, and clocks |
| Boundary | “For every boundary” lacks a complete enumeration contract | Identify what qualifies, its source of evidence, its owner, and its enforcement mechanism |
| Metrics | Used loosely for imports, classifications, and other facts | Use collected evidence as the umbrella term; reserve metrics for measured quantities |

The blanket statement that plugins never depend on one another needs separate
justification. Core independence does not, by itself, establish every possible
restriction between outer components.

### 5. Clarify presentation responsibility

The presenter prepares data for the view. Its architectural role does not assign
it to a particular deployment location: it can run in a browser-side SPA or on
the server in a server-rendered application.

“Dates and money arrive formatted” refers to arrival at the view, not necessarily
at the frontend through an API. Locale, timezone, and changing relative-time
labels belong to the presentation context.

The distinction between binding, mapping a display flag to appearance, and
deriving a decision from domain data needs concrete examples. Whether every
formatting operation warrants a separate presenter remains a tradeoff to decide.

### 6. Explain overlaps and avoid redundant findings

W1's dependency rules overlap with W3's entity restrictions. Some overlap adds a
stricter entity-specific requirement; some describes the same dependency problem
under another rule number.

The current finding identity is target plus rule. Different rules can therefore
produce duplicate-looking findings for one underlying defect. Consolidation
should preserve distinct evidence while avoiding repeated correction requests.

### 7. Make classification quality and missing evidence explicit

Actor lists, unit kinds, layer assignments, and component membership determine
which checks run and how evidence is interpreted. Empty actors are missing
ownership evidence, not evidence that only one owner exists.

Broad pattern rules can become inaccurate as files evolve. The review needs an
explicit policy for reassessing classifications without requiring a full manual
classification pass on every small change.

## Proposed direction

Technology independence and project-owned tooling adapters are requested design
requirements for this proposal. The remaining recommendations are proposals,
not approved decisions; implementation has not been approved.

### Review maintainability consequences

Prioritize a compact set of concerns:

1. Dependencies crossing agreed boundaries.
2. Business decisions duplicated or spread across unrelated places.
3. Coupling through implementation details or shared mutable data.
4. Changes propagating across responsibilities that should evolve independently.
5. Tests that make safe internal refactoring unnecessarily difficult.
6. Abstractions and component splits whose maintenance cost exceeds their
   demonstrated benefit.

Require findings to explain a concrete maintenance consequence. A named upcoming
change is useful evidence, but should not be mandatory when an existing problem
already demonstrates the cost. Architectural pattern names or numerical metrics
alone should not justify restructuring.

Recommend the smallest useful correction. A local function, clearer module
ownership, or a narrower export may solve the problem without creating another
interface, layer, package, or service.

### Respect scope and accepted decisions

| Mode | Proposed responsibility |
| --- | --- |
| Code-change review | Assess introduced or worsened maintainability problems and conformance to accepted boundaries |
| Plan review | Assess the proposed change and only the design decisions that remain open within its scope |
| Architecture audit | Examine the explicitly selected area and its current tradeoffs; distinguish observations from proposed redesign |

A problem with an approved design can be reported with its consequences, but
should not silently expand an implementation review into a topology redesign.
Acceptance records need enough scope to distinguish a one-off exception from a
standing architectural decision.

### Define an explicit check contract

Each check group should state:

| Field | Proposed content |
| --- | --- |
| Purpose | The maintainability concern being assessed |
| Applicability | Modes, targets, and conditions that make the check relevant |
| Collected inputs | Technology-neutral evidence fields, metrics, classifications, and adapter capabilities required |
| Additional inputs | Source facts, requirements, decisions, or history interpretation, with a named provider |
| Steps and rules | Ordered inspections, each connected to its condition and canonical rule definition |
| Execution | Which extraction and decisions are deterministic, agent-evaluated, or mixed |
| Output | Target, evidence, consequence, verdict, severity, and smallest proposed correction |
| Missing evidence | What to request, what remains unknown, and whether the check is incomplete |
| Coverage | Targets examined, skipped, or unresolved, with reasons |

Keep shared preparation separate only where it is actually shared or ordered.
An independent check should be understandable without reconciling two parallel
descriptions of its logic.

### Use a technology-agnostic core and project-owned tooling adapters

The skill defines the review process, check contracts, common evidence format,
and interpretation of results. Each project implements and configures its own
adapters to connect that contract to its languages, build system, and analysis
tools. Checks request capabilities and facts rather than invoking a particular
compiler, dependency analyzer, or test runner directly.

| Responsibility | Owner | Purpose |
| --- | --- | --- |
| Review contracts and orchestration | Skill | Define required evidence, run applicable checks, and consolidate findings |
| Architectural policy | Project | Define components, classifications, allowed dependencies, boundaries, and accepted exceptions |
| Collection adapters | Project | Invoke suitable tools and return normalized dependencies, metrics, source facts, provenance, and coverage |
| Enforcement adapters | Project | Translate agreed architectural constraints into tool-specific checks, execute them, and return violations with evidence |
| Analysis and enforcement engines | Existing maintained tools, selected by the project | Parse code, resolve dependencies, calculate supported metrics, or enforce configured rules |

For example, a TypeScript project's collection adapter could wrap
dependency-cruiser and the TypeScript compiler API. Another project's adapter
could use its own compiler and build tools while supplying the same supported
evidence fields. The skill should not contain language-specific branches for
either project.

Collection and enforcement are separate responsibilities, but may share an
implementation and underlying tools. An enforcement adapter must report which
project rule ran, against which scope and revision, and its result. Merely
finding an enforcement configuration does not prove that a check ran or passed.
The same project enforcement can run in CI and be consumed during a review.

Adapters declare their capabilities and explicitly report unsupported facts,
partial coverage, and execution failures. Missing capability must not become a
passing result. Agents may fill evidence gaps where a check permits it, with the
result identified as agent-derived; this does not count as automated enforcement.

Reusable adapter packages are possible, but each project owns their integration
and policy configuration. Start with a small contract and adapters needed by real
projects; a universal tooling framework is not required.

### Automate stable facts and enforceable constraints

Use maintained tooling behind project adapters for language facts, dependency
discovery, and enforcement. Keep custom adapter code focused on integration,
normalization, and policy translation; keep shared skill code focused on the
technology-neutral review contract and artifact maintenance.

Agents should concentrate on meaning, consequences, and tradeoffs. They can also
supply facts that tooling cannot obtain, but that fallback must be visible.
Recurring, precise architectural constraints should become project build checks
where the implementation cost is justified.

Do not confuse static analysis with runtime proof. An import graph can establish
dependency direction; it cannot establish that replacing an integration preserves
behavior. Any requested runtime verification needs an explicit scope and evidence.

### Keep artifacts proportionate

Maintain a compact record of important boundaries and decisions. Derive code
inventories rather than documenting them twice. Preserve finding history where
it helps avoid repeated work, but do not require elaborate documentation for a
small application merely to satisfy the workflow.

Make code-change review the routine path and broader audits deliberate. Reports
should emphasize actionable consequences, incomplete evidence, and the few
corrections worth making. Leaving the simple existing structure in place is a
legitimate outcome.

## Open questions

| Question | Discussion so far | Proposed direction to evaluate |
| --- | --- | --- |
| What is the skill's primary contract? | Architecture compliance and maintainability are currently intertwined | Prioritize maintainability within agreed architectural constraints |
| Should the eight workflows remain? | We have examined W1–W5 more closely; W6–W8 have not received equivalent discussion | Finish reviewing the remaining workflows before selecting final group boundaries |
| Where should canonical rules live? | Procedure and rule files duplicate or disconnect meaning and execution | Make each check group self-contained; choose whether a separate rationale catalog adds enough value |
| What belongs in planning rather than review? | Domain-first sequencing, initial in-memory implementations, and early topology decisions were challenged | Remove mandatory sequencing from compliance; scope design evaluation explicitly |
| Which approved decisions may a reviewer challenge? | The user does not want implementation review to reopen a microservice decision | Report concrete consequences; require explicit scope to reassess topology |
| Which Clean Architecture prescriptions remain hard rules? | Required interfaces, presenter separation, strict boundary data, and plugin independence can add structure | Distinguish project constraints from defaults and heuristics; justify each mandatory rule |
| How should terminology change? | Gateway, adapter, plugin, and device boundary are ambiguous | Establish concrete contract/implementation/technology terms and define relationships separately |
| What is the boundary inventory? | W5 does not define precisely what “every boundary” enumerates | Model or derive named boundary targets with ownership, evidence, and enforcement |
| How are classifications trusted and refreshed? | Broad rules cover files without individual verification; actors may be absent | Record provenance and revisit affected or suspicious classifications; define when evidence is insufficient |
| Which checks should be automated first? | Several W2 inspections are mechanically expressible in part | Prioritize high-value, reliable facts and narrowly defined decisions rather than broad semantic guesses |
| How should findings be consolidated? | Target-plus-rule identity permits repeated findings for one defect | Group by underlying problem and correction while retaining every supporting rule and evidence |
| How should severity and blocking work? | Current fixed severities and escalation can turn broad prescriptions into blockers | Base blocking on consequence, evidence, scope, and agreed constraints; define uncertainty separately |
| What documentation is essential? | The model, decisions, overview, graph, ledger, and slices have different purposes | Keep a minimal shared baseline and derive the rest; decide what history is genuinely useful |
| Should evaluator and source-auditor roles remain separate? | Evaluators cannot inspect code, so missing facts require another agent round | Measure whether the separation improves evidence quality enough to justify its cost |
| What is the minimum adapter contract? | The requested direction is a technology-agnostic skill with project-owned collection and enforcement adapters | Define invocation, evidence schema, capabilities, scope/revision identity, coverage, and error/result semantics; keep tool-specific configuration in the project |
| How are checks handled when an adapter lacks a capability? | Different stacks will expose different facts and enforcement capabilities | Define required versus optional evidence per check, permitted agent fallbacks, and when a result must remain incomplete |
| How should projects reuse adapters? | Projects own their adapters and tooling integration; common implementations may be reusable | Decide how projects bind and version shared adapters without making a particular stack mandatory for the skill |
| How will the rework be evaluated? | No implementation or evaluation plan has been approved | Include small applications, legitimate exceptions, known defects, and over-engineered examples; assess missed issues, false positives, effort, and proposed-change size |

## Sources for the next design pass

- [Current audit procedure](../../skills/workflows/inspect-architecture-workflow/references/audit.md)
- [Current change-review procedure](../../skills/workflows/inspect-architecture-workflow/references/change-review.md)
- [Current plan-review procedure](../../skills/workflows/inspect-architecture-workflow/references/plan-review.md)
- [Classification and mapping](../../skills/workflows/inspect-architecture-workflow/references/mapping.md)
- [Agent dispatch and evidence packets](../../skills/workflows/inspect-architecture-workflow/references/slicing.md)
- [Rule vocabulary](../../skills/workflows/inspect-architecture-workflow/references/rules/preface.md)
- [Evaluation workflows](../../skills/workflows/inspect-architecture-workflow/references/workflows/)
- [Tool contract and limitations](../../skills/workflows/inspect-architecture-workflow/references/command.md)
- [Finding identity, severity, and verdicts](../../skills/workflows/inspect-architecture-workflow/references/verdicts.md)

The next discussion should resolve the scope and check contract, complete the
remaining workflow review, and then decide which current rules to retain,
rewrite, automate, relocate, or remove. Implementation planning follows those
decisions.
