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

## Cross-cutting: value and priority

**R1. Deliver behavior and structure together, and judge structure by the cost of the next
change.** Behavior is what the change makes the system do; structure is what the change does to
the cost of the next change. Every design, plan, implementation, or review states both: the
behavior it delivers and how it keeps or lowers the effort of the next known change. Pattern names, layer counts, and diagrams
are not evidence; "it works" is the floor. No level of the code is exempt: a signature, a
parameter shape, or a helper's location constrains future change as much as a module boundary.
- Check: does the artifact contain both a behavior statement and a structure statement? For the one to three likely next requests here, how many units does each touch, and does any require reworking something unrelated?
- Bad review: "Works as described, approving."
- Good review: "Works as described. The retry policy is duplicated in both callers and the config is read inside the loop, so tuning it means three edits."

**R2. Name a shape mismatch instead of forcing the piece in.** When a request does not fit the
current structure, say so and either reshape first or record the debt with its cost. Never hide
the mismatch behind a boolean or mode parameter, a special case keyed on the caller, or a copy
with a twist. A boolean field in boundary data that describes state to display is not a
mismatch; a flag steering control flow through layers is.
- Check: did the change add a caller-specific parameter, a special case, or a near-copy? Was it named?
- Bad: `regularHours(threshold = 8)` so one caller can pass 9.
- Good: one function per owning actor, or a policy object per actor.

**R3. Importance first, urgency second; schedule structural work against a named upcoming
change.** Urgent work has a concrete cost if it ships later; important work changes the cost of
every later change. Structural work is important and rarely urgent, so it outranks
urgent-but-unimportant feature work; the common error is mistaking urgent-and-unimportant for
urgent-and-important.
Stakeholders will not ask for structure; the plan includes it, each item justified by a known
upcoming request whose cost it lowers. Structural work with no named upcoming change is
speculation and is not scheduled. Structural work that has become urgent is scheduled as
important-and-urgent and noted as earlier neglect.
- Check: is an important-not-urgent item ranked below an urgent-not-important one? Does every structural item name the request it protects? What concretely happens if the urgent item ships one iteration later?
- Bad: "Client asked for it in the demo, so the refactor waits."
- Good: "Invert the payment gateway first; the next provider integration lands as one adapter."

## W1. Dependency direction and ports

**R4. Dependencies point from detail toward policy, whatever way the data flows.** Level is
distance from the system's inputs and outputs; use cases and entities are highest, I/O adapters
lowest. Every source dependency that crosses levels points from lower to higher, so a policy
module never imports a database, framework, transport, vendor SDK, clock, file system,
configuration reader, the modules that read or write them, or the formats they generate. Data
flow and call flow do not set import direction: when a use case hands output to a presenter or
store, the adapter still depends on the use case; agreement between data flow and imports on
the input side is incidental. Drawn as rings (entities, use cases, interface adapters,
frameworks and drivers), the same rule reads: every cross-ring dependency points inward and no
inner ring names anything declared in an outer ring. The ring count is schematic; add a ring
when needed and state which two rings it sits between. The depended-upon side is immune to the
dependent; business rules must be that side at every boundary. Change frequency is the
diagnostic: a module meant to be high level that keeps changing for device, format, transport,
or vendor reasons is mis-leveled or holds detail; a rarely changing business rule sitting in an
I/O module is misplaced the other way.
- Check: list the imports and signature types of each policy module. Any framework, driver, SDK, environment read, or `new ConcreteDetail()`? Any module importing one nearer the I/O than itself? Could a schema, screen, or transport change break an entity or use case? For the last several changes, did any high-level module change for a low-level reason?
```ts
// bad: the highest-level function imports the I/O it is farthest from
import { PgClient } from "../persistence/PgClient";
class PayrollService { private db = new PgClient(); }
// good: policy owns the port; the detail implements it and imports the policy
interface EmployeeRepository { load(id: EmployeeId): Promise<Employee> }   // billing/
class PayrollService { constructor(private employees: EmployeeRepository) {} }
class PgEmployeeRepository implements EmployeeRepository { ... }            // persistence/, imports billing/
```

**R5. The consumer owns the port; the port carries only policy-side types.** The interface
lives beside the policy that calls it, not in the module that implements it and not in a shared
"interfaces" bucket. The line is drawn across the implementation relationship: interface above,
implementer below, the only crossing arrow the implements-edge pointing at the policy.
Inversion is two edges, policy to port and detail to port, with no direct edge between policy
and detail in either direction; the detail's name appears only in its own module, its tests,
and the composition root. Port signatures use domain types (a gateway may construct and return
entities, because its dependency points inward) or plain boundary data for ports facing the UI
or external agencies; never driver handles, framework request objects, ORM rows, or vendor
payloads, and a framework's row type is detail even when it is "just data". When several stable
consumers share one port, or the consumer must stay concrete, the port may live in its own
interface-only component that both sides depend on; such a component holds no executable code
and is a normal unit in statically typed languages, not a dumping ground.
- Check: which package declares the interface, and does the implementing package import it? Does any parameter or return type come from a detail module? Is there still a direct edge between policy and detail?
- Bad: `interface EmployeeRepository { find(conn: PgClient, id: string): PgRow }`
- Good: `interface EmployeeRepository { find(id: EmployeeId): Employee }`

