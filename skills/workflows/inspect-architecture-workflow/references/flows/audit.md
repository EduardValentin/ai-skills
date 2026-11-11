# Audit

The procedure for a deliberate baseline audit of the whole project: build or complete the model,
let the command decide every condition it can, have one reviewer per rule group judge the rest, and
store the findings. Follow it step by step when the skill is invoked with `audit` or a calling
workflow names this flow.

Inputs: the project, and whether the user asked for design or topology decisions to be reviewed;
only then do R24, R29, and R33 count. Run every command from the inspected project's root. `arch`
stands for `node <skill>/scripts/arch.mjs`, where `<skill>` is the folder that holds this skill's
`SKILL.md`, and paths that start with `references` are inside that folder. Working files live
under `.architecture/work/`. Terms are defined in `references/rules/vocabulary.md`.

## Steps

1. Run `arch model status --json`. If `model` is `true`, go to step 5.
2. Ask the user which baseline fits: `greenfield`, for a project with little code, where every
   enforced rule counts from the start; or `legacy`, for existing code, where existing breaches
   are inherited and R6, R19, R21, and R22 start advisory.
3. The model names the project's adapter, the command that prints the code's dependency facts. If
   the project has none, copy the adapter template folder for its language from the skill's
   `adapter-templates` assets into the project, follow its README, and check the output against
   `references/adapter-contract.md`. The adapter command is the line that runs the copied script.
4. Run `arch model init --start <greenfield|legacy> --adapter "<command>"`. Add
   `--record-mode local` if the user does not want the record committed. If the project has the
   four model files of the earlier format instead, run `arch model migrate`, then
   `arch model set-adapter "<command>"`. A new model has no components yet.
5. Run `arch model validate`. Exit 0 means the model fits the code: go to step 7. Exit 2 with
   `model does not fit the code:` or "the model has no components" means it needs classifying:
   keep the message and continue. Any other exit 2 is a failure; see the last line.
6. Run `arch uncovered`, which lists the uncovered modules (exit 1) or nothing (exit 0). Dispatch
   `architecture-classifier` with that list, the message step 5 kept,
   `references/classification.md`, `references/rules/vocabulary.md`, and the baseline. For a
   greenfield project it proposes the first two or three intended components and how the build
   will enforce their boundaries; for a legacy project it classifies what exists. It returns
   `arch model` commands, one per line, each with a one-sentence reason, such as
   `arch model add-component <name> paths=<globs>` and
   `arch model classify <component> <pattern> <kind>`. Run them and go back to step 5.
7. Run `arch collect`. It rewrites `current.md` in the record path.
8. Run `arch check --out .architecture/work/check.json`. Exit 1 means an enforced rule is breached;
   continue either way.
9. Run `arch applicable --all --json`. If `review` is `false`, no judgment condition applies: go
   to step 12 and leave out `--judged`.
10. Dispatch, in parallel, one `architecture-reviewer` for each rule group in `groups` other than
    `cross-cutting`, or one for `cross-cutting` when it is the only group. Each packet names each
    file once: the flow `audit` and the scope, the whole project; the check output
    `.architecture/work/check.json`; `references/rules/vocabulary.md`;
    `references/rules/cross-cutting.md` with the `cross-cutting` ids from `judgments`; the group's
    own file (for example `references/rules/dependency-direction.md`) with its ids; and whether
    design or topology decisions are in scope. Each returns judged findings:

    ```json
    { "findings": [ { "judgment": "<judgment id>", "target": "<unit, edge, port, or component>",
        "consequence": "<one sentence>", "correction": "<smallest change inside the project>",
        "evidence": ["<path>:<line>"] } ],
      "questions": ["<question for the owner>"] }
    ```

    An audit finding has no `origin` and no `wider`, and never sets `rules`, `defect`, or
    `severity`. A classification dispute goes once to `architecture-classifier`; run its commands
    and step 8 again, and the same reviewer continues.
11. Put the questions to the user. Give each confirmed answer to the reviewer that asked; it sets
    `liftedBy` to that exact text where the answer makes a finding heavier. If the owner wants the
    answer remembered, run `arch model add-upcoming "<text>"`. Drop answered questions. Write each
    reviewer's judged findings to its own file, `.architecture/work/judged-<group>.json`.
12. Run `arch findings add --flow audit --check .architecture/work/check.json --judged .architecture/work/judged-<group>.json --upcoming "<upcoming change>"`.
    Give `--judged` once per reviewer file and `--upcoming` once per confirmed answer. A `liftedBy`
    that names none of them and no change recorded with `add-upcoming` is refused. It prints the
    result.
    A refusal names the file and the finding: send each problem to that reviewer, rewrite its
    file, and run this step again. If it says the check is stale, run step 8 again, then this step.
13. Run `arch findings list --rank`. It orders the findings by consequence within the components
    that changed most in the history window, and counts the rest per rule.
14. If the user accepts a finding instead of fixing it, run the edit the user chooses:
    `arch model add-exception <from> <to> rule=<R> reason="<text>"` for an edge,
    `arch model add-exception <target> '*' rule=<R> reason="<text>"` for a unit, port, or component,
    `arch model set-rule <R>[@<component>] off reason="<text>"` (or `advisory`) for a rule, or
    `arch model set-threshold <knob> <value>` for a number. Then run steps 8 and 12 again with the
    same judged files; the finding is counted under `Dropped:` or `Advisory:`.
15. After code is fixed, run step 8 again, ask each reviewer to judge again only the findings it
    raised, write its fresh file over the old one, and run step 12. Never pass judged findings
    written before the fix.
16. Read `record` in `architecture.json` in the record path (`docs/architecture/` unless the
    project names another). If it is `committed`, tell the user to commit `architecture.json`,
    `current.md`, and the copied adapter; if `local`, nothing is committed. `.architecture/` is
    never committed.
17. Return the printed result and the ranking. An audit has no origin, so every finding of an
    enforced rule counts toward the verdict.

If a command fails, it exits 2 and says what was wrong and what to do next; for more, read that subcommand's page, such as `references/commands/model.md`.
