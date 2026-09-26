# Change review

Reviews a diff against the committed baseline. Maps only the diff's neighborhood, evaluates
only what changed, writes the ledger, and updates the committed record for the rows the diff
changed, but only where the review found nothing wrong: the record never records a violation
as accepted structure.

## Preflight

1. Read the project's agent instructions for artifact paths and named boundaries.
2. Fix the scope: the diff or changed-file list, frozen.
3. Check the committed record covers the diff's paths; if not, run `audit.md` on the affected
   scope first and note in the return that the record was created.
4. Confirm the ledger root is ignored. Load the ledger to match finding IDs; when none exists,
   start one. A missing ledger is never a blocker.
5. Build the upcoming-changes list from the ticket, the baseline's `decisions.md`, and anything
   the caller supplied.

## Map

1. Slices: the units the diff touches, every unit they import or that imports them, and every
   edge the diff adds, removes, or redirects. Group by component; a small diff is one slice.
2. Dispatch in parallel one `architecture-code-auditor` per slice and one history slice limited
   to the diff's files, told which commits the ledger already holds rows for so it returns only
   the missing ones.
3. Merge as in the audit, marking every row the diff added, removed, or altered `changed`.
   Recompute metrics only for touched components; mark the rest carried over.
4. Hold the additions, removals, and alterations as candidate record updates until evaluation
   decides which may be written.

## Evaluate

1. A workflow W1 to W8 is applicable when a `changed` row falls in a section it reads. Carry the
   others' previous rows forward and name them in the run log.
2. Dispatch one `architecture-evaluator` that runs every applicable workflow in order, with the
   evaluation packet from `slicing.md` (the full component graph when W6 is applicable). It
   judges only changed targets and the edges touching them, from rows and never from code, and
   phrases findings as "the diff introduces" or "the diff leaves in place".
3. Merge, escalate, group changes, and build the improvement map per `verdicts.md`. A row the
   plan review of this ticket set to `ACCEPTED` keeps that verdict while its target and rule
   still match; it is not raised again.

## Record

1. Append the run to `ledger.md` and new rows to `change-history.md`; write `slices/`.
2. Update `docs/architecture/` directly, in the diff's branch, only for candidate rows whose
   target has no open `SHOULD_CHANGE` finding in this run. Write each row as the current fact:
   a moved unit gets its new path under its old ID, a deleted one loses its row, and no cell
   gains a note about the ticket, plan step, or commit that caused the change; the ledger's
   change history holds that. Refresh the metrics rows of touched
   components. In every record file written, replace the header's last-update part (date,
   commit, mode) in place and leave the last-audit part; never add a header line.
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
