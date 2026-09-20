# Evaluation workflows

Run W1 to W8 in order. Each workflow names the inventory sections it reads, the procedure, a
decision table whose conditions are evaluated in order (the first match decides), and what it
writes. Rule numbers refer to `rules.md`. A target that matches no `SHOULD_CHANGE` condition is
written as `OK` with the rule it satisfies.

Common columns for every assessment row: `id`, `workflow`, `target` (inventory IDs), `rule`,
`verdict` (`OK`, `SHOULD_CHANGE`, `RESOLVED`, `ACCEPTED`), `severity`, `evidence` (paths), `change`,
`protects` (the upcoming change), `run`.

Before applying a decision table, check the intended exceptions and cohesion groups in
`decisions.md`. A candidate finding whose edge, layer skip, or shared shape a recorded exception
covers (same from-and-to components or rings, or the same shape) is written as `OK` naming the
exception, never as `SHOULD_CHANGE`. Exceptions are read at component and ring level; a packet
carrying no `decisions.md` has none.

Every `SHOULD_CHANGE` row in a decision table carries a base severity. The coordinator may raise
it by the escalation rules in the skill body (policy target, path of a named upcoming change,
fan-in of three or more, cycle); nothing lowers it. Base severities follow one scale: `blocker`
when the rule violated is a dependency-direction or cycle rule whose breach couples policy to
detail; `major` when the breach couples two units that change for different reasons or leaves a
relied-upon boundary unenforced; `minor` when the breach is local to one unit and no dependent
inherits it.

## W1. Dependency direction and ports

Reads: Units (ring), Edges, Boundaries, Entry points and composition roots, Change history.

Procedure:
1. For every edge with `crosses-ring` yes, compare the rings of both ends.
2. For every port in Boundaries, locate the owner's ring and the signature's types.
3. For every `constructs` edge, check whether its source is a composition root.
4. For every use case, check that its callers depend on an input boundary and that it calls presenters and stores through boundaries it declares.
5. For every high-level unit in Change history, classify each change's reason as policy or detail.

| Condition | Verdict | Rule | Base severity |
|---|---|---|---|
| Edge from a policy unit (entity, use-case, port, boundary-data) to a detail unit or `external:` framework, vendor, or runtime | SHOULD_CHANGE | R4 | blocker |
| Edge crosses rings outward for any other unit | SHOULD_CHANGE | R4 | blocker |
| Port owner is in a lower ring than its consumer, or the port sits in a shared interfaces bucket with no consumer beside it | SHOULD_CHANGE | R5 | blocker |
| Port signature names a detail type or an `external:` type | SHOULD_CHANGE | R5 | blocker |
| Direct edge remains between a policy unit and a detail unit that also share a port | SHOULD_CHANGE | R5 | blocker |
| Controller imports the use-case class rather than an input boundary; use case imports its presenter or gateway implementation | SHOULD_CHANGE | R6 | blocker |
| `constructs` edge to a concrete detail from a unit that is not a composition root | SHOULD_CHANGE | R7 | blocker |
| High-level unit changed for a detail reason in two or more recent changes | SHOULD_CHANGE | R4 | blocker |
| Abstraction with exactly one consumer and one implementer and no named deferred decision or forbidden ripple | SHOULD_CHANGE | R8 | minor |
| Otherwise, for each cross-ring edge and port | OK | R4, R5 |  |

Writes: one row per cross-ring edge, per port, per constructs edge, per use case. Records in the
inventory's Boundaries section the `direction-verdict` of each port.

## W2. Reasons to change

Reads: Units (actors, kind), Edges (import between units), Change history.

Procedure:
1. For every unit with two or more actors, list the operations per actor.
2. For every unit imported by units owned by different actors, check whether the shared unit is behavior or data.
3. For every consumer of an interface, count members used versus exposed.
4. For every `extends` edge, check whether the subtype is used where the supertype is expected.
5. For every consumer of an abstraction, search for type checks on implementations.
6. For behavior-bearing units, check for public data reachable from outside; for boundary-data, confirm no behavior.
7. List units that mutate state.

