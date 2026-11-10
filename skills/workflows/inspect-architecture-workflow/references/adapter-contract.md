# Adapter contract

What the project's adapter command receives and must print, and how a project gets one. Read this
when writing or changing an adapter, or when `arch` reports a problem with the adapter's output.

## The command

The model names one command in its `adapter` field. `arch` runs it through the shell with these
guarantees:

- The working directory is the root of the tree being analysed: the project root for the current
  state, or a materialized checkout of a base commit.
- The environment variable `ARCH_SOURCE_ROOT` holds the project root that has the installed
  tooling. It equals the working directory for the current state, and differs when `arch` analyses
  a base commit's tree, which has no installed packages. The adapter resolves its tools from
  `ARCH_SOURCE_ROOT` and analyses the files in the working directory.
- Standard input carries the request, one JSON object.
- Standard output must carry the document, one JSON object, and nothing else. Logs go to standard
  error.
- Exit status 0 means success. Any other status is a tooling error: `arch` exits 2, quoting the
  command, the status, and the last five lines of standard error. Run the command by hand from the
  project root to see its full output.

The adapter reads only the working tree. It never needs the model file, so a base commit never
needs a model of its own: `arch` applies the current model to the document.

## The request

```json
{ "version": 1,
  "frameworks": ["express"],
  "ports": [ { "path": "src/domain/clock.ts", "symbol": "Clock" } ] }
```

| Field | Meaning |
|---|---|
| `version` | Request format version. Always 1. |
| `frameworks` | Package names the model classifies as frameworks. The adapter tags an external with one of these names `framework`. |
| `ports` | The model's ports, each as the file and the exported symbol. An adapter that detects structural implementation uses them to decide which modules implement which port. |

## The document

```json
{ "version": 1,
  "capabilities": { "exports": true, "implements": true, "constructs": true, "signatures": true,
                    "symbolImports": false, "typeChecks": false },
  "modules": [ { "path": "src/a.ts", "exports": { "abstract": 0, "concrete": 1 }, "implements": [],
                 "constructs": [ { "symbol": "S", "path": "src/b.ts" } ],
                 "signatures": [ { "symbol": "S", "types": [ { "symbol": "T", "path": "src/b.ts" } ] } ],
                 "typeChecks": [ { "symbol": "S", "path": "src/b.ts", "line": 12 } ] } ],
  "edges": [ { "from": "src/a.ts", "to": "src/b.ts", "kind": "import", "symbols": ["S"] },
             { "from": "src/a.ts", "external": { "name": "pg", "tag": "vendor" } } ],
  "warnings": [] }
```

The published schema is the adapter document schema under assets; `arch` validates every document
against it and names the failing path, for example `edges[0].kind`.

### Capabilities

Each capability says whether the adapter provides one fact. A capability left out is false. A fact
whose capability is false is ignored even if present. A condition that needs a missing fact is
reported incomplete and handed to the reviewer when its rule group permits; it is never reported as
passing.

| Capability | Fact it enables |
|---|---|
| `exports` | `modules[].exports`: counts of abstract and concrete exported symbols. |
| `implements` | `modules[].implements`: names of the abstractions the module implements. |
| `constructs` | `modules[].constructs`: concrete types the module instantiates, with the file declaring each. |
| `signatures` | `modules[].signatures`: for each exported symbol, the types from other modules in its public surface. |
| `symbolImports` | `edges[].symbols`: which exported symbols each edge uses. |
| `typeChecks` | `modules[].typeChecks`: sites where the module tests for a concrete type declared elsewhere, with the line. |

### Modules

`path` is relative to the working directory, with forward slashes. List every analysed source file
once. Every other field is optional and read only when its capability is true.

### Edges

- An internal edge has `from`, `to`, and `kind`: `import`, `type-import`, `dynamic`, or
  `constructs`. `symbols` is read only with `symbolImports`.
- An external edge has `from` and `external`, with the package `name` and a `tag`: `vendor`,
  `framework`, or `runtime`.
- Every path in an edge is a module path.

### Warnings

Free text for problems the adapter met and worked around, such as an import it could not resolve.
`arch` shows them; it does not fail on them.

## Getting an adapter

The skill ships a ready adapter in the adapter template folder under assets. To use it:

1. Copy that whole folder into the project, for example into a tooling directory, and commit it.
   The project owns the copy; the skill never rewrites it.
2. Edit the constants at the top of the copied adapter script: the source roots to analyse, the
   compiler configuration file, and the dependency analyser configuration file.
3. Install the tools the template names in its README in the project.
4. Set `adapter` in the model to the command that runs the copied script, then run it by hand
   from the project root and read the document before relying on it.

For a project in another language, write an adapter that follows this page. The template is a
worked example, not a requirement. The smallest valid adapter prints modules and edges and leaves
every capability false.
