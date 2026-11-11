# arch uncovered

What `arch uncovered` does, its flags, exit codes, and output. Read it when classifying a codebase
or when it fails. It lists every module the adapter reports that the model leaves without a
component or a kind. A condition that needs such a module's classification is reported incomplete,
never as passing, so the baseline flow, and an audit after it, repeat classification until this
list is empty.

## Synopsis

```
arch uncovered
arch uncovered --json
```

## Flags

| Flag | Value | Meaning |
|---|---|---|
| `--json` | none | Print the paths as one JSON array. |
| `--record` | a directory | Read the model from this record path instead of `docs/architecture/`. `ARCH_RECORD_DIR` does the same. |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Every module is classified. |
| 1 | At least one module is uncovered; the paths are printed. |
| 2 | No model, in which case the message names the baseline flow to run first, an invalid model, an adapter failure, or a usage error. |

## Output

One path per line, relative to the project root, or nothing when every module is covered. With
`--json`, one array of paths, `[]` when every module is covered.

## Example

The payroll fixture right after `arch model init`, which writes no components, so no module is
covered yet:

```
$ arch uncovered
src/adapters/memory-payroll-repository.ts
src/adapters/pg-payroll-repository.ts
src/adapters/system-clock.ts
src/domain/clock.ts
src/domain/employee.ts
src/domain/index.ts
src/domain/payroll-repository.ts
src/domain/payroll-use-case.ts
src/web/legacy-router.js
src/web/main.ts
src/web/payroll-controller.ts
```
