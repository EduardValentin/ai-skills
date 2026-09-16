# Audit

Maps a whole repository or a named area, evaluates every target, and writes the committed
record and the ledger. The first audit creates the baseline; a later audit refreshes it.

## Preflight

1. Read the project's agent instructions for artifact paths and named boundaries.
2. Fix the scope: the whole repository or the named area.
3. Confirm the ledger root is ignored; if not, add it to the local exclude file. Load the
   existing ledger and record, if any, so IDs can be reused; a missing ledger is never a blocker.
4. Build the list of named upcoming changes, `UC-1`, `UC-2`, and so on, each with its source:
   the brief or ticket handed to you, the deferred decisions and open questions in an existing
   `decisions.md`, and any roadmap items the caller supplied. An empty list is valid.

## Map

1. Slice the scope by component, or by top-level source folder when the code declares no
   enforced components. A scope of fifteen source files or fewer is one slice.
2. Dispatch, in parallel: one `architecture-code-auditor` per slice with the mapping packet, and
   one history slice for the whole scope with the history packet covering the full window. Packets
   are defined in `slicing.md`; classification rules in `mapping.md`.
3. Merge: resolve edges whose target lies in another slice; reuse IDs where path and symbol match
   the existing record, assign new ones otherwise, mark vanished rows `removed`; attach history
   rows to units by path; decide component boundaries from the slices' published-surface and
   enforcement observations; compute metrics per `metrics.md` when there are more than five
   components.

## Evaluate

1. Dispatch one `architecture-evaluator` per workflow W1 to W8, in parallel, each with the
   evaluation packet: the catalog preface and vocabulary, its rule section and decision table,
   the full inventory sections it reads, `decisions.md` when one exists, and the upcoming
   changes.
2. Merge per `slicing.md`: drop duplicate target-and-rule pairs, match rows to existing ledger
   IDs, and settle each previous `SHOULD_CHANGE` row as resolved, still open, or removed.
3. Apply severity escalation, group changes, and build the improvement map per `verdicts.md`.

## Record

1. Write every committed file from the templates (`assets/docs/README.md` and its five
   siblings), refreshing the README's shape paragraphs and header.
2. Write `ledger.md` (new run in the run log), `change-history.md`, and `slices/`.

## Return

Reply with the return contract from `verdicts.md`. When this audit was run only to create a
baseline for a review, state that the record must be committed with the PR, then continue with
the review's procedure.
