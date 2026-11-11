# Audit

The procedure for a deliberate baseline audit of the whole project: build or complete the model,
let the command decide every condition it can, have one reviewer per rule group judge the rest, and
store the findings. Follow it step by step when the skill is invoked with `audit` or a calling
workflow names this flow.

Inputs: the project, and whether the user asked for design or topology decisions to be reviewed;
only then do R24, R29, and R33 count. Run every command from the project root. The skill folder
holds `SKILL.md`, two levels above this file; `arch` stands for `node <skill folder>/scripts/arch.mjs`,
and paths that start with `references` are inside it. Every packet opens with the absolute paths of
the project root and the skill folder. Working files live under `.architecture/work/`. Terms are
defined in `references/rules/vocabulary.md`.

## Steps

1. Run `arch model status --json`; its `path` is the model path. If `model` is `true`, go to step 5.
2. Ask the user for the baseline: `greenfield`, little code, every enforced rule counts from the
   start; or `legacy`, existing breaches are inherited and R6, R19, R21, and R22 start advisory.
3. Without an adapter, the command that prints the dependency facts, copy the skill's `adapter-templates`
   asset for the language, follow its README, and check it against `references/adapter-contract.md`.
4. Run `arch model init --start <greenfield|legacy> --adapter "<command>"`, with `--record-mode local`
   if the user does not want the record committed. A project with the four model files of the
   earlier format runs `arch model migrate`, then `arch model set-adapter "<command>"`, instead.
5. Run `arch model validate`. Exit 0: continue. Exit 2 with `model does not fit the code:` or "the
   model has no components": keep the message and continue. Any other exit 2 is a failure.
6. Run `arch uncovered`. If it exits 0 and step 5 kept no message, go to step 8.
7. Dispatch `architecture-classifier` with the uncovered modules, the message step 5 kept,
   `references/classification.md`, `references/rules/vocabulary.md`, and the baseline. It returns
   `arch model` commands with a reason each, such as `arch model add-component <name> paths=<globs>`
   and `arch model classify <component> <pattern> <kind>`, and open questions. Run the commands,
   put the questions to the user, and go back to step 5.
8. Run `arch collect`. It rewrites `current.md` in the record path.
9. Run `arch check --out .architecture/work/check.json`. Exit 1 means an enforced blocker or major
   finding; continue either way.
10. Run `arch applicable --all --json`. If `review` is `false`, go to step 14 without `--judged`.
11. Dispatch, in parallel, one `architecture-reviewer` per rule group in `groups` other than
    `cross-cutting`, or one for `cross-cutting` when it is the only group. Each packet: the flow
    `audit` and the scope, the whole project; `.architecture/work/check.json`;
    `references/rules/vocabulary.md`; the group's file, such as
    `references/rules/dependency-direction.md`, with its `judgments` entries as printed (`id`,
    `targets`, `condition`); and whether design or topology decisions are in scope. Only the first
    reviewer dispatched also gets `references/rules/cross-cutting.md` with the `cross-cutting`
    entries. Each returns judged findings, which you write to `.architecture/work/judged-<group>.json`:

    ```json
    { "findings": [ { "judgment": "<judgment id>", "target": "<unit, edge, port, or component>",
        "consequence": "<one sentence>", "correction": "<smallest change inside the project>",
        "evidence": ["<path>:<line>"] } ], "questions": ["<question for the user>"] }
    ```

    It has no `origin`, never sets `rules`, `defect`, or `severity`, and is `"wider": true` only
    when no smaller correction removes its consequence, under R8 (Constraints need a named reason).
12. If reviewers report classification disputes, and only once per run, dispatch
    `architecture-classifier` with the disputed paths, each with the reviewer's reason, the model
    path, and `references/classification.md`; run its commands, then step 18. A later dispute is
    not sent again: it goes in the result as an open question for the user.
13. Put the questions to the user. Send each reviewer its questions with the answers; it returns a
    fresh judged file, written over its own, in which each answered question became a finding, a
    `liftedBy` on a finding, or nothing, and unanswered ones remain. Never edit a judged file by
    hand. To remember an answer, run `arch model add-upcoming "<text>"`.
14. Run `arch findings add --flow audit --check .architecture/work/check.json --judged .architecture/work/judged-<group>.json --upcoming "<upcoming change>"`,
    with `--judged` once per judged file and `--upcoming` once per confirmed answer. A refusal names
    the file and the finding: send each problem to that reviewer, write its fresh file, and run this
    step again. If it says the check is stale, run step 9 again, then this step.
15. If the output has an `Overlapping findings` section, once per run, send those findings and the
    judged files they came from (each line's `from`) to one reviewer. It returns one judged file
    with every finding of those files: one correction per overlapping unit, or the findings
    unchanged when they are independent. Write it to `.architecture/work/judged-reconciled.json`
    and run step 14 again, with `--judged` for that file and for every judged file the section did
    not name, leaving out the files it named.
16. Run `arch findings list --rank`: findings by consequence within the most-changed components.
17. If the user accepts a finding instead of fixing it, run the edit the user chooses:
    `arch model add-exception <from> <to> rule=<R> reason="<text>"` for an edge other than a cycle;
    `arch model add-exception <target> '*' rule=<R> reason="<text>"` for a unit, a port
    (`<path>#<Symbol>`), or a component; `arch model set-rule <R>[@<component>] off reason="<text>"`
    (or `advisory`) for a rule, the only way to accept a cycle; or
    `arch model set-threshold <knob> <value>`, with a knob `arch model explain-thresholds` lists.
    Then run steps 8, 9, 14, and 16 again with the same judged files. An exception or a rule status
    moves the finding to `Dropped:` or `Advisory:`; after a threshold it no longer appears at all.
18. After a fix to the code or the classification, run steps 8 to 10 again. Each reviewer whose group
    is still in `groups` judges again against the new `judgments`, writing a fresh file; delete
    `judged-reconciled.json` and the file of a group that left scope, and dispatch a reviewer for a
    group that entered. Then run steps 13 to 16. Never pass judged findings from before the fix.
19. If `record` in `architecture.json` is `committed`, tell the user to commit `architecture.json`,
    `current.md`, and the copied adapter. `.architecture/` is never committed.
20. Return the printed result, the ranking, and the open questions; show `Wider observations` to the
    user as non-blocking. Every finding of an enforced rule counts, since an audit has no origin.

If a command fails, it exits 2 and says what was wrong and what to do next; for more, read that subcommand's page, such as `references/commands/model.md`.
