# Rule catalog

The rules the inspection workflows check, grouped by the workflow that uses them. Each rule is
an imperative statement, a check to run against the inventory, and an example. Cite rules by
number in findings. R1 to R3 are cross-cutting and drive how findings are ranked.

## Reading this catalog

**Behavior and structure.** Every change to a system delivers two things. Behavior is what the
system does for its users: the features, the outputs, the fixed bugs. Structure is the shape of
the code that decides how much work the next change will take. Behavior is what stakeholders ask
for and see; structure is what they never ask for and always pay for. The rules treat both as
deliverables of equal standing.

**Importance and urgency.** Work is classified on two independent axes. Urgent work has a
concrete cost if it ships one iteration later; important work changes the cost of every later
change. Behavior is usually urgent; structure is always important and rarely urgent. Ranking is
by importance first, then urgency, so structural work outranks urgent work that has no concrete
cost of delay.

**The dependency graph.** The inventory records units (classes, modules, functions, interfaces,
data structures) and components (enforced groups of units) as nodes, and source dependencies as
edges. An edge, drawn as an arrow from A to B, means A's source code names B: it imports B,
implements or extends B, constructs B, or uses one of B's types in a signature. This is about
source code, not about which function calls which at runtime; the two often differ. "Walking
arrows forward" from A finds what A depends on; "walking arrows backwards" from B finds B's
dependents, the code that must be re-verified when B changes. A cycle is a path of arrows that
returns to its start.

**Policy, detail, level, and rings.** Policy is the business rules: the code that would still
describe the organization's work without software, plus the application-specific rules that
sequence it. Detail is everything that exists because the software runs on machines: databases,
frameworks, transports, vendors, UI, clocks, configuration, and the data shapes they produce.
Level is a unit's distance from the system's inputs and outputs: a request handler or a database
adapter is low level, a use case is higher, an entity highest. A ring is a band of units at one
level. This catalog uses four rings, from the inside out: entities, use cases, interface
adapters (controllers, presenters, gateways), frameworks and drivers. The rule the rings encode
is that every arrow crossing a ring boundary points inward, toward higher level, and no inner
ring names anything declared in an outer ring. The count is schematic; systems may have more
rings, and the direction rule is what matters.

**Components, cohesion, and releases.** A component is a group of units that tooling keeps
behind one published surface: the set of symbols other code may import from it. Cohesion is how
strongly the units inside a component belong together. Three motives pull on where a component's
edges go, and they conflict: grouping units that change for the same reasons so a change lands in
one place (cohesion for maintenance); grouping units that are always used together and publishing
them as one versioned release so consumers can pick a version (cohesion for reuse); and splitting
off units that some consumers never use so those consumers stop receiving releases they do not
need. The first two grow components, the third shrinks them; no component satisfies all three, so
each component sits at a chosen position and pays a cost. A release unit is a component that is
built, versioned, and published on its own so consumers depend on a named version rather than on
a path.

**Metrics.** Where a rule mentions instability, abstractness, distance, or the zones of pain and
uselessness, the definitions, formulas, counting rules, and thresholds are in `metrics.md`. The
rules here state only what the metrics are for.

## Vocabulary

