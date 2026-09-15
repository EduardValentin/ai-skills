# Mapping the architecture

How a mapping slice fills inventory rows, and how the coordinator merges them into the committed
record (`docs/architecture/`) or into `deltas.md`. Work from the code, not from documentation;
documentation is recorded as the intended structure and compared with the mapped graph in W8.
A mapping slice covers one component or top-level folder and returns rows; it never writes files.

## Identifiers

- Component: `C<n>` with its path, for example `C3 packages/billing`.
- Unit: `U<n>` with its path and symbol, for example `U17 src/billing/PayrollService.ts:PayrollService`.
- Edge: `E<n>`, `from -> to`, using unit IDs. Shared data shapes use `E<n> C2 ~ C5 (table orders)`.
- Boundary: `B<n>`.
- External pseudo-unit: `external:<name>`, tagged framework, vendor, runtime, or standard library.

IDs are never reused. A removed unit keeps its row with status `removed` and the commit.

## Components

A component is an enforced unit behind one published surface: a package with an export map or
index, a module system module, a separately built library, or a folder whose imports are
restricted by a build-failing rule. When the repository has none of these, record each top-level
source folder as a component with enforcement `none`; W8 reports the gap.

Per component record: path; published surface (the exported symbols reachable from outside);
enforcement mode (`visibility`, `exports`, `build-unit`, `import-rule`, `none`); ring (see below,
by the majority of its units, with mixed rings noted); actors; and whether it is a release unit
with a version.

## Unit kinds

| Kind | Recognize by |
|---|---|
| entity | Rules a clerk would apply without software, bound to the data they need; no imports beyond other entities and value types |
| use-case | Application-specific sequencing, gating, input validation; calls entities and ports; has a request and response model |
| port | Interface, protocol, abstract type, or function type declared on the policy side and implemented elsewhere |
| boundary-data | Request, response, view model, record, payload: public fields, no behavior |
| adapter | Controller, presenter, gateway implementation, mapper, sender, listener: converts between policy shapes and an external agency |
| view | UI code bound to a framework that copies a view model to the screen |
| framework-glue | Configuration, routing tables, DI registration, migrations |
| composition-root | Constructs concrete details and wires them; imports every level |
| test | Test suites, fixtures, fakes, testing API |
| utility | Behavior-free helpers with no domain meaning (string, date, math) |
| mixed | A unit that matches two or more kinds; always a candidate for W2 and W3 |

## Ring and level

Assign each unit a ring: `entities`, `use-cases`, `adapters`, `frameworks`, with `tests` and
`composition` as the two outermost pseudo-rings. Classify by what the unit does, not by its folder
name; a `services/` folder full of SQL is `adapters`.

The ring is the unit's level for most purposes: entities highest, frameworks lowest. When W1 must
compare two units in the same ring, or decide whether a `mixed` unit is policy or detail, use the
finer definition of level, distance from the system's inputs and outputs, measured on the
dependency graph:

1. Find the nearest entry point (route handler, command, message consumer) and count the hops from
   the unit to it along dependency edges, ignoring arrow direction.
2. Find the nearest device adapter (database client, mailer, screen, file system) and count the
   hops to it the same way.
3. The unit farther from both is the higher level.

Example: a use case imported by a route handler and importing a database client is one hop from
the entry and one from a device. A pay rule imported only by that use case is two hops from each,
so it is higher level than the use case; the route handler and the client, at zero hops from their
own side, are lowest.

## Actors and reasons to change

For each component and each `mixed` or public unit, list the actors: the roles or teams whose
requests would change it. Derive from: the ticket or brief when present; commit history (which
features touched the unit and for whom); domain vocabulary in the code (finance terms, compliance
terms, delivery terms). Two actors on one unit is the evidence W2 needs; one actor is `OK`.

## Edges

Record every source dependency:

| Edge kind | Recognize by |
|---|---|
| import | Module import, include, require, using |
| implements | Class implements interface, protocol conformance, structural satisfaction declared |
| extends | Inheritance |
| constructs | `new Concrete(...)`, factory call to a concrete detail |
| signature | A type from another unit in a parameter, return, field, or generic argument |
| shared-shape | Two components read or write the same table, document, topic, or wire format |

Per edge record: from, to, kind, `crosses-component` yes or no, `crosses-ring` yes or no,
`direction` `inward` (toward policy) or `outward` (toward detail) or `lateral` (same ring). An
outward edge from a policy unit is the primary W1 finding. Also record, per component, the list of
forbidden edges the design names (from documentation or agent instructions) and whether each is
enforced.

## Boundaries

For each port record: owner unit and its ring; implementers and their rings; the consumers; the
crossing data type and whether it is boundary-data; which side is humble; the enforcement mode of
the line (what fails if a consumer imports an implementer directly). A port whose owner is on the
detail side, or whose signature carries a detail type, is recorded as-is and flagged by W1.

## Entry points and composition roots

List every place control enters (routes, handlers, CLI commands, job triggers, message consumers)
and every place concrete details are constructed. A concrete detail constructed outside a
composition root is a W1 finding; more than one composition root per deployable is noted for W8.

## Metrics

Compute only when there are more than five components. Per component: fan-in (units outside
depending on units inside), fan-out (units inside depending on units outside), I = fan-out /
(fan-in + fan-out), A = abstract types / total types counting types that exist only to be
implemented, D = abs(A + I - 1). Record volatility from change history (changes in the last N
releases). Keep the previous run's D so W6 can compare.

## Change history

Produced by the single history slice, not by mapping slices (see `slicing.md`). It walks the
version-control log once for the whole scope, default the last ten commits touching it or the
commits the ticket names, and returns one row per touched file per commit: the reason in one
phrase, the actor it served, and whether that reason is a policy or a detail reason. The
coordinator attaches rows to units by path and writes them to the ledger's `change-history.md`.
The rows feed W2 (two reasons on one unit), W1 (a high-level unit changing for low-level reasons),
and W6 (volatility). A scope with no history of its own yields an empty table, and the affected
workflows run without volatility evidence.

## Incremental update

Audit re-run: re-derive components, units, and edges for the scope; mark units and edges no longer
present as `removed` with the commit; add new ones with new IDs; refresh metrics and change
history; leave every other row untouched. Change review: map only units the diff touches, their
direct dependents and dependencies, and every edge the diff adds, removes, or redirects; write the
resulting row additions, removals, and alterations to `deltas.md` for the implementer, and mark the
header `partial`. Plan review: the same, from proposed rows (see `plan-review.md`).
