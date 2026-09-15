# Architecture

Last audit: <date> at commit <hash>, scope <scope>. Maintained by the architecture inspection
workflow; changes ship with the PR that causes them.

## Shape

<Paragraph 1: what the business rules are and where they live (entities, use cases).>

<Paragraph 2: how details plug in: the ports the rules declare, who implements them, where
the composition root is.>

<Paragraph 3: how boundaries are enforced (visibility, exports, build units, import rules),
and which boundaries are drawn but not enforced.>

## Reading this folder

- `components.md`: the enforced units and what each publishes.
- `units.md`: classes, modules, functions, interfaces, and data structures, with their kind and ring.
- `dependencies.md`: every source dependency, the forbidden edges, the ports, entry points, and shared data shapes.
- `metrics.md`: stability and abstractness per component.
- `decisions.md`: deferred decisions, accepted trade-offs, intended exceptions, accepted findings.

Terms: a *unit* is a class, module, function, interface, or data structure. A *component* is a
group of units behind one published interface that tooling enforces. An *edge* from A to B means
A's source code names B. *Policy* is business rules; *detail* is databases, frameworks,
transports, vendors, UI, and the data shapes they produce. A *ring* is a band of units at one
level of distance from inputs and outputs; dependencies point inward.
