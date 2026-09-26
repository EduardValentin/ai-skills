# Audit

Maps a whole repository or a named area, evaluates every target, and writes the committed
record and the ledger. The first audit creates the baseline; a later one refreshes it.

## Preflight

1. Read the project's agent instructions for artifact paths and named boundaries.
2. Fix the scope: the whole repository or the named area.
3. Confirm the ledger root is ignored; if not, add it to the local exclude file. Load any
   existing ledger and record to reuse IDs; a missing ledger is never a blocker.
4. List the named upcoming changes, `UC-1`, `UC-2`, and so on, each with its source: the brief
   or ticket, the deferred decisions and open questions in an existing `decisions.md`, and
   roadmap items the caller supplied. An empty list is valid.

## Map

1. Slice by component, or by top-level source folder when the code declares no enforced
   components. A scope of fifteen source files or fewer is one slice.
2. Dispatch in parallel one `architecture-code-auditor` per slice with the mapping packet and
   one history slice over the whole scope and the full window. Packets are defined in
   `slicing.md`, classification rules in `mapping.md`.
3. Merge: resolve edges whose target lies in another slice; reuse IDs where path and symbol match
   the existing record or a slice's `moved from` tag, assign new ones otherwise, delete vanished
   rows; attach history
   rows to units by path; decide component boundaries from the slices' published-surface and
   enforcement observations; compute metrics per `metrics.md` when there are more than five
   components.

## Evaluate

1. Dispatch one `architecture-evaluator` per workflow W1 to W8, in parallel, each with the
   evaluation packet from `slicing.md` over the full inventory. Evaluators judge rows and open
   no project file.
2. Merge per `slicing.md`: drop duplicate target-and-rule pairs, match rows to existing ledger
   IDs, and settle each previous `SHOULD_CHANGE` row as resolved, still open, or removed.
3. Apply severity escalation, group changes, and build the improvement map per `verdicts.md`.

## Record

1. Write every committed file from the templates (`assets/docs/README.md` and its five
   siblings), refreshing the README's shape paragraphs and setting both parts of every header
   (last audit and last update) to this run.
2. Write `ledger.md` (new run in the run log), `change-history.md`, and `slices/`.

## Return

Reply with the return contract from `verdicts.md`. When the audit only created a baseline for a
review, state that the record must be committed with the PR, then continue with the review's
procedure.
