# Plan review

Reviews a written implementation plan before it is approved, treating the plan as a proposed
diff to the committed baseline. Writes the ledger and the plan overlay; never writes the
committed record or the plan.

## Preflight

1. Read the project's agent instructions for artifact paths and named boundaries.
2. Inputs: the plan or spec, the ticket or brief with acceptance criteria, the committed record
   for the affected scope, the current ledger.
3. Check the committed record covers the units the plan touches; if not, run `audit.md` on the
   affected scope first and note in the return that the record was created.
4. Confirm the ledger root is ignored. Load the ledger to match finding IDs; when none exists,
   start one.
5. Build the upcoming-changes list from the plan, the ticket, the baseline's `decisions.md`, and
   anything the caller supplied.

## Build the plan overlay

No mapping or history slices run; the plan has not changed the code.

The plan overlay is the inventory this mode evaluates: the committed record's rows for every
unit the plan touches, with the plan's edits applied, plus one new row per unit the plan
creates, so it shows what the record would contain if the plan were implemented as written.
The coordinator writes it to `.architecture/slices/plan-overlay.md` so the evaluators read a
file. Nothing in this mode writes to the committed record.

| Step | Reads | Writes |
|---|---|---|
| 1. Join the plan to the baseline | The plan; `docs/architecture/units.md`, `dependencies.md`, `components.md`, `decisions.md` | The rows of every unit the plan creates, deletes, or edits, copied unchanged into `slices/plan-overlay.md`, with their component, ring, actors, edges, ports and owners, enforcement, and deferred decisions |
| 2. Apply the plan's edits | The plan's snippets and prose; the current source of any named file whose dependencies the plan does not describe | Those overlay rows updated with the imports, implemented interfaces, constructed details, signature types, data shapes, and tests the plan adds, removes, or redirects, and marked `changed`; where current imports are assumed kept, that assumption written on the row |
| 3. Add new units | The plan's snippets; the ticket | One overlay row per unit the plan creates, marked `proposed`, with kind, ring, component, and edges derived from the snippet and from what the plan says calls it; actors from the ticket and from the touched units' recorded actors |
| 4. Ask for what cannot be derived | The overlay | A row in `.architecture/ledger.md` with verdict `UNDERSPECIFIED`, naming the plan task and the missing fact (a new unit's imports, callers, or component; an ambiguous target type); no rule, no severity; a clarification request to the planner, not a finding |

From the overlay the coordinator can state, without relying on the plan's wording, the change's
home component (or that it spreads across several), the actors it serves, every boundary it
crosses or creates with owner and enforcement, which technologies it commits to and which
decisions it leaves deferred, and what each named test would falsify. These statements go into
the evaluation packet as facts.

## Evaluate

1. A workflow W1 to W8 is applicable when a `proposed` row falls in a section it reads. Carry
   the others forward and name them in the run log.
2. Dispatch one `architecture-evaluator` that runs every applicable workflow in order, with the
   evaluation packet from `slicing.md` (the full component graph when W6 is applicable).
   Evidence cites the plan's section where the code does not exist yet.
3. Walk the plan's smallest realistic follow-up (from the upcoming changes) through the proposed
   graph, count the units edited, and record the count in the R1 row.
4. Phrase every finding in the plan's own terms: the task number, the file, and the concrete
   edit ("task 3 has `PayrollService` construct `PgClient`"), never in terms of a heading the
   plan lacks.
5. Merge, escalate, group changes, and build the improvement map per `verdicts.md`.

## Record

Append the run to `ledger.md` with targets set to the proposed row IDs; write `slices/`,
including `slices/plan-overlay.md`. Do not touch `change-history.md` or the committed record;
the change review after implementation updates the record from real code.

## Return and the fix loop

Reply with the return contract from `verdicts.md`, listing `UNDERSPECIFIED` rows separately as
clarification requests. A `SHOULD_CHANGE` verdict, or any open `UNDERSPECIFIED` row, blocks
approval. The agent that wrote the plan answers the clarifications, revises the plan for every
blocker and major finding, and re-dispatches this review, until the verdict is `OK` or the user,
shown the remaining rows, explicitly accepts each with a reason, recorded per "Accepting a
finding" in `verdicts.md`: a one-off stays in the ledger and carries into this ticket's change
review; a standing rule becomes one generalized row in `decisions.md`. No implementer exists at
this point and none is involved.
