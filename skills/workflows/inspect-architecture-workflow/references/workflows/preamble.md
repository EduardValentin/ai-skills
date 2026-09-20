# Evaluation workflows

Run W1 to W8 in order. Each workflow names the inventory sections it reads, its procedure, a
decision table whose conditions are evaluated in order (the first match decides), and what it
writes. Rule numbers refer to the rule file named after the workflow (`references/rules/w1.md`
for W1, and so on). A target matching no `SHOULD_CHANGE` condition is written as `OK` with the
rule it satisfies.

Columns of every assessment row: `id`, `workflow`, `target` (inventory IDs), `rule`,
`verdict` (`OK`, `SHOULD_CHANGE`, `RESOLVED`, `ACCEPTED`), `severity`, `evidence` (paths), `change`,
`protects` (the upcoming change), `run`.

Before applying a decision table, check the intended exceptions and cohesion groups in
`decisions.md`. A candidate finding whose edge, layer skip, or shared shape a recorded exception
covers (same from-and-to components or rings, or the same shape) is written as `OK` naming the
exception, never as `SHOULD_CHANGE`. Exceptions are read at component and ring level; a packet
with no `decisions.md` has none.

Every `SHOULD_CHANGE` row carries a base severity. The coordinator may raise it by the escalation
rules in the skill body (policy target, path of a named upcoming change, fan-in of three or more,
cycle); nothing lowers it. One scale: `blocker` when the violated rule is a dependency-direction
or cycle rule whose breach couples policy to detail; `major` when the breach couples two units
that change for different reasons or leaves a relied-upon boundary unenforced; `minor` when the
breach is local to one unit and no dependent inherits it.

Each workflow has its own file, `w1.md` to `w8.md`, beside this preamble. Read the preamble
before any workflow file.
