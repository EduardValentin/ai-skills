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

1. When `docs/architecture/model` is missing, create it from the templates and write
   `components.json` from the repository's package and folder layout (one component per
   workspace package and per top-level app folder), with `tooling.roots` listing one entry per
   source root in that layout and `tooling.tsConfig` naming the TypeScript config that declares
   the project's path aliases when it uses any; write `rules.json` from the project's
   conventions document when one exists. When the project runs a code formatter over JSON (for
   example a `prettier` config or a `format:check` script), add `docs/architecture/model` to its
   ignore file so the canonical model files are not reformatted.
2. Run `arch graph`; fix every hard model problem it reports. When it stops with the
   unsupported-language escalation or a missing-tooling error, return the escalation to the
   caller instead of mapping by hand; never write an extractor.
3. Run `arch uncovered`; when it lists modules, dispatch mapping slices per `slicing.md`, apply
   their proposals, and rerun until empty.
4. Run `arch model validate`.

## Evaluate

1. Run `arch assess` and write its output to `.architecture/slices/packet/00-assess.md`.
2. Dispatch one `architecture-evaluator` per workflow W1 to W8, in parallel, each with the
   evaluation packet from `slicing.md`; each receives the query output its `Reads:` line names
   and the assess output file as decided rows. Evaluators judge rows and open no project file.
3. Merge per `slicing.md`, the assessed rows included, into one row file; `arch ledger add-run`
   in Record drops duplicate target-and-rule pairs, keeps existing IDs, and settles each previous
   `SHOULD_CHANGE` row.
4. Apply severity escalation, group changes, and build the improvement map per `verdicts.md`.

## Record

1. Write `decisions.md` from its template when missing; run `arch readme-summary`; commit the
   model, decisions, and README with the audit.
2. Write the ledger through its subcommands, in this order: `arch ledger add-run --mode audit`
   with the merged rows; `arch ledger accept` once per finding the user accepts; `arch ledger
   map`. Then write `change-history.md` and `slices/`.

## Return

Reply with the return contract from `verdicts.md`. When the audit only created a baseline for a
review, state that the record must be committed with the PR, then continue with the review's
procedure.