| Condition | Verdict | Rule | Base severity |
|---|---|---|---|
| Unit with two or more actors and behavior for each | SHOULD_CHANGE | R10 | major |
| Behavior-bearing unit imported by units of different actors (shared helper across actors) | SHOULD_CHANGE | R11 | major |
| Consumer contains `instanceof`, kind check, or downcast on an implementation of an abstraction | SHOULD_CHANGE | R13 | major |
| Consumer uses fewer than half the members of the interface it depends on | SHOULD_CHANGE | R13 | major |
| Variant added by a conditional ladder over kinds in a stable unit | SHOULD_CHANGE | R12 | major |
| `extends` edge where the subtype is not substituted for the supertype anywhere | SHOULD_CHANGE | R12 | major |
| Behavior-bearing unit exposes mutable internal data to outside code | SHOULD_CHANGE | R14 | major |
| Function with flag-driven loops, exceptions as control flow, or non-local state deciding the path | SHOULD_CHANGE | R15 | minor |
| Mutation of shared state outside the listed mutating units | SHOULD_CHANGE | R16 | major |
| Two units with identical bodies and different actors | OK (note: keep separate) | R11 |  |
| Otherwise, per unit with a public surface | OK | R10 |  |

Writes: one row per multi-actor unit, per shared helper, per consumer of an abstraction, per
`extends` edge, per mutating unit. Adds the list of mutating units to the inventory header.

## W3. Business-rule placement

Reads: Units (kind entity, use-case, boundary-data, mixed), Edges from those units, Boundaries.

Procedure:
1. For every entity, list imports and decorators; list fields and the rule-functions that read them.
2. For every use case, strip calls to entities and ports and classify what remains.
3. For every request and response model, list imports, base types, and field types.
4. For every edge from an entity, check the target's kind.

| Condition | Verdict | Rule | Base severity |
|---|---|---|---|
| Entity imports anything other than entities and value types, or carries framework annotations, base classes, or serialization methods | SHOULD_CHANGE | R17 | blocker |
| Entity has fields no rule-function reads, or functions only the system needs | SHOULD_CHANGE | R17 | minor |
| Use case contains business arithmetic or a decision a clerk would make | SHOULD_CHANGE | R18 | blocker |
| Edge from an entity to a use case, or entity exposes a hook or callback for a use case | SHOULD_CHANGE | R18 | blocker |
| Request or response model imports anything, extends a framework type, wraps a row or envelope, carries channel fields, or has an entity-typed field | SHOULD_CHANGE | R19 | blocker |
| Use case returns or accepts an entity across its input or output boundary | SHOULD_CHANGE | R19 | blocker |
| Adapter or presenter branches on which shape it received | SHOULD_CHANGE | R19 | blocker |
| No unit is classified entity or use-case although the code has business rules (rules live in adapters or framework glue) | SHOULD_CHANGE | R17, R18 | blocker |
| Otherwise, per entity, use case, and model | OK | R17 to R19 |  |

Writes: one row per entity, per use case, per request and response model.

## W4. Humble objects and adapters

Reads: Units (kind adapter, view, mixed), Edges, Boundaries (humble side).

Procedure:
1. For every view, read it line by line; classify each line as binding, flag-to-appearance, or decision.
2. For every presenter, list view-model field types.
3. For every controller, handler, or listener, classify each statement as parse, convert, invoke, or other.
4. For every gateway port, list methods and check for generic escape hatches; for every use case and entity, search for query strings, builders, sessions, ORM types.
5. For every unit that needs a device to be tested, check whether a testable counterpart exists.

