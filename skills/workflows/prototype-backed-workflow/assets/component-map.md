# Parity component map

Session: <ticket id or branch>
Prototype app: <relative path to the reference app root>
Production app: <relative path to the production app root>
Generated: <date>

One row per production component, page section or page touched in this
session. Locators are repository-relative paths. Routes are listed as
production route then prototype route. Confirm every pairing that is not an
obvious name match before the parity step runs.

| Id | Production component | Prototype counterpart | Routes (prod → proto) | States | Pairing confidence | Notes |
|---|---|---|---|---|---|---|
| C1 | <path to component or section> | <path to prototype component> | <route> → <route> | <default, empty, error, ...> | <obvious / confirmed> | <why this pairing, or None> |
