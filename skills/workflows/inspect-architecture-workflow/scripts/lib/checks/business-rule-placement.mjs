import { touchesBarrel } from "./context.mjs";
import { describedPair, externalEdgeRow, unitEdgeRow } from "./rows.mjs";
import { describeUnit, edgePairs } from "./targets.mjs";

const GROUP = "business-rule-placement";
const ENTITY_NEIGHBOURS = new Set(["entity", "barrel"]);

const CORRECTIONS = {
  entity: (from, to) =>
    `Keep ${from} free of ${to}: pass what it needs as plain values, or move the rule that needs ${to} to a use case`,
  external: (from, name) =>
    `Remove external:${name} from ${from}: the entity states the rule, and a use case calls the outside world`,
  useCase: (from, to) => `Invert the dependency: have ${to} call ${from}, never the reverse`,
  boundaryData: (from, to) => `Keep ${from} plain data: remove its dependency on ${to}`,
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
          correction: CORRECTIONS.external(importer, entry.name),
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
  },
];
