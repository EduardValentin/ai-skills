# Mapping the architecture

How a person or agent classifies modules so the `arch` command can derive the rest of the graph.
Work from the code, not from documentation; documentation is recorded as the intended structure
and compared with the derived graph in W8.

## Unit kinds

The allowed kinds are the `kinds` list in `model/rules.json`; when it is absent, the default
list below applies. `arch model` refuses an override or rule whose kind is not listed.

| Kind | Recognize by |
|---|---|
| entity | Rules a clerk would apply without software, bound to the data they need, importing nothing beyond other entities and value types. |
| use-case | Application-specific sequencing, gating, and input validation that calls entities and ports through a request and response model. |
| port | An interface, protocol, abstract type, or function type declared on the policy side and implemented elsewhere. |
| boundary-data | A request, response, view model, record, or payload with public fields and no behavior. |
| controller | Converts an incoming request from a delivery mechanism into a use-case request and calls the use case. |
| presenter | Turns use-case output into a view model of display-ready strings and flags. |
| gateway | Implements a port against a database, a vendor service, or another external agency. |
| adapter | Any other converter between policy shapes and an external agency: a mapper, sender, or listener. |
| composition-root | Constructs concrete details and wires them together, importing every level. |
| entry-point | A place control enters: a route handler, CLI command, job trigger, or message consumer. |
| test | A test suite, fixture, fake, or testing API. |
| config | Configuration, routing tables, dependency-injection registration, and migrations. |
| ui | Framework-bound screen code that copies a view model to the screen. |
| barrel | A module that only re-exports other modules; its edges are publication, not dependency. |
| mixed | A unit that matches two or more kinds; always a candidate for W2 and W3. |

## Ring and level

Rings: `entities`, `use-cases`, `adapters`, `frameworks`, innermost first, unless `rules.json`
lists others. A test is `kind: test` in the `adapters` ring; a composition root is
`kind: composition-root` in the `frameworks` ring. Classify by what the unit does, not by folder
name; a `services/` folder full of SQL is `adapters`.

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

## Boundaries

Per port record: owner unit and its ring; implementers and their rings; consumers; the crossing
data type and whether it is boundary-data; which side is humble; the enforcement mode of the line
(what fails if a consumer imports an implementer directly). A port owned on the detail side, or
whose signature carries a detail type, is recorded as-is and flagged by W1.

## Entry points and composition roots

List every place control enters (routes, handlers, CLI commands, job triggers, message consumers)
and every place concrete details are constructed. A concrete detail constructed outside a
composition root is a W1 finding; more than one composition root per deployable is noted for W8.

## What the command derives

Units are modules (files). Edges, externals, component edges, fan-in, fan-out, instability,
abstractness, distance, cycles, entry-point construction, port implementers and consumers, and
volatility come from `arch graph`, `arch diff`, and `arch query`, never from an agent. A unit's
component comes from `model/components.json` globs; its ring, kind, and actors come from an
override, else the first matching rule in `model/rules.json`.

## Classifying uncovered modules

`arch uncovered` lists modules no component glob or no rule classifies. For each, decide from
the module's behavior (the sections above) whether a rule covers a folder or naming pattern
(`model add-rule`), a single file is an exception (`model add-override`), or a new component
exists (`model add-component`). Prefer a rule over an override; an override needs a reason in
one sentence that names behavior, never a ticket. Rerun `arch uncovered` until it prints nothing.

## Incremental update

Change review: `arch diff <base>` reports units added, removed, moved, or reclassified and
edges added or removed; `arch uncovered` reports what the diff left unclassified. The model
changes only through the edit subcommands, only for rows no open finding disputes, and never
with a note about the ticket, plan step, or commit that caused the change. A plan review
changes nothing; it builds its overlay per `plan-review.md`.
