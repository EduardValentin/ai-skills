# Architecture

Last audit: <date> at commit <hash>, scope <scope>. Last update: <date> at commit <hash>,
<mode>. Maintained by the architecture inspection workflow; changes ship with the PR that
causes them.

## Shape

<Paragraph 1: what the business rules are and where they live (entities, use cases).>

<Paragraph 2: how details plug in: the ports the rules declare, who implements them, where
the composition root is.>

<Paragraph 3: how boundaries are enforced (visibility, exports, build units, import rules),
and which boundaries are drawn but not enforced.>

## Current shape (generated)

<!-- arch:summary -->
<!-- /arch:summary -->

## Reading this folder

- `model/components.json`: the enforced components and the path globs that belong to each.
- `model/rules.json`: the rings and the glob rules that classify a path's ring, kind, and actors.
- `model/overrides.json`: per-path exceptions to the rules, by exact path.
- `model/boundaries.json`: the ports rules declare, their owners and humble sides, and shared data shapes.
- `decisions.md`: deferred decisions, accepted trade-offs, intended exceptions, accepted findings.

Terms: a *unit* is a class, module, function, interface, or data structure. A *component* is a
group of units behind one published interface that tooling enforces. An *edge* from A to B means
A's source code names B. *Policy* is business rules; *detail* is databases, frameworks,
transports, vendors, UI, and the data shapes they produce. A *ring* is a band of units at one
level of distance from inputs and outputs; dependencies point inward.
