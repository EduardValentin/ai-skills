# Vocabulary

The terms the rule catalog, the classification guide, the metrics page, and the three flows use,
each defined here and nowhere else. Read it before the first rule file, and come back to it
whenever a rule or a flow uses a word in a sense that seems narrower than everyday speech.

## Change and value

| Term | Meaning |
|---|---|
| Behavior | What the system does for its users: features, outputs, fixed bugs. Stakeholders ask for it and see it. |
| Structure | The shape of the code, which decides how much work the next change takes. Stakeholders never ask for it and always pay for it. Every change delivers both behavior and structure. |
| Urgency | Whether work has a concrete cost if it ships one iteration later. Behavior is usually urgent. |
| Importance | Whether work changes the cost of every later change. Structure is always important and rarely urgent. |
| Actor | A role or team that requests changes for its own reasons: finance, HR, operations, a partner integration. |
| Reason to change | An actor's motive for modifying a unit. A unit should have one. |
| Axis of change | A place where the two sides change at different rates for different reasons. Boundaries belong there. |
| Shape mismatch | A change the current structure absorbs only through a special case, a flag threaded through layers, or a near-copy. |
| Accidental duplication | Code that looks identical today but is owned by different actors and will diverge. |
| Premature decision | A framework, store, server, library, dependency-injection container, or deployment-topology choice made before a use case forces it. |
| Named upcoming change | A future change stated in the ticket or plan under review, or one the user confirmed in this session. Roadmap items given without confirmation are not named upcoming changes. |
| Scope | What a session reviews: a whole codebase or a named area in an audit, a diff in a change review, a written plan in a plan review. |
| Design or topology decision | A choice about how the system is split into components, deployables, processes, or services, or how components are released. It is in scope only when the session's request asks for it. |

## Units, levels, and dependencies

| Term | Meaning |
|---|---|
| Unit | A module (one file) of the codebase, the smallest thing the model classifies. |
| Kind | What a unit does, such as entity, use case, port, or controller. The default kinds are listed in the classification guide. |
| Role | What a kind means for dependency direction: `policy`, `detail`, `wiring` (composition roots, tests, config), or `neutral` (barrels and mixed units). |
| Policy | Business rules: entities and use cases, plus the ports and boundary data they own. Code that would still describe the organization's work without software, and the application rules that sequence it. |
| Detail | Everything that exists because the software runs on machines: persistence, transport, frameworks, vendor SDKs, UI, clocks, file systems, configuration, and the formats they produce (rows, request objects, payloads). |
| Critical business rule | A rule the organization would apply without software, together with the data it needs, which would exist on paper. |
| Entity | A module binding a small set of critical business rules to their data. Its interface is the rule functions. It knows nothing of storage, UI, frameworks, or use cases, and need not be a class. |
| Value type | A small immutable type with no identity and no I/O, such as `Money` or `Period`, which entities and use cases may use freely. |
| Flow threshold | A limit that exists because the process is automated, such as how many attempts a user gets or how many items one request may carry. It is an application rule and belongs in a use case. |
| Use case | Application rules (sequencing, gating, input validation, flow thresholds) stated as input, output, and ordered steps. It orchestrates entities and does not know the delivery mechanism. |
| Request and response model | The boundary data a use case accepts and returns. |
| Boundary data | A plain structure (request, response, view model, record, payload) with public fields and no behavior, declared on the inner side. It is the only thing that crosses a boundary. |
| Level | A unit's distance from the system's inputs and outputs. A request handler or a database client is low level, a use case higher, an entity highest. Dependencies point from low to high. |
| Ring | A band of units at one level. Four by default, inside out: entities, use cases, adapters, frameworks. A project may add rings; what matters is that dependencies point inward. |
| Dependency | A source reference from one unit to another: an import, an implements or extends clause, a construction, or a type in a signature. It is what the code names, not what calls what at run time. |
| Dependent | A unit that depends on another, directly or through other units. The dependents of B are what must be re-verified when B changes. |
| Cycle | A path of dependencies that returns to where it started. |
| Ring skip | A dependency on a unit more than one ring inward, which bypasses the ring between. |
| Mixed unit | A unit that matches two or more kinds. It is always a candidate for a split. |
| Barrel | A unit that only re-exports others. Its dependencies are publication, not use. |

## Ports, adapters, and boundaries

