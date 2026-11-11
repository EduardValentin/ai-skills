# Classifying the code

How a person or agent tells the command what each module is: which component it belongs to, its
kind, its ring, and its actors. Read it before classifying modules for a new model, when
`arch uncovered` lists modules no pattern covers, or when a reviewer disputes a classification.
Work from what the code does, not from its folder names or from documentation.

## The model

The whole model is one file, `architecture.json`, edited only through `arch model`. Each component
names the globs its modules live under and an ordered list of classification pairs. A pair is a
pattern, relative to the component's paths, and a kind; the first pair that matches a module
decides it, so order matters within one component. A per-file exception is an exact-path pair
placed before the broader patterns. A pair may carry a third element for what differs from the
kind's default: a `ring`, the `actors`, a one-sentence `reason`, or `valueType`.

```json
{ "name": "orders", "paths": ["src/orders/**"], "classify": [
    ["legacy/order-report.*", "mixed", { "reason": "builds the report and also writes it to disk" }],
    ["**/*-use-case.*", "use-case", { "actors": ["sales"] }],
    ["**/money.*", "entity", { "valueType": true }],
    ["index.*", "barrel"],
    ["**", "entity"] ] }
```

The commands that build it:

```
arch model add-component orders paths=src/orders/**
arch model classify orders "**/*-use-case.*" use-case actors=sales
arch model classify orders "legacy/order-report.*" mixed reason="builds the report and also writes it to disk" before="**/*-use-case.*"
arch model add-port src/orders/orders.ts#Orders owner=orders defers="which store keeps orders"
arch model explain src/orders/place-order-use-case.ts
```

`arch model classify` replaces a pair with the same pattern, or appends a new one; `before=` places
it ahead of an existing pattern. `arch model unclassify` removes a pair and
`arch model remove-component` removes a component. `arch model add-port` records a port as
`path#Symbol` with the component that owns it, and optionally the ring of its humble side and the
decision it defers, which R8 (Constraints need a named reason) and R25 (Boundaries at axes of
change) read. `arch model explain <path>` prints a module's component, kind, ring, actors, and the
pair that matched, so nobody has to read the model to find out.

## Default kinds

The model's `kinds` section may add project-defined kinds, each with its role and default ring;
a kind that is neither a default nor declared there is refused. The defaults:

| Kind | Role | Ring | Recognize by |
|---|---|---|---|
| `entity` | policy | entities | Rule functions a clerk would apply without software, over the data they need, depending only on other entities and value types. |
| `use-case` | policy | use-cases | Sequencing, gating, and input validation that calls entities and ports through a request and response model. |
| `port` | policy | entities | An interface, protocol, abstract type, or function type declared beside the policy that calls it and implemented elsewhere. |
| `boundary-data` | policy | use-cases | Public fields and no behavior: a request, response, view model, record, or payload. |
| `controller` | detail | adapters | Turns an incoming request into a request model and calls a use case. |
| `presenter` | detail | adapters | Turns use-case output into a view model of display-ready strings and flags. |
| `gateway` | detail | adapters | Implements a port against a store or a vendor service and holds its query or client code. |
| `adapter` | detail | adapters | Any other translator between policy shapes and an external agency: a mapper, sender, or listener. |
| `entry-point` | detail | frameworks | Where control enters: a route handler, command, job trigger, or message consumer. |
| `ui` | detail | frameworks | Framework-bound screen code that copies a view model to the screen. |
| `composition-root` | wiring | frameworks | Constructs concrete details and wires them together, depending on every ring. |
| `test` | wiring | adapters | A test suite, fixture, test double, or testing API. |
| `config` | wiring | frameworks | Configuration, routing tables, dependency-injection registration, and migrations. |
| `barrel` | neutral | none | Only re-exports other modules. |
| `mixed` | neutral | none | Matches two or more kinds; a candidate for a split under R10 (One actor per module) and R17 (Critical rules live in entities). |

A kind with no default ring takes the ring the other pairs of its component share, when they all
share one; otherwise its ring is unknown until the pair states one.

## Rings and level

The default rings, innermost first, are `entities`, `use-cases`, `adapters`, and `frameworks`; a
project may list others in the model's `rings` section. A pair writes a ring only when it differs
from the kind's default. Classify by what a unit does, not by its folder: a `services` folder full
of query code is `adapters`.

The ring is a unit's level for most purposes. When two units in one ring must be compared, or a
`mixed` unit placed, use the finer level: count the dependency hops, ignoring direction, from the
unit to the nearest entry point and to the nearest device-facing unit (a database client, mailer,
screen, or file system). The unit farther from both is the higher level. For example, a use case
imported by a route handler and importing a database client is one hop from each; a pay rule
imported only by that use case is two hops from each, so it is higher than the use case.
R4 (Dependencies point toward policy) uses this level: inside one ring, too, a unit never depends
on one at a lower level.

## An unstated field is unknown

A field the model does not state is unknown, never an empty value and never a guess. A module no
pattern covers has no kind and no ring; a pair without actors has unknown actors. A condition that
needs an unknown field reports itself as incomplete: it is neither passed nor failed until someone
states the field. Write a field only from evidence in the code or the history, and leave it unstated
otherwise.

## Actors

For each component, and for each `mixed` or public unit, the actors are the roles or teams whose
requests would change it. Take them from the ticket or brief when one exists, from the change
history (which features touched the unit, and for whom), and from the domain words in the code
(finance, compliance, delivery). Record them with `actors=` on the pair. One actor is the normal
case; more than one is the evidence R10 (One actor per module) needs.

## What the command derives

Units, dependencies, externals, component dependencies, fan-in and fan-out, the metrics, cycles,
port implementers and consumers, and change history come from the project's adapter and from
`arch`, never from a person or an agent. Classification is the only input that is written by hand.

## Covering every module

`arch uncovered` lists the modules no component or no pair covers, and exits non-zero while any
remain. For each, decide from its behavior whether a pattern covers a whole folder or naming
convention (`arch model classify` with a glob), a single file is an exception (an exact-path pair
placed first), or a new component exists (`arch model add-component`). Prefer a pattern to an
exception. An exception's `reason` is one sentence that names the behavior, never a ticket. Run
`arch uncovered` again until it prints nothing, then `arch model validate`, which also fails on a
pattern that no module matches.
