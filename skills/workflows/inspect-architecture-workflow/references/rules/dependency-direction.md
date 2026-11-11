# Dependency direction and ports

The rules that keep every dependency pointing from detail toward policy (R4 to R9): where ports
live, who constructs details, when an abstraction is justified, and how far a change ripples.
Read this file when a review or audit touches a cross-ring edge, a port, a construction site, or
a use case's callers.

## Rules

### R4. Dependencies point toward policy

**Dependencies point from detail toward policy, whatever way the data flows.** Every source
dependency that crosses levels points from the lower level to the higher one, so the
depended-upon side is immune to changes on the depending side, and business rules are that side
at every boundary. A policy unit never depends on a database, framework, transport, vendor SDK,
clock, file system, configuration reader, the units that read or write them, or the formats they
produce. Data flow and call flow do not set the direction: a use case handing output to a
presenter or a store is still depended on by that adapter. Every dependency that crosses rings
points inward, and a ring added when needed states which two rings it sits between. Inside one
ring the same holds by the finer level the classification guide describes: a unit never depends on
one nearer the inputs and outputs than itself. Change frequency is the diagnostic: a policy unit
that keeps changing for device, format, transport, or vendor reasons holds detail, and a rarely
changing business rule inside an I/O unit is misplaced the other way.

Check questions:
- What does each policy unit import and name in its signatures? Any framework, driver, SDK,
  environment read, or construction of a concrete detail?
- Does any unit import one nearer the inputs and outputs than itself?
- Could a schema, screen, or transport change break an entity or a use case?
- In the change history, did a policy unit change for a detail reason?

Examples:
```ts
// bad: the highest-level unit imports the I/O it is farthest from
import { PgClient } from "../persistence/PgClient";
class PayrollService { private db = new PgClient(); }
// good: policy owns the port; the detail implements it and depends on the policy
interface EmployeeRepository { load(id: EmployeeId): Promise<Employee> }   // payroll/
class PayrollService { constructor(private employees: EmployeeRepository) {} }
class PgEmployeeRepository implements EmployeeRepository { ... }            // persistence/, imports payroll/
```

Not a finding when: `policy-imports-external`: the external does no I/O and a recorded exception names it as part of the policy's language, such as a decimal or date-arithmetic library; `outward-ring-edge`: the depending unit is a test that drives the system through its composition root or an entry point, since tests are the outermost component.

### R5. The consumer owns the port

**The consumer owns the port, and the port carries only policy-side types.** The port lives
beside the policy that calls it, not in the implementing unit or a shared interfaces bucket.
Inversion is two dependencies, policy to port and detail to port, with no direct dependency left
between policy and detail. The detail's name appears only in its own unit, its tests, and the
composition root. Port signatures use domain types (a storage port may return entities, since the
gateway behind it depends inward) or plain boundary data; never driver handles, framework request
objects, rows, or vendor payloads. A framework's row type is detail even when it is "just data".
When several stable consumers share one port, or the consumer must stay concrete, the port may
live in an interface-only component both sides depend on.

Check questions:
- Which component declares the port, and does the implementing component depend on it?
- Does any parameter or return type come from a detail unit?
- Is there still a direct dependency between the policy and the detail?

Examples:
- Bad: `interface EmployeeRepository { find(conn: PgClient, id: string): PgRow }`
- Good: `interface EmployeeRepository { find(id: EmployeeId): Employee }`

Not a finding when: `port-in-shared-bucket`: the shared component holds only ports that several stable consumers use, with no executable code, so it is an interface-only component rather than a bucket.

### R6. Use cases own their boundaries

Advisory by default in a legacy baseline.

**Give each use case an input boundary it implements and output boundaries it declares.** The
controller depends on the input boundary, not on the use-case class. The use case calls an output
boundary toward the UI and a storage port toward storage; the presenter and the gateway implement
them. These ports and their boundary data live in the use-case component. Control runs from
controller to use case to presenter while every dependency runs from adapter to use case: wherever
control must flow outward, declare the port inward, implement it outward, and never call outward
directly.

Check questions:
- Does the use case import its presenter or its gateway?
- Does the controller import the use-case class?
- Are the boundaries declared in the use-case component?

Examples:
```ts
// usecases/place-order/
export interface PlaceOrderInput  { customerId: string; lines: Line[] }
export interface PlaceOrderOutput { orderId: string; total: string }
export interface PlaceOrderInputBoundary  { execute(input: PlaceOrderInput): void }
export interface PlaceOrderOutputBoundary { present(output: PlaceOrderOutput): void }
export interface Orders { save(order: Order): void }
export class PlaceOrder implements PlaceOrderInputBoundary {
  constructor(private orders: Orders, private out: PlaceOrderOutputBoundary) {} ...
}
// web/PlaceOrderController imports PlaceOrderInputBoundary; web/PlaceOrderPresenter implements PlaceOrderOutputBoundary
// persistence/SqlOrders implements Orders and holds all the query code
```

Not a finding when: `controller-imports-use-case`: the system has one delivery mechanism and no second one is stated in the scope or confirmed by the user, so record an exception for that controller-to-use-case dependency with the reason, and add no input boundary for a caller that does not exist.

### R7. Lower-level components are plugins

