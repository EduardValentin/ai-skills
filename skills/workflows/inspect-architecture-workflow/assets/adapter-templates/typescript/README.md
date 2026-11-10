# TypeScript adapter template

A ready adapter for TypeScript and JavaScript projects. Copy this whole folder into the project,
commit it, and own it. The contract it follows is in the adapter-contract reference of the skill.

## Files

| File | Purpose |
|---|---|
| `adapter.mjs` | The entry point and the settings. Reads the request on standard input, assembles the document, prints it. |
| `dependency-tool.mjs` | Locates and runs dependency-cruiser, and turns its output into modules, edges, and externals. |
| `link-packages.mjs` | Links the source root's installed packages into a bare checkout for the run, and removes the links. |
| `compiler.mjs` | Loads the compiler, builds the program, and assembles the per-module facts. |
| `compiler-facts.mjs` | The compiler-based fact scans: exports, implements, constructs, signatures, symbol imports, type checks. |
| `files.mjs` | Two small file helpers shared by the others. |
| `cruise-config.cjs` | The dependency-cruiser configuration the adapter passes by default. |

All files import only each other and Node built-ins. Nothing is imported from the skill.

## Settings

Edit the `settings` constant at the top of your copy of `adapter.mjs`:

| Setting | Meaning | Default |
|---|---|---|
| `roots` | Folders passed to dependency-cruiser, relative to the project root. | `["src"]` |
| `tsConfig` | Compiler configuration file, relative to the project root. Ignored when absent. | `tsconfig.json` |
| `dependencyCruiserConfig` | dependency-cruiser configuration, relative to the adapter script. | `cruise-config.cjs` |

## Requirements

`typescript` 5.x or 6.x and `dependency-cruiser`, installed in the project that `ARCH_SOURCE_ROOT` names. The
adapter resolves both from `ARCH_SOURCE_ROOT` and falls back to the current directory when the
variable is unset. TypeScript 7 and later have no JavaScript compiler API; when the adapter finds one
it exits with status 1 and prints `The TypeScript found in <root> is version <v>, which has no
JavaScript compiler API. This adapter supports TypeScript 5.x and 6.x. Install a supported version
in <root>.` You can also run it by hand:

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
