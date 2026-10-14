# Verdicts, severity, and the return contract

Shared by every mode. The coordinator applies it after merging the evaluation slices.

## Targets and rows

A target is a unit path, an edge written `from -> to` as paths, a port written `path:symbol`, a
component ID (`C<n>`), or a cycle. A cycle's target is its sorted member list joined by ` -> `:
component IDs for a component cycle (`C17 -> C18 -> C22 -> C23`), paths for a module cycle. A
cycle is one finding, never one per member. Each finding points at exactly one target and one
rule; that pair
identifies the finding across runs. Two findings with the same target and rule are duplicates,
and a finding keeps its ID while both still match.

Ledger finding IDs and run numbers are transitory: they never appear in the committed record or
any other committed file. The record names a finding by the target and the rule number.

## Row verdicts

`OK`, `SHOULD_CHANGE`, `RESOLVED` (a later run found the target compliant; keep the row, add
the commit), `ACCEPTED` (the user explicitly accepted the finding), or, in plan review only,
`UNDERSPECIFIED` (the plan is not concrete enough to derive a fact the review needs; a
clarification request to the planner, carrying no rule or severity).

### Introduced or left in place

In a change review a `SHOULD_CHANGE` row is *introduced* when its target is a unit or edge that
`arch diff` reports as added. In the base-without-model fallback (`change-review.md`, Map step 4)
it is introduced when its target is a unit that `arch query touched` marks `added`, an edge
whose `from` or `to` is such a unit, or a cohesion row (R27, R28), which describes the change
itself; `arch assess --base <base>` marks its own rows that way in the fallback. With a model at
the base, `arch assess --base <base>` sets the mark on its own rows
the same way, matching an edge by its `from -> to` pair, and also marks *introduced* a cycle
with an edge between its members that is new since the base (a cycle the change only shrinks
stays left), a component edge or component absent at the base, and a cohesion row (R27, R28),
which describes the change itself (`command.md`, `assess`). Every other row is *left in place*. The coordinator sets the
mark after merging and writes it in the ledger's `Origin` column as `introduced` or `left`. An
audit or a plan review marks every row `introduced`.

## Accepting a finding

Acceptance lives in the ledger, never in `decisions.md` as a finding. When the user accepts a
row, ask one question: a one-off for this change, or a standing rule of the architecture?

- **One-off.** Set the row to `ACCEPTED` and add who, when, and why to the ledger's Acceptances
  table. The row stays `ACCEPTED` while the same target and rule still match, so an acceptance
  made in plan review carries into the change review of the same ticket. On a machine with no
  ledger the finding resurfaces once and is accepted again or promoted.
- **Standing rule.** For a cohesion group, run the printed `arch model add-group` (or
  `remove-group`) invocation and add the group's explaining paragraph to `decisions.md`; for
  anything else, write one generalized row in `decisions.md`: an intended exception stated from
  component or ring to component or ring, a deferred decision, or a cohesion position. Evaluators
  read `model/boundaries.json`'s groups and those `decisions.md` tables and raise nothing they
  cover, so no per-ticket acceptance follows. Then set the row to `ACCEPTED` in the ledger as
  above.

Cohesion groups live in `model/boundaries.json`, never in `decisions.md`. `decisions.md` holds
only the decisions the workflows consume that are not already model data, each stated at
component or boundary level: never a row per finding, per ticket, or per symbol.

## Severity

Base severity comes from the matched decision-table row (see `references/workflows/preamble.md`).
Escalation, in order; nothing lowers a severity:

1. The target is a policy unit (entity, use case, port, boundary data) or the edge starts in
   one: at least `major`.
2. A named upcoming change would cost less if this violation were already fixed: with it in
   place, that change must edit a unit it would otherwise leave alone, thread a flag through
   layers, or copy code. `blocker`. Ask "would fixing this first make the upcoming change
   smaller?"; a yes escalates. Touching the same file as the upcoming change does not count on
   its own: if the change does the same work whether or not the violation is fixed, the row
   keeps its severity.
