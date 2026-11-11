# Deferral and boundary drawing

The rules about which decisions to postpone and where lines belong (R23 to R26): defer what no use
case forces, pay for no topology without a present reason, draw boundaries at axes of change, and
show the rules working with no I/O present. Read this file when a review, audit, or plan touches
a framework, store, or vendor choice, a boundary between two parts, a plugin, or the order in which
work is delivered.

## Rules

### R23. Defer unforced decisions

Guidance: advisory by default.

**Defer every decision the use cases do not force, and start each port in memory.** Framework,
store, web server, utility library, dependency injection, and deployment topology are premature
decisions until a use case requires them. Decide the port and its direction now; build the first
features on test doubles, then an in-memory implementation, then the cheapest durable option that
meets the requirement (flat files count). Add a heavier option only as a new implementation when a
real need arrives; it may never be written. When a mechanism is simple to write, a thin one you
control beats an early framework commitment because it keeps the framework choice open: the point
is to postpone the choice, not to avoid frameworks.

Check questions:
- For each technology the plan names, which use case needs it now?
- Does an in-memory implementation of each port exist, and do the rule tests use it?
- Has any feature been blocked on choosing a store or a framework?
- Is the chosen implementation the simplest that meets today's requirement, with the heavier one
  still a one-class addition?

Examples:
- Bad: first task "choose ORM, design schema, pick web framework".
- Good: first task "`PageStore` port with an in-memory implementation; formatting features shipped
  on it; store chosen when saving across restarts is required."

Not a finding when: `port-without-test-double`: the tests that need the real detail verify the gateway itself, not business rules.

### R24. No tiers without a reason

Guidance: advisory by default. Evaluated only when the session's scope includes a design or topology decision.

**Do not pay for tiers, processes, or a service suite before a team or deployment reason exists
today.** Topology is a deployment decision, not an architecture. Adopted early, one field added to
one record becomes edits in every tier, new wire messages, handlers on both ends, serialization,
timeouts, and retries, often for a distribution that never happens. Structuring around services
is not wrong in itself; adopting and enforcing a whole suite of services before teams or
deployments actually diverge is. Walk the smallest realistic feature through the proposed
structure and count the components edited, messages designed, fields invented, and processes a
test must start: the count must be proportional to the feature.

Check questions:
- Does each service or tier exist for a team or deployment reason that holds today, or for
  anticipated scale?
- What does the simplest change cost in this structure?

Examples:
- Bad: three deployables and four message protocols to add a phone number; tests boot every
  service and the message bus.
- Good: one deployable with component boundaries; a remote adapter added when a second machine
  actually exists.

Not a finding when: each deployable has a team or deployment reason that holds today and is recorded, or the topology was approved earlier, in which case it is verified against that approval and never reopened.

### R25. Boundaries at axes of change

**Draw a line at each axis of change, between every pair where one side does not matter to the
other.** UI versus rules, rules versus store, formatting versus storage, rules versus a
dependency-injection framework: each such pair gets its own boundary, with the port on the side
that does not care and the dependency pointing at it. Every optional or many-formed part is a
plugin to the core, and by default plugins do not depend on each other directly; a project that
lets two plugins depend on each other on purpose records an exception for that pair, with its
reason. Sides that change
together for the same reason need no line, and a unit carrying two cadences is missing one inside
it. Every boundary justifies itself by a decision it defers or an axis of change it separates, as
R8 (Constraints need a named reason) requires.

Check questions:
- For each proposed line, what is the reason and cadence of change on each side?
- Do any two plugins depend on each other?
- Did a recent change cross a line, or did a unit change for two unrelated reasons?

Examples:
- Bad: the web component imports the store component to read a row for display; one
  `PageService` edited for wiki-syntax reasons and for file-format reasons.
- Good: web, store, and mail each depend on the rules and never on each other; `WikiFormatter` and
  `FileSystemPageStore` sit on opposite sides of `PageStore`.

Not a finding when: `plugin-imports-plugin`: the project lets those two plugins depend on each other on purpose and has recorded an exception for that pair with its reason; `boundary-defers-nothing`: the port records the decision it defers, or the change history shows its two sides changing at different cadences; `unit-mixes-change-cadences`: the unit is large but changes for one reason at one cadence.

### R26. Demonstrate the model without I/O

Guidance: advisory by default.

**The system is the model behind the ports: plan and demonstrate it with no I/O present.**
Stakeholders see the screen and call it the system; it is not. Every acceptance criterion is
exercisable through an input boundary or the testing API with no UI, store, or server in the
process, and the first delivery shows the rules that way, described by the model's outputs rather
than by widgets. When visible progress is needed early, provide it through a console or test
adapter rather than pulling the UI or schema decision forward.

Check questions:
- Does the plan's first delivery need a screen or a schema to show progress?
- Can every acceptance criterion run with the UI absent?

Examples:
- Bad: "first deliver the screens, then wire the logic behind them".
- Good: "first deliver the model behind an input port and a recording output port; the first
  screen adapter comes two deliveries later".

Not a finding when: `plan-sequences-io-first`: the early work is about the screen, store, or transport itself, such as a layout, a migration, or a wire protocol, and no rule waits on it; `rules-need-io`: the only behavior that needs the device is the device's own, such as a migration's correctness or a protocol's framing.

## Conditions

| Id | Condition | Rule | Decided by | Severity | Defect |
|---|---|---|---|---|---|
| `detail-reached-without-port` | A framework, store, or vendor is reached with no port between it and the policy. | R23 | judgment | major | `policy-depends-on-detail` |
| `port-without-test-double` | A port has no in-memory or stub implementation while the rule tests need the real detail. | R23 | judgment | major | `rules-need-real-detail` |
| `tiers-without-reason` | More than one deployable or a service catalog exists with no recorded team or deployment reason, and the simplest change edits more than one of them. | R24 | judgment | major | `tiers-without-reason` |
| `plugin-imports-plugin` | A unit that implements a recorded port depends on a unit in another component that also implements a recorded port. | R25 | check (needs implements) | major | `plugins-coupled` |
| `boundary-defers-nothing` | A boundary defers no decision and the code on both sides of it changes together for the same reason. | R25 | judgment | minor | `unjustified-abstraction` |
| `unit-mixes-change-cadences` | A unit changes for unrelated reasons at unrelated cadences, so an internal boundary is missing. | R25 | judgment | major | `missing-boundary` |
| `rules-need-io` | The business rules cannot be exercised without a UI, a store, or a server in the process. | R26 | judgment | major | `rules-need-real-detail` |
| `plan-sequences-io-first` | The plan or brief sequences framework, schema, or screen work before the rules. | R26 | judgment | major | `plan-sequences-io-first` |