| Term | Meaning |
|---|---|
| Actor | A role or team that requests changes for its own reasons (finance, HR, ops, a partner API). |
| Reason to change | An actor-driven motive for modifying a unit; a unit should have one. |
| Policy | Business rules: entities and use cases. Far from inputs and outputs; never imports detail. |
| Detail | Persistence, transport, frameworks, vendor SDKs, UI, clocks, file systems, configuration, and the data formats they generate (rows, request objects, payloads). |
| Critical business rule / data | A rule the organization would apply without software, and the data that rule needs and that would exist on paper. |
| Entity | A module binding a small set of critical rules to their critical data; its interface is the rule-functions; knows nothing of storage, UI, frameworks, or use cases. Not necessarily a class. |
| Use case / interactor | Application-specific rules (sequencing, gating, input validation, flow thresholds) as input, output, and ordered steps; orchestrates entities; delivery-agnostic. The interactor is the class implementing it. |
| Request / response model | Plain data a use case accepts and returns; imports nothing, extends no framework type, references no entity. |
| Port | An interface, protocol, abstract type, or function type owned by the policy side and implemented by a detail. |
| Input boundary / output boundary | The use case's own interfaces: the controller calls the input boundary the use case implements; the presenter implements the output boundary the use case declares. |
| Gateway | A consumer-owned port between use cases and a store, one method per application need, named in domain language; its implementation holds all query code. |
| Level | Distance from the system's inputs and outputs; I/O-managing modules are lowest. Dependencies point from low to high. |
| Ring | A band of units at one level of distance from I/O. Four by default, inside out: entities, use cases, interface adapters, frameworks and drivers. Every dependency arrow that crosses a ring boundary points inward. |
| Interface adapter | Controller, presenter, gateway, or external-service adapter converting between the policy's shape and the external agency's shape. |
| Plugin | A lower-level component that implements a port and is unknown to the policy, so it can be added, swapped, or removed without the policy changing. |
| Composition root | The one lowest-level module that constructs and wires everything; imports every level, imported by nothing. |
| Humble object | The unit that keeps only the hard-to-test essence (paint, execute, transmit) with every decision stripped out; always the low-level side of a boundary. |
| Presenter / view / view model | The testable unit that turns use-case output into a view model; the humble unit that copies it to the screen; the plain structure of display-ready strings and flags between them. |
| Data mapper | What an ORM is: a humble persistence component that loads rows into structures; never the domain model. |
| Boundary data | A plain structure (request, response, view model, record, payload) with public fields and no behavior, declared on the inner side; the only thing that crosses a boundary. |
| Component | Related functionality behind one published surface inside an enforced unit (package, module, or separately built library). Independent release is one enforcement mode, not the definition. |
| Published surface | The symbols a component exports for other code to import; everything else in it is unit-private. |
| Cohesion | How strongly the units in a component belong together: because they change for the same reasons, because they are used and released together, or both. |
| Cohesion tension | The conflict between grouping for maintenance, grouping for reuse, and splitting to avoid unneeded releases; the first two grow components, the third shrinks them. |
| Release unit | A component built, versioned, and published on its own, so consumers depend on a named version and choose when to adopt a new one. |
| Stable / volatile | Many dependents and few dependencies, hard to change; the reverse, easy to change. |
| Instability, abstractness, distance | Screening metrics for component graphs: how much a component depends on others versus is depended on, how much of it is interfaces, and how far it sits from the balanced line. Defined in `metrics.md`. Never verdicts on their own. |
| Zone of pain | A component many others depend on, made of concrete code, that also changes often: every change ripples to its dependents and it cannot be extended without editing. |
| Zone of uselessness | A component of interfaces or abstract types that nothing implements or nothing depends on: abstraction paid for and unused. |
| Testing API | A surface tests use to drive use cases with test-only powers (act as any role, short-circuit expensive resources, force a state); never shipped to production. |
| Shape mismatch | A change the current structure absorbs only through a special case, a flag threaded through layers, or a near-copy. |
| Accidental duplication | Code that looks identical today but is owned by different actors and will diverge. |
| Axis of change | A place where the two sides change at different rates for different reasons; where boundaries belong. |
| Premature decision | A framework, store, server, library, dependency-injection container, or deployment-topology choice made before a use case forces it. |
| Enforced boundary | A line the compiler, module exports, build, or a build-failing import rule refuses to let code cross. A drawn boundary exists only in a diagram. |
| Published versus public | Exported from the unit versus merely visible inside it. |
| Structural coupling | Tests organized to mirror production class per class, so structure changes force test changes without behavior change. |

The rules themselves are in `cross-cutting.md` (R1 to R3) and `w1.md` to `w8.md`, one file per
evaluation workflow. Read this preface before any of them.
