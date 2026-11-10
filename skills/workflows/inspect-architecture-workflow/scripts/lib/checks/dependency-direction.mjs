import { touchesBarrel } from "./context.mjs";
import { describeUnit, edgePairs, edgeTarget } from "./targets.mjs";

const GROUP = "dependency-direction";
const DETAIL_SIDE_ROLES = new Set(["detail", "wiring"]);

const CORRECTIONS = {
  ring: (to) =>
    `Route the dependency on ${to} through a port declared in the inner ring and implemented by ${to}, ` +
    `or move ${to} to the ring it belongs to`,
  external: (name) =>
    `Route the dependency on external:${name} through a port the policy ring owns, implemented outside it`,
  construction: (from) =>
    `Move the construction in ${from} into a composition root and hand the details in through ports ${from} declares`,
};

function unitEdgeRow({ from, to, evidence, correction }) {
  return {
    target: edgeTarget(from, to),
    evidence,
    correction,
    units: [from, to],
    components: [],
    originKey: { type: "edge", from, to },
    edge: { level: "unit", from, to },
  };
}

function isPolicyToDetail(context, pair) {
  return context.roleOf(pair.from) === "policy" && DETAIL_SIDE_ROLES.has(context.roleOf(pair.to));
}

function describedPair(context, pair) {
  const from = describeUnit(context.unitOf(pair.from) ?? { path: pair.from });
  const to = describeUnit(context.unitOf(pair.to) ?? { path: pair.to });
  return `${from} -> ${to} by ${pair.kinds.join(", ")}`;
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
      .map((importer) => {
        const target = `external:${external.name}`;
        return {
          ...unitEdgeRow({
            from: importer,
            to: target,
            evidence:
              `policy unit depends on a ${external.tag} external: ` +
              `${describeUnit(context.unitOf(importer))} imports ${external.name}`,
            correction: CORRECTIONS.external(external.name),
          }),
          units: [importer],
          originKey: { type: "external", from: importer, name: external.name },
        };
      }),
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
];
