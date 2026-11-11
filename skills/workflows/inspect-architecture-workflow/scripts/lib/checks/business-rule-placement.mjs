import { touchesBarrel } from "./context.mjs";
import { externalName, removeExternalImport } from "./corrections.mjs";
import { describedPair, externalEdgeRow, unitEdgeRow } from "./rows.mjs";
import { describeUnit, edgePairs } from "./targets.mjs";

const GROUP = "business-rule-placement";
const ENTITY_NEIGHBOURS = new Set(["entity", "barrel"]);

const CORRECTIONS = {
  entity: (from, to) =>
    `Keep ${from} free of ${to}: pass what it needs as plain values, or move the rule that needs ${to} to a use case`,
  useCase: (from, to) => `Remove the dependency of ${from} on ${to}: have ${to} call ${from} and pass it what it needs`,
  boundaryData: (from, to) =>
    `Keep ${from} plain data: copy the fields it needs from ${to} as plain values and remove the dependency`,
};

const CONSEQUENCES = {
  entity: ({ edge }) =>
    `A change to ${externalName(edge.to)} can force a change to the entity ${edge.from}, the code that should change ` +
    "least.",
  useCase: ({ edge }) =>
    `A change to the application rules in ${edge.to} can force a change to the entity ${edge.from}.`,
  boundaryData: ({ edge }) =>
    `A change to ${externalName(edge.to)} changes the data ${edge.from} carries across the boundary, and every side ` +
    "that reads it.",
};

function isEntityNeighbour(unit) {
  return ENTITY_NEIGHBOURS.has(unit.kind) || unit.valueType === true;
}

function entityDefect(context, pair) {
  return context.roleOf(pair.to) === "detail" ? "policy-depends-on-detail" : "entity-depends-outward";
}

function entityEdges(context) {
  return edgePairs(context.graph)
    .filter((pair) => !touchesBarrel(context, pair.from, pair.to))
    .filter((pair) => context.unitOf(pair.from)?.kind === "entity")
    .filter((pair) => context.unitOf(pair.to)?.kind && !isEntityNeighbour(context.unitOf(pair.to)));
}

function entityImportsNonEntity(context) {
  const internal = entityEdges(context).map((pair) => ({
    ...unitEdgeRow({
      ...pair,
      evidence: `entity depends on a unit that is not an entity: ${describedPair(context, pair)}`,
      correction: CORRECTIONS.entity(pair.from, pair.to),
    }),
    defect: entityDefect(context, pair),
  }));
  const external = (context.graph.externals ?? []).flatMap((entry) =>
    entry.importers
      .filter((importer) => context.unitOf(importer)?.kind === "entity")
      .map((importer) => ({
        ...externalEdgeRow({
          from: importer,
          name: entry.name,
          evidence: `entity imports the ${entry.tag} external ${entry.name}: ${describeUnit(context.unitOf(importer))}`,
          correction: removeExternalImport(context, importer, entry.name),
        }),
        defect: "policy-depends-on-detail",
      })),
  );
  return [...internal, ...external];
}

function entityImportsUseCase(context) {
  return edgePairs(context.graph)
    .filter((pair) => context.unitOf(pair.from)?.kind === "entity" && context.unitOf(pair.to)?.kind === "use-case")
    .map((pair) =>
      unitEdgeRow({
        ...pair,
        evidence: `entity depends on a use case: ${describedPair(context, pair)}`,
        correction: CORRECTIONS.useCase(pair.from, pair.to),
      }),
    );
}

function boundaryDataImports(context) {
  return edgePairs(context.graph)
    .filter((pair) => !touchesBarrel(context, pair.from, pair.to))
    .filter((pair) => context.unitOf(pair.from)?.kind === "boundary-data" && context.unitOf(pair.to))
    .filter((pair) => context.unitOf(pair.to).kind !== "boundary-data")
    .map((pair) =>
      unitEdgeRow({
        ...pair,
        evidence: `boundary data depends on something other than boundary data: ${describedPair(context, pair)}`,
        correction: CORRECTIONS.boundaryData(pair.from, pair.to),
      }),
    );
}

function boundaryDataImportsExternal(context) {
  return (context.graph.externals ?? []).flatMap((entry) =>
    entry.importers
      .filter((importer) => context.unitOf(importer)?.kind === "boundary-data")
      .map((importer) =>
        externalEdgeRow({
          from: importer,
          name: entry.name,
          evidence:
            `boundary data imports the ${entry.tag} external ${entry.name}: ` +
            describeUnit(context.unitOf(importer)),
          correction: CORRECTIONS.boundaryData(importer, `external:${entry.name}`),
        }),
      ),
  );
}

export const BUSINESS_RULE_PLACEMENT_CHECKS = [
  {
    id: "entity-imports-non-entity",
    rules: ["R17"],
    group: GROUP,
    defect: "entity-depends-outward",
    severity: "blocker",
    facts: [],
    needsBase: false,
    run: entityImportsNonEntity,
    consequence: CONSEQUENCES.entity,
  },
  {
    id: "entity-imports-use-case",
    rules: ["R18"],
    group: GROUP,
    defect: "entity-depends-outward",
    severity: "blocker",
    facts: [],
    needsBase: false,
    run: entityImportsUseCase,
    consequence: CONSEQUENCES.useCase,
  },
  {
    id: "boundary-data-imports",
    rules: ["R19"],
    group: GROUP,
    defect: "boundary-data-not-plain",
    severity: "blocker",
    facts: [],
    needsBase: false,
    run: (context) => [...boundaryDataImports(context), ...boundaryDataImportsExternal(context)],
    consequence: CONSEQUENCES.boundaryData,
  },
];