**R6. Give each use case an input boundary it implements and output boundaries it declares.**
The controller depends on the input boundary, not on the use-case class. The use case calls an
output boundary toward the UI and a gateway toward storage; the presenter and the gateway
implement them. All these interfaces and the boundary data live in the use-case module. Control
runs controller to use case to presenter; every source dependency runs adapter to use case.
Whenever control must flow outward, use the same move: declare the interface inward, implement
it outward, never call outward directly.
- Check: does the use case import its presenter or gateway? Does the controller import the use-case class? Are the boundaries declared in the use-case module?
```ts
// usecases/place-order/
export interface PlaceOrderInput  { customerId: string; lines: Line[] }
export interface PlaceOrderOutput { orderId: string; total: Money }
export interface PlaceOrderInputBoundary  { execute(input: PlaceOrderInput): void }
export interface PlaceOrderOutputBoundary { present(output: PlaceOrderOutput): void }
export interface Orders { save(order: Order): void }
export class PlaceOrder implements PlaceOrderInputBoundary {
  constructor(private orders: Orders, private out: PlaceOrderOutputBoundary) {} ...
}
// web/PlaceOrderController.ts imports PlaceOrderInputBoundary; web/PlaceOrderPresenter.ts implements PlaceOrderOutputBoundary
// persistence/SqlOrders.ts implements Orders and holds all the SQL
```

**R7. Lower-level components are plugins; the policy builds and passes its tests with every
plugin absent.** The policy knows none of its plugins. Adding, swapping, or removing a UI,
store, framework, or vendor never edits an entity or use case; a replacement of a different
kind (a console UI where a web UI was) may adjust a port's boundary data, and that is the whole
cost: plugin structure makes replacement practical, not free. The asymmetry test: delete the
detail component and the rules still build and pass; delete the rules and the detail cannot
build, because the detail holds the translation into the rules' terms. Only the composition
root constructs concrete details and imports every level; nothing imports it. Frameworks are
tools the system uses, never a structure the rules are shaped to fit.
- Check: stub or delete the detail component; does the policy still build and pass? For each of framework, UI, database, and external service, list the modules a replacement would touch; is any in the policy? Is any concrete detail constructed outside the composition root?
- Bad: the use-case test suite boots the web framework and a database container.
- Good: use-case tests run against an in-memory store and a recording output boundary; a framework swap lists only controllers, presenters, and wiring.

**R8. Adopt a constraint only for the failure it prevents or the decision it defers.** Every
boundary, interface, or discipline removes a capability rather than adding one. Introduce one
when you can name what it forbids and the defect class that eliminates, or the decision about
the far side it lets you postpone. "Best practice" is not a reason; a boundary that does neither
is itself a premature decision.
- Check: for each abstraction introduced, can you write "this forbids X from naming Y, so a change to Y cannot ripple into X", or "this lets us choose Y after feature Z"?
- Bad: an interface per class because "we use interfaces".
- Good: "`PaymentGateway` forbids checkout from naming the vendor SDK, so a vendor swap cannot touch checkout."

**R9. Trace change impact along source dependencies, not calls, and include the tests.** To
assess what a change can break, follow imports and references (what must recompile and be
re-verified), not the runtime call graph. The impact set of a change to B is every unit that
depends on B directly or through other units, found by following dependency arrows backwards
from B; it is bounded by visibility, since a published
symbol can be depended on by anything and a unit-private symbol only by its unit. A change that
forces edits to many tests whose asserted behavior did not change is test coupling, not expected
fallout.
- Check: which modules import the changed symbol? Is it published beyond its unit? How many tests change, and did their asserted behavior change?

## W2. Reasons to change

**R10. One actor per module; split on evidence, not speculation.** A module serves exactly one
actor. When its public operations are requested by different roles or teams, split it along
actor lines; the evidence is two actors actually asking for different things, the request naming
them, or unrelated features repeatedly colliding in one file (a merge-conflict pattern is a
design signal, not a tooling problem). Separated units share a plain data type, never behavior;
any edge between two per-actor units re-couples the actors. If existing call sites must keep one
entry point, a thin facade is acceptable: a class that exposes the old operations and does
nothing but construct the per-actor units and forward calls to them. It holds no branching,
calculation, or persistence, and new consumers depend on the per-actor unit they need.
- Check: for each public operation, who would ask for it to change? Two or more distinct roles means two or more reasons to change. Do the split units depend only on the shared data type? Does the change history show unrelated features editing this file?
```ts
// bad: three actors in one class
class Employee { calculatePay() {}  reportHours() {}  save() {} }
// good: one unit per actor over a shared plain data type
class PayCalculator  { calculatePay(e: EmployeeData) {} }     // finance
class HourReporter   { reportHours(e: EmployeeData) {} }      // HR
class EmployeeSaver  { save(e: EmployeeData) {} }             // persistence
```

**R11. Deduplicate only when one owner wants every future change.** Identical code with
different owners is accidental duplication; merging it lets one actor's change silently alter
another's behavior. Real duplication has the same owner and the same reason to change. Request
and response models that mirror entity fields are not duplication: they change for different
reasons, so never collapse one into an entity reference.
- Check: before extracting a shared helper, would both callers want every future change to it?
- Bad: `regularHours()` shared by pay (finance) and the hours report (HR); finance changes it and HR reports go wrong silently.
- Good: `payableRegularHours()` in the finance unit, `reportedRegularHours()` in the HR unit.

