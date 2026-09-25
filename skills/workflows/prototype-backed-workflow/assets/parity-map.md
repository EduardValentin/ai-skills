# Parity map

Prototype app: <relative path to the reference app root>
Real app: <relative path to the real app root>

This file lives at the project root and is committed with the code. It holds
one row per root pair the project has ever verified, not per session. Ids are
stable and never reused: a new pair takes the next free `C<n>` even when an
earlier row was deleted. The implementer adds and edits rows as the work
progresses; the parity verifier reads this file and never writes it.

The prototype component is the React component name the root finder resolves
at runtime, or `root:<selector>` to address the prototype side by selector.
The real app root is a CSS selector, or the value of a `data-parity-root`
attribute the real app sets on that element. Routes are the real app route,
then the prototype route. States are comma-separated names, each optionally
followed by an action recipe file name in parentheses that lives under
`parity-actions/`. Viewports is empty for the full viewport set or a
comma-separated `WxH` subset. Ignore is empty or semicolon-separated
`proto:` and `real:` entries, each `hook:<data-parity value>` or
`path:<snapshot path prefix>`; only the implementer adds them, because they
change what is verified. Confidence is `obvious` for a name match or
`confirmed` after the pairing was checked by hand. Source file locators belong
in Notes. Run `parity_map.py check parity-map.md --project-root .` before the
parity step.

| Id | Prototype component | Real app root | Routes (real → prototype) | States | Viewports | Ignore | Confidence | Notes |
|---|---|---|---|---|---|---|---|---|
| C1 | <ComponentName or root:selector> | <selector or data-parity-root value> | <route> → <route> | <default, empty, hover (file.json), ...> | <empty or WxH, WxH> | <empty or proto:hook:x; real:path:p> | <obvious / confirmed> | <why this pairing, source locators, or None> |
