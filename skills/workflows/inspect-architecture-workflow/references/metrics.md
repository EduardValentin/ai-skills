# Metrics

How the command measures the component graph, and every knob a project can set. Read it when a
rule or condition names a metric or a knob in braces, when `arch` reports a component in a zone or
off the balanced line, or before changing a threshold with `arch model set-threshold`. A metric
never decides a finding on its own: R32 (Use metrics as a screen) says how the numbers are used.

## Knobs

Every number a rule or condition depends on is a knob with a default. A project overrides one with
`arch model set-threshold <knob> <value>` and restores the default with `arch model unset-threshold
<knob>`; `arch model explain-thresholds` prints each knob with its default and the project's value.
Rule text refers to a knob by its name in braces, such as `{historyWindow}`.

| Knob | Default | Meaning |
|---|---|---|
| `interfaceUseShare` | 0.5 | Share of an interface's members a consumer must use for the interface to fit that consumer. |
| `componentUseShare` | 0.25 | Share of a component's exports a consumer must use for the dependency to count as real use. |
| `detailReasonChanges` | 2 | Count of recent changes for a detail reason that marks a unit as changing for that reason. |
| `historyWindow` | 6 months | How far back change history reaches, written as a date expression such as 6 months. |
| `escalationFanIn` | 3 | Count of dependents that makes a unit widely depended on, which escalates findings about it. |
| `painMaxInstability` | 0.2 | Highest instability of a unit that still sits in the zone of pain. |
| `painMaxAbstractness` | 0.2 | Highest abstractness of a unit that still sits in the zone of pain. |
| `painMinFanIn` | 3 | Count of dependents a stable, concrete unit needs before it is reported in the zone of pain. |
| `uselessMinAbstractness` | 0.8 | Lowest abstractness of a unit that sits in the zone of uselessness. |
| `uselessMinInstability` | 0.8 | Lowest instability of a unit that sits in the zone of uselessness. |
| `distanceDeviations` | 1 | Standard deviations above the mean distance to the main sequence that mark an outlier. |
| `distanceJump` | 0.1 | Increase in a component's distance to the main sequence between base and head that is reported. |
| `distanceMinComponents` | 8 | Fewest components for which distance from the balanced line is compared across the graph. |
| `planFixRounds` | 2 | Rounds of plan fixes before the remaining findings go to the user. |

## What is counted

The unit of counting is the module (one file). A dependency is any source reference the adapter
resolves: an import, an implements or extends clause, a construction, or a type in a signature.
External packages and modules that belong to no component count toward neither fan-in nor fan-out.

For a component C:

| Quantity | How it is counted |
|---|---|
| Fan-in | Distinct modules outside C, each in some component, that depend on at least one module inside C. |
| Fan-out | Distinct modules inside C that depend on at least one module in another component. |
| Abstract exports | Exported interfaces, type aliases, and abstract classes across C's modules. |
| Total exports | All exported symbols, abstract and concrete, across C's modules. |

A barrel adds nothing to either export count, since its exports are other modules' declarations
published again. The export counts need the adapter fact `exports`; without it abstractness and
distance are undefined, and the conditions that need them are incomplete.

Worked count: component `Cc` holds modules `t` and `u`. Modules `q`, `r`, and `s`, each in some
other component, depend on `t` or `u`, so fan-in is 3. Module `u` depends on `v` in another
component, so fan-out is 1.

## Formulas

| Metric | Formula | Undefined when |
|---|---|---|
| Instability (I) | fan-out / (fan-in + fan-out) | fan-in and fan-out are both zero |
| Abstractness (A) | abstract exports / total exports | C has no exports, or the adapter gives no `exports` fact |
| Distance (D) | abs(A + I - 1) | I or A is undefined |

Every value is rounded to two decimals.

Instability runs from 0 to 1. At 0 a component is depended on and depends on nothing: maximally
stable, and hard to change, because every change must be reconciled with every dependent. At 1 it
depends on others and nothing depends on it: maximally volatile, and cheap to change. In the worked
count, I = 1 / (3 + 1) = 0.25. R31 (Depend toward stability) in metric form: instability decreases
along every dependency between components.

Abstractness runs from 0 (all concrete) to 1 (nothing but interfaces and abstract types). A stable
component should be abstract, so it can be extended without being edited; a volatile one should be
concrete, so it stays cheap to change. An interface-only component has A = 1 and, once
implemented, I = 0.

The two ideal positions on the I and A plane are stable and abstract (I = 0, A = 1) and volatile
and concrete (I = 1, A = 0). The line between them, A + I = 1, is the balanced line: a component on
it is depended on to the extent that it is abstract. Distance measures how far a component sits
from that line, from 0 (on it) to 1.

## Zones

The zone column of the metrics table names the zone a component falls in, by these bounds:

| Zone column | Bounds |
|---|---|
| `pain` | I at most {painMaxInstability}, A at most {painMaxAbstractness}, and fan-in at least {painMinFanIn} |
| `uselessness` | A at least {uselessMinAbstractness} and I at least {uselessMinInstability} |

A component in the zone of pain is harmful only when it also changes: a concrete utility that never
changes is left alone. Its typical inhabitant is a schema or a shared concrete model that every
service imports. A component in the zone of uselessness is often a set of interfaces left over
after a refactor.

## How the numbers are used

- Across the graph: with at least {distanceMinComponents} components, the command computes the
  mean and standard deviation of D and reports every component more than {distanceDeviations}
  standard deviations above the mean. On a smaller graph the comparison is not run, and R30 (No
  dependency cycles) and R31 (Depend toward stability) are applied without arithmetic.
- Between base and head: in a change review, a component whose D rose by at least {distanceJump}
  between the base and the head of the change is reported.
- In words: each reported component gets a sentence saying which side of the line it fell to,
  whether it changes, and what the harm is, for example "concrete, depended on by nine components,
  changed in most recent commits, so every change re-verifies nine components". Only then does it
  become a finding under R32 (Use metrics as a screen), with the correction that moves it: own a port, extract an
  interface-only component, or delete unused abstractions.
- What the numbers cannot see: shared data shapes, run-time coupling through a message bus, and a
  boundary that exists in a diagram but not in the code. R41 (Verify the real dependency graph)
  covers those.

## Where the numbers appear

`arch collect` writes the metrics table and any zone or distance breach into the current picture.
`arch query metrics` prints the same table, with `none` in the zone column when no zone applies
and `undefined` in a column whose value is undefined. `arch query volatility` counts the commits
that touched each component within {historyWindow}. Nothing is written by hand.
