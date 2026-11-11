# Business-rule placement

The rules that put each business rule where it belongs (R17 to R19): critical rules in entities,
application rules in use cases, and only plain data across a boundary. Read this file when a
review or audit touches an entity, a use case, a request or response model, or an adapter that
receives data from the policy.

## Rules

### R17. Critical rules live in entities

**Bind critical business rules to their data in an entity that knows nothing outside the
business.** Put a small set of such rules with exactly the data they need in one unit whose
interface is the rule functions; a data type plus its rule functions qualifies, no class
required. The entity imports no persistence, transport, framework, UI, clock, configuration, or
use-case code, carries no framework annotations, base classes, or serialization methods, and
would work unchanged in another application with a different delivery mechanism and store.
Different actors owning rules over the same data get one rule unit each over a shared plain data
type, as R10 (One actor per module) requires.

Check questions:
- Is every field read by a rule function, and would a clerk perform every function?
- What does the entity import, and what annotations does it carry? Anything beyond another entity
  or a value type is a defect.
- Does any method name a channel or a use case (`toJson`, `fromRow`, `onEstimationStarted`)?

Examples:
- Bad: `unit Loan extends OrmModel, annotated Entity: toJson()`
- Good: `unit Loan: applyInterest() -> Loan` importing only `Money`, `Rate`, and `Period`.

Not a finding when: `entity-imports-non-entity`: the imported unit is a value type the model has not marked as one, so mark its pair with `value-type=true` instead of raising it; `entity-holds-system-concerns`: the field no rule reads is the entity's identifier, which the paper record has too.

### R18. Use cases hold application rules

**Use cases hold application rules, orchestrate entities, and depend on them only.** Rules that
exist because the system is automated (a required sequence, a gate before an action, input
format validation, a flow threshold) live in a use case statable as input, output, and ordered
steps. The use case validates input format, loads entities through ports, calls their rule
functions, stores results through ports, and decides what follows. Invariants a manual process
would also enforce, and any arithmetic or decision a clerk would make, belong on an entity.
Choosing the next use case is application flow, expressed in the response; navigating there is
the delivery mechanism's job. Use cases depend on entities; entities never import, call back, or
expose hooks for use cases. A stateless service and an object holding its request and response
are both acceptable shapes.

Check questions:
- With every call to entities and ports removed, does only validation, sequencing, and branching
  remain?
- Can any dependency path from an entity reach a use case?
- Can the use case be stated as input, output, and ordered steps?

Examples:
```
// bad: the use case computes interest
loan.balance = loan.balance * (1 + loan.rate / 12)
// good: the entity owns the rule; the use case sequences it
loan = loans.load(request.loanId)
loans.save(loan.applyInterest())
```

Not a finding when: `critical-rule-in-use-case`: the arithmetic or branch is input format validation, sequencing, a gate before an action, or a flow threshold, which exist only because the system is automated and belong in the use case.

### R19. Cross boundaries with plain data

Advisory by default in a legacy baseline.

**Cross every boundary with plain data declared on the inner side.** A use case takes a request
model and returns a response model; both import nothing, extend no framework type, wrap no row or
transport envelope, carry no channel-specific fields (headers, session, cookies, widget state),
and reference no entity, so the code cannot tell a web interface from a console or a headless
service. View models, gateway results, and wire payloads are plain structures too: public fields,
no behavior, no lazy references back across the boundary, shaped for the inner ring's
convenience. Entities do not cross outward to adapters or views; rows and framework objects do
not cross inward. Sharing one type across a boundary yields fields carried through code that never
reads them, and conditionals that test the shape.

Check questions:
- Can the request and response be built in a test from literals alone?
- Does any boundary type have an import, a method, a framework base class, a lazy proxy, or an
  entity-typed field?
- Does any adapter branch on which shape of data it received?

Examples:
```
// bad
data GatherContactInfoRequest extends HttpRequest
data CreateLoanResponse(loan: Loan)
// good
data GatherContactInfoRequest(name: Text, address: Text, birthdate: Text)
data CreateLoanResponse(loanId: Text, principal: Number, periodMonths: Number)
```

Not a finding when: `boundary-data-carries-detail-shape`: a field is a string, number, boolean, or enumeration that describes state, even when its name mirrors an entity field, since mirroring is expected and carrying the entity itself is the breach; `adapter-branches-on-shape`: the adapter branches on the value of a state field, such as a status enumeration, rather than on which type of data it received.

## Conditions

| Id | Condition | Rule | Decided by | Severity | Defect |
|---|---|---|---|---|---|
| `entity-imports-non-entity` | An entity depends on a unit that is not an entity, a barrel, or a value type, or imports any external package. | R17 | check | blocker | `entity-depends-outward` |
| `entity-carries-framework-traits` | An entity carries framework annotations, a framework base class, or serialization methods. | R17 | judgment | blocker | `policy-depends-on-detail` |
| `entity-holds-system-concerns` | An entity has fields no rule function reads, or functions only the system needs. | R17 | judgment | minor | `entity-holds-system-concerns` |
| `entity-imports-use-case` | An entity depends on a use-case unit. | R18 | check | blocker | `entity-depends-outward` |
| `critical-rule-in-use-case` | A use case contains business arithmetic or a decision a clerk would make without the system. | R18 | judgment | blocker | `critical-rule-outside-entity` |
| `entity-hook-for-use-case` | An entity exposes a hook or callback that exists for a use case. | R18 | judgment | blocker | `entity-depends-outward` |
| `business-rules-outside-policy` | The code has business rules but no unit is classified entity or use case, so the rules live in adapters or framework glue. | R17, R18 | judgment | blocker | `business-rules-outside-policy` |
| `boundary-data-imports` | A boundary-data unit depends on a unit that is not boundary data, or imports any external package. | R19 | check | blocker | `boundary-data-not-plain` |
| `boundary-data-carries-detail-shape` | A request or response model extends a framework type, wraps a row or envelope, carries channel fields, or has an entity-typed field. | R19 | judgment | blocker | `boundary-data-not-plain` |
| `entity-crosses-use-case-boundary` | A use case accepts or returns an entity across its input or output boundary. | R19 | judgment | blocker | `entity-crosses-boundary` |
| `adapter-branches-on-shape` | An adapter or presenter branches on which shape of data it received. | R19 | judgment | blocker | `adapter-branches-on-shape` |
