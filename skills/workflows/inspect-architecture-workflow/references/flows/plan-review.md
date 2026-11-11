# Plan review

The procedure for reviewing an implementation plan or spec before it is approved and before any
code exists: a reviewer turns the plan into a proposal, the command checks it against the current
code, the same reviewer judges the rest, and the plan is revised a bounded number of times. Follow
it step by step when the skill is invoked with `plan-review` or a calling workflow names this flow.
Nothing in it writes the model or `current.md`.

Inputs: the plan file's path from the project root, written `<plan>` below, and the upcoming
changes the plan states. Run every command from the inspected project's root. `arch` stands for
`node <skill>/scripts/arch.mjs`, where `<skill>` is the folder that holds this skill's `SKILL.md`,
and paths that start with `references` are inside that folder. Working files live under
`.architecture/work/`. Terms are defined in `references/rules/vocabulary.md`.

## Steps

1. Run `arch model status --json`.
2. If `model` is `false`, return `Verdict: OK` with the line
   "no architecture model; run a baseline audit to enable the full review", and stop with `OK`.
3. Run `arch model explain-thresholds --json` and note the `project` value of `planFixRounds`, the
   number of revisions this review allows. No revision has been made yet.
4. Dispatch one `architecture-reviewer` to write the proposal, with the flow `plan-review`, the
   plan path, `references/adapter-contract.md` for the module and edge shapes, and
   `references/classification.md`. It may run `arch model explain <path>` to see how the model
   classifies a path. Write the proposal it returns to `.architecture/work/proposal.json`:

   ```json
   { "version": 1,
     "modules": [ { "path": "src/billing/invoice-use-case.ts" } ],
     "edges": [ { "from": "src/billing/invoice-use-case.ts", "to": "src/billing/invoices.ts", "kind": "import" } ],
     "removedModules": [], "removedEdges": [ { "from": "src/billing/a.ts", "to": "src/billing/b.ts" } ],
     "classify": [ { "path": "src/billing/invoice-use-case.ts", "kind": "use-case", "component": "billing" } ],
     "unknown": [ { "task": "Task 2: Invoice report", "fact": "which component the report reads from" } ] }
   ```

   `classify` is only for a new module no model pattern covers. Each `unknown` entry becomes a
   clarification request.
5. Run `arch check --proposal .architecture/work/proposal.json --out .architecture/work/check.json`.
   Exit 0 means the plan introduces no breach of an enforced rule and exit 1 means it does;
   continue either way. If it refuses the proposal, give its message to the reviewer, write the
   corrected proposal, and run this step again.
6. Run `arch applicable --proposal .architecture/work/proposal.json --full --json`. If `groups` is
   empty, go to step 9 and leave out `--judged`.
7. Ask the same reviewer to judge, with the check output `.architecture/work/check.json`,
   `references/rules/vocabulary.md`, `references/rules/cross-cutting.md`, the file of every other
   rule group in `groups` (for example `references/rules/dependency-direction.md`) with its ids
   from `judgments`, and the upcoming changes the plan states, word for word. A classification
   dispute goes once to `architecture-classifier`; tell the user its proposed `arch model`
   commands for after this review, and the same reviewer continues. It returns judged findings:

   ```json
   { "findings": [ { "judgment": "<judgment id>", "target": "<unit, edge, port, or component>",
       "consequence": "<one sentence>", "correction": "<smallest change to the plan>",
       "evidence": ["<plan>#<heading>"], "origin": "introduced", "liftedBy": "<upcoming change>" } ],
     "questions": ["<question for the user>"] }
   ```

   A judgment that applies to the plan as a whole takes the target `plan`. `origin` is `inherited`
   for a defect the plan leaves in place. A target outside the plan adds `"wider": true`, as does a
   finding whose correction cannot be made smaller under R8 (Constraints need a named reason).
   `liftedBy` is optional. `rules`, `defect`, and `severity` are never set.
8. Put each question to the user, or return the questions to the calling workflow to ask. Give each
   confirmed answer to the same reviewer, which sets `liftedBy` to that exact text where the answer
   makes a finding heavier. Drop answered questions; an unanswered one changes nothing. This flow
   never writes the model: tell the user that the `add-upcoming` model edit remembers an answer.
   Write the judged findings to `.architecture/work/judged.json`.
9. Run `arch findings add --flow plan-review --plan <plan> --proposal .architecture/work/proposal.json --check .architecture/work/check.json --judged .architecture/work/judged.json --upcoming "<upcoming change>"`.
   Give `--upcoming` once for every upcoming change the plan states and every answer the user
   confirmed. A `liftedBy` that names neither one of those nor a change recorded with
   `add-upcoming` is refused. It prints the result and its verdict. If it refuses judged findings,
   send the listed problems to the reviewer and run this step again; if it says the check is stale
   or made from another proposal, run step 5 again, then this step.
10. Collect the clarification requests: the `incomplete` entries of `.architecture/work/check.json`
    that have `"clarification": true`, each a `task` and the `fact` it leaves open. Report them
    apart from the findings: the plan is not concrete enough to review fully.
11. If the verdict is `SHOULD_CHANGE` or `INCOMPLETE` and fewer than `planFixRounds` revisions have
    been made, the plan's author revises the plan; count the revision and run steps 4 to 6 again,
    since rule groups may enter or leave scope. The same reviewer judges again against the new
    `judgments`, not only its earlier findings, and its fresh judged findings replace
    `.architecture/work/judged.json` before step 9. Never pass judged findings written before the
    revision. After `planFixRounds` revisions, hand the remaining findings and clarification
    requests to the user instead of another round.
12. Accepting a finding is a model edit the user makes after this flow: an exception
    (`add-exception`, with `'*'` as its `to` end for a unit, port, or component), a rule status
    (`set-rule` with `advisory` or `off`, the only way to accept a cycle), or a threshold
    (`set-threshold`). This flow only reports the finding.
13. Return the printed result, the clarification requests, and the number of revisions. `OK`
    passes a gate; `SHOULD_CHANGE` and `INCOMPLETE` block it.

If a command fails, it exits 2 and says what was wrong and what to do next; for more, read that subcommand's page, such as `references/commands/check.md`.
