# Audit

The procedure for a deliberate baseline audit of a codebase or a named part of it: build or
complete the model, let the command decide every condition it can, have one reviewer per rule group
judge the rest, and store the findings. Follow it step by step when the skill is invoked with
`audit` or a calling workflow names this flow.

Inputs: the scope, the whole codebase or named components, and whether the user asked for design
or topology decisions to be reviewed; only then do R24, R29, and R33 count. Run every command from
the inspected project's root. `arch` stands for `node <skill>/scripts/arch.mjs`, where `<skill>` is
the folder that holds this skill's `SKILL.md`, and paths that start with `references` are inside
that folder. Working files live under `.architecture/work/`, the only place inside the project the
command accepts them.

## Steps

1. Run `arch model validate`. If it prints `model: ok`, go to step 5. If it reports that no
   architecture model was found, continue. If it lists entries that do not fit the code, such as
   a pattern that matches no module, go to step 6 with that list.
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
   `arch model set-adapter "<command>"`. A new model holds one example component to replace.
5. Run `arch uncovered`. If it exits 0, every module is classified: go to step 7. If it exits 1,
   it lists the uncovered paths.
6. Dispatch `architecture-classifier` with the uncovered paths or the entries `validate` listed,
   `references/classification.md`, `references/rules/vocabulary.md`, and the baseline. For a
   greenfield project it also proposes the first two or three intended components and how the
   build will enforce their boundaries; for a legacy project it classifies what exists. It returns
   `arch model` commands, one per line, each with a one-sentence reason, including any that
   replace the example component. Run them and go back to step 1.
7. Run `arch collect`. It rewrites `current.md` in the record path.
8. Run `arch check --out .architecture/work/check.json`. Exit 1 means an enforced rule is breached;
   continue either way.
9. Run `arch query units --json` and take the first value, the path, of every row; add
   `--component <name>` to list one named component. Then run
   `arch applicable --files <paths> --full --json` with those paths, comma-separated.
10. Dispatch, in parallel, one `architecture-reviewer` per name in `groups`, each with this packet:
    the flow `audit` and the scope; the check output `.architecture/work/check.json`;
    `references/rules/vocabulary.md`, `references/rules/cross-cutting.md`, and that group's file
    (for example `references/rules/dependency-direction.md`) with its ids from `judgments`; and
    whether design or topology decisions are in scope. Each returns `{ "findings": [...],
    "questions": [...] }`, where a finding is `{ "judgment": "<id>", "target": "<unit, edge, port,
    or component>", "consequence": "<one sentence>", "correction": "<smallest change inside the
    scope>", "evidence": ["path:line"] }`, plus `"wider": true` only outside the scope. An audit
    finding has no `origin`, and none sets `rules`, `defect`, or `severity`.
11. Put the questions to the user. Give each confirmed answer to the reviewer that asked; it sets
    `liftedBy` to that exact text where the answer makes a finding heavier. Merge every reviewer's
    findings and the unanswered questions into one object; write it to `.architecture/work/judged.json`.
12. Run `arch findings add --flow audit --check .architecture/work/check.json --judged .architecture/work/judged.json`,
    adding `--upcoming "<text>"` once per confirmed answer, with the same text as `liftedBy`.
    It prints the result. If it refuses judged findings, send each listed problem to the reviewer
    of that group and run this step again; if it says the check is stale, go back to step 8.
13. Run `arch findings list --rank`. It orders the findings by consequence within the components
    that changed most in the history window, and counts the rest per rule.
14. If the user would rather accept a finding than fix it, that is a model edit the user chooses:
    `arch model add-exception <from> <to> rule=<R> reason=<text>`,
    `arch model set-rule <R>[@<component>] advisory reason=<text>` (or `off`), or
    `arch model set-threshold <knob> <value>`. Run the chosen edit, then go back to step 8. A
    legacy audit records nothing as accepted on its own.
15. Read `record` in the model file, `architecture.json` in the record path (`docs/architecture/`
    unless the project names another). If it is `committed`, tell the user to commit
    `architecture.json`, `current.md`, and the copied adapter. If it is `local`, nothing is
    committed. The `.architecture/` folder is never committed.
16. Return the printed result and the ranking. An audit has no origin, so every finding of an
    enforced rule counts toward the verdict.

If a command fails, it exits 2 and says what was wrong and what to do next; for more, read that subcommand's page, such as `references/commands/model.md`.
