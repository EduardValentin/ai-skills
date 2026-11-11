# Audit

The procedure for a deliberate audit of the whole project against its model: classify the files added
since the model was made, let the command decide every condition it can, have one reviewer per rule
group judge the rest, and store the findings. Follow it step by step when the skill is invoked with
`audit` or a calling workflow names it.

Inputs: the project, and whether the user asked for design or topology decisions to be reviewed;
only then do R24, R29, and R33 count. Run every command from the project root. The skill folder
holds `SKILL.md`, two levels above this file; `arch` stands for `node <skill folder>/scripts/arch.mjs`,
and paths that start with `references` are inside it. Every packet opens with the absolute paths of
the project root and the skill folder. Working files live under `.architecture/work/`. Terms are
defined in `references/rules/vocabulary.md`.

## Steps

1. Run `arch model status --json`; its `path` is the model path.
2. If `model` is `false`, stop here: run no other command, dispatch no agent, give no verdict, and
   return to the caller only this message: "There is no architecture model for this project. Run the
   baseline flow first (`inspect-architecture-workflow` with the flow name `baseline`), then run this review again."
3. Run `arch model validate`. Exit 0 continues, even with `warning:` lines for components with no
   modules yet. Exit 2 with `model does not fit the code:` or "the model has no components": keep the
   message and continue. Any other exit 2 is a failure.
4. Run `arch uncovered`. If it exits 0 and step 3 kept no message, go to step 6.
5. Dispatch `architecture-classifier` with the uncovered modules, files added since the model was
   made, the message step 3 kept, `references/classification.md`, and `references/rules/vocabulary.md`.
   It returns `arch model` commands with reasons, such as `arch model add-component <name> paths=<globs>` and
   `arch model classify <component> <pattern> <kind>`, and open questions. Run the commands, put the
   questions to the user, and go back to step 3, unless `arch uncovered` lists the same modules as
   before this pass: then stop and show them to the user.
6. Run `arch collect`. It rewrites `current.md` in the record path.
7. Run `arch check --out .architecture/work/check.json`; exit 1, an enforced blocker or major, continues.
8. Run `arch applicable --all --out .architecture/work/applicable.json`; `groups` names the reviewers, none if `inScope` is 0.
9. Dispatch, in parallel, one `architecture-reviewer` per rule group in `groups` other than
   `cross-cutting`, or one for `cross-cutting` when it is the only group. Each packet: the flow
   `audit` and the scope, the whole project; `.architecture/work/check.json`;
   `references/rules/vocabulary.md`; the group's file, such as `references/rules/tests.md`, with
   its `judgments` entries as printed (`id`, `targets`, `condition`); and whether design or topology
   decisions are in scope. Only the first reviewer dispatched also gets
   `references/rules/cross-cutting.md` with the `cross-cutting` entries. Each returns one JSON
   object, which you write to `.architecture/work/judged-<group>.json`:
   ```json
   { "findings": [ { "judgment": "<judgment id>", "target": "<unit, edge, port, or component>",
       "consequence": "<one sentence>", "correction": "<smallest change inside the project>",
       "evidence": ["<path>:<line>"] } ], "questions": ["<question for the user>"],
     "disputes": [ { "path": "<unit path>", "reason": "<what its code shows that the model contradicts>" } ] }
   ```
   It has no `origin`, never sets `rules`, `defect`, or `severity`, and is `"wider": true` only
   when no smaller correction removes its consequence, under R8 (Constraints need a named reason).
10. On the run's first judged pass, send the `disputes` of every judged file, if any, once to
    `architecture-classifier` with the model path and `references/classification.md`; run its commands,
    then step 16. Later disputes, which `arch findings add` prints, go to the user as open questions.
11. Put the questions to the user. Send each reviewer its questions with the answers; it returns a
    fresh judged file, written over its own, in which each answered question became a finding, a
    `liftedBy` on a finding, or nothing, and unanswered ones remain. Never edit a judged file by
    hand. To remember an answer, run `arch model add-upcoming "<text>"`.
12. Run `arch findings add --flow audit --check .architecture/work/check.json --applicable .architecture/work/applicable.json --judged .architecture/work/judged-<group>.json --upcoming "<upcoming change>"`,
    with `--judged` once per judged file and `--upcoming` once per confirmed answer. A refusal names
    the file and the finding: send each problem to that reviewer, write its fresh file, and run this
    step again. If it says the check or the applicable file is stale, run steps 7 and 8, then this step.
13. Reconcile before any acceptance. If the output has an `Overlapping findings` section and these
    judged files were not reconciled yet, give a fresh `architecture-reviewer`, same prompt, the
    section as printed, `.architecture/work/check.json`, `references/rules/vocabulary.md`, and each
    judged file a line names after `from` with its group's file, such as `references/rules/tests.md`
    for `judged-tests.json`. Its one JSON object holds every finding and question of those files, one
    correction per overlapping unit, or the findings unchanged when independent. Write it to
    `.architecture/work/judged-reconciled.json`, which replaces the files it covers, and run step 12.
14. Run `arch findings list --rank`: findings by consequence within the most-changed components.
15. To accept a finding, run the edit the user chooses, then `arch model validate`, then steps 6, 7, 8,
    12, and 14 again: `arch model add-exception <from> <to> rule=<R> reason="<text>"` for an edge other
    than a cycle; `arch model add-exception <target> '*' rule=<R> reason="<text>"` for a unit, a port
    (`<path>#<Symbol>`), or a component; `arch model set-rule <R>[@<component>] off reason="<text>"`,
    or `advisory`, for a rule, the only way to accept a cycle; `arch model set-threshold <knob> <value>`,
    with a knob `arch model explain-thresholds` lists. An exception or `off` covering every rule of a
    finding moves it to `Dropped:`, `advisory` to `Advisory:`; covering some rules leaves it with the
    rest. After a threshold, a finding from `check` no longer appears on the rerun, and a judged
    finding whose condition names that knob is judged again by its reviewer first, in a fresh file.
16. After a fix to the code or the classification, run steps 6 to 8 again. Each reviewer whose group
    is still in `groups` judges again against the new `judgments`, in a fresh file; delete
    `judged-reconciled.json` and the file of a group that left scope, dispatch a reviewer for a group
    that entered, and run steps 10 to 14, never with judged findings from before the fix.
17. If `record` in `architecture.json` is `committed`, tell the user to commit `architecture.json`
    and `current.md`. `.architecture/` is never committed.
18. Return the printed result, the ranking, and the open questions; show `Wider observations` to the
    user as non-blocking. Every finding of an enforced rule counts, since an audit has no origin.

If a command fails, it exits 2 and says what was wrong and what to do next; for more, read that subcommand's page, such as `references/commands/model.md`.
