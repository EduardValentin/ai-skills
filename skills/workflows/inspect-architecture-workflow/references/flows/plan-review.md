# Plan review

The procedure for reviewing an implementation plan or spec before it is approved and before any
code exists: a reviewer turns the plan into proposed facts, the command checks them against the
current code, the same reviewer judges the rest, and the plan is fixed for a bounded number of
rounds. Follow it step by step when the skill is invoked with `plan-review` or a calling workflow
names this flow. Nothing in it writes the model or `current.md`.

Inputs: the plan file's path from the project root, written `<plan>` below, and any upcoming
changes the plan states. Run every command from the inspected project's root. `arch` stands for
`node <skill>/scripts/arch.mjs`, where `<skill>` is the folder that holds this skill's `SKILL.md`,
and paths that start with `references` are inside that folder. Working files live under
`.architecture/work/`, the only place inside the project the command accepts them.

## Steps

1. Run `arch applicable --all --json` and read its `model` field.
2. If it is `false`, return `Verdict: OK` with the line
   "no architecture model; run a baseline audit to enable the full review", and stop with `OK`.
3. Run `arch model explain-thresholds --json` and note the `project` value of `planFixRounds`:
   how many times the plan may be revised in this review. No revision has been made yet.
4. Dispatch one `architecture-reviewer` to write the proposal, with the flow `plan-review`, the
   plan path, `references/adapter-contract.md` for the module and edge shapes, and
   `references/classification.md`. It may run `arch model explain <path>` to see how the model
   classifies a path. It returns one JSON object; write it to `.architecture/work/proposal.json`:

   ```json
   { "version": 1,
     "modules": [ { "path": "src/billing/invoice-use-case.ts" } ],
     "edges": [ { "from": "src/billing/invoice-use-case.ts", "to": "src/billing/invoices.ts", "kind": "import" } ],
     "removedModules": [], "removedEdges": [ { "from": "src/billing/a.ts", "to": "src/billing/b.ts" } ],
     "classify": [ { "path": "src/billing/invoice-use-case.ts", "kind": "use-case", "component": "billing" } ],
     "unknown": [ { "task": "Task 2: Invoice report", "fact": "which component the report reads from" } ] }
   ```

   `classify` is only for a new module no model pattern covers. `unknown` names each fact a task
   leaves open; the command turns it into a clarification request.
5. Run `arch check --proposal .architecture/work/proposal.json --out .architecture/work/check.json`.
   Exit 1 means the plan introduces a breach of an enforced rule; continue either way. If it
   refuses the proposal, send its message to the reviewer and write the corrected object.
6. Run `arch applicable --proposal .architecture/work/proposal.json --full --json`. It lists in
   `groups` the rule groups the plan's modules, edges, and components bring into scope, and in
   `judgments` their ids. If `groups` is empty, go to step 9 and leave out `--judged`.
7. Send the same reviewer the judging packet: the check output `.architecture/work/check.json`,
   `references/rules/vocabulary.md`, `references/rules/cross-cutting.md`, the rule-group file of
   each name in `groups` (for example `references/rules/dependency-direction.md`) with its ids from
   `judgments`, and the upcoming changes the plan states. It returns `{ "findings": [...],
   "questions": [...] }`. Each finding is `{ "judgment": "<id>", "target": "<unit, edge, port, or
   component>", "consequence": "<one sentence>", "correction": "<smallest change to the plan>",
   "evidence": ["<plan>#<heading>"], "origin": "introduced" }` (`"inherited"` for a defect the plan
   leaves in place), plus `"wider": true` only outside the plan's scope and `"liftedBy"` only for a
   confirmed upcoming change. It never sets `rules`, `defect`, or `severity`.
8. Put each question to the user, or return the questions to the calling workflow to ask. Give
   every confirmed answer to the same reviewer; it sets `liftedBy` to that exact text where the
   answer makes a finding heavier. Drop answered questions; an unanswered one changes nothing.
   Write the object to `.architecture/work/judged.json`. This flow never writes the model; tell the
   owner that the `add-upcoming` model edit, made after this review, remembers an answer for later.
9. Run `arch findings add --flow plan-review --plan <plan> --proposal .architecture/work/proposal.json --check .architecture/work/check.json --judged .architecture/work/judged.json`.
   Add `--upcoming "<text>"` once per confirmed answer, with the same text as `liftedBy`. It prints
   the result. If it refuses judged findings, send the listed problems to the reviewer and run this
   step again; if it says the check is stale or made from another proposal, run step 5 again,
   then this step.
10. Collect the clarification requests: the `incomplete` entries of `.architecture/work/check.json`
    with `"clarification": true`, each a `task` and the `fact` it does not state. They are kept
    apart from the findings and mean the plan is not concrete enough to review fully.
11. If the verdict is `SHOULD_CHANGE` or `INCOMPLETE` and fewer revisions than `planFixRounds`
    have been made, the plan's author revises the plan from the corrections and clarifications;
    count the revision and go back to step 4. Once `planFixRounds` revisions have been made, stop
    and hand the remaining findings and clarifications to the user instead of another round.
12. Accepting a finding is a model edit the user chooses after this flow (`add-exception`,
    `set-rule` with `advisory` or `off`, or `set-threshold`); this flow only reports the finding.
13. Return the printed result, the clarification requests, and the number of revisions. `OK`
    passes a gate. `SHOULD_CHANGE` and `INCOMPLETE` block it.

If a command fails, it exits 2 and says what was wrong and what to do next; for more, read that subcommand's page, such as `references/commands/check.md`.
