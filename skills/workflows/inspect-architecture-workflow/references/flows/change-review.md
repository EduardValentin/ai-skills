# Change review

The procedure for reviewing a diff against a base commit: the command decides every condition it
can, at most one reviewer judges the rest, and the command stores the findings and prints the
result. Follow it step by step when the skill is invoked with `change-review` or a calling workflow
names this flow.

Inputs: the base ref the diff is compared with, written `<ref>` below, and the upcoming changes the
ticket or plan states. Run every command from the inspected project's root. `arch` stands for
`node <skill>/scripts/arch.mjs`, where `<skill>` is the folder that holds this skill's `SKILL.md`,
and paths that start with `references` are inside that folder. Working files live under
`.architecture/work/`. Terms are defined in `references/rules/vocabulary.md`.

## Steps

1. Run `arch model status --json`.
2. If `model` is `false`, return `Verdict: OK` with the line
   "no architecture model; run a baseline audit to enable the full review", and stop with `OK`.
3. Run `arch applicable --base <ref> --json`.
4. If `uncovered` lists uncovered modules, dispatch `architecture-classifier` with them,
   `references/classification.md`, and `references/rules/vocabulary.md`. It returns `arch model`
   commands, one per line, each with a one-sentence reason. Run them, then step 3 again, once: a
   module still uncovered after that is reported incomplete, never as passing.
5. Run `arch check --base <ref> --out .architecture/work/check.json`. Exit 0 means no introduced
   breach of an enforced rule and exit 1 means at least one; continue either way.
6. If `review` is `false` or `groups` is empty, no reviewer is needed: go to step 10 and leave out
   `--judged`. `notReviewed` counts the judgment conditions a contained change leaves out; if the
   user wants them judged, run step 3 again with `--full` added.
7. Dispatch one `architecture-reviewer` with this packet, which names each file once:
   - the flow `change-review`, the base ref, and the scope: the diff against `<ref>`;
   - the check output `.architecture/work/check.json`, whose findings it does not repeat;
   - `references/rules/vocabulary.md`, `references/rules/cross-cutting.md`, and the file of every
     other rule group in `groups` (for example `references/rules/dependency-direction.md`), with
     the judgment ids `judgments` lists for each;
   - the touched units and their classification, as `arch query touched --base <ref> --with-neighbors` prints them;
   - the upcoming changes the ticket or plan states, word for word.

   It returns its judged findings in this shape, and apart from them any classification disputes,
   each a touched path and what its code shows that the model contradicts:

   ```json
   { "findings": [ { "judgment": "<judgment id>", "target": "<unit, edge, port, or component>",
       "consequence": "<one sentence>", "correction": "<smallest change inside the diff>",
       "evidence": ["<path>:<line>"], "origin": "introduced", "liftedBy": "<upcoming change>" } ],
     "questions": ["<question for the user>"] }
   ```

   `origin` is `inherited` for a defect the diff leaves in place. A target outside the diff adds
   `"wider": true`, as does a finding whose correction cannot be made smaller under R8 (Constraints
   need a named reason). `liftedBy` is optional. `rules`, `defect`, and `severity` are never set.
8. If there are disputes, dispatch `architecture-classifier` once with the disputed paths and the
   reviewer's reasons, run the commands it returns, then follow step 12; no second reviewer.
9. Put each question to the user, or return the questions to the calling workflow to ask. Give each
   confirmed answer to the same reviewer, which sets `liftedBy` to that exact text where the answer
   makes a finding heavier. Drop answered questions; an unanswered one changes nothing and stays.
   If the user wants an answer remembered, run `arch model add-upcoming "<text>"`. Write the
   judged findings to `.architecture/work/judged.json`.
10. Run `arch findings add --flow change-review --base <ref> --check .architecture/work/check.json --judged .architecture/work/judged.json --upcoming "<upcoming change>"`.
    Give `--upcoming` once for every upcoming change the packet stated and every answer the user
    confirmed. A `liftedBy` that names neither one of those nor a change recorded with
    `add-upcoming` is refused. It prints the result and its verdict.
    - If it refuses judged findings, it names the file and the finding of each problem: send them
      to the reviewer, write its corrected judged findings, and run this step again.
    - If it says the check is stale or made with another base, run step 5 again, then this step.
11. If the user accepts a finding instead of fixing it, run the edit the user chooses:
    - an edge other than a cycle: `arch model add-exception <from> <to> rule=<R> reason="<text>"`;
    - a unit, a port (`<path>#<Symbol>`), or a component, from the check or the reviewer:
      `arch model add-exception <target> '*' rule=<R> reason="<text>"`;
    - a whole rule, for the project or one component, and the only way to accept a cycle or an
      incomplete condition: `arch model set-rule <R>[@<component>] off reason="<text>"`, or
      `advisory` in place of `off`;
    - a number: `arch model set-threshold <knob> <value>`.

    Then run step 5 and step 10 again with the same judged findings file. The accepted finding is
    counted under `Dropped:` (an exception covers it, or its rule is off) or under `Advisory:`.
12. After a fix to the code or to the classification, run steps 3 and 5 again: rule groups may
    enter or leave scope. If `groups` is now empty, run step 10 without `--judged`. Otherwise ask
    the same reviewer to judge again against the new `judgments`, not only its earlier findings,
    write its fresh judged findings over `.architecture/work/judged.json`, and run step 10. Never
    pass judged findings written before the fix.
13. For a judged finding the fix resolved, offer a check that catches it next time:
    `arch model add-forbidden-edge <from> <to> reason="<text>"` for an edge, or
    `arch model set-threshold <knob> <value>` for a number. Run it only if the user agrees.
14. Return the printed result. `OK` passes a gate; `SHOULD_CHANGE` and `INCOMPLETE` block it until
    the findings are fixed or accepted.

If a command fails, it exits 2 and says what was wrong and what to do next; for more, read that subcommand's page, such as `references/commands/check.md`.
