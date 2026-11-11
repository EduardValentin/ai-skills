# recorded-exceptions fixture

The `known-defects` structure cut down to a handful of defects, each answered by a recorded model decision: an exception
for one edge, `*` exceptions for a unit and for a port, an `external:orm` exception, rule R38 switched off for the
`reports` component, rule R27 set to advisory, and thresholds changed (`componentUseShare`, `distanceDeviations`,
`distanceMinComponents`).

`arch check` must raise no enforced row and exit 0. `covered` equals the number of rows the exceptions cover, `skipped`
lists the off and advisory rules with their reasons, and the one advisory row (`web -> catalog`, thin use) is present
with status `advisory`.