**R12. Add behavior by adding code, behind an interface rather than a concrete base class.** New
variants (a payment method, license type, export format, channel) arrive as new implementations
of an existing abstraction; shipped, widely-depended-on code is not edited to add a case.
Implementations of an interface are independent and share no code; when two should share,
compose a helper in. Use inheritance only where the subtype is substitutable everywhere the
supertype is expected, never to borrow helpers.
- Check: list files modified versus files created. Is a stable module in the modified list to add a variant? Is a class extending another only to reuse a method?
```ts
// bad: every new kind edits Billing
if (l.kind === "personal") ... else if (l.kind === "business") ... else if (l.kind === "edu") ...
// good: Billing calls license.calcFee(); add class EduLicense implements License
```

**R13. Every implementation is substitutable and every consumer sees a narrow interface.**
Consumers of an abstraction never check the concrete type or special-case one implementation;
`instanceof`, kind checks, and downcasts in a consumer are architectural defects, because the
workaround spreads to every consumer. Each consumer depends on an interface containing only the
operations it calls; one implementation may satisfy several narrow interfaces, and the split
happens at the consumer's boundary, not by fragmenting the implementation. This holds in
dynamically and structurally typed languages too: the coupling exists whether or not a compiler
forces a rebuild. Polymorphism needs no class hierarchy: interfaces, protocols, structural
types, and function parameters all count.
- Check: search consumers for type checks on implementations. For each consumer, members used versus members exposed; a large gap means a narrower interface at the consumer.
```ts
// bad
fee = l instanceof BusinessLicense ? l.calcFee() * l.users : l.calcFee();
// good: BusinessLicense.calcFee() already accounts for users
fee = l.calcFee();
interface U1Ops { op1(): void }  interface U2Ops { op2(): void }
class Ops implements U1Ops, U2Ops { op1() {}  op2() {} }     // one implementation, two narrow views
```

**R14. Hide data behind behavior; only boundary data is public.** In a behavior-bearing unit,
data is reachable only through the functions that legitimately operate on it, and code outside
never reads or writes the internal representation, so the representation can change freely. The
exception is boundary data (request, response, view model, record): public fields, no behavior,
existing only to cross a boundary.
- Check: can any code outside the module read or write its data directly? Would a change to the internal representation break callers? Is the public-field structure a boundary type or a behavior-bearing object with its insides exposed?
```ts
// bad
export const cart = { items: [] as Item[] };   // callers push into items
// good
export class Cart { private items: Item[] = []; add(i: Item) {}  total(): Money {} }
```

**R15. Decompose into units that can be reasoned about alone.** Each function does one
stateable thing using only sequence, selection, and iteration (structured control flow): no
loops steered by flags set elsewhere, no exceptions used to jump out of ordinary paths, no
non-local state deciding which branch runs. Recursive decomposition into provable units
is what makes a program understandable and testable.
- Check: can you state what each function does without tracing shared flags or non-local jumps? Does each unit have a predictable exit?
```ts
// bad: control flow driven by flags across a large body
let done = false; while (!done) { ... if (x) { done = true; continue; } ... }
// good: recursively decomposed
const rows = parse(input); const valid = rows.filter(isValid); return summarize(valid);
```

