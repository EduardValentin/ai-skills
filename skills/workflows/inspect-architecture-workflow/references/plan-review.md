# Plan review

A plan is reviewed before it is approved, against the committed baseline, by treating the plan
as a proposed diff to the inventory.

## Inputs

The written implementation plan (or spec), the ticket or brief with its acceptance criteria and
any named upcoming changes, the committed record for the affected scope, and the current ledger.

## Procedure

1. **Extract proposals.** From the plan, list every unit it creates, deletes, or edits; every
   dependency it adds, removes, or redirects; every port it declares and who implements it; every
   boundary data type it introduces; every technology it names; every test surface it names.
   Each becomes a proposed inventory row marked `proposed`, keyed like real rows. A plan that
   names files but not the dependencies between them is mapped by reading those files' current
   imports and assuming the plan keeps them unless it says otherwise; state that assumption.
2. **Check the plan's own slots.** A plan that omits any of these is incomplete before any rule
   is applied: the actors of the change; the one component that absorbs it; for each boundary
   crossed or created, direction, port owner, crossing data, and enforcement; files created
   versus stable files edited; the known upcoming changes and how the plan leaves each; the
   decisions it defers and behind which port; which defect each test catches and through which
   surface. Report missing slots as `SHOULD_CHANGE` rows citing R1 for behavior and structure,
   R10 for direction and enforcement, R23 for deferral, and R37 for tests, severity `major`.
3. **Evaluate.** Overlay the proposed rows on the baseline inventory and dispatch the eight
   evaluation slices with the proposed and affected rows marked. The workflows run unchanged;
   the evidence column cites the plan's section instead of a path where the code does not exist
   yet.
4. **Cost of the simplest change.** Walk the plan's smallest realistic follow-up (from the named
   upcoming changes) through the proposed graph and count units edited; record it in the ledger
   row for R1.

## Output

Findings go to the ledger with `target` set to the proposed row IDs. The return contract's verdict
blocks approval on any open blocker or major row.

Who acts on the findings: the agent that wrote the plan (the requirements-gathering agent for one
ticket, the coordinating agent for a set of tickets) revises it for every blocker and major
finding and re-dispatches the plan review. The loop ends when the verdict is `OK` or when the
user, shown the remaining rows, explicitly accepts each with a reason that the coordinator records
in `decisions.md` as `ACCEPTED`. No implementer exists at this point and none is involved.

The coordinator writes only the ledger and `deltas.md`. Proposed rows stay marked `proposed` in
the ledger until a later change review confirms or replaces them; what happens to `deltas.md`
after approval is the implementation workflow's concern, not this reference's.