| Condition | Verdict | Rule | Base severity |
|---|---|---|---|
| Unit talks to a device and also contains conditionals, calculations, formatting, or lookups, with no testable counterpart | SHOULD_CHANGE | R20 | major |
| Handler or sender validates business rules, branches on domain state, or formats for display | SHOULD_CHANGE | R20 | major |
| View contains a decision beyond flag or enum to appearance | SHOULD_CHANGE | R21 | major |
| View model contains a date, money type, unformatted number, domain object, or method | SHOULD_CHANGE | R21 | major |
| Presenter imports a UI framework | SHOULD_CHANGE | R21 | major |
| Gateway port exposes `query(sql)`, `find(spec)`, or a builder | SHOULD_CHANGE | R22 | blocker |
| Query string, builder, session, or ORM type inside a use case or entity | SHOULD_CHANGE | R22 | blocker |
| ORM-annotated class used as the domain model | SHOULD_CHANGE | R22 | blocker |
| Domain-owned port carries a storage, transport, or vendor word in its name | SHOULD_CHANGE | R22 | minor |
| Otherwise, per adapter and view | OK | R20 to R22 |  |

Writes: one row per view, presenter, handler, gateway port, and per use case or entity searched.

## W5. Deferral and boundary drawing

Reads: Components, Boundaries, Edges to `external:`, the brief or plan when present, Change history.

Procedure:
1. For every `external:` framework, store, or vendor, find the port behind it and whether an in-memory implementation exists.
2. For every boundary, name the decision it defers or the axis of change it separates.
3. List deployables, processes, and services; walk the smallest realistic feature through them.
4. Check whether any plugin depends on another plugin directly.
5. Check whether the rules can run with no UI, store, or server present.

| Condition | Verdict | Rule | Base severity |
|---|---|---|---|
| Framework, store, or vendor reached with no port between it and the policy | SHOULD_CHANGE | R23 | major |
| Port with no in-memory or stub implementation while rule tests need the real detail | SHOULD_CHANGE | R23 | major |
| Two or more deployables or a service catalog with no team or deployment reason recorded, and the simplest change edits several of them | SHOULD_CHANGE | R24 | major |
| Boundary that defers no decision and whose two sides change together for the same reason | SHOULD_CHANGE | R25 | minor |
| Unit that changes for two unrelated cadences (a missing internal line) | SHOULD_CHANGE | R25 | major |
| Plugin imports another plugin directly | SHOULD_CHANGE | R25 | major |
| Rules cannot be exercised without a UI, store, or server in the process | SHOULD_CHANGE | R26 | major |
| Plan or brief sequences framework, schema, or screens before rules | SHOULD_CHANGE | R26 | major |
| Otherwise, per external dependency and boundary | OK | R23 to R26 |  |

Writes: one row per external dependency, per boundary, per deployable. Records in the report's
"Deferred and open" the decisions currently left open behind ports.

## W6. Components, cycles, and stability

Reads: Components, Edges (crosses-component), Metrics, Change history.

Procedure:
1. Build the component graph; detect cycles.
2. For every component edge, compare stability (fan-in versus fan-out) at both ends.
3. For every recent change and the change under review, list the touched components and look up their cohesion groups in `decisions.md`; a component may belong to several groups. Also note which consumers use how much of each component.
4. Compute D and volatility when metrics exist; compare with the previous run.
5. Check versioning and adoption across release units.

| Condition | Verdict | Rule | Base severity |
|---|---|---|---|
| Cycle in the component graph | SHOULD_CHANGE | R30 | blocker |
| Edge from a more stable component to a less stable one | SHOULD_CHANGE | R31 | major |
| Heavily depended-on component that is concrete and changed in the recent history | SHOULD_CHANGE | R31, R32 | major |
| Component with abstract types that have no implementor or no consumer outside | SHOULD_CHANGE | R31, R32 | minor |
| Change touches two or more components and no cohesion groups are recorded in `decisions.md` | SHOULD_CHANGE (one row per run, asking for the groups to be recorded; propose them from change history) | R28 | minor |
| Change touches a component that shares no recorded cohesion group with the other touched components (the change spreads across groups) | SHOULD_CHANGE | R27 | major |
| Change touches several components that all belong to one recorded cohesion group, or touches a single component | OK | R27 |  |
| Consumer imports a component for fewer than a quarter of its exported symbols | SHOULD_CHANGE | R27 | minor |
| Component D more than one standard deviation from the mean, or D crossed the threshold since the previous run, and the position is harmful in words | SHOULD_CHANGE | R32 | minor |
| Component whose cohesion position and cost are not stated and whose boundaries have not been revisited while change patterns shifted | SHOULD_CHANGE | R28 | minor |
| Cross-component dependency consumed by path with no version, where components release separately | SHOULD_CHANGE | R33 | major |
| Greenfield structure with a full component map fixed before code exists | SHOULD_CHANGE | R29 | minor |
| Otherwise, per component and component edge | OK | R27 to R33 |  |

