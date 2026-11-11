# Reasons to change

The rules that give every unit one reason to change (R10 to R16): one actor per unit, duplication
judged by ownership, variants added as new code, narrow and substitutable interfaces, hidden data,
units understood alone, and mutation kept at the edges. Read this file when a review or audit
touches a unit with a public surface, a shared helper, an abstraction and its consumers, or state
that changes.

## Rules

### R10. One actor per module

**Give each unit one actor, and split on evidence, not speculation.** When different roles or
teams request changes to a unit's public operations, split it along actor lines. The evidence is
actors actually asking for different things, the request naming them, or unrelated features
repeatedly colliding in one file; a pattern of merge conflicts is a design signal, not a tooling
problem. Separated units share a plain data type, never behavior, since any dependency between
two per-actor units couples the actors again. If existing callers must keep one entry point, a
thin facade is acceptable: it exposes the old operations and only constructs the per-actor units
and forwards calls, with no branching, calculation, or persistence. New consumers depend on the
per-actor unit they need.

Check questions:
- For each public operation, who would ask for it to change? More than one role means more than
  one reason to change.
- Do the split units depend only on the shared data type?
- Does the change history show unrelated features editing this unit?

Examples:
```ts
// bad: three actors in one class
class Employee { calculatePay() {}  reportHours() {}  save() {} }
// good: one unit per actor over a shared plain data type
class PayCalculator  { calculatePay(e: EmployeeData) {} }     // finance
class HourReporter   { reportHours(e: EmployeeData) {} }      // HR
class EmployeeSaver  { save(e: EmployeeData) {} }             // operations
```

Not a finding when: one actor requests the unit's changes, however many operations it has, or the unit is a thin facade that only constructs per-actor units and forwards calls; a second actor who is only imagined is a question for the user, not evidence.

### R11. Deduplicate only for one owner

**Deduplicate only when one owner wants every future change.** Identical code with different
owners is accidental duplication: merging it lets one actor's change silently alter another's
behavior. Real duplication has the same owner and the same reason to change. Request and response
models that mirror entity fields change for different reasons, so they are not duplication; never
collapse one into a reference to the entity.

Check questions:
- Before extracting a shared helper: would every caller want every future change to it?

Examples:
- Bad: `regularHours()` shared by pay (finance) and the hours report (HR); finance changes it and
  HR reports go wrong silently.
- Good: `payableRegularHours()` in the finance unit, `reportedRegularHours()` in the HR unit.

Not a finding when: every importer of the shared unit serves the same actor, or the shared unit is plain data with no behavior, such as a request model that mirrors an entity's fields.

### R12. Add behavior by adding code

**Add behavior by adding code, behind an interface rather than a concrete base class.** New
variants (a payment method, a license type, an export format, a channel) arrive as new
implementations of an existing abstraction; shipped code that many units depend on is not edited
to add a case. Implementations of an interface are independent and share no code; when two should
share, compose a helper in. Use inheritance only where the subtype is substitutable everywhere the
supertype is expected, never to borrow helpers.

Check questions:
- Which files were modified and which created? Is a stable unit among the modified ones only to
  add a variant?
- Does a class extend another only to reuse a method?

Examples:
```ts
// bad: every new kind edits Billing
if (l.kind === "personal") ... else if (l.kind === "business") ... else if (l.kind === "edu") ...
// good: Billing calls license.calcFee(); a new kind is class EduLicense implements License
```

Not a finding when: the branch selects an implementation once, in a factory or the composition root, or the edited unit has no dependents outside its own component yet, so editing it costs no more than adding a class; a subtype used only as a test double still counts as substituted.

### R13. Substitutable implementations, narrow interfaces

**Make every implementation substitutable, and give every consumer a narrow interface.**
Consumers of an abstraction never check the concrete type or special-case one implementation:
type checks, kind checks, and downcasts in a consumer are architectural defects, because the
workaround spreads to every consumer. Each consumer depends on an interface holding only the
operations it calls; one implementation may satisfy several narrow interfaces, split at the
consumer's boundary rather than by fragmenting the implementation. This holds whether or not a
compiler forces a rebuild, and polymorphism needs no class hierarchy: interfaces, protocols,
structural types, and function parameters all count.

Check questions:
- Does any consumer check the type of an implementation?
- For each consumer, how many of the interface's members does it use, against how many the
  interface exposes?

