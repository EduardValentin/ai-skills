# Components, cycles, and stability

The rules for the component graph (R27 to R33): what a component is and what belongs in it, how
its cohesion position is chosen, how the map grows, why it has no cycles, which way stability
must point, how the metrics screen it, and how components are released. Read this file when a
review or audit touches more than one component, a component edge, a cycle, or the metrics, and
read the metrics page with it.

## Rules

### R27. One component, one published surface

**A component is one enforced unit behind one published surface; group by reason to change and by
co-reuse.** A component's contents hide behind one published surface and, where they form a
release unit, build, test, version, and release together; two "components" that always release
together behind one surface are one component. Units that change for the same reasons at the same
time share a component, so a requirement change lands in one component or in one cohesion group.
A plan names that home, or the boundary defect preventing it. A change across cohesion groups is
the finding; one inside a group, however many components it touches, is not. Units reused
together live together: depending on a component means depending on all of it, so a consumer that
uses less than {componentUseShare} of what a component exports depends on far more than it needs,
and a unit outsiders use alone belongs with its co-reused neighbors. One concept that changes for
both policy and persistence reasons may share one enforced unit with the persistence part kept
private; splitting it into two release units waits until change patterns demand it.

Check questions:
- Do the components the change touches, and those touched together within {historyWindow}, fall in
  one recorded cohesion group (`arch query groups`)?
- Does every consumer use a real share of each component it imports?
- Can you say in one sentence what each component is for?

Examples:
- Bad: a tax-rule change edits `core`, `api`, and `reporting`; billing imports `cms-kernel` for one
  string helper; a `common` package holds date helpers, a retry policy, and a `Money` type.
- Good: tax rules live in `tax-policy`; `slugify` lives in a `text` component.

Not a finding when: `change-spans-groups`: the change is a repository-wide mechanical edit, such as a dependency upgrade or a formatting pass, with no change of behavior in the components it touches; `change-history-spans-groups`: the changes that touched the components together were such mechanical edits; `thin-component-use`: the consumer is a composition root that uses only the component's wiring factory; `thin-use-of-unpublished-component`: the consumer is a composition root that uses only the component's wiring factory.

### R28. Name your cohesion position

**Choose a position in the cohesion tension, name its cost, and expect it to drift.** Neglect
splitting and consumers receive too many releases they do not need; neglect grouping for
maintenance and too many components change per requirement; neglect grouping for reuse and the
component is hard to reuse or version. Early projects lean toward grouping for maintenance,
because localizing change matters more than reuse; as reuse appears, the structure drifts toward
finer splits driven by reuse. Revisit boundaries when change and reuse patterns shift. The model records
each cohesion group with `arch model add-group <name> members=<a,b> absorbs=<text>`, where
`absorbs` names the kind of change the group takes in; the decisions file states which cost each
component currently accepts and may explain a group at length for people. An audit proposes
groups from the change history and a person confirms them; a cross-cutting change that crosses
them may be recorded once as an exception, and recurring crossings revise the groups.

Check questions:
- Which of the three motives does this component neglect, and is that cost acceptable for the
  project today?
- When were its boundaries last reconsidered against current change and reuse patterns?

Examples:
- Early product: "`orders` grouped broadly so one change lands in one place; we accept releases
  some consumers do not need."
- Mature platform: "`orders-reporting` split out so reporting consumers stop receiving core
  releases."

Not a finding when: `no-cohesion-groups`: the change is a repository-wide mechanical edit, such as a dependency upgrade or a formatting pass, with no change of behavior in the components it touches; `change-history-without-groups`: the changes that touched components together were such mechanical edits.

### R29. Let the component map emerge

Guidance: advisory by default. Evaluated only when the session's scope includes a design or topology decision.

**Let the component map emerge from real change, and decide how boundaries are enforced up
front.** Which units belong together depends on which actually change and are reused together,
visible only after code has been written and changed a few times. So a design made before code
exists does not fix the full component map. It names only the first few components, by the code
the first features will change together, and states that splits for reuse and fixes for cycles
follow as the code grows. It does fix the enforcement mechanism, which is cheap to decide early
and expensive to change later: what a component publishes, whether folders carry import rules
that fail the build, and whether components are separate build units. With the mechanism fixed,
adding or splitting a component later changes the map, not the tooling. A single change names the
component it lands in and the direction of any new dependency it adds; it never redraws the map.

Check questions:
- Was the component map derived from observed change and reuse, or guessed from the domain's
  nouns before any code existed?
