# Change review

The procedure for reviewing a diff against a base commit: the command decides every condition it
can, one reviewer always judges the rest, and the command stores and prints the findings. Follow
it step by step when the skill is invoked with `change-review` or a calling workflow names this flow.

Inputs: the base ref the diff is compared with, written `<ref>` below, and the upcoming changes the
ticket or plan states. Run every command from the project root. The skill folder holds `SKILL.md`,
two levels above this file; `arch` stands for `node <skill folder>/scripts/arch.mjs`, and paths that
start with `references` are inside it. Every packet opens with the absolute paths of the project
root and the skill folder. Working files live under `.architecture/work/`. Terms are defined in
`references/rules/vocabulary.md`.

## Steps

1. Run `arch model status --json`; its `path` is the model path.
2. If `model` is `false`, return `Verdict: OK` with the line
   "no architecture model; run a baseline audit to enable the full review", and stop with `OK`.
3. Run `arch applicable --base <ref> --out .architecture/work/applicable.json` and read that file.
4. If `uncovered` lists modules, dispatch `architecture-classifier` with them,
   `references/classification.md`, and `references/rules/vocabulary.md`. It returns `arch model`
   commands with a reason each, and open questions. Run the commands, then step 3 again, once: a
   module still uncovered after that is reported incomplete, never as passing.
5. Run `arch check --base <ref> --out .architecture/work/check.json`. It exits 1 only when the change
   introduces a blocker or major finding of an enforced rule; continue either way.
6. If `units` and `uncovered` in `applicable.json` are both empty, the change touches no unit and
   there is no code to review: dispatch nobody, run step 10 without `--judged`, and return its
   result with the line "no unit touched; no code to review". Otherwise the reviewer runs, however
   small the change.
7. Dispatch one `architecture-reviewer`, once, with this packet:
   - the flow `change-review`, the base ref, and the scope: the diff against `<ref>`;
   - the check output `.architecture/work/check.json`, whose findings it does not repeat;
   - `references/rules/vocabulary.md`, `references/rules/cross-cutting.md`, and the file of every
     other group in `groups`, such as `references/rules/dependency-direction.md`, each with its
     `judgments` entries as printed (`id`, `targets`, `condition`);
   - the touched units and their classification, as `arch query touched --base <ref> --with-neighbors` prints them;
   - the upcoming changes the ticket or plan states, word for word.

   It returns one JSON object, which you write to `.architecture/work/judged.json`:

   ```json
   { "findings": [ { "judgment": "<judgment id>", "target": "<unit, edge, port, or component>",
       "consequence": "<one sentence>", "correction": "<smallest change inside the diff>",
       "evidence": ["<path>:<line>"], "origin": "introduced", "liftedBy": "<upcoming change>" } ],
     "questions": ["<question for the user>"],
     "disputes": [ { "path": "<unit path>", "reason": "<what its code shows that the model contradicts>" } ] }
   ```

   `origin` is `inherited` for a defect the diff leaves in place. A target outside the diff adds
   `"wider": true`, as does a finding no smaller correction can fix under R8 (Constraints need a
   named reason). `liftedBy` is optional. `rules`, `defect`, and `severity` are never set.
8. If `disputes` is not empty on the run's first judged pass, send them to `architecture-classifier`
   with the model path and `references/classification.md`; run its commands, then step 12. Later
   disputes, which `arch findings add` prints, go to the user as open questions with the result.
9. Put each question to the user, or return the questions to the calling workflow to ask. Send the
   questions with the answers to the same reviewer; it returns a fresh judged file, written over
   `judged.json`, in which each answered question became a finding, a `liftedBy` on a finding, or
   nothing, and unanswered ones remain. Never edit a judged file by hand. If the user wants an
   answer remembered, run `arch model add-upcoming "<text>"`.
10. Run `arch findings add --flow change-review --base <ref> --check .architecture/work/check.json --applicable .architecture/work/applicable.json --judged .architecture/work/judged.json --upcoming "<upcoming change>"`,
    with `--upcoming` once for every upcoming change the packet stated and every confirmed answer.
    It prints the result and its verdict.
    - If it refuses judged findings, it names the file and the finding: send the problems to the
      reviewer, write its fresh judged file, and run this step again.
    - If it says the check is stale or made with another base, run step 5 again, then this step.
11. If the user accepts a finding instead of fixing it, run the edit the user chooses:
    - an edge other than a cycle: `arch model add-exception <from> <to> rule=<R> reason="<text>"`;
    - a unit, a port (`<path>#<Symbol>`), or a component:
      `arch model add-exception <target> '*' rule=<R> reason="<text>"`;
    - a whole rule, for the project or one component, and the only way to accept a cycle or an
      incomplete condition: `arch model set-rule <R>[@<component>] off reason="<text>"`, or
      `advisory` in place of `off`;
    - a number: `arch model set-threshold <knob> <value>`, with a knob `arch model explain-thresholds` lists.

    Then run `arch model validate`, and steps 5 and 10 again. An exception or `off` covering every
    rule of a finding moves it to `Dropped:`, `advisory` to `Advisory:`; covering some rules leaves
    it with the rest. After a threshold, a finding from `check` no longer appears on the rerun, and a
    judged finding whose condition names that knob is judged again by the same reviewer, in a fresh
    `judged.json`, beforehand.
12. After a fix to the code or to the classification, run steps 3, 5, and 6 again. The same reviewer
    judges again against the new `judgments`, writes a fresh `judged.json`, and steps 9 and 10
    follow. Never pass judged findings written before the fix.
13. For a judged finding the fix resolved, offer a check that catches it next time:
    `arch model add-forbidden-edge <from> <to> reason="<text>"` for an edge, or
    `arch model set-threshold <knob> <value>` for a number. Run it only if the user agrees.
14. Return the printed result and any open question. Show the user the `Inherited findings` and
    `Wider observations` lines as non-blocking. The verdict line is what the caller returns: `OK`
    passes a gate; `SHOULD_CHANGE` and `INCOMPLETE` block it until the findings are fixed or accepted.

If a command fails, it exits 2 and says what was wrong and what to do next; for more, read that subcommand's page, such as `references/commands/check.md`.