| Term | Meaning |
|---|---|
| Port | A contract the policy side owns and a detail implements: an interface, protocol, abstract type, or function type. |
| Storage port | A port through which the policy reaches stored data. It has one method per application need, is named in domain language (`Orders`, not `OrdersRepository`), and is typed in application terms. |
| Input boundary | The port a use case implements and a controller calls. |
| Output boundary | The port a use case declares and a presenter implements. |
| Adapter | A detail that implements a port or translates between the policy's shapes and an external agency's. Controllers, presenters, and gateways are adapters. |
| Gateway | The kind of adapter that implements a port against a store or a vendor service, and holds all of its query or client code. |
| Controller | An adapter that turns an incoming request from a delivery mechanism into a request model and calls the use case. |
| Presenter | An adapter that turns use-case output into a view model. Its role does not fix where it runs: a presenter may run on the server or in the client. |
| View | The humble unit that copies a view model to the screen. |
| View model | Boundary data of display-ready strings, booleans, and enumerations, set by the presenter. "Arrives formatted" means it reaches the view already formatted. |
| Plugin | A relationship, not a kind of unit: a detail the policy does not know, which can be added, swapped, or removed without the policy changing. By default plugins do not depend on each other. |
| Wiring factory | A function a component publishes that constructs the component's concrete parts and returns its published interface, so the composition root wires the component without reaching its internals. |
| Composition root | The one lowest-level unit that constructs concrete details and wires everything together. It may depend on every ring, and nothing depends on it. |
| Entry point | A place control enters the system: a route handler, a command, a job trigger, a message consumer. |
| Device boundary | The line between code that decides and code that talks to a screen, store, network, file system, or clock. |
| Humble object | The unit on the device side of a device boundary. It keeps only what is hard to test (paint, execute, transmit) and makes no decision. Its testable counterpart holds every decision. |
| Data mapper | What an ORM (object-relational mapper) is: a humble persistence component that loads rows into structures. It is never the domain model. |
| Delivery mechanism | How users or other systems reach the use cases: a web interface, a command line, a message queue, a public API. |
| Testing API | A surface through which tests drive use cases with test-only powers: act as any role, short-circuit expensive resources, force a state. It never ships to production. |
| Test double | A stub or in-memory implementation of a port that tests use in place of the real detail. |

## Components

| Term | Meaning |
|---|---|
| Component | A group of units that tooling keeps behind one published surface inside an enforced unit (a package, a module, or a separately built library). Independent release is one way to enforce it, not the definition. |
| Interface-only component | A component holding only ports and the boundary data they use, with no executable code, that several components depend on. It is not a place for unrelated interfaces. |
| Published surface | What a component exports for code outside it. Everything else in it is private to the component. |
| Published versus public | Exported for use outside the component, versus visible only inside it. |
| Enforced boundary | A line the compiler, module exports, the build, or a build-failing import rule refuses to let code cross. A boundary that exists only in a diagram is a drawn boundary, not an enforced one. |
| Forbidden edge | A dependency between two named units or components that must not exist, recorded in the model with its reason. |
| Recorded exception | An intended dependency or shape recorded in the model with a reason, scoped to one target or generalized to a component or ring pair. A finding it covers is not raised. |
| Cohesion | How strongly the units in a component belong together: because they change for the same reasons, because they are used and released together, or both. |
| Cohesion group | A recorded set of components the project lets change together for one kind of reason, such as the domain, UI, and feature packages of a repository organized by feature. |
| Cohesion tension | The conflict between three motives for a component's edges: grouping units that change for the same reasons, so a change lands in one place; grouping units always used together into one versioned release; and splitting off units some consumers never use, so those consumers stop receiving releases they do not need. The first two grow components and the third shrinks them, so each component sits at a chosen position and pays a cost. |
| Cohesive leaf | A component extracted to break a cycle, holding units that belong together for one reason and depending on no component of the cycle it broke. |
| Deployable | A program or service built, shipped, and run on its own. |
| Monolith | A system built and deployed as one deployable, however many components it holds. |
| Release unit | A component built, versioned, and published on its own, so consumers depend on a named version rather than a path and choose when to adopt a new one. |
| Stable | Hard to change because many units depend on it and it depends on few. |
| Volatile | Easy to change because few units depend on it and it depends on many. Code meant to change often belongs in volatile components. |
| Zone of pain | The position of a component that is stable, concrete, and still changing: every change ripples to its dependents, and it cannot be extended without editing. |
| Zone of uselessness | The position of a component of interfaces or abstract types that nothing implements or nothing depends on: abstraction paid for and unused. |
| Structural coupling | Tests organized to mirror production class for class, so a change of structure forces test changes without any change of behavior. |

