import { touchesBarrel } from "./context.mjs";
import { externalName, inwardDependencyCorrection, removeExternalImport } from "./corrections.mjs";
import { PORT_OWNERSHIP_CHECKS } from "./port-ownership.mjs";
import { existingPort, portsImplementedBy } from "./ports.mjs";
import { describedPair, externalEdgeRow, unitEdgeRow } from "./rows.mjs";
import { describeUnit, edgePairs } from "./targets.mjs";

const GROUP = "dependency-direction";
const DETAIL_SIDE_ROLES = new Set(["detail", "wiring"]);

const CORRECTIONS = {
  wiring: (from, to) => `Have the composition root pass ${from} what it reads from ${to}, and remove the import`,
  detail: (from, to) =>
    `If ${to} does no input or output, classify it as policy with arch model classify; otherwise declare a port ` +
    `beside ${from} for what it needs from ${to}, and have ${to} implement it`,
  outward: (from, to, ring) =>
    `If ${to} belongs in ${ring} or further in, classify it there with arch model classify; otherwise move ` +
    `what ${from} uses from ${to} into ${from}`,
  boundary: (to, components) =>
    `Declare one input boundary beside ${to} that it implements, and have the controllers of ` +
    `${components.join(", ")} call it instead of the class`,
  boundaryExists: (port, components) =>
    `Have the controllers of ${components.join(", ")} call ${existingPort(port)} instead of the class`,
  construction: (from, to) =>
    `Move the construction of ${to} from ${from} into the composition root and pass the instance to ${from}`,
  constructionThroughPort: (from, to, port) =>
    `Move the construction of ${to} from ${from} into the composition root and pass it to ${from} as ` +
    existingPort(port),
};

const CONSEQUENCES = {
  policyImportsDetail: ({ edge }) =>
    `A change to ${edge.to} can force a change to the business rule in ${edge.from}, which cannot be tested ` +
    "without it.",
  policyImportsExternal: ({ edge }) =>
    `An upgrade or replacement of ${externalName(edge.to)} forces a change to the business rule in ${edge.from}.`,
  outwardRingEdge: ({ edge }) =>
    `A change to ${edge.to} in an outer ring can force a change to ${edge.from} and to everything that depends ` +
    "on it.",
  detailConstructed: ({ edge }) =>
    `Replacing or reconfiguring ${edge.to} means editing ${edge.from}, which cannot be tested with a stand-in.`,
  controllerImportsUseCase: ({ edge }) =>
    `Every change to the class ${edge.to} reaches the controllers of each delivery mechanism, so they cannot ` +
    "change independently.",
};

function isPolicyToDetail(context, pair) {
  return context.roleOf(pair.from) === "policy" && DETAIL_SIDE_ROLES.has(context.roleOf(pair.to));
}

function policyDetailCorrection(context, pair) {
  const throughPort = inwardDependencyCorrection(context, pair.from, pair.to);
  if (throughPort) return throughPort;
  if (context.roleOf(pair.to) === "wiring") return CORRECTIONS.wiring(pair.from, pair.to);
  return CORRECTIONS.detail(pair.from, pair.to);
}

function policyImportsDetail(context) {
  return edgePairs(context.graph)
    .filter((pair) => !touchesBarrel(context, pair.from, pair.to) && isPolicyToDetail(context, pair))
    .map((pair) =>
      unitEdgeRow({
        ...pair,
        evidence: `policy unit depends on a detail unit: ${describedPair(context, pair)}`,
        correction: policyDetailCorrection(context, pair),
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
          correction: removeExternalImport(context, importer, external.name),
        }),
      ),
  );
}

function outwardCorrection(context, pair) {
  const throughPort = inwardDependencyCorrection(context, pair.from, pair.to);
  return throughPort ?? CORRECTIONS.outward(pair.from, pair.to, context.unitOf(pair.from)?.ring);
}

function outwardRingEdge(context) {
  return edgePairs(context.graph)
    .filter((pair) => pair.direction === "outward" && !touchesBarrel(context, pair.from, pair.to))
    .filter((pair) => !isPolicyToDetail(context, pair))
    .map((pair) =>
      unitEdgeRow({
        ...pair,
        evidence: `edge crosses rings outward: ${describedPair(context, pair)}`,
        correction: outwardCorrection(context, pair),
      }),
    );
}

function constructionCorrection(context, edge) {
  const [port] = portsImplementedBy(context, edge.to);
  if (port) return CORRECTIONS.constructionThroughPort(edge.from, edge.to, port);
  return CORRECTIONS.construction(edge.from, edge.to);
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
        correction: constructionCorrection(context, edge),
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

function boundaryCorrection(context, useCase, components) {
  const [port] = portsImplementedBy(context, useCase);
  return port ? CORRECTIONS.boundaryExists(port, components) : CORRECTIONS.boundary(useCase, components);
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
        correction: boundaryCorrection(context, pair.to, components),
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
    consequence: CONSEQUENCES.policyImportsDetail,
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
    consequence: CONSEQUENCES.policyImportsExternal,
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
    consequence: CONSEQUENCES.outwardRingEdge,
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
    consequence: CONSEQUENCES.detailConstructed,
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
    consequence: CONSEQUENCES.controllerImportsUseCase,
  },
  ...PORT_OWNERSHIP_CHECKS,
];
