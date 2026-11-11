# Plan review

The procedure for reviewing an implementation plan or spec before it is approved and before any
code exists: a reviewer turns the plan into a proposal, the command checks it against the current
code, the same reviewer judges the rest, and the plan is revised a bounded number of times. Follow
it step by step when the skill is invoked with `plan-review` or a calling workflow names this flow.
Nothing in it writes the model or `current.md`.

Inputs: the plan file's path from the project root, written `<plan>` below, and the upcoming
changes the plan states. Run every command from the project root. The skill folder holds
`SKILL.md`, two levels above this file; `arch` stands for `node <skill folder>/scripts/arch.mjs`,
and paths that start with `references` are inside it. Every packet opens with the absolute paths of
the project root and the skill folder. Working files live under `.architecture/work/`. Terms are
defined in `references/rules/vocabulary.md`.

## Steps

1. Run `arch model status --json`; its `path` is the model path.
2. If `model` is `false`, stop here: run no other command, dispatch no agent, give no verdict, and
   return to the caller only this message: "There is no architecture model for this project. Run the
   baseline flow first (`inspect-architecture-workflow` with the flow name `baseline`), then run this review again."
3. Run `arch model explain-thresholds --json` and note the `project` value of `planFixRounds`, the
   number of revisions this review allows. No revision has been made yet: the count starts at 0.
4. Dispatch one `architecture-reviewer` to write the proposal, with the flow `plan-review`, the
   plan path, `references/adapter-contract.md` for the module and edge shapes, and
   `references/classification.md`. It may run `arch model explain <path>` to see how the model
   classifies a path. It returns one JSON object, which you write to `.architecture/work/proposal.json`:

   ```json
   { "version": 1,
     "modules": [ { "path": "src/billing/invoice-use-case" } ],
     "edges": [ { "from": "src/billing/invoice-use-case", "to": "src/billing/invoices", "kind": "import" } ],
     "removedModules": [], "removedEdges": [ { "from": "src/billing/a", "to": "src/billing/b" } ],
     "classify": [ { "path": "src/billing/invoice-use-case", "kind": "use-case", "component": "billing" } ],
     "unknown": [ { "task": "Task 2: Invoice report", "fact": "which component the report reads from" } ] }
   ```

   `classify` is only for a new module no model pattern covers. Each `unknown` entry becomes a clarification request.
5. Run `arch check --proposal .architecture/work/proposal.json --out .architecture/work/check.json`.
   It exits 1 only when the plan introduces a blocker or major finding of an enforced rule;
   continue either way. If it refuses the proposal, give its message to the reviewer, write the
   corrected proposal, and run this step again.
6. Run `arch applicable --proposal .architecture/work/proposal.json --out .architecture/work/applicable.json`.
   If `inScope` in that file is 0, no judgment condition applies: dispatch nobody; run step 9 without `--judged`.
7. Ask the same reviewer to judge, with `.architecture/work/check.json`,
   `references/rules/vocabulary.md`, `references/rules/cross-cutting.md`, the file of every other
   group in `groups`, such as `references/rules/dependency-direction.md`, each with its `judgments`
   entries as printed (`id`, `targets`, `condition`), and the upcoming changes the plan states, word
   for word. It returns one JSON object, which you write to `.architecture/work/judged.json`:

   ```json
   { "findings": [ { "judgment": "<judgment id>", "target": "<unit, edge, port, or component>",
       "consequence": "<one sentence>", "correction": "<smallest change to the plan>",
       "evidence": ["<plan>#<heading>"], "origin": "introduced", "liftedBy": "<upcoming change>" } ],
     "questions": ["<question for the user>"],
     "disputes": [ { "path": "<unit path>", "reason": "<what its code shows that the model contradicts>" } ] }
   ```

   A judgment that applies to the plan as a whole takes the target `plan`. `origin` is `inherited`
   for a defect the plan leaves in place. A target outside the plan adds `"wider": true`, as does a
   finding no smaller correction can fix under R8 (Constraints need a named reason). If `disputes`
   is not empty on the first judged pass, send them to `architecture-classifier` with the model path
   and `references/classification.md`, and only report its commands to the user with the result,
   since this flow never edits the model; later disputes go to the user as open questions.
8. Put each question to the user, or return the questions to the calling workflow to ask. Send the
   questions with the answers to the same reviewer; it returns a fresh judged file, written over
   `judged.json`, in which each answered question became a finding, a `liftedBy` on a finding, or
   nothing, and unanswered ones remain. Never edit a judged file by hand. This flow never writes
   the model: tell the user that the `add-upcoming` model edit remembers an answer.
9. Run `arch findings add --flow plan-review --plan <plan> --proposal .architecture/work/proposal.json --check .architecture/work/check.json --applicable .architecture/work/applicable.json --judged .architecture/work/judged.json --upcoming "<upcoming change>"`.
   Give `--upcoming` once for every upcoming change the plan states and every confirmed answer. It
   prints the result and its verdict. If it refuses judged findings, send the listed problems to
   the reviewer, write its fresh judged file, and run this step again; if it says the check or the
   applicable file is stale or made from another proposal, run steps 5 and 6 again, then this step.
10. The printed result lists each clarification request under `Incomplete:` on its own
    `- clarification: <task>: <reason>` line, naming the fact the task leaves open; report them apart.
11. If the verdict is `SHOULD_CHANGE` or `INCOMPLETE` and fewer than `planFixRounds` revisions have
    been made, the plan's author revises it; count the revision and run steps 4 to 6 again. The same
    reviewer judges again against the new `judgments`, its fresh file replaces `judged.json`, and
    steps 8 and 9 follow; never pass judged findings from before the revision. After `planFixRounds`
    revisions, hand the remaining findings and clarification requests to the user instead.
12. This flow only reports findings. The user accepts one after it with a model edit: an exception
    (`add-exception`, `'*'` as the `to` end for a unit, port, or component), a rule status (`set-rule`
    `advisory` or `off`, the only way to accept a cycle), or a threshold, after which a judged finding
    whose condition names that knob needs the same reviewer to judge it again.
13. Return the printed result, the clarification requests, the open questions, and the revision
    count; show `Inherited findings` and `Wider observations` to the user as non-blocking. The
    verdict line is what the caller returns: `OK` passes a gate; `SHOULD_CHANGE` and `INCOMPLETE` block it.

If a command fails, it exits 2 and says what was wrong and what to do next; for more, read that subcommand's page, such as `references/commands/check.md`.