3. Three or more other units depend on the target (its fan-in: the count of units that import,
   implement, construct, or use its types), so a defect in it reaches all of them: at least
   `major`. Likewise a boundary the design reasons on but nothing enforces (no visibility rule,
   export list, build unit, or build-failing import rule stops a crossing): at least `major`,
   even if it has not been crossed yet.
4. A cycle: `blocker` regardless of table.

Rule 3 applies to the evaluator rows: the coordinator applies it to them, and rules 1, 2, and 4
to every row. No assessed row has a base below `major` today, so rule 3 lifts none of them; should
a future one qualify, `arch assess` records the lift itself, from the fan-in of the target's
component (for an edge, the component of its `to` unit), in its Severity and Escalation cells.

Keep the base severity beside the escalated one in the ledger: the Severity cell reads
`<severity>` when no rule lifted the row and `<severity> (base <severity>)` when one did, as in
`major (base minor)`; the first word is the severity every count and ordering uses. A row with a
`[rule <n>]` mark and no base in its Severity cell is refused by `arch ledger add-run`, so write
the base on every lifted row. Report how many rows each rule lifted, so a distribution dominated
by one rule is visible.

## Changes and the improvement map

Rows whose `change` descriptions name the same move (same port, same split, same extraction)
form one change, `CH-A`, `CH-B`, and so on, described once. The improvement map orders changes
by the highest severity each resolves, then by the number of rows resolved. It is derived from
the rows, never written independently of them.

## Run verdict

`OK` when no counted open `SHOULD_CHANGE` row is `blocker` or `major`; otherwise
`SHOULD_CHANGE`. Every introduced row counts. A left-in-place row counts only when escalation
rule 2 lifted its severity (fixing it first makes the named change cheaper). The other
left-in-place rows never block: the return contract reports them under `Pre-existing` with their
severities. A
re-run of the same mode and key (the plan review fix loop over one plan, a second round of a
change review against one base commit) counts its own rows and the open rows the earlier runs
with that mode and key carried forward, so a finding the re-run did not evaluate still blocks.
The key is the base commit in a change review and the plan's path in a plan review; the scope
text never decides it. Open rows of any other mode or key never block; the
return contract reports them on the `Carried` line so they never vanish. In
plan review a `SHOULD_CHANGE` verdict, or any open `UNDERSPECIFIED` row, blocks plan approval
until each blocker and major row is resolved in the plan or `ACCEPTED` by the user and each
clarification is answered.

## Return contract

No report file: the ledger is for agents, the committed record for people. `arch ledger map`
prints the Verdict, Pre-existing, Carried, Escalation, Direction, and Agents lines from the ledger
(`references/command.md`, `ledger`); the coordinator fills in the rest. The Verdict line
counts the rows the run verdict counts; the Pre-existing line counts the left-in-place rows it
does not, and reads `0 blocker, 0 major, 0 minor` outside a change review. Reply to the caller
with:

```markdown
# Architecture <audit | change review | plan review> — <scope>
Verdict: <OK | SHOULD_CHANGE> — <n> blocker, <n> major, <n> minor open; <n> targets OK; <n> changes named
Pre-existing: <n> blocker, <n> major, <n> minor (not blocking)
Carried: <n> open from earlier scopes (not blocking)
Escalation: <n> rows lifted by rule 1, <n> by rule 2, <n> by rule 3, <n> by rule 4
Baseline: <docs/architecture at commit, or "created this run, commit with the PR">
Direction:
1. <CH-x> — <rule> — <change> — protects <upcoming change>
2. ...
3. ...
Clarifications: <n> UNDERSPECIFIED rows, plan review only, or none
Record: <files under docs/architecture edited this run, or none> | Pending record updates: <n> rows waiting on open findings
Ledger: <path> | Agents: <n> dispatched (<n> mapping, <n> fact, <n> evaluation) | Tokens: <per-agent totals when the harness reports them, else "not reported">
Out of scope: <one line of non-structural observations for other reviewers, or None>
```
