# Mapping the architecture

How a mapping slice fills inventory rows, which the coordinator merges into the committed record
(`docs/architecture/`) or holds as candidate record updates. Work from the code, not
from documentation; documentation is recorded as the intended structure and compared with the
mapped graph in W8. A slice covers one component or top-level folder, returns rows, and never
writes files.

## Identifiers

- Component: `C<n>` with its path, for example `C3 packages/billing`.
- Unit: `U<n>` with its path and symbol, for example `U17 src/billing/PayrollService.ts:PayrollService`.
- Edge: `E<n>`, `from -> to`, using unit IDs. Shared data shapes use `E<n> C2 ~ C5 (table orders)`.
- Boundary: `B<n>`.
- External pseudo-unit: `external:<name>`, tagged framework, vendor, runtime, or standard library.

IDs are never reused. A removed unit keeps its row with status `removed` and the commit.

## Components

A component is an enforced unit behind one published surface: a package with an export map or
index, a module system module, a separately built library, or a folder whose imports a
build-failing rule restricts. With none of these, record each top-level source folder as a
component with enforcement `none`; W8 reports the gap.

Per component record: path; published surface (exported symbols reachable from outside);
enforcement mode (`visibility`, `exports`, `build-unit`, `import-rule`, `none`); ring (by the
majority of its units, mixed rings noted); actors; whether it is a release unit with a version.

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

Rings: `entities`, `use-cases`, `adapters`, `frameworks`, with `tests` and `composition` as the
two outermost pseudo-rings. Classify by what the unit does, not by folder name; a `services/`
folder full of SQL is `adapters`.

The ring is the unit's level for most purposes: entities highest, frameworks lowest. When W1 must
compare two units in one ring, or decide whether a `mixed` unit is policy or detail, use the finer
level: distance from the system's inputs and outputs, measured on the dependency graph.

1. Find the nearest entry point (route handler, command, message consumer) and count the hops to
   it along dependency edges, ignoring arrow direction.
2. Find the nearest device adapter (database client, mailer, screen, file system) and count the
   hops the same way.
3. The unit farther from both is the higher level.

Example: a use case imported by a route handler and importing a database client is one hop from
the entry and one from a device. A pay rule imported only by that use case is two hops from each,
so it is higher level than the use case; the route handler and the client, at zero hops from their
own side, are lowest.

## Actors and reasons to change

For each component and each `mixed` or public unit, list the actors: the roles or teams whose
requests would change it. Derive them from the ticket or brief when present, from commit history
(which features touched the unit and for whom), and from domain vocabulary in the code (finance,
compliance, delivery terms). Two actors on one unit is the evidence W2 needs; one actor is `OK`.

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
`direction` `inward` (toward policy), `outward` (toward detail), or `lateral` (same ring). An
outward edge from a policy unit is the primary W1 finding. Per component, also list the forbidden
edges the design names (in documentation or agent instructions) and whether each is enforced.

## Boundaries

Per port record: owner unit and its ring; implementers and their rings; consumers; the crossing
data type and whether it is boundary-data; which side is humble; the enforcement mode of the line
(what fails if a consumer imports an implementer directly). A port owned on the detail side, or
whose signature carries a detail type, is recorded as-is and flagged by W1.

## Entry points and composition roots

List every place control enters (routes, handlers, CLI commands, job triggers, message consumers)
and every place concrete details are constructed. A concrete detail constructed outside a
composition root is a W1 finding; more than one composition root per deployable is noted for W8.

## Metrics

Compute only when there are more than five components. Per component: fan-in (units outside
depending on units inside), fan-out (units inside depending on units outside), I = fan-out /
(fan-in + fan-out), A = abstract types / total types, counting types that exist only to be
implemented, D = abs(A + I - 1). Record volatility from change history (changes in the last N
releases). Keep the previous run's D for W6 to compare.

## Change history

The single history slice produces it, not mapping slices (see `slicing.md`). It walks the
version-control log once for the whole scope, default the last ten commits touching it or the
commits the ticket names, and returns one row per touched file per commit: the reason in one
phrase, the actor it served, and whether the reason is policy or detail. The coordinator attaches
rows to units by path and writes them to the ledger's `change-history.md`. The rows feed W2 (two
reasons on one unit), W1 (a high-level unit changing for low-level reasons), and W6 (volatility).
A scope with no history of its own yields an empty table, and those workflows run without
volatility evidence.

## Incremental update

Audit re-run: re-derive components, units, and edges for the scope; mark those no longer present
`removed` with the commit; add new ones with new IDs; refresh metrics and change history; leave
every other row untouched. Change review: map only units the diff touches, their direct dependents
and dependencies, and every edge the diff adds, removes, or redirects; hold the resulting row
additions, removals, and alterations as candidate record updates, written to the record only where
no open finding disputes them, and set each written file's header last-update part to this run. Plan review: the same, from proposed
rows (see `plan-review.md`).
