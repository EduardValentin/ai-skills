# Enforcement and code organization

The rules that make boundaries real (R38 to R41): enforce them with the compiler or the build,
publish only what a named consumer needs, make forbidden edges uncompilable, organize a monolith
by domain component, and compare the real dependency graph with the intended one. Read this file
when a review or audit touches a component's published surface or enforcement, a forbidden edge,
the top-level organization, or a shape that several components read or write.

## Rules

### R38. Enforce boundaries with the build

**Enforce every boundary with the compiler or the build, and publish only for a named consumer.**
A boundary exists only if crossing it fails to compile, resolve, or build; with everything public,
every way of organizing code becomes layers that any unit may skip. Prefer, in order: language
visibility and module exports, which are immediate and non-negotiable; separate build units, which
fail at compile time and cost build complexity; dependency rules that fail the build, which are
cruder and slower but the strongest mode where the language has no visibility across folders; and
code review, never alone, since it fails under deadline pressure. Every symbol is private to its
component unless a concrete outside consumer needs it; a concrete implementation is never
published when only its interface is consumed; a deep import into a component's internals does
not resolve. Publish only the component's interface and its wiring factory.

Check questions:
- For each boundary, what concrete error does a developer see when crossing it?
- For each published symbol, who outside the component consumes it?
- Does a deep import into another component resolve?

Examples:
```ts
// bad: everything published; the package is a folder
export interface OrdersComponent {}   export class OrdersComponentImpl {}
export interface Orders {}            export class SqlOrders {}
// good: one published interface plus wiring; the rest is private to the component
export type { OrdersComponent } from "./OrdersComponent";
export { createOrdersComponent } from "./wiring";
```

Not a finding when: `unenforced-component`: no exemption; `unconsumed-export`: the component is a library whose published surface serves consumers outside the repository, as its documentation states; `unconsumed-export-of-unpublished-component`: the component is such a library, serving consumers outside the repository.

### R39. Make forbidden edges uncompilable

**Name the forbidden edges and make them uncompilable.** An acyclic graph whose dependencies all
point inward can still let a controller reach storage directly, bypassing the use case that
authorizes access. Plans and reviews name the dependencies between units that must not exist and
the mechanism that prevents each, and record them as forbidden edges. A ring skip is forbidden by
default; an intended skip, such as a read path that bypasses command-side logic, is recorded with
the risk it accepts. A detail implementing or translating to policy types, such as a gateway
constructing entities as R5 (The consumer owns the port) allows, bypasses no check and is not a
forbidden skip.

Check questions:
- Which dependencies must not exist, and what fails if one is written?
- Does any unit skip a ring, and is that recorded?

Examples:
- Bad: `OrdersController` is handed `Orders` "because the interface was already there".
- Good: `Orders` is unreachable from `web`; the plan lists "web to persistence: forbidden, enforced
  by package exports".

Not a finding when: `edge-skips-ring`: no exemption; `forbidden-edge-present`: no exemption.

### R40. Organize a monolith by domain

**Organize a monolith by domain component, choose the style by the public surface it leaves, and
size enforcement to the team.** Given the same classes, each style leaves a different minimum
public set. Package by layer: every layer's interface is public and layers can be skipped. Package
by feature: only the entry class is public, but that entry is a delivery-mechanism controller.
Ports and adapters: domain ports are public to UI and persistence, and adapters still see each
other. Package by component: one interface per concept, independent of any delivery mechanism, is
public, and persistence is unreachable from outside; this is the default for a monolith. Bundle
one concept's logic and persistence into one enforced unit with one published interface and a
wiring factory; controllers and views stay outside, and ring separation inside it is private
structure. That unit is the stepping stone to a later service extraction with the same boundary
and a different way of decoupling. Top-level names are concepts (`orders`, `catalog`) plus the
delivery units outside them, never `web`, `service`, `data`, so one use case's code lives in one
unit. Ideally there is one build unit per component; the pragmatic fallback is a domain build unit
and an infrastructure build unit, with visibility restricted inside infrastructure so no adapter
calls another around the domain. The design states the style, the enforcement mode per boundary,
and the run-time decoupling (in-process wiring or a separate process), sized to the team's size,
skill, complexity, time, and budget, and says why that level suffices; it leaves cheap options open and pays
for no build unit the team does not yet need.