## Evidence and findings

| Term | Meaning |
|---|---|
| Collected evidence | Everything the command gathers for a review: the dependency graph, the adapter's facts, the change history, and the metrics. |
| Metrics | Measured quantities of the component graph only: fan-in, fan-out, instability, abstractness, and distance. Their formulas and knobs are on the metrics page. |
| Knob | A per-project number with a default, written in braces in rule text, such as `{componentUseShare}`. A project changes it with `arch model set-threshold`. |
| Adapter fact | Something the project's adapter reports beyond plain dependencies, such as which units construct others (`constructs`), which ports a unit implements (`implements`), or the types in a signature (`signatures`). |
| Condition | One line of a rule group's conditions table: a situation that breaks one or more rules, with its base severity and defect kind. |
| Check | A condition the command decides from collected evidence. A check that lacks a fact or a classification it needs reports the condition as incomplete, never as passing. |
| Judgment | A condition a reviewer decides by reading code or a plan, citing `path:line` evidence. |
| Finding | A target that meets a condition: a unit, an edge, a port, a component, or a plan section, with its evidence, its consequence for maintenance in one sentence, and the smallest correction inside the scope. |
| Defect kind | The name of what is wrong, shared by conditions of different rules that describe the same defect. A finding is identified by its target and defect kind and lists every rule it breaks. |
| Severity | How costly a finding's consequence is: `blocker` when the breach couples policy to detail or forms a cycle, `major` when it couples two units that change for different reasons or leaves a relied-upon boundary unenforced, `minor` when it is local to one unit and no dependent inherits it. This scale explains what the levels mean; it is not applied anew to each finding. Each condition keeps the base severity in its row of the conditions table, and a reviewer never regrades a condition. |
| Rule status | Whether a rule counts for a project or a component: `enforced`, `advisory` (reported, never counted toward the verdict), or `off` (not evaluated). A status is recorded with a one-sentence reason. |
| Guidance | A rule about sequencing, topology, or practice, such as naming a cohesion position or reading the metrics, that is advisory by default in every project. |
| Decisions file | An optional `decisions.md` beside the model, holding longer explanations for people, such as the cost each component's cohesion position accepts. No check reads it. |
| Smallest correction | The least change inside the scope that removes the finding's consequence. |
| Wider observation | A finding whose target lies outside the scope, or whose only correction is larger than the smallest change inside the scope. It keeps its target, consequence, and evidence, is reported apart, and never blocks. |
| Overlapping findings | Judged findings of one run, from two or more reviewers' judged files, that name the same unit, as their target or as an edge end, with different corrections. `arch findings add` and `arch findings list` group them per unit, and one reviewer reconciles them into one correction per unit, or states that they are independent. Check findings never overlap, since their corrections are fixed. |

## Flows and their files

| Term | Meaning |
|---|---|
| Rule group | One file of the catalog: a set of related rules with their conditions table, such as dependency direction. `arch applicable` names the rule groups a scope brings into play. |
| Uncovered module | A module the adapter reports that no classification pair of the model matches, so it has no component or kind. Conditions that need it are incomplete until it is classified. |
| Judged finding | A finding a reviewer returns for a judgment condition, in the shape `arch findings add` reads: the judgment id, the target, the consequence, the correction, the evidence, and in a review its origin. The command adds the rules, defect kind, and severity from the judgment. |
| Origin | Whether a finding is `introduced` by the change or plan under review or `inherited` from the code before it. An audit has no origin. Only introduced findings, and inherited ones a named upcoming change makes heavier, can block a review. |
| Verdict | The one-word result of a flow: `OK`, `SHOULD_CHANGE` when a blocking finding of an enforced rule is a blocker or major, or `INCOMPLETE` when none is and a condition of an enforced rule could not be decided. `SHOULD_CHANGE` and `INCOMPLETE` block a caller's gate. |
| Proposal | What a plan would add to or remove from the code, written in the module and edge shapes of the adapter document, so the command can check a plan before the code exists. |
| Clarification request | A fact a plan leaves open that the review needs, such as where a new module lives. It is reported as incomplete, apart from the findings, and means the plan is not concrete enough to review fully. |
| Working files | The files a flow writes for the command to read: the check output, the proposal, and the judged findings. Working files live under `.architecture/work/`, which is never committed. |
