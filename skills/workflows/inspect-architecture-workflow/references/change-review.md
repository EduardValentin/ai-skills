# Change review

Reviews a diff against the committed baseline. Maps only the diff's neighborhood, evaluates
only what changed, writes the ledger, and updates the committed record for the rows the diff
changed, but only where the review found nothing wrong: the record never records a violation
as accepted structure.

## Preflight

1. Read the project's agent instructions for artifact paths and named boundaries.
2. Fix the scope: the diff or changed-file list, frozen.
3. Check the committed record covers the diff's paths: `docs/architecture/model/components.json`
   exists at HEAD and `arch uncovered` lists none of the diff's files. When the model is missing,
   run `audit.md` on the affected scope first and note in the return that the record was created.
4. Confirm the ledger root is ignored. Load the ledger to match finding IDs; when none exists,
   start one. A missing ledger is never a blocker.
5. Build the upcoming-changes list from the ticket, the baseline's `decisions.md`, and anything
   the caller supplied.

## Map

1. `arch diff <base>`: the units added, removed, moved, or reclassified and the edges added or
   removed are the changed set.
2. `arch uncovered`; dispatch mapping slices only for what it lists.
3. `arch query touched --base <base> --with-neighbors` gives the changed units and the unit
   rows of their neighbors for the packets.
4. When the base commit predates the model (no `docs/architecture/model/components.json` at
   that commit), `arch diff` exits 1. Evaluate the working tree instead:
   1. Run `arch graph` on the working tree.
   2. Run `arch query touched --base <base> --with-neighbors`.
   3. The scope is the touched units plus every edge touching them, taken from `arch query edges
      <path>` per touched unit, or from the `edges` of `arch graph --json`.
   4. W6 is always applicable, since added component edges cannot be told apart from old ones.
   5. Every finding is left in place unless its target is an `added` unit or an edge touching one
      ("Introduced or left in place" in `verdicts.md`).
   6. The run log states "base <base> predates the model; evaluated the working-tree graph".

## Evaluate

1. A workflow W1 to W8 is applicable when a `changed` row falls in a section it reads. Carry the
   others' previous rows forward and name them in the run log.
2. Run `arch assess --base <base>` and write its output to
   `.architecture/slices/packet/00-assess.md`. It emits only rows inside the change, and they
   keep the Origin it sets; in the base-without-model fallback (Map step 4) it marks every row
   `left` and warns, and the coordinator re-marks each row from `arch query touched` as that
   step says.
3. Dispatch one `architecture-evaluator` that runs every applicable workflow in order, with the
   evaluation packet from `slicing.md` (the full component graph when W6 is applicable) and the
   assess output file as decided rows. It judges only changed targets and the edges touching
   them, from rows and never from code, and phrases findings as "the diff introduces" or "the
   diff leaves in place".
4. Merge the evaluator rows with the assessed rows, escalate, mark each evaluator row introduced
   or left in place, group changes, and build the improvement map per `verdicts.md`. A row the
   plan review of this ticket set to `ACCEPTED` keeps that verdict while its target and rule
   still match; it is not raised again.

## Record

1. Write the ledger through its subcommands, in this order: `arch ledger add-run --mode
   change-review` with the merged rows, the skipped workflows, the evaluated targets, and the
   targets `arch diff` reports removed; `arch ledger accept` once per finding the user accepts;
   `arch ledger map`. Then append new rows to `change-history.md` and write `slices/`.
2. Apply model edits through the subcommands only for changes no open finding disputes; run
   `arch readme-summary`; the implementer commits `docs/architecture/` with the code.
3. Candidate rows implicated in an open finding are not written. List them in the ledger under
   "Pending record updates", keyed to the finding ID. The run that changes the verdict writes
   them: when the finding becomes `RESOLVED` (a later round or run finds the code fixed) or
   `ACCEPTED` (per "Accepting a finding" in `verdicts.md`; a one-off acceptance is recorded in
   the ledger only, a standing rule as one generalized row in `decisions.md`).
4. Never write a row that describes a violation as ordinary structure: a new edge from policy
   to detail, a port declared on the wrong side, a cycle. The record holds the architecture the
   project stands behind; the ledger holds what is disputed.

## Return

Reply with the return contract from `verdicts.md`, naming the record files this run edited so
the implementer commits them with the code, and the count of pending record updates waiting on
open findings.