Examples:
```ts
// bad
fee = l instanceof BusinessLicense ? l.calcFee() * l.users : l.calcFee();
// good: BusinessLicense.calcFee() already accounts for users
fee = l.calcFee();
interface U1Ops { op1(): void }  interface U2Ops { op2(): void }
class Ops implements U1Ops, U2Ops { op1() {}  op2() {} }     // one implementation, two narrow views
```

Not a finding when: the type check sits where external input is parsed into a typed value rather than in a consumer of the abstraction, or the consumer uses every member because it is the composition root or an adapter that forwards the whole interface.

### R14. Hide data behind behavior

**Hide data behind behavior; only boundary data is public.** In a unit that carries behavior,
data is reachable only through the functions that operate on it, so code outside never reads or
writes the internal representation and it can change freely. Boundary data is the exception:
public fields and no behavior, existing only to cross a boundary.

Check questions:
- Can code outside the unit read or write its data directly?
- Would a change to the internal representation break callers?
- Is a structure with public fields boundary data, or a unit with behavior whose insides are
  exposed?

Examples:
```ts
// bad
export const cart = { items: [] as Item[] };   // callers push into items
// good
export class Cart { private items: Item[] = []; add(i: Item) {}  total(): Money {} }
```

Not a finding when: the exposed structure is boundary data or a value type, or the unit hands out a read-only copy or view through which its state cannot be changed.

### R15. Decompose into independently understood units

Guidance: advisory by default. Reported to the reviewers who own it.

**Decompose into units that can be reasoned about alone.** Each function does one thing that can
be stated, using only sequence, selection, and iteration: no loops steered by flags set
elsewhere, no exceptions used to jump out of ordinary paths, no non-local state deciding which
branch runs. Recursive decomposition into units that can be checked alone is what makes a program
understandable and testable.

Check questions:
- Can you state what each function does without tracing shared flags or non-local jumps?
- Does each unit have a predictable exit?

Examples:
```ts
// bad: control flow driven by flags across a large body
let done = false; while (!done) { ... if (x) { done = true; continue; } ... }
// good: decomposed
const rows = parse(input); const valid = rows.filter(isValid); return summarize(valid);
```

Not a finding when: the function still states one thing despite a guard clause or an early return, or an exception reports a genuine failure to the caller rather than steering an ordinary path.

### R16. Default to immutable values

**Default to immutable values, and keep mutation in a few named units at the edges.** Shared
mutable state is the source of races, deadlocks, and lost updates. Express state as new values
derived from old ones: an entity's rule functions return the updated entity, and the use case
stores it through a port. The units that mutate (storage, caches, sessions, the testing API's
state-forcing operations) are few, listed, and invoked by the use case; everything else takes
inputs and returns outputs. Mutation elsewhere is justified only by a measured cost.

Check questions:
- Can you list the units that mutate shared state? Is the list short?
- Is every other in-place update justified by a measured cost?

Not a finding when: the mutation stays inside one function's own local variables, happens in a unit named as a mutating one (storage, a cache, a session), or carries the measured cost that justifies it beside it.

## Conditions

| Id | Condition | Rule | Decided by | Severity | Defect |
|---|---|---|---|---|---|
| `unit-serves-several-actors` | A unit serves more than one actor and holds behavior for each of them. | R10 | judgment | major | `several-actors-in-one-unit` |
| `helper-shared-across-actors` | A behavior-bearing unit is imported by units that serve different actors. | R11 | judgment | major | `helper-shared-across-actors` |
| `variant-added-by-conditional` | A variant is added through a conditional ladder over kinds inside a stable unit. | R12 | judgment | major | `variant-added-by-conditional` |
| `subtype-never-substituted` | A subtype is never used where its supertype is expected. | R12 | judgment | major | `subtype-never-substituted` |
| `type-check-on-implementation` | A consumer checks a value's type against an implementation of a recorded port. | R13 | check (needs typeChecks, implements) | major | `consumer-checks-implementation` |
| `consumer-uses-few-interface-members` | A consumer uses less than {interfaceUseShare} of the members of the interface it depends on. | R13 | judgment | major | `interface-wider-than-consumer` |
| `mutable-internals-exposed` | A behavior-bearing unit exposes mutable internal data to outside code. | R14 | judgment | major | `mutable-internals-exposed` |
| `function-not-understood-alone` | A function's path is decided by flag-driven loops, exceptions used as control flow, or non-local state. | R15 | judgment | minor | `function-not-understood-alone` |
| `shared-state-mutated-outside-edges` | Shared state is mutated outside the units named as the mutating ones. | R16 | judgment | major | `shared-state-mutated-outside-edges` |