Writes: one row per component and per component edge; the cycle list; the D table with the
previous run's values.

## W7. Tests as a component

Reads: Units (kind test), Edges from and to test units, Entry points, Boundaries.

Procedure:
1. For every edge into a test unit from a production unit, record it.
2. Check whether test code, fixtures, or test-only routes are in the production artifact or behind a runtime flag.
3. For every business-rule assertion, trace what the test traverses to reach the rule.
4. Compare the test tree with the production tree.
5. Check for a testing API and for authorization tests that do not use its bypass.

| Condition | Verdict | Rule | Base severity |
|---|---|---|---|
| Production unit imports a test, fixture, fake, or helper | SHOULD_CHANGE | R34 | blocker |
| Test-only power behind a runtime flag or environment check in production code | SHOULD_CHANGE | R34 | blocker |
| Test-only routes or fixtures included in the production deployable | SHOULD_CHANGE | R34 | blocker |
| Business-rule assertion reached through a screen, navigation, login, or vendor path | SHOULD_CHANGE | R35 | blocker |
| No testing API or direct use-case boundary available to tests while rules exist | SHOULD_CHANGE | R35 | blocker |
| Test tree mirrors the production tree class for class and recent internal refactors changed tests | SHOULD_CHANGE | R36 | major |
| Tests that assert nothing a specific defect would falsify, or reports claiming correctness from green tests | SHOULD_CHANGE | R37 | minor |
| Security bypass used by tests with no separate authorization tests | SHOULD_CHANGE | R34 | blocker |
| Otherwise, per test suite | OK | R34 to R37 |  |

Writes: one row per test suite and per production-to-test edge.

## W8. Enforcement and code organization

Reads: Components (enforcement mode, published surface), Edges, forbidden edges, documentation of
intended structure, Metrics.

Procedure:
1. For every component boundary, name what fails when it is crossed.
2. For every published symbol, find an outside consumer.
3. Compare the intended graph (documentation, agent instructions, plan) with the mapped graph.
4. For every forbidden edge named by the design, check whether it exists and whether it is enforced.
5. Classify the organization style by top-level names and public surfaces; list shared data shapes.

| Condition | Verdict | Rule | Base severity |
|---|---|---|---|
| Component with enforcement `none` whose boundary the design relies on | SHOULD_CHANGE | R38 | major |
| Published symbol with no outside consumer, or a concrete implementation published when only its interface is consumed | SHOULD_CHANGE | R38 | major |
| Deep import into another component's internals resolves | SHOULD_CHANGE | R38 | major |
| Forbidden edge exists in code, or is absent but unenforced | SHOULD_CHANGE | R39 | major |
| Module depends on a module two or more levels below it with no documented intended skip | SHOULD_CHANGE | R39 | major |
| Top-level structure named by technology (web, service, data) with a use case spread across three technical folders | SHOULD_CHANGE | R40 | major |
| Delivery-mechanism class inside a domain component, or persistence reachable from delivery code | SHOULD_CHANGE | R40 | major |
| Edge present in code but absent from the intended graph | SHOULD_CHANGE | R41 | major |
| Two components sharing a table, document, or wire shape with no owning component | SHOULD_CHANGE | R41 | major |
| Otherwise, per component boundary and published symbol | OK | R38 to R41 |  |

Writes: one row per component boundary, per forbidden edge, per shared shape; the diff between
intended and mapped graphs.