**Lower-level components are plugins: the policy builds and passes its tests with every plugin
absent.** Adding, swapping, or removing a UI, store, framework, or vendor never edits an entity or
a use case. A replacement of a different kind (a console UI where a web UI was) may adjust a port's
boundary data; that is the whole cost. Asymmetry test: delete the detail and the rules still build
and pass; delete the rules and the detail cannot build, because it holds the translation into the
rules' terms. Only the composition root constructs concrete details. Frameworks are tools the
system uses, never a structure the rules are shaped to fit.

Check questions:
- With the detail stubbed or deleted, does the policy still build and pass?
- For a replacement of the framework, UI, store, or an external service, which units change? Is
  any of them policy?
- Is any concrete detail constructed outside the composition root?

Examples:
- Bad: the use-case tests boot the web framework and a database container.
- Good: use-case tests run against an in-memory store and a recording output boundary; a framework
  swap touches only controllers, presenters, and wiring.

Not a finding when: `detail-constructed-outside-root`: the constructing unit is a component's wiring factory, which R38 (Enforce boundaries with the build) has the component publish and which the model classifies under a kind whose role is wiring, such as `config`.

### R8. Constraints need a named reason

**Adopt a constraint only for the failure it prevents or the decision it defers.** Every boundary,
interface, or discipline removes a capability rather than adding one. Introduce one when you can
name what it forbids and the class of defect that removes, or the decision about the far side it
postpones. "Best practice" is not a reason, and a boundary that does neither is itself a
premature decision.

Check questions:
- For each abstraction introduced, can you write "this forbids X from naming Y, so a change to Y
  cannot ripple into X", or "this lets us choose Y after feature Z"?

Examples:
- Bad: an interface per class because "we use interfaces".
- Good: "The port `Payments` forbids checkout from naming the vendor SDK, so a vendor swap cannot touch
  checkout."

Not a finding when: the abstraction names the decision it defers or the ripple it forbids, for example in its port's recorded `defers` reason, however few consumers and implementers it has.

### R9. Trace change impact along dependencies

**Trace change impact along dependencies, not calls, and include the tests.** Follow imports and
references, which decide what must be rebuilt and re-verified, not the run-time call graph. The
impact of a change to B is every dependent of B. Visibility bounds it: a published symbol can be
depended on by anything, a private one only inside its component. A change that forces edits to
many tests whose asserted behavior did not change is structural coupling, not expected fallout.

Check questions:
- Which units depend on the changed symbol? Is it published beyond its component?
- How many tests change, and did their asserted behavior change?

Not a finding when: the edited tests assert behavior the change deliberately altered, or the only test edits follow a deliberate rename of a published symbol the tests call.

## Conditions

| Id | Condition | Rule | Decided by | Severity | Defect |
|---|---|---|---|---|---|
| `policy-imports-detail` | A policy unit depends on a unit whose role is detail or wiring, with no barrel at either end. | R4 | check | blocker | `policy-depends-on-detail` |
| `policy-imports-external` | A policy unit imports an external package tagged framework, vendor, or runtime. | R4 | check | blocker | `policy-depends-on-detail` |
| `outward-ring-edge` | Any other dependency points from an inner ring to an outer one, with no barrel at either end. | R4 | check | blocker | `outward-dependency` |
| `policy-changes-for-detail-reason` | A policy unit changed for a device, format, transport, or vendor reason in at least {detailReasonChanges} changes within {historyWindow}. | R4 | judgment | blocker | `policy-changes-for-detail-reason` |
| `port-owner-below-consumer` | A recorded port is owned by a component whose innermost ring lies outside the ring of a unit that depends on the port. | R5 | check | blocker | `port-on-wrong-side` |
| `port-signature-detail-type` | The signature of a recorded port names a type declared in a detail unit. | R5 | check (needs signatures) | blocker | `port-carries-detail-type` |
| `policy-detail-edge-beside-port` | A policy unit depends directly on a detail unit that implements a port the policy unit's component owns. | R5 | check (needs implements) | blocker | `policy-depends-on-detail` |
| `port-in-shared-bucket` | A port sits in a shared interfaces bucket with no consumer beside it, instead of beside the policy that calls it. | R5 | judgment | blocker | `port-on-wrong-side` |
| `controller-imports-use-case` | A controller imports a use-case unit for more than its types, so it calls the use-case class instead of an input boundary. | R6 | check | blocker | `use-case-called-without-boundary` |
| `use-case-names-its-details` | A use case reaches its presenter or its store through their implementations instead of an output boundary and a storage port declared in the use-case module. | R6 | judgment | blocker | `policy-depends-on-detail` |
| `detail-constructed-outside-root` | A unit whose role is not wiring constructs a unit whose role is detail. | R7 | check (needs constructs) | blocker | `detail-constructed-outside-root` |
| `mixed-unit-constructed-outside-root` | A unit that is not a composition root, config, or test constructs a mixed unit that holds a concrete detail. | R7 | judgment | blocker | `detail-constructed-outside-root` |
| `abstraction-without-reason` | An abstraction has a single consumer and a single implementer, and names neither a deferred decision nor a ripple it forbids. | R8 | judgment | minor | `unjustified-abstraction` |
| `tests-change-without-behavior-change` | A change forces edits to tests whose asserted behavior did not change. | R9 | judgment | major | `tests-coupled-to-structure` |