- Is the enforcement mechanism decided even though the map is deliberately incomplete?

Examples:
- Bad: a design for a new system fixes twelve packages and the arrows between them before any
  feature is written, with no statement of how a package boundary is enforced.
- Good: "Every package publishes only its index; import rules fail the build on deep imports
  across packages. First components: `orders` and `catalog`, because the first features change
  them together. `membership` stays inside `lending` until it gains its own actor."

Not a finding when: the plan names only the first components and fixes the enforcement mechanism, or the map it presents was derived from the change history of code that already exists.

### R30. No dependency cycles

**Allow no dependency cycles; break one by inverting a dependency or extracting a cohesive
leaf.** A cycle makes its components one component that none can build, test, or release alone,
and a change anywhere in it can break work everywhere in it. Preferred fix: declare the needed
port in the component that needs it and have the other implement it. Alternatives: an
interface-only component both depend on, or extraction of the shared concrete units into a new
component both depend on, which is acceptable when the extracted set is cohesive and a smell when
it is a grab-bag. Draw the graph with volatile components on top, so an upward arrow is visibly
wrong. A loop that exists only at run time, such as a callback handed in through a port, is not a
cycle: dependencies decide, not calls. Acyclic is necessary, not sufficient: name the forbidden
edges too, as R39 (Make forbidden edges uncompilable) requires.

Check questions:
- Following dependencies from this component, can you return to it?
- Does tooling enforce acyclicity?
- Drawn with volatile components on top, does any arrow point up?

Examples:
```ts
// before: entities -> authorizer (User imports Permissions) -> interactors -> entities
// after:  entities/Permissions.ts       export interface Permissions { allows(action: string): boolean }
//         authorizer/PermissionsImpl.ts import { Permissions } from "entities"; class PermissionsImpl implements Permissions {}
// now authorizer depends on entities, and entities depends on nothing
```

Not a finding when: `component-cycle`: no exemption; `module-cycle`: no exemption.

### R31. Depend toward stability

**Depend toward stability, and make stable components abstract at their edges.** Stability is a
property of the graph, not of intent. For each dependency from A to B, B is at least as stable as
A; a component designed to change often must not be depended on by one that is hard to change, or
it inherits that stability and cannot fulfil its purpose. Business rules sit in the most stable
components; vendor clients, framework glue, and UI sit in the most volatile, where only code meant
to change quickly lives. A stable component is mostly ports and abstract types, extended without
modification, and owns a port for everything it needs from the volatile world; concrete code there
is acceptable only when it genuinely does not change. A volatile component stays concrete so it is
cheap to change. Correct level ordering yields correct stability ordering, because plugins give
the higher level its dependents; where the two disagree, level wins and the mismatch signals a
missing plugin dependency.

Check questions:
- Does stability increase along each dependency?
- Is any component that many units depend on both concrete and frequently changed?
- Does a rarely depended-on component declare interfaces nobody implements?

Examples:
- Bad: `entities` depends on `feature-flags-ui`; `payments-domain` contains `StripeClient`.
- Good: `feature-flags-ui` depends on `entities`; `payments-domain` publishes the port `Payments` and
  `stripe-gateway` implements it.

Not a finding when: `abstractions-without-implementor`: the component is a published extension point whose abstract types code outside the repository implements, and its published surface says so; `unused-abstractions`: the component is such a published extension point, consumed outside the repository.

### R32. Use metrics as a screen

**Use the metrics as a screen, never a verdict.** When the graph has at least
{distanceMinComponents} components, compare each component's distance with the rest of the graph:
the metrics page defines instability, abstractness, distance, and the bounds of the zones. Two
positions are harmful. In the zone of pain, every change ripples outward and the component cannot
be extended without editing; the canonical case is a schema every service imports. Fix it by
shielding the dependents behind a port the component owns, or by moving them onto an
interface-only component. In the zone of uselessness, abstraction was paid for and is unused:
delete it or fold it into its one consumer. Examine components far from the balanced line relative
to the rest of the graph, and any whose distance rose between the base and head of the change
under review. A flagged number is a measurement against a chosen pattern: say in words why the
position is harmful, volatile and depended on or abstract and unused, before asking for a
restructure. On a smaller graph, skip the arithmetic and apply R31
qualitatively.

Check questions:
- Which components lie far from the balanced line, and to which side?
- Did any component's distance rise between base and head?
- Can each flagged component be explained in words?

Examples:
- Fine: a domain component that is mostly interfaces and depended on by everything sits near the
  line.
