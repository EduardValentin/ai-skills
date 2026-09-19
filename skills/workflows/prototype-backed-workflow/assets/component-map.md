# Parity component map

Session: <ticket id or branch>
Prototype app: <relative path to the reference app root>
Real app: <relative path to the real app root>
Generated: <date>

One row per root pair touched in this session. The prototype component is the
React component name the root finder resolves at runtime. The real app root is
a CSS selector, or the value of a `data-parity-root` attribute the real app
sets on that element. Routes are listed as real app route then prototype
route. Confirm every pairing that is not an obvious name match before the
parity step runs. Source file locators belong in Notes.

| Id | Prototype component | Real app root | Routes (real → prototype) | States | Pairing confidence | Notes |
|---|---|---|---|---|---|---|
| C1 | <ComponentName> | <selector or data-parity-root value> | <route> → <route> | <default, empty, error, ...> | <obvious / confirmed> | <why this pairing, source locators, or None> |
