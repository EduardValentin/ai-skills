import { touchesBarrel } from "./context.mjs";
import { PORT_OWNERSHIP_CHECKS } from "./port-ownership.mjs";
import { describedPair, externalEdgeRow, unitEdgeRow } from "./rows.mjs";
import { describeUnit, edgePairs } from "./targets.mjs";

const GROUP = "dependency-direction";
const DETAIL_SIDE_ROLES = new Set(["detail", "wiring"]);

const CORRECTIONS = {
  ring: (to) =>
    `Route the dependency on ${to} through a port declared in the inner ring and implemented by ${to}, ` +
    `or move ${to} to the ring it belongs to`,
  external: (name) =>
    `Route the dependency on external:${name} through a port the policy ring owns, implemented outside it`,
  boundary: (from, to) =>
    `Have ${from} call ${to} through an input boundary the use case implements, declared beside the use case`,
  construction: (from) =>
    `Move the construction in ${from} into a composition root and hand the details in through ports ${from} declares`,
};

function isPolicyToDetail(context, pair) {
  return context.roleOf(pair.from) === "policy" && DETAIL_SIDE_ROLES.has(context.roleOf(pair.to));
}

function policyImportsDetail(context) {
  return edgePairs(context.graph)
    .filter((pair) => !touchesBarrel(context, pair.from, pair.to) && isPolicyToDetail(context, pair))
    .map((pair) =>
      unitEdgeRow({
        ...pair,
        evidence: `policy unit depends on a detail unit: ${describedPair(context, pair)}`,
        correction: CORRECTIONS.ring(pair.to),
      }),
    );
}

function policyImportsExternal(context) {
  return (context.graph.externals ?? []).flatMap((external) =>
    external.importers
      .filter((importer) => context.roleOf(importer) === "policy")
      .map((importer) =>
        externalEdgeRow({
          from: importer,
          name: external.name,
          evidence:
            `policy unit depends on a ${external.tag} external: ` +
            `${describeUnit(context.unitOf(importer))} imports ${external.name}`,
          correction: CORRECTIONS.external(external.name),
        }),
      ),
  );
}

function outwardRingEdge(context) {
  return edgePairs(context.graph)
    .filter((pair) => pair.direction === "outward" && !touchesBarrel(context, pair.from, pair.to))
    .filter((pair) => !isPolicyToDetail(context, pair))
    .map((pair) =>
      unitEdgeRow({
        ...pair,
        evidence: `edge crosses rings outward: ${describedPair(context, pair)}`,
        correction: CORRECTIONS.ring(pair.to),
      }),
    );
}

function detailConstructedOutsideRoot(context) {
  return context.graph.edges
    .filter((edge) => edge.kind === "constructs")
    .filter((edge) => context.unitOf(edge.from) && context.unitOf(edge.to))
    .filter((edge) => !touchesBarrel(context, edge.from, edge.to))
    .filter((edge) => context.roleOf(edge.from) !== "wiring" && context.roleOf(edge.to) === "detail")
    .map((edge) =>
      unitEdgeRow({
        ...edge,
        evidence:
          "concrete detail constructed outside a composition root: " +
          `${describeUnit(context.unitOf(edge.from))} constructs ${describeUnit(context.unitOf(edge.to))}`,
        correction: CORRECTIONS.construction(edge.from),
      }),
    );
}

function controllerCallsByUseCase(context) {
  const calls = new Map();
  edgePairs(context.graph)
    .filter((pair) => context.unitOf(pair.from)?.kind === "controller" && context.unitOf(pair.to)?.kind === "use-case")
    .filter((pair) => pair.kinds.some((kind) => kind !== "type-import"))
    .forEach((pair) => calls.set(pair.to, [...(calls.get(pair.to) ?? []), pair]));
  return [...calls.values()];
}

function callingComponents(context, calls) {
  return [...new Set(calls.map((pair) => context.componentOf(pair.from)).filter(Boolean))].sort();
}

function controllerImportsUseCase(context) {
  return controllerCallsByUseCase(context).flatMap((calls) => {
    const components = callingComponents(context, calls);
    if (components.length < 2) return [];
    return calls.map((pair) =>
      unitEdgeRow({
        ...pair,
        evidence:
          `controllers of ${components.join(", ")} call ${pair.to} directly: ${describedPair(context, pair)}`,
        correction: CORRECTIONS.boundary(pair.from, pair.to),
      }),
    );
  });
}

export const DEPENDENCY_DIRECTION_CHECKS = [
  {
    id: "policy-imports-detail",
    rules: ["R4"],
    group: GROUP,
    defect: "policy-depends-on-detail",
    severity: "blocker",
    facts: [],
    needsBase: false,
    run: policyImportsDetail,
  },
  {
    id: "policy-imports-external",
    rules: ["R4"],
    group: GROUP,
    defect: "policy-depends-on-detail",
    severity: "blocker",
    facts: [],
    needsBase: false,
    run: policyImportsExternal,
  },
  {
    id: "outward-ring-edge",
    rules: ["R4"],
    group: GROUP,
    defect: "outward-dependency",
    severity: "blocker",
    facts: [],
    needsBase: false,
    run: outwardRingEdge,
  },
  {
    id: "detail-constructed-outside-root",
    rules: ["R7"],
    group: GROUP,
    defect: "detail-constructed-outside-root",
    severity: "blocker",
    facts: ["constructs"],
    needsBase: false,
    run: detailConstructedOutsideRoot,
  },
  {
    id: "controller-imports-use-case",
    rules: ["R6"],
    group: GROUP,
    defect: "use-case-called-without-boundary",
    severity: "blocker",
    facts: [],
    needsBase: false,
    run: controllerImportsUseCase,
  },
  ...PORT_OWNERSHIP_CHECKS,
];
