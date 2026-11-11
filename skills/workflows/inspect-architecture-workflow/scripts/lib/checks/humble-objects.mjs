import { externalEdgeRow } from "./rows.mjs";
import { describeUnit } from "./targets.mjs";

const GROUP = "humble-objects";

function presenterImportsUiFramework(context) {
  return (context.graph.externals ?? [])
    .filter((external) => external.tag === "framework")
    .flatMap((external) =>
      external.importers
        .filter((importer) => context.unitOf(importer)?.kind === "presenter")
        .map((importer) =>
          externalEdgeRow({
            from: importer,
            name: external.name,
            evidence: `presenter imports the framework ${external.name}: ${describeUnit(context.unitOf(importer))}`,
            correction:
              `Keep ${importer} free of ${external.name}: have it return a plain view model and let the view ` +
              "own the framework calls",
          }),
        ),
    );
}

export const HUMBLE_OBJECTS_CHECKS = [
  {
    id: "presenter-imports-ui-framework",
    rules: ["R21"],
    group: GROUP,
    defect: "presenter-bound-to-framework",
    severity: "major",
    facts: [],
    needsBase: false,
    run: presenterImportsUiFramework,
  },
];
