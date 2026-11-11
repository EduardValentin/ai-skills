# Change review

The procedure for reviewing a diff against a base commit: the command decides every condition it
can, at most one reviewer judges the rest, and the command stores the findings and prints the
result. Follow it step by step when the skill is invoked with `change-review` or a calling workflow
names this flow.

Inputs: the base ref the diff is compared with, written `<ref>` below, and any upcoming changes the
ticket or plan states. Run every command from the inspected project's root. `arch` stands for
`node <skill>/scripts/arch.mjs`, where `<skill>` is the folder that holds this skill's `SKILL.md`,
and paths that start with `references` are inside that folder. Working files live under
`.architecture/work/`, the only place inside the project the command accepts them.

## Steps

1. Run `arch applicable --base <ref> --json`.
2. If the output has `"model": false`, return `Verdict: OK` with the line
   "no architecture model; run a baseline audit to enable the full review", and stop with `OK`.
3. If `uncovered` lists files, dispatch `architecture-classifier` with those paths,
   `references/classification.md`, and `references/rules/vocabulary.md`. It returns `arch model`
   commands, one per line, each with a one-sentence reason. Run them and go back to step 1, once:
   a file still uncovered after that round is reported incomplete, never as passing.
4. Run `arch check --base <ref> --out .architecture/work/check.json`. It prints one line. Exit 1
   means an introduced breach of an enforced rule; continue either way.
5. If `review` is `false`, the change stays inside one component and adds no component, port,
   cross-component edge, or external: skip to step 9 with no reviewer. `notReviewed` counts the
   judgment conditions left out; if the user wants them, rerun step 1 with `--full` added. If
   `review` is `true` but `groups` is empty, every rule in scope is off: also skip to step 9.
6. Dispatch one `architecture-reviewer` with this packet:
   - the flow `change-review`, the base ref, and the scope: the diff against `<ref>`;
   - the check output `.architecture/work/check.json`, whose findings it does not repeat;
   - `references/rules/vocabulary.md`, `references/rules/cross-cutting.md`, and the rule-group
     file of each name in `groups` (for example `references/rules/dependency-direction.md`), with
     the judgment ids `judgments` lists for that group;
   - the touched units and their classification, which `arch query touched --base <ref> --with-neighbors` prints;
   - the upcoming changes the ticket or plan states, word for word.

   It returns two things. First a judged object, `{ "findings": [...], "questions": [...] }`, where
   each finding is `{ "judgment": "<id>", "target": "<unit, edge, port, or component>",
   "consequence": "<one sentence>", "correction": "<smallest change inside the diff>",
   "evidence": ["path:line"], "origin": "introduced" }` (`"inherited"` when the defect was there
   before the diff), plus `"wider": true` only for a target outside the diff and `"liftedBy"` only
   for an upcoming change from the packet or confirmed by the owner. It never sets `rules`,
   `defect`, or `severity`. Second, any classification disputes: a touched path and what its code
   shows that the model contradicts.
7. If there are disputes, dispatch `architecture-classifier` with the disputed paths and the
   reviewer's reasons, run the commands it returns, and go back to step 1.
8. Put each question to the user, or return the questions to the calling workflow to ask. Give
   every confirmed answer to the same reviewer; it returns the judged object with `liftedBy` set to
   that exact text on the findings the answer makes heavier. Drop answered questions; an
   unanswered one changes nothing and stays, so the result lists it. If the owner wants a confirmed
   answer remembered beyond this review, run `arch model add-upcoming "<text>"` with the same text.
   Write the object to `.architecture/work/judged.json`.
9. Run `arch findings add --flow change-review --base <ref> --check .architecture/work/check.json --judged .architecture/work/judged.json`.
   Leave out `--judged` when no reviewer ran. Add `--upcoming "<text>"` once per confirmed answer,
   with the same text as `liftedBy`. It prints the result.
   - If it refuses judged findings, it lists each problem: send them to the reviewer, write its
     corrected object, and run this step again.
   - If it says the check is stale or made with another base, run step 4 again, then this step.
10. If the user would rather accept a finding than fix it, that is a model edit the user chooses:
    `arch model add-exception <from> <to> rule=<R> reason=<text>` for one target or a component
    pair, `arch model set-rule <R>[@<component>] advisory reason=<text>` (or `off`) for a rule, or
    `arch model set-threshold <knob> <value>` for a number. Run the chosen edit, then steps 4 and 9
    again.
11. If the code was changed in this session to resolve a judged finding, offer to catch it with a
    check next time: `arch model add-forbidden-edge <from> <to> reason=<text>` for an edge that
    must not return, or `arch model set-threshold <knob> <value>` for a number. Run it only if the
    user agrees, then steps 4 and 9 again.
12. Return the printed result to the caller; `arch findings list` prints it again. `OK` passes a
    gate. `SHOULD_CHANGE` and `INCOMPLETE` block it until the findings are fixed or accepted.

If a command fails, it exits 2 and says what was wrong and what to do next; for more, read that subcommand's page, such as `references/commands/check.md`.
