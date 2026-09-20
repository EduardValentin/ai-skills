# Verdicts, severity, and the return contract

Shared by every mode. The coordinator applies it after merging the evaluation slices.

## Targets and rows

A target is the one inventory row a finding is about, named by ID: a unit (`U<n>`), an edge
(`E<n>`), a boundary (`B<n>`), or a component (`C<n>`). Each finding row points at exactly one
target and one rule; that pair identifies the finding across runs. Two rows with the same target
and rule are duplicates, and a finding keeps its ID while both still match.

Ledger finding IDs and run numbers are transitory: they never appear in the committed record or
any other committed file. The record names a finding by the target's path and symbol and the
rule number.

## Row verdicts

`OK`, `SHOULD_CHANGE`, `RESOLVED` (a later run found the target compliant; keep the row, add
the commit), `ACCEPTED` (the user explicitly accepted the finding), or, in plan review only,
`UNDERSPECIFIED` (the plan is not concrete enough to derive a fact the review needs; a
clarification request to the planner, carrying no rule or severity).

## Accepting a finding

Acceptance lives in the ledger, never in `decisions.md` as a finding. When the user accepts a
row, ask one question: a one-off for this change, or a standing rule of the architecture?

- **One-off.** Set the row to `ACCEPTED` and add who, when, and why to the ledger's Acceptances
  table. The row stays `ACCEPTED` while the same target and rule still match, so an acceptance
  made in plan review carries into the change review of the same ticket. On a machine with no
  ledger the finding resurfaces once and is accepted again or promoted.
- **Standing rule.** Write one generalized row in `decisions.md`: an intended exception stated
  from component or ring to component or ring, a cohesion group, a deferred decision, or a
  cohesion position. Evaluators read those tables and raise nothing they cover, so no
  per-ticket acceptance follows. Then set the row to `ACCEPTED` in the ledger as above.

`decisions.md` holds only decisions the workflows consume, each stated at component or boundary
level: never a row per finding, per ticket, or per symbol.

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

Keep the base severity beside the escalated one in the ledger, and report how many rows each
rule lifted, so a distribution dominated by one rule is visible.

## Changes and the improvement map

Rows whose `change` descriptions name the same move (same port, same split, same extraction)
form one change, `CH-A`, `CH-B`, and so on, described once. The improvement map orders changes
by the highest severity each resolves, then by the number of rows resolved. It is derived from
the rows, never written independently of them.

## Run verdict

`OK` when no open `SHOULD_CHANGE` row is `blocker` or `major`; otherwise `SHOULD_CHANGE`. In
plan review a `SHOULD_CHANGE` verdict, or any open `UNDERSPECIFIED` row, blocks plan approval
until each blocker and major row is resolved in the plan or `ACCEPTED` by the user and each
clarification is answered.

## Return contract

No report file: the ledger is for agents, the committed record for people. Reply to the caller
with:

```markdown
# Architecture <audit | change review | plan review> — <scope>
Verdict: <OK | SHOULD_CHANGE> — <n> blocker, <n> major, <n> minor open; <n> targets OK; <n> changes named
Escalation: <n> rows lifted by rule 1, <n> by rule 2, <n> by rule 3, <n> by rule 4
Baseline: <docs/architecture at commit, or "created this run, commit with the PR">
Direction:
1. <CH-x> — <rule> — <change> — protects <upcoming change>
2. ...
3. ...
Clarifications: <n> UNDERSPECIFIED rows, plan review only, or none
Record: <files under docs/architecture edited this run, or none> | Pending record updates: <n> rows waiting on open findings
Ledger: <path> | Agents: <n> dispatched (<n> mapping, <n> history, <n> evaluation) | Tokens: <per-agent totals when the harness reports them, else "not reported">
Out of scope: <one line of non-structural observations for other reviewers, or None>
```