**R16. Default to immutable values; keep mutation in few, named units at the edges.** Mutable
shared state is the source of races, deadlocks, and concurrent-update bugs. Express state as new
values derived from old ones; entity rule-functions return the updated entity and the use case
persists it through a port. The units that mutate (repositories, caches, sessions, the testing
API's state-forcing operations) are few, listed, and invoked by the use case; everything else
takes inputs and returns outputs. Mutation elsewhere is justified only by a measured cost.
- Check: can you list the units that mutate state? Is the list short? Is every remaining in-place update justified by a measured cost?

## W3. Business-rule placement

**R17. Bind critical rules to their critical data in an entity that knows nothing outside the
business.** A critical rule is one the organization would apply without software; its critical
data is what that rule needs and would exist on paper. Put a small set of such rules and exactly
that data in one module whose interface is the rule-functions; a data type with its
rule-functions in one module qualifies, no class required. Entity modules import no
persistence, transport, framework, UI, clock, or configuration code and no use case; they carry
no framework annotations, base classes, or serialization methods, and must be usable unchanged
in another application with a different delivery mechanism and store. When different actors own
different rules over the same data, one rule module per actor over a shared plain data type is
the split (R10).
- Check: is every field read by a rule-function, and would a clerk perform every function? List the entity's imports and decorators; anything beyond another entity or a value type (a small immutable type such as `Money` or `Period` that carries no identity) is a defect. Does any method name a channel or use case (`toJson`, `fromRow`, `onEstimationStarted`)?
- Bad: `@Entity() class Loan extends OrmModel { toJson() {} }`
- Good: `class Loan { applyInterest(): Loan {} }` importing only `Money`, `Rate`, `Period`.

**R18. Use cases hold application-specific rules, orchestrate entities, and depend on them
only.** A rule that exists because the system is automated (a required sequence, a gate before
an action, input-format validation, a flow threshold) lives in a use case, statable as input,
output, and numbered steps. The use case validates input format, loads entities through ports,
calls their rule-functions, persists results through ports, and decides what follows; business
invariants a manual operation would also enforce, and any arithmetic or decision a clerk would
make, belong on an entity. Choosing the next use case is application flow expressed in the
response; performing the navigation is the delivery mechanism's job. Use cases import entities;
entities never import, call back, or expose hooks for use cases. A stateless service or an
object holding its request and response are both acceptable shapes.
- Check: strip the use case of calls to entities and ports; only validation, sequencing, and branching should remain. Can any import path from an entity reach a use case? Is the use case statable as a card: input, output, numbered steps?
```ts
// bad: the use case computes interest
loan.balance = loan.balance * (1 + loan.rate / 12);
// good: the entity owns the rule; the use case sequences it
const loan = await this.loans.load(request.loanId);
await this.loans.save(loan.applyInterest());
```

**R19. Cross every boundary with plain data declared on the inner side.** A use case takes a
request model and returns a response model that import nothing, extend no framework type, wrap
no row or transport envelope, carry no channel-specific fields (headers, session, cookies,
widget state), and reference no entity; from its code it must be impossible to tell whether the
application is a web app, a console, or a headless service. The same holds for view models,
gateway results, and wire payloads: plain structures with public fields, no behavior, no lazy
references back across the boundary, shaped for the inner ring's convenience. Entities do not
cross outward to adapters or views; rows and framework objects do not cross inward. A shared
type across a boundary produces fields carried through code that never reads them and
shape-testing conditionals.
- Check: can the request and response be built in a test from literals alone? Does any boundary type have an import, a method, a framework base class, a lazy proxy, or an entity-typed field? Does any adapter branch on which shape it received?
```ts
// bad
class GatherContactInfoRequest extends HttpRequest {}
interface CreateLoanResponse { loan: Loan }
// good
interface GatherContactInfoRequest { name: string; address: string; birthdate: string }
interface CreateLoanResponse { loanId: string; principal: number; periodMonths: number }
```

## W4. Humble objects and adapters

**R20. Split hard-to-test behavior into a humble unit and a testable unit at every device
boundary.** Wherever code talks to a screen, driver, network, file system, or clock, the humble
unit keeps only the untestable essence with no conditional, calculation, formatting, or lookup,
and the testable unit holds every decision and is unit-tested with the humble unit replaced by
a double. The humble unit is the lower level; the testable unit owns the port it is reached
through. Inbound handlers and outbound senders are humble too: a controller only parses, builds
the request model, and calls the use case; a sender only serializes and transmits; neither
validates business rules, branches on domain state, or formats for display. Where the two
halves cannot be separated cleanly, a boundary is missing; draw it there. Once drawn, the humble
side's only defect class is mis-wiring, covered by a thin integration test through the entry
point.
- Check: name both units. Does the humble one contain any decision? Do the testable unit's tests run without the real device? If the humble unit had no tests, what defects could hide there? Does the handler do anything besides parse, convert, and invoke?
- Bad: `ReportPage` queries the store, sums rows, formats totals, and renders; an HTTP handler rejects orders over 10k before calling the use case.
- Good: `ReportPresenter` (tested with in-memory rows) produces `ReportViewModel`; `ReportPage` copies it to the screen; the approval rule lives in the use case.

**R21. The presenter finishes every decision; the view only copies the view model.** The view
model covers everything the application controls on the screen: for every label, button, menu
item, field, and table cell, and for every enabled, visible, selected, or highlighted state,
there is a field of type string, boolean, or enum set by the presenter; tables are tables of
formatted strings; dates and money are already formatted. The view model is a plain structure
with no methods and no domain references. The view binds fields to widgets and maps a flag or
enum to an appearance (color, icon, disabled state); it contains no conditionals on domain data,
arithmetic, formatting, lookups, or calls into the application. The presenter implements the
use case's output boundary and imports no UI framework. A framework's declarative formatter may
render a value only when no decision on domain data is involved.
- Check: walk the screen element by element and state by state; each maps to a field. Does the view model contain a `Date`, money type, raw number the view will format, or domain object? Read the view line by line: anything beyond binding or flag-to-appearance moves to the presenter. Can presenter tests assert on the view model with structural equality?
- Bad: `if (order.total < 0) label.color = RED; label.text = fmt(order.total)`; the view hides "Refund" by inspecting `order.status`.
- Good: `label.text = vm.totalText; label.color = vm.totalIsNegative ? RED : DEFAULT`; `refundButtonVisible: boolean`.

**R22. Reach storage through a gateway with one method per application need, and keep every
query below it.** The gateway is a consumer-owned port named in domain language (`Orders`, not
`OrdersRepository`) with methods for exactly the operations the application performs, typed in
application terms; per-need methods are the narrow interfaces of R13 in practice, and a generic
`query(sql)` or `find(spec)` escape hatch moves the decision to the caller. SQL, query builders,
ORM sessions, and connection handles appear only inside gateway implementations; a use case or
entity containing any of them is untestable without the store and has a missing gateway method.
An ORM (object-relational mapper, a library that turns table rows into objects) is a data mapper: its mapped types stay in the persistence component, converted to and
from domain types inside the gateway, and are never the domain model. The technology name
belongs on the adapter (`SqlOrders implements Orders`).
- Check: does each gateway method state a concrete need? Search use cases and entities for query strings, builders, sessions, or ORM-annotated types. Is an ORM entity class doubling as the domain model?
```ts
// good
interface Users { lastNamesOfUsersWhoLoggedInAfter(since: Date): Promise<string[]> }
// bad
interface Users { query(sql: string): Promise<Row[]> }
```

## W5. Deferral and boundary drawing

**R23. Defer every decision the use cases do not force; start each port in memory.** Framework,
store, web server, utility library, dependency injection, and deployment topology are premature
until a use case requires them. Decide the port and its direction now, build the first features
on stubs, then an in-memory implementation, then the cheapest durable option that meets the
requirement (flat files count), adding a heavier option only as a new implementation when a
real need arrives; the heavier option may never be written. When a mechanism is simple to write,
a thin one you control beats an early framework commitment, because it keeps the framework
choice open; the point is to postpone the choice, not to avoid frameworks.
- Check: for each technology the plan names, which use case needs it now? Does an in-memory implementation of each port exist and do the rule tests use it? Has any feature been blocked on choosing a store or framework? Is the chosen implementation the simplest that meets today's requirement, with the heavier one still a one-class addition?
- Bad: first task "choose ORM, design schema, pick web framework".
- Good: first task "`PageStore` port with an in-memory implementation; formatting features shipped on it; store chosen when saving across restarts is required."

**R24. Do not pay for tiers, processes, or a service suite before a team or deployment reason
exists today.** Topology is a deployment decision, not an architecture. Adopted early, one field
added to one record becomes edits in every tier, new wire messages, handlers on both ends,
serialization, timeouts, and retries, often for a distribution that never happens. Structuring
around services is not wrong in itself; adopting and enforcing a whole suite of domain services
before two teams or two deployments actually diverge is. Walk the smallest realistic feature
through the proposed structure and count components edited, messages designed, fields invented,
and processes a test must start; the count must be proportional to the feature.
- Check: does each service or tier exist for a team or deployment reason that holds today, or for anticipated scale? What is the cost of the simplest change?
- Bad: three deployables and four message protocols to add a phone number; tests boot every service and the bus.
- Good: one deployable with component boundaries; a remote adapter added when a second machine actually exists.

**R25. Draw a line at each axis of change, between every pair where one side does not matter
to the other.** A boundary belongs where the two sides change at different rates for different
reasons: UI versus rules, rules versus store, formatting versus storage, rules versus a
dependency-injection framework. The UI does not matter to the rules, the store does not matter
to the UI, so each pair gets its own boundary with the interface on the side that does not care
and the arrow pointing at it; every optional or many-formed component is a plugin to the core,
and plugins never depend on each other directly. Where both sides change together for the same
reason, no line is needed; where one module carries two cadences, a line is missing inside it.
Every boundary must justify itself by a decision it defers or an axis of change it separates
(R8).
- Check: for each proposed line, name the reason and cadence of change on each side. Do any two plugins import each other? Did any recent change cross a line, or did any module change for two unrelated reasons?
- Bad: the web module imports the store module to read a row for display; one `PageService` edited for wiki-syntax reasons and for file-format reasons.
- Good: web, store, and mail each depend on the rules and never on each other; `WikiFormatter` and `FileSystemPageStore` sit on opposite sides of `PageStore`.

**R26. The system is the model behind the ports; plan and demonstrate it with no I/O present.**
Stakeholders see the screen and call it the system; it is not. Every acceptance criterion must
be exercisable through a use-case boundary or testing API with no UI, store, or server in the
process, and the first slice delivers rules that way, described in terms of the model's
outputs rather than widgets. When visible progress is needed early, provide it through a console
or test adapter rather than by pulling the UI or schema decision forward.
- Check: does the plan's first slice require a screen or a schema to demonstrate progress? Can every acceptance criterion run with the UI absent?
- Bad: "first deliver the screens, then wire the logic behind them".
- Good: "first deliver the model behind an input port and a recording output port; the first screen adapter comes two deliveries later".

## W6. Components, cycles, and stability

**R27. A component is one enforced unit behind one published surface; group by reason to
change and by co-reuse.** Draw component boundaries where the contents hide behind a single
published surface (the symbols other code may import) and, where they are a release unit,
build, test, version, and release together; two "components" that always release together and share a public surface are one
component. Classes that change for the same reasons at the same time live in one component
(single responsibility at component scale), so a requirement change lands in one component; a
plan names that home component or the boundary defect that prevents it. Classes reused together
live together, and a dependency on a component is a dependency on all of it, so consumers must
use most of what they import; a class used alone by outsiders belongs with its co-reused
neighbors. Code for one concept that changes for both policy and persistence reasons may share
one enforced unit when the persistence part is unit-private; the split into two release units
waits until change patterns demand it.
- Check: for the planned change and the last several, how many components did each touch? Does every consumer use most of each component it imports? Can you state in one sentence what each component is for?
- Bad: a tax-rule change edits `core`, `api`, and `reporting`; billing imports `cms-kernel` for one string helper; a `common` package holds date helpers, a retry policy, and a `Money` type.
- Good: tax rules live in `tax-policy`; `slugify` lives in a `text` component.

**R28. Choose a position in the cohesion tension and name its cost; expect it to drift.**
Three motives decide where a component's edges go, and they cannot all be satisfied. Grouping
for maintenance puts units that change for the same reasons together, so one change lands in one
component. Grouping for reuse puts units that are always used together into one versioned
release, so consumers can adopt them as a whole. Splitting to avoid unneeded releases takes out
units that some consumers never use, so those consumers stop being rebuilt and redeployed for
changes that do not concern them. The first two grow components; the third shrinks them. Each
neglect has a cost: neglect splitting and consumers receive too many unneeded releases; neglect
maintenance grouping and too many components change per requirement; neglect reuse grouping and
the component is hard to reuse or version. Early projects lean toward grouping for maintenance,
because localizing change matters more than reuse; as reuse appears the structure drifts toward
finer, reuse-driven splits. Revisit boundaries when change and reuse patterns shift, and record
which cost each component currently accepts in the decisions file.
- Check: which of the three motives is this component neglecting, and is that cost acceptable for the project today? When were its boundaries last reconsidered against current change and reuse patterns?
- Example: early product: "`orders` grouped broadly so one change lands in one place; we accept unneeded releases." Mature platform: "`orders-reporting` split out so reporting consumers stop receiving core releases."

**R29. Let the component map emerge from real change; decide how boundaries are enforced up
front.** Which units belong in one component depends on which ones actually change together
and are reused together, and that is only visible after code has been written and changed a few
times. So a design made before code exists does not fix the full component map. It names the
first two or three components by the code the first features will change together, and states
that splits for reuse and fixes for cycles will follow as the code grows. What such a design does
fix is the mechanism that will make every boundary real, because that is cheap to decide early
and expensive to change later: what a component exports (its published surface), whether folders
carry import rules that fail the build, and whether components are separate build units (built
and versioned on their own). With the mechanism fixed, adding or splitting a component later
changes the map, not the tooling. A single change works at a smaller scale: it names the
component it lands in and the direction of any new dependency it introduces, and it never
redraws the map.
- Check: was the component map derived from observed change and reuse, or guessed from the domain's nouns before any code existed? Is the enforcement mechanism decided even though the map is deliberately incomplete?
- Bad: a design for a new system fixes twelve packages and the arrows between them before any feature is written, with no statement of how a package boundary is enforced.
- Good: "Every package exports only its index; import rules fail the build on cross-package deep imports. First components: `orders` and `catalog`, because the first three features change them together. `membership` stays inside `lending` until it gains its own actor."

**R30. No dependency cycles; break one by inverting an edge or extracting a cohesive leaf.** A
cycle makes every component in it one component that none can build, test, or release alone,
and a change anywhere in the cycle can break work everywhere in it. Preferred fix: define the
needed interface in the component that needs it and have the other implement it. Alternatives:
an interface-only component both depend on, or extraction of the shared concrete classes into a
new component both depend on, acceptable when the extracted set is cohesive and a smell when it
is a grab-bag. Draw the graph with unstable components on top so an upward arrow is visibly
wrong. Acyclic is necessary, not sufficient: list the specific forbidden edges too (R39).
- Check: following "depends on" from this component, can you return to it? Does tooling enforce acyclicity? Drawn with unstable components on top, does any arrow point up?
```ts
// before: entities -> authorizer (User imports Permissions) -> interactors -> entities
// after:  entities/Permissions.ts       export interface Permissions { allows(action: string): boolean }
//         authorizer/PermissionsImpl.ts import { Permissions } from "entities"; class PermissionsImpl implements Permissions {}
// now authorizer -> entities, and entities depends on nothing
```

**R31. Depend toward stability, and make stable components abstract at their edges.** Stability
is a property of the graph, not of intent: many dependents and few dependencies means hard to
change. For each edge A depends on B, B must be at least as stable as A; a component designed to
change often must not be depended on by one that is hard to change, or it inherits that
stability and cannot fulfil its purpose. Business rules sit in the most stable components;
vendor clients, framework glue, and UI sit in the least stable, and only software meant to
change quickly lives there. A stable component is made of interfaces and abstract types so it
can be extended without modification; everything it needs from the volatile world is a port it
owns. Concrete code in a stable component is acceptable only when it genuinely does not change;
an unstable component stays concrete so it is cheap to change. A correct level ordering yields a
correct stability ordering because plugins give the high level its fan-in; where they disagree,
level wins and the mismatch signals a missing plugin edge.
- Check: count incoming and outgoing dependencies at both ends of each edge; does stability increase along the arrow? Is any heavily depended-on component both concrete and frequently changed? Does a rarely depended-on component declare interfaces nobody implements?
- Bad: `entities` depends on `feature-flags-ui`; `payments-domain` contains `StripeClient`.
- Good: `feature-flags-ui` depends on `entities`; `payments-domain` exports `PaymentGateway` and `stripe-gateway` implements it.

**R32. On larger graphs, use instability and abstractness as a screen, never a verdict.**
When the component graph has more than a handful of components, compute the metrics defined in
`metrics.md`: instability (how much a component depends on others compared with how much others
depend on it), abstractness (how much of it is interfaces and abstract types), and distance from
the balanced line where the two add up. Two positions are harmful. Zone of pain: many
dependents, concrete code, and frequent change, so every change ripples outward and the
component cannot be extended without editing; the canonical case is a database schema every
service imports. Fix by shielding dependents behind a port the component owns or by moving them
onto an interface-only component. Zone of uselessness: interfaces or abstract types that nothing
implements or nothing depends on; delete them or fold them into their one consumer. Examine
components that sit far from the balanced line relative to the rest of the graph, and a
component whose distance jumped since the previous run. A flagged number is a measurement
against a chosen pattern: explain in words why the position is harmful (volatile and depended
on, or abstract and unused) before demanding a restructure. On small graphs skip the arithmetic
and apply R31 qualitatively.
- Check: which components lie far from the balanced line, and to which side? What was each component's distance at the previous run? Can each flag be explained in words?
- Example: a domain component that is mostly interfaces and depended on by everything sits near the line: fine. A `shared-utils` package that is all concrete code, depended on by everything, and changed weekly sits in the zone of pain: examine. A `string-utils` package in the same position but unchanged for two years: note and leave alone.

**R33. Release components bottom-up, let dependents adopt on their own schedule, and integrate
continuously.** In an acyclic graph a component is released once everything it depends on is
released; the set a release can affect is exactly its transitive dependents, and their owners
decide whether and when to adopt. Cross-component dependencies target a published interface
and, across release units, name a version with a readable change record; consumption by path,
where any commit changes everyone's build, is a missing boundary. Integration happens
continuously at component boundaries; batching it into a scheduled step lowers cost for days
and then concentrates it into a crisis that grows with the project.
- Check: given this change's component, have you listed its transitive dependents? Can a dependent stay on the previous version? Does the plan rely on a big-bang integration step?
- Bad: shared code consumed by relative path so any commit in it changes everyone's build; "teams work in isolation Monday to Thursday, integrate Friday."
- Good: consumers pin a version and upgrade deliberately; each team releases its component when ready.

## W7. Tests as a component

**R34. Tests are the outermost component: they depend inward, nothing depends on them, and they
never ship to production.** The test suite imports what it verifies; no production module
imports a test, fixture, fake, or helper, and every kind of test, from a small developer test to
a large acceptance suite, follows the same dependency rules. Tests are built and run as their
own unit and the production deployable carries no test code or test-only endpoints; in a
monorepo (one repository holding several packages), a separate package or an enforced folder excluded from the production artifact
satisfies this. Test-only powers (bypass security, force state, skip expensive resources) live
in a separate testing component the production composition root never imports, never as a flag
or environment check in production code. Because such tests bypass authorization, a separate
small set exercises the security adapters.
- Check: does any production module import a test path? Does the production artifact contain test routes or a test-mode flag? Is authorization covered by tests that do not use the bypass?
- Bad: `if (process.env.TEST_MODE) skipAuth()` in the production auth adapter.
- Good: a `testing-api` package depends on the use cases' ports and is imported only by the test component and the test-environment composition root.

**R35. Verify business rules through a testing API, never through volatile surfaces.** GUIs,
navigation, login flows, and vendor paths are volatile; a suite that reaches rules through them
breaks on every small change and makes the system rigid because developers stop changing it.
Provide one surface that exposes every use case the UI can reach, with the same request and
response models, plus test-only powers: act as any role without a credential flow,
short-circuit expensive resources such as databases and vendors, force the system into a chosen
state in one call rather than replaying a workflow. It is an entry point of the test deployment,
not an intermediate component. End-to-end tests through the UI stay few and assert the UI
itself, not business outcomes. A wide breakage from a small change is an architecture defect,
not test maintenance.
- Check: for each business-rule assertion, what does the test traverse to reach the rule? Can a test reach its starting state in one call? For the last few UI or structural changes, how many tests changed while asserted behavior did not?
```ts
// bad: rule reached through login and navigation
await page.goto("/login"); await login(page); await page.click("#loans"); await page.click("#new");
expect(await page.textContent("#interest")).toBe("12.50");
// good: rule reached through the testing API
const r = await testApi.applyInterest({ loanId: seeded.loanId });
expect(r.interest).toBe("12.50");
```

**R36. Organize tests by behavior, so tests and production evolve independently.** A test class
per production class and a test method per method is structural coupling: renames, splits, and
merges force test changes with no behavior change. A unit under test is a behavior reached
through its public surface or the testing API. Over time tests grow more concrete and specific
while production grows more abstract and general; the test boundary exists so production
internals can be refactored without touching tests and tests can be consolidated without
touching production.
- Check: does the test tree mirror the production tree file for file? Would extracting or merging a production class force tests to move? After the last internal refactor, did tests change? After the last suite cleanup, did production change?
- Bad: `InterestCalculator.test.ts` asserts `monthlyRate()` and `compound()` separately.
- Good: `loan-interest.test.ts` asserts `applyInterest` outcomes; the class split is invisible; forty scenario tests collapse into one data-driven table with zero production edits.

**R37. Tests falsify, they do not prove; design them into the plan.** A green suite means no
test found a defect. Each test targets a concrete way the code could be wrong, and the plan
states, per behavior, which defect the test catches and through which surface it is verified.
Never write "tests pass, therefore correct". A test that broke because structure changed while
behavior did not falsified nothing; count it as a coupling defect. A humble unit that is hard to
unit test is not evidence of correctness either; its defect classes are limited by keeping it
thin. Tests not designed as part of the system become fragile and are eventually discarded,
taking their regression protection with them.
- Check: does each test name the wrong behavior it would catch? Does the plan name the verification surface per behavior? Does the review ask what the tests are coupled to?
- Bad: `expect(sort([])).toEqual([])` as the only test, then "sort is verified".
- Good: "a 10-hour day pays 9 regular hours (catches the old cap); the report still counts 8 (catches a shared helper); the use case runs against an in-memory store (catches a policy-to-detail import)."

## W8. Enforcement and code organization

**R38. Enforce every boundary with the compiler or the build, and publish only for a named
consumer.** A boundary exists only if crossing it fails to compile, resolve, or build; with
everything public, every organization style is a layered architecture with optional layer
skipping. Prefer, in order: language visibility and module exports (immediate,
non-negotiable); separate build units (compile-time, costs build complexity); dependency rules
that fail the build (crude, slower feedback, the strongest mode where the language has no
cross-folder visibility); code review, never alone, because it fails under deadline pressure.
Every symbol is unit-private unless a concrete outside consumer needs it; concrete
implementations are never published when only their interface is consumed; deep imports into a
component's internals must not resolve. Module systems and package export maps distinguish
public (visible inside the module) from published (visible outside); publish only the
component interface and its wiring factory.
- Check: for each boundary, what concrete error does a developer see when crossing it? For each exported symbol, who outside consumes it? Does a deep import into another component resolve?
```ts
// bad: everything published; the package is a folder
export interface OrdersComponent {}   export class OrdersComponentImpl {}
export interface Orders {}            export class SqlOrders {}
// good: one published interface plus wiring; the rest is unit-private
export type { OrdersComponent } from "./OrdersComponent";
export { createOrdersComponent } from "./wiring";
```

**R39. List the forbidden edges and make them uncompilable.** A graph can be acyclic and
inward-pointing and still let a controller reach a repository directly, bypassing the layer
that authorizes access. Plans and reviews name the unit-to-unit edges that must not exist and
the mechanism that prevents each. Layer skipping, a unit depending on one two or more levels
below it and so bypassing the checks of the level between, is forbidden by default; an intended
skip (a read path bypassing command-side logic) is written into the plan with the risk it
accepts.
- Check: which module-to-module edges must not exist, and what fails if one is written? Does any module depend on one two or more levels below it, and is that written down?
- Bad: `OrdersController` injects `Orders` "because the interface was already there".
- Good: `Orders` is unreachable from `web`; the plan lists "web to persistence: forbidden, enforced by package exports".

**R40. Organize a monolith by domain component, choose the style by the public surface it
leaves, and size enforcement to the team.** Given the same classes, each style leaves a
different minimum public set. Package by layer: every layer interface public, layer skipping
possible. Package by feature: only the entry class public, but that entry is a
delivery-mechanism controller. Ports and adapters: domain interfaces public to UI and
persistence units, adapters can still see each other. Package by component: one
delivery-agnostic interface per concept public, persistence unreachable from outside; the
default for a monolith. Bundle the logic and persistence for one concept into one enforced unit
with one published interface and a wiring factory; keep controllers and views outside; inside,
the ring separation is unit-private structure; this is the stepping stone to extracting a
service later with the same boundary and a different decoupling mode. Top-level names are
concepts (`orders`, `catalog`) plus the delivery units outside them, never `web`, `service`,
`data`, so the code for one use case lives in one unit. Ideally one build unit per component;
the pragmatic fallback is two (domain, infrastructure) with visibility restricted inside
infrastructure so one adapter cannot call another around the domain. The design states the style,
the enforcement mode per boundary, and the run-time decoupling (in-process wiring or separate
process), sized to team size, skill, complexity, time, and budget, and says why that level is
sufficient; leave options open where cheap and do not pay for build units the team does not yet
need.
- Check: list what stays public under the chosen style; does it contain a repository, mapper, or implementation the design says must not be reached directly? Does each concept have exactly one published entry with implementation, ports, and adapters unit-private and no delivery class inside? From the top-level names alone, what business is this? Does the plan name style, enforcement per boundary, and run-time mode, with a justification against team constraints?
```ts
// orders/        OrdersComponent (published), OrdersComponentImpl, Orders port, SqlOrders adapter (private)
// web/           OrdersController imports only OrdersComponent
// app/wiring.ts  createOrdersComponent(...) handed to the controller
```

**R41. Verify the real dependency graph and watch for coupling imports do not show.** Derive
the module graph from the code (imports and build dependencies), compare it with the intended
one, and turn each unexpected edge into a finding. Two components reading or writing the same
tables, documents, or wire shapes are coupled although no import connects them.
- Check: has the graph been generated rather than recalled? Which edges exist in code but not in the design? Which components share a persisted or serialized shape, and would a change to it edit both?
- Bad: `orders` and `reporting` both map the `orders` table; a column rename edits both.
- Good: `reporting` reads through `OrdersComponent` or a projection `orders` owns and publishes.
