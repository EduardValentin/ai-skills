# Metrics

Screening metrics for component graphs. Compute them only when the graph has more than five
components; on smaller graphs the qualitative rules R30 and R31 are enough. A metric never
decides a finding on its own: every flagged value must be explained in words before it becomes
a `SHOULD_CHANGE` row (R32).

## What is counted

The unit of counting is the module or file, because most codebases are file-per-module. A
dependency is any source reference: import, implements, extends, construct, or a type used in a
signature. Only dependencies that cross the component boundary count.

For a component C:

| Quantity | Definition |
|---|---|
| Fan-in | Number of modules outside C that depend on at least one module inside C. Two modules in one neighbor that both depend on C count as 2. |
| Fan-out | Number of modules inside C that depend on at least one module outside C, excluding the standard library and runtime. |
| Abstract types | Interfaces, protocols, abstract classes, and any type that exists only to be implemented (a port type, a structural type used as a contract). |
| Total types | All classes, interfaces, and named types declared in C. |
| Volatility | Number of commits or releases that changed C in the observation window (default the last ten commits touching the scope, or the releases since the previous run). |

Worked count: component `Cc` holds modules `t` and `u`. Modules `q`, `r`, and `s` in other
components import `t` or `u`, so fan-in is 3. Module `u` imports `v` in another component, so
fan-out is 1.

## Instability

    I = fan-out / (fan-in + fan-out)

Range 0 to 1. I = 0: the component is depended on and depends on nothing; maximally stable, hard
to change because every change must be reconciled with every dependent. I = 1: the component
depends on others and nothing depends on it; maximally unstable, cheap to change. In the worked
count, I = 1 / (3 + 1) = 0.25.

Rule R31 in metric form: for every dependency arrow from component A to component B, I(A) must
be greater than I(B). Instability decreases along every arrow. Drawn with unstable components at
the top and arrows pointing down, an arrow that points up is a violation.

## Abstractness

    A = abstract types / total types

Range 0 to 1. A = 1: the component is nothing but interfaces and abstract types. A = 0: all
concrete. A stable component (low I) should be abstract (high A) so it can be extended without
being edited; an unstable component (high I) should be concrete (low A) so it stays cheap to
change. An interface-only component has A = 1 and, once implemented, I = 0.

In dynamically or structurally typed languages, count as abstract the types that exist only to
be implemented: protocols, port types, abstract base classes. If the language has no such
declarations, treat A as undefined and use the qualitative form of R31.

## The balanced line and distance

The two ideal positions on the I/A plane are (I = 0, A = 1), stable and abstract, and (I = 1,
A = 0), unstable and concrete. The line between them, A + I = 1, is the balanced line: a
component on it is depended on to the extent it is abstract and depends on others to the extent
it is concrete.

    D = abs(A + I - 1)

Range 0 to 1. D = 0 means on the line. Most components should sit at or near one of the two
endpoints; the rest should sit close to the line. A component with a large D fell to one of two
sides:

| Position | Name | Reading |
|---|---|---|
| Low I, low A (near 0, 0) | Zone of pain | Many dependents, concrete code. Harmful only when it also has volatility above zero; a concrete utility that never changes is harmless. Typical inhabitant: a database schema or a shared concrete model every service imports. |
| High I, high A (near 1, 1) | Zone of uselessness | Abstract types nothing implements or nothing depends on. Abstraction paid for and unused; leftover interfaces after a refactor. |

## How to use the numbers

1. **Across the graph.** Compute D for every component. Compute the mean and standard deviation.
   Examine every component more than one standard deviation from the mean; the rest are within
   the graph's own norm.
2. **Over time.** Keep each component's D from the previous run in the inventory. A component
   whose D crossed a threshold since the previous run (default 0.1, tune per project) deserves a
   look at the dependencies or abstractions that changed.
3. **In words.** For each examined component, state which side of the line it fell to, whether it
   is volatile, and what the harm is: "concrete, depended on by nine components, changed in six
   of the last ten commits, so every change re-verifies nine components". Only then write a
   `SHOULD_CHANGE` row citing R32, with the change that moves it (own a port, extract an
   interface-only component, delete unused abstractions).
4. **What the numbers cannot say.** They do not see shared data shapes, runtime coupling through
   a message bus, or a boundary that exists in a diagram but not in code. W8 covers those.

## Recording

Inventory section `Metrics`: one row per component with fan-in, fan-out, I, A, D, previous D,
and volatility. Recompute on every audit; in change-review mode recompute only for components
the diff touches and mark the others as carried over.
