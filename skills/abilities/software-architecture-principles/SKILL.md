---
name: software-architecture-principles
description: >-
  Use whenever code is written, changed, planned, or reviewed, at any size, to
  hold the structural invariants that decide how expensive the next change will
  be. Also use when unsure whether a shortcut in module layout, dependency
  direction, shared helpers, or a framework choice is acceptable.
compatibility: >-
  Standalone. When a mapped, evidenced assessment is needed, the
  `inspect-architecture-workflow` skill turns these invariants into an
  inventory, findings, and a verdict; when it is not installed, apply the
  invariants directly and say which one a decision rests on.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Software Architecture Principles

Every change to a system delivers two things: behavior, meaning the system now
does what was asked, and structure, meaning the next change stays cheap. Both
are deliverables. Structure is judged by one question, "how much work will the
next likely change take?", never by pattern names or diagrams. No part of the
code is exempt: a function signature or a helper's location constrains future
change as much as a package boundary does.

## Terms used below

- **Business rules**: the code that would still describe the organization's
  work if the software disappeared: how pay is calculated, when an order may
  ship, what a late fee is. Also called the policy of the system.
- **Details**: everything that exists because the software is running on
  machines: databases, web frameworks, message queues, vendor SDKs, user
  interfaces, clocks, file systems, and the data shapes they produce (table
  rows, HTTP request objects, API payloads).
- **Depends on**: module A depends on module B when A's source code names B:
  imports it, extends it, constructs it, or uses one of its types in a
  signature. This is about source code, not about which function calls which
  at runtime.
- **Port**: an interface, protocol, or function type that the business rules
  declare to say what they need from the outside world, for example "something
  that can load an employee by id". A detail satisfies the port by
  implementing it.
- **Actor**: a role or team that asks for changes for its own reasons:
  finance, human resources, operations, a partner integration.
- **Boundary**: a line between two parts of the code where one side is not
  allowed to know about the other. Boundaries are crossed by plain data.

## Invariants

1. **Business rules never depend on details.** A module holding business
   rules imports no database client, framework, transport, vendor SDK, UI
   library, clock, or generated data shape. The direction of data flow does not
   matter: even when a rule hands its result to a database or a screen, the
   database or screen code depends on the rule, not the reverse. Only one
   module, the place where the application is assembled at startup, may import
   everything.
2. **Business rules declare ports; details implement them.** The interface
   lives next to the code that calls it, uses only types that code already
   owns, and a detail module imports it to implement it. Test: the business
   rules compile and pass their tests with every detail module deleted and
   replaced by an in-memory stand-in.
3. **One actor per module.** A module changes for the requests of one actor.
   When two actors ask for different things from the same module, split it
   along those lines. Two functions with identical bodies but different actors
   are not duplication; merge shared code only when one actor would want every
   future change to it.
4. **Business rules sit at two levels, and the lower depends on the higher.**
   Rules a clerk would apply with paper and a calculator form the core. Rules
   that exist only because the system is automated, such as the order of steps
   in a workflow, input validation, or a gate before an action, form the
   application layer around it. The application layer calls the core; the core
   never knows the application layer exists.
5. **Data that crosses a boundary is plain.** Requests, responses, view data,
   and records passed between parts are simple structures with public fields
   and no behavior, defined on the side receiving them. A core object never
   travels out to a screen or a database adapter; a table row or framework
   request object never travels in to the rules.
6. **Code that touches a device makes no decisions.** A view only copies
   prepared values onto the screen; a request handler only parses input and
   calls a rule; a sender only transmits; database code only executes queries.
   Every conditional, calculation, and formatting choice lives in a unit that
   can be tested without the screen, network, or database present.
7. **New behavior arrives as new code.** A new variant, such as a payment
   method or export format, is a new implementation behind an existing
   interface, not an edit to code that many modules already depend on. Callers
   never check which implementation they hold, and each caller sees only the
   operations it uses.
8. **No dependency cycles, and dependencies point at what changes least.** A
   module that many others depend on is expensive to change, so it must not
   depend on a module that changes often. Modules many depend on expose
   interfaces; modules few depend on hold the concrete, changeable code.
9. **Decisions no current need forces are postponed.** Which database, web
   framework, message broker, or deployment split to use waits until a feature
   requires it. Until then the rules talk to a port with an in-memory
   implementation. A boundary that postpones no decision and separates nothing
   that changes at a different rate is unnecessary and is itself a premature
   decision.
10. **Tests are the outermost layer.** Tests depend on the code they verify;
    no production code depends on a test, fixture, or fake, and no test-only
    switch exists in production code. Tests of business rules reach the rules
    directly, never through screens, logins, or vendor systems.
11. **A boundary exists only if tooling enforces it.** A rule written in a
    document or held by review alone will be crossed under deadline pressure.
    Every boundary names what fails when it is crossed: a visibility modifier,
    a package export list, a separate build unit, or an import rule that fails
    the build. Export a symbol only when a named module outside needs it.
12. **Values are immutable by default.** State changes happen in a few named
    places at the edges of the system, such as a repository or a cache;
    everything else takes inputs and returns new values.

## When the smallest change breaks an invariant

Do not force the change in with a flag, a mode parameter, a special case for
one caller, or a copy with a small twist. Name the mismatch, say which
invariant it touches and which upcoming change it would make harder, then
either reshape first or record the debt with its cost. Structural work is
scheduled against a named upcoming change, and it ranks above urgent work that
has no concrete cost of delay.
