# Humble objects and adapters

The rules for code at a device boundary (R20 to R22): split what is hard to test from what
decides, let the presenter finish every decision before the view, and reach storage through a
storage port with all query code below it. Read this file when a review or audit touches a view,
a presenter, a controller or other handler, a gateway, or a storage port.

## Rules

### R20. Split humble from testable units

**Split hard-to-test behavior into a humble unit and a testable unit at every device boundary.**
Wherever code talks to a screen, driver, network, file system, or clock, the humble unit keeps
only what cannot be tested without the device, with no conditional, calculation, formatting, or
lookup; the testable unit holds every decision and is tested with the humble unit replaced by a
test double. The humble unit is the lower level, and the testable unit owns the port that reaches
it. Inbound handlers and outbound senders are humble too: a controller only parses, builds the
request model, and calls the use case; a sender only serializes and transmits; neither validates
business rules, branches on domain state, or formats for display. Halves that cannot be separated
cleanly mark a missing boundary, which belongs there. Once it is drawn, the humble side's only
remaining defect is mis-wiring, covered by a thin integration test through the entry point.

Check questions:
- Which two units sit on either side of the device boundary? Does the humble one contain any
  decision?
- Do the testable unit's tests run without the real device?
- If the humble unit had no tests, what defects could hide in it?
- Does the handler do anything besides parse, convert, and invoke?

Examples:
- Bad: `ReportPage` queries the store, sums rows, formats totals, and renders; an HTTP handler
  rejects orders over a limit before calling the use case.
- Good: `ReportPresenter`, tested with in-memory rows, produces `ReportViewModel`; `ReportPage`
  copies it to the screen; the approval rule lives in the use case.

Not a finding when: `handler-holds-business-logic`: the handler's only checks parse the input format to build the request model, which a controller must do; `device-unit-holds-logic`: the conditionals it holds only encode or decode a wire or file format, such as escaping or framing, with no decision on domain data.

### R21. Presenter finishes every decision

Advisory by default in a legacy baseline.

**The presenter finishes every decision; the view only copies the view model.** The view model
covers everything the application controls on the screen: every label, button, menu item, field,
and table cell, and every enabled, visible, selected, or highlighted state, has a string, boolean,
or enumeration field set by the presenter. Tables are tables of formatted strings, and dates and
money arrive formatted. The view binds fields to widgets and maps a flag or enumeration to an
appearance (a color, an icon, a disabled state), with no conditionals on domain data, arithmetic,
formatting, lookups, or calls into the application. The presenter implements the use case's
output boundary and imports no UI framework. A framework's declarative formatter may render a
value only when no decision on domain data is involved.

Check questions:
- Walking the screen element by element and state by state, does each map to a view-model field?
- Does the view model hold a date, a money type, a raw number the view will format, or a domain
  object?
- Read the view line by line: is anything beyond binding or flag-to-appearance left in it?
- Can presenter tests assert on the view model with structural equality?

Examples:
- Bad: `if order.total < 0 then label.color = RED`, `label.text = fmt(order.total)`; the view
  hides "Refund" by inspecting `order.status`.
- Good: `label.text = vm.totalText`, `label.color = if vm.totalIsNegative then RED else DEFAULT`,
  with a `refundButtonVisible: Boolean` field.

Not a finding when: `view-makes-decisions`: the view only binds view-model fields to widgets, or maps a flag or enumeration field of the view model to an appearance, as on a static page or a screen with no decision to make. A view that reads a domain object, a domain status, or any value outside the view model is never exempt.

### R22. Reach storage through a gateway

Advisory by default in a legacy baseline.

**Reach storage through a storage port with one method per application need, implemented by a
gateway that holds every query.** The storage port is owned by the consumer, named in domain
language, and has methods for exactly the operations the application performs, typed in
application terms. These per-need methods are the narrow interfaces of R13 (Substitutable
implementations, narrow interfaces) in practice; a generic `query(sql)` or `find(spec)` escape
hatch moves the decision to the caller. Query strings, query builders, ORM sessions, and
connection handles appear only inside gateways; a use case or entity containing any of them
cannot be tested without the store, and marks a missing storage-port method. An ORM is a data
mapper: its mapped types stay in the persistence component and are converted to
and from domain types inside the gateway. The technology name belongs on the gateway
(`SqlOrders implements Orders`), never on the storage port.

Check questions:
- Does each storage-port method state one concrete need?
- Do use cases and entities contain query strings, builders, sessions, or ORM-annotated types?
- Is an ORM-annotated class doubling as the domain model?

Examples:
```
// good
interface Users: lastNamesOfUsersWhoLoggedInAfter(since: Date) -> List of Text
// bad
interface Users: query(sql: Text) -> List of Row
```

Not a finding when: `query-inside-policy`: the string is a domain value that only resembles a query, such as a search phrase the user typed, passed to the storage port unchanged; `storage-port-exposes-queries`: each method takes parameters named in domain terms for one application need, such as `ordersPlacedBetween(start, end)`, even though the gateway turns them into a query; `port-named-for-detail`: the word names a domain concept that shares a technical term, such as `Queue` for customers waiting in line.

## Conditions

| Id | Condition | Rule | Decided by | Severity | Defect |
|---|---|---|---|---|---|
| `device-unit-holds-logic` | A unit talks to a device and also holds conditionals, calculations, formatting, or lookups, with no testable counterpart. | R20 | judgment | major | `humble-unit-holds-logic` |
| `handler-holds-business-logic` | A handler or sender validates business rules, branches on domain state, or formats for display. | R20 | judgment | major | `humble-unit-holds-logic` |
| `presenter-imports-ui-framework` | A presenter imports an external package tagged framework. | R21 | check | major | `presenter-bound-to-framework` |
| `view-makes-decisions` | A view makes a decision beyond mapping a flag or enumeration to its appearance. | R21 | judgment | major | `view-makes-decisions` |
| `view-model-not-formatted` | A view model holds a date, a money type, an unformatted number, a domain object, or a method. | R21 | judgment | major | `view-model-not-formatted` |
| `storage-port-exposes-queries` | A storage port exposes a raw query, a generic find by specification, or a query builder. | R22 | judgment | blocker | `storage-port-exposes-queries` |
| `query-inside-policy` | A query string, query builder, session, or ORM type appears inside a use case or entity. | R22 | judgment | blocker | `policy-depends-on-detail` |
| `orm-class-as-domain-model` | An ORM-annotated class is used as the domain model. | R22 | judgment | blocker | `policy-depends-on-detail` |
| `port-named-for-detail` | A port the domain owns carries a storage, transport, or vendor word in its name. | R22 | judgment | minor | `port-named-for-detail` |
