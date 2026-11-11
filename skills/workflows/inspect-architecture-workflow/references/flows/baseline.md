# Baseline

The procedure that records a project's architecture baseline: create the model or keep the one that
exists, classify every module, collect the current picture, and show the findings the command
decides on the current code. It dispatches no reviewer and records no findings. Follow it step by
step when the skill is invoked with `baseline` or a calling workflow names it.

Inputs: the project, and the ticket or brief when one exists, for actors and intended components.
Run every command from the project root. The skill folder holds `SKILL.md`, two levels above this
file; `arch` stands for `node <skill folder>/scripts/arch.mjs`, and paths that start with
`references` are inside it. Every packet opens with the absolute paths of the project root and the
skill folder. Terms are defined in `references/rules/vocabulary.md`.

## Steps

1. Run `arch model status --json`; its `path` is the model path. If `model` is `true`, keep that
   model, its starting point, its record mode, and its adapter, and go to step 5.
2. Ask the user two questions. The starting point: `greenfield`, little code, every enforced rule
   counts from the start; or `legacy`, existing breaches are inherited and R6, R19, R21, and R22
   start advisory. The record: `committed`, the model and `current.md` are committed with the
   code; or `local`, they stay on this machine and out of version control.
3. Set up the adapter, the command that prints the dependency facts. If the project already has
   one, use its command. Otherwise copy the skill's `adapter-templates` asset folder for the
   project's language into the project, follow its README, and check it against
   `references/adapter-contract.md`; for a language with no template, write an adapter that page
   describes. Run the command by hand from the project root and read its output before going on.
4. Run `arch model init --start <greenfield|legacy> --adapter "<command>" --record-mode <committed|local>`.
   A project with the four model files of the earlier format runs `arch model migrate`, then
   `arch model set-adapter "<command>"`, instead.
5. Run `arch model validate`. Exit 0 continues, even with `warning:` lines for components with no
   modules yet. Exit 2 with `model does not fit the code:` or "the model has no components": keep
   the message and continue. Any other exit 2 is a failure.
6. Run `arch uncovered`. If it exits 0 and step 5 kept no message, go to step 8.
7. Dispatch `architecture-classifier` with the uncovered modules, the message step 5 kept, the
   starting point when step 2 asked for it, the ticket or brief, `references/classification.md`,
   and `references/rules/vocabulary.md`. It returns `arch model` commands with reasons, such as
   `arch model add-component <name> paths=<globs>` and
   `arch model classify <component> <pattern> <kind>`, and open questions. Run the commands, put the
   questions to the user, and go back to step 5, unless `arch uncovered` lists the same modules as
   before this pass: then stop and show them to the user.
8. Run `arch collect`. It rewrites `current.md` in the record path and prints the counts.
9. Run `arch check` once; exit 1, an enforced blocker or major, continues. Show the user its table
   and sections as the deterministic findings of the current code, and say plainly that this is not
   a review: no agent judged anything, and no finding was recorded.
10. If `record` in `architecture.json` is `committed`, tell the user to commit `architecture.json`,
    `current.md`, and the copied adapter. `.architecture/` is never committed.
11. Return a short result:
    - the model path, and `current.md` beside it in the record path;
    - the counts `arch collect` printed;
    - each rule the check lists under `Rules not enforced`, with its status and reason;
    - the deterministic findings by severity, counted from the check table's Severity column, and
      the number of `Incomplete` entries;
    - what to commit, when the record is `committed`;
    - the classifier's open questions the user has not answered.

If a command fails, it exits 2 and says what was wrong and what to do next; for more, read that subcommand's page, such as `references/commands/model.md`.