- Examine: a `shared-utils` package that is all concrete code, depended on by everything, and
  changed weekly sits in the zone of pain.
- Note and leave alone: a `string-utils` package in the same position but unchanged within
  {historyWindow}.

Not a finding when: `distance-over-threshold`: nobody can say in words why the component's position is harmful, volatile and depended on or abstract and unused, since a number alone is never a finding; `unused-abstractions`: the published extension point stated under R31; `abstractions-without-implementor`: the published extension point stated under R31.

### R33. Release components bottom-up

Guidance: advisory by default. Evaluated only when the session's scope includes a design or topology decision.

**Release components bottom-up, let dependents adopt on their own schedule, and integrate
continuously.** In an acyclic graph a component is released once everything it depends on is
released; a release can affect exactly its dependents, whose owners decide whether and when to
adopt it. Dependencies between components target a published surface and, across release units,
name a version with a readable change record; consumption by path, where any commit changes
everyone's build, is a missing boundary. Integrate continuously at component boundaries: batching
integration into a scheduled step lowers cost for a few days and then concentrates it into a
crisis that grows with the project.

Check questions:
- Given this change's component, are its dependents listed?
- Can a dependent stay on the previous version?
- Does the plan rely on a single big integration step?

Examples:
- Bad: shared code consumed by relative path, so any commit in it changes everyone's build; "teams
  work in isolation Monday to Thursday, integrate Friday."
- Good: consumers pin a version and upgrade deliberately; each team releases its component when
  ready.

Not a finding when: the components build and release together from one repository as one release unit, so a path dependency is the normal shape, or the release arrangement was approved earlier and is only being verified.

## Conditions

| Id | Condition | Rule | Decided by | Severity | Defect |
|---|---|---|---|---|---|
| `change-spans-groups` | In a change review, the change touches a component that shares no recorded cohesion group with another touched component. | R27 | check | major | `change-spans-groups` |
| `thin-component-use` | A consumer uses less than {componentUseShare} of the symbols that a component with a declared published surface exports. | R27 | check (needs symbolImports) | minor | `thin-component-use` |
| `change-history-spans-groups` | In an audit, changes within {historyWindow} touched this component together with a component it shares no recorded cohesion group with. | R27 | judgment | major | `change-spans-groups` |
| `thin-use-of-unpublished-component` | A consumer uses less than {componentUseShare} of what a component with no declared published surface exports. | R27 | judgment | minor | `thin-component-use` |
| `no-cohesion-groups` | In a change review, the change touches more than one component and the model records no cohesion groups. | R28 | check | minor | `no-cohesion-groups` |
| `change-history-without-groups` | In an audit, the model records no cohesion groups and changes within {historyWindow} touched more than one component together. | R28 | judgment | minor | `no-cohesion-groups` |
| `cohesion-position-unstated` | A component's cohesion position and its cost are not stated, and its boundaries were not revisited while its change patterns shifted. | R28 | judgment | minor | `cohesion-position-unstated` |
| `component-map-fixed-upfront` | A greenfield plan fixes the full component map before code exists. | R29 | judgment | minor | `component-map-fixed-upfront` |
| `component-cycle` | The component graph contains a cycle. | R30 | check | blocker | `cycle` |
| `module-cycle` | The graph of units contains a cycle. | R30 | check | blocker | `cycle` |
| `unstable-dependency` | A component depends on a component whose instability is higher than its own. | R31 | check | major | `depends-on-less-stable` |
| `zone-of-pain` | In a change review, the change touches a component whose metrics place it in the zone of pain. | R31, R32 | check (needs exports) | major | `zone-of-pain` |
| `zone-of-pain-changing` | In an audit, a component in the zone of pain changed within {historyWindow}, where no change under review touches it for the check to decide. | R31, R32 | judgment | major | `zone-of-pain` |
| `unused-abstractions` | A component exports abstract types and no unit outside it depends on it. | R31, R32 | check (needs exports) | minor | `unused-abstraction` |
| `abstractions-without-implementor` | A component has abstract types with no implementor, or outside consumers that use none of its abstract types. | R31, R32 | judgment | minor | `unused-abstraction` |
| `distance-over-threshold` | With at least {distanceMinComponents} components, a component's distance lies more than {distanceDeviations} standard deviations above the mean, or rose by at least {distanceJump} between base and head. | R32 | check (needs exports) | minor | `off-balance` |
| `unversioned-dependency-across-releases` | A component is consumed by path with no version although it and its consumer release separately. | R33 | judgment | major | `unversioned-dependency-across-releases` |