Check questions:
- Under the chosen style, what stays public? Does it include a gateway, mapper, or implementation
  the design says must not be reached directly?
- Does each concept have exactly one published entry, with its implementation, ports, and adapters
  private and no delivery class inside?
- From the top-level names alone, what business is this?
- Does the plan name the style, the enforcement per boundary, and the run-time mode, with a reason
  tied to the team?

Examples:
```ts
// orders/        OrdersComponent (published), OrdersComponentImpl, Orders port, SqlOrders gateway (private)
// web/           OrdersController imports only OrdersComponent
// app/wiring.ts  createOrdersComponent(...) handed to the controller
```

Not a finding when: `structure-named-by-technology`: the technical top-level folders hold only delivery or infrastructure code, while each concept's rules and persistence live in its own component.

### R41. Verify the real dependency graph

**Verify the real dependency graph, and watch for coupling that imports do not show.** Derive the
graph from the code, compare it with the intended graph, and turn each unexpected dependency into a
finding. Two components that read or write the same tables, documents, or wire shapes are coupled
although no import connects them.

Check questions:
- Was the graph generated from the code rather than recalled?
- Which dependencies exist in the code but not in the design?
- Which components share a stored or serialized shape, and would a change to it edit both?

Examples:
- Bad: `orders` and `reporting` both map the `orders` table, so a column rename edits both.
- Good: `reporting` reads through `OrdersComponent`, or through a projection `orders` owns and
  publishes.

Not a finding when: `shared-shape-without-owner`: the shape is an external standard both components implement, such as a file format or a wire protocol defined outside the system, so its owner is that standard.

## Conditions

| Id | Condition | Rule | Decided by | Severity | Defect |
|---|---|---|---|---|---|
| `unenforced-component` | A component whose enforcement is none or review has dependents in other components. | R38 | check | major | `boundary-not-enforced` |
| `deep-import` | A unit in another component depends on a unit outside a component's declared published surface. | R38 | check | major | `deep-import` |
| `unconsumed-export` | A component with a declared published surface publishes a symbol that no unit outside it imports. | R38 | check (needs signatures, symbolImports) | major | `published-without-consumer` |
| `concrete-published-beside-interface` | A component publishes a concrete implementation although outside code consumes only its interface. | R38 | judgment | major | `published-without-consumer` |
| `unconsumed-export-of-unpublished-component` | A component with no declared published surface exports a symbol that no unit outside it consumes. | R38 | judgment | major | `published-without-consumer` |
| `forbidden-edge-present` | A dependency matches a recorded forbidden edge. | R39 | check | major | `forbidden-edge` |
| `forbidden-edge-unenforced` | A recorded forbidden edge is absent from the code, but nothing in the build would stop it. | R39 | judgment | major | `forbidden-edge-unenforced` |
| `edge-skips-ring` | A unit depends on a unit more than one ring inward with no recorded exception, and the skip is not a detail implementing or translating to policy types. | R39 | judgment | major | `edge-skips-ring` |
| `structure-named-by-technology` | The top-level structure is named by technology, such as web, service, or data, so a use case's code is spread across those technical folders. | R40 | judgment | major | `structure-named-by-technology` |
| `delivery-inside-domain-component` | A delivery-mechanism class sits inside a domain component, or persistence is reachable from delivery code. | R40 | judgment | major | `delivery-inside-domain-component` |
| `edge-outside-intended-graph` | An edge present in the code is absent from the intended component graph. | R41 | judgment | major | `edge-outside-intended-graph` |
| `shared-shape-without-owner` | Components share a table, document, or wire shape that no component owns. | R41 | judgment | major | `shared-shape-without-owner` |
