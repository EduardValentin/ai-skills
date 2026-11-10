# TypeScript adapter template

A ready adapter for TypeScript and JavaScript projects. Copy this whole folder into the project,
commit it, and own it. The contract it follows is in the adapter-contract reference of the skill.

## Files

| File | Purpose |
|---|---|
| `adapter.mjs` | Reads the request on standard input, runs dependency-cruiser and the TypeScript program, prints the document. Standalone: it imports nothing from the skill. |
| `cruise-config.cjs` | The dependency-cruiser configuration the adapter passes by default. |

## Settings

Edit the `settings` constant at the top of your copy of `adapter.mjs`:

| Setting | Meaning | Default |
|---|---|---|
| `roots` | Folders passed to dependency-cruiser, relative to the project root. | `["src"]` |
| `tsConfig` | Compiler configuration file, relative to the project root. Ignored when absent. | `tsconfig.json` |
| `dependencyCruiserConfig` | dependency-cruiser configuration, relative to the adapter script. | `cruise-config.cjs` |

## Requirements

`typescript` and `dependency-cruiser` installed in the project that `ARCH_SOURCE_ROOT` names. The
adapter resolves both from `ARCH_SOURCE_ROOT` and falls back to the current directory when the
variable is unset, so you can also run it by hand:

```
echo '{"version":1,"frameworks":[],"ports":[]}' | node adapter.mjs
```

## Facts provided

All six capabilities: `exports`, `implements`, `constructs`, `signatures`, `symbolImports`, and
`typeChecks` (an `instanceof` test on a class declared in another module). When the TypeScript
program cannot be built, it falls back to `exports` and `implements` from a per-file scan and
says so in `warnings`.

## Analysing a base commit

When `arch` analyses a base commit, the working directory is a checkout of that commit with no
installed packages, and `ARCH_SOURCE_ROOT` is the project with the packages. The tools themselves
resolve from `ARCH_SOURCE_ROOT`, so no mirror of the tools is needed. dependency-cruiser decides
whether an import is a package by resolving it from the analysed tree, and an unresolved import
becomes a warning instead of an external edge. For that reason, and only that one, the adapter
temporarily symlinks each `node_modules` folder it finds in the source root (up to three levels
deep) into the working directory when the working directory has none there, and removes the links
before it exits. A `node_modules` folder hoisted above the project root is not linked.
