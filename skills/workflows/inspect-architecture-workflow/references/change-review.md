# Change review

Reviews a diff against the committed baseline. Maps only the diff's neighborhood, evaluates
only what changed, writes the ledger, and updates the committed record for the rows the diff
changed, but only where the review found nothing wrong, so the record never records a violation
as accepted structure.

## Preflight

1. Read the project's agent instructions for artifact paths and named boundaries.
2. Fix the scope: the diff or changed-file list, frozen.
3. Check the baseline: the committed record must cover the diff's paths. If it does not, run
   `audit.md` on the affected scope first and note in the return that the record was created.
4. Confirm the ledger root is ignored. Load the ledger so finding IDs can be matched; when none
   exists, start one. A missing ledger is never a blocker.
5. Build the upcoming-changes list from the ticket, the baseline's `decisions.md`, and anything
   the caller supplied.

## Map

1. Slices: the units the diff touches, every unit they import or that imports them, and every
   edge the diff adds, removes, or redirects. Group by component; a small diff is one slice.
2. Dispatch, in parallel: one `architecture-code-auditor` per slice, and one history slice
   limited to the diff's files, told which commits the ledger already holds rows for so it
   returns only the missing ones.
3. Merge as in the audit, marking every row the diff added, removed, or altered as `changed`.
   Recompute metrics only for touched components; mark the rest carried over.
4. Hold the additions, removals, and alterations as candidate record updates until evaluation
   decides which may be written.

## Evaluate

1. For each workflow W1 to W8, check whether a `changed` row falls in the sections it reads.
   Those workflows are applicable; carry the others' previous rows forward and name them in the
   run log.
2. Dispatch one `architecture-evaluator` that runs every applicable workflow in order, with the
   packet from `slicing.md`: the paths of the preface and of each applicable workflow and rule
   file, the changed rows, their direct neighbors, and a component-level summary of the graph
   (the full component graph when W6 is applicable). It judges only changed targets and the
   edges touching them, from the rows and never from code, phrasing findings as "the diff
   introduces" or "the diff leaves in place".
3. Merge, escalate, group changes, and build the improvement map per `verdicts.md`. A row the
   plan review of this ticket set to `ACCEPTED` keeps that verdict while its target and rule
   still match; it is not raised again.

## Record

1. Append the run to `ledger.md` and new rows to `change-history.md`; write `slices/`.
2. Update `docs/architecture/` directly, in the same branch as the diff, but only for candidate
   rows whose target has no open `SHOULD_CHANGE` finding in this run. Refresh the metrics rows of
   touched components and the README header.
3. Candidate rows implicated in an open finding are not written to the record. List them in the
   ledger under "Pending record updates", keyed to the finding ID. They are written when the
   finding becomes `RESOLVED` (a later round or run finds the code fixed) or `ACCEPTED` (per
   "Accepting a finding" in `verdicts.md`; a one-off acceptance is recorded in the ledger only, a
   standing rule as one generalized row in `decisions.md`); the run that changes the verdict
   writes the rows.
4. Never write a row that would describe a violation as ordinary structure: a new edge from
   policy to detail, a port declared on the wrong side, a cycle. The record describes the
   architecture the project stands behind; the ledger holds what is being disputed.

## Return

Reply with the return contract from `verdicts.md`. Name the record files this run edited so
the implementer commits them with the code, and the count of pending record updates waiting on
open findings.
