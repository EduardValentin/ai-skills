import { touchesBarrel } from "./context.mjs";
import { portSymbolsOwnedBy } from "./ports.mjs";
import { unitEdgeRow } from "./rows.mjs";
import { describeUnit, edgePairs } from "./targets.mjs";

const GROUP = "dependency-direction";

const CORRECTIONS = {
  owner: (port, consumerRing) =>
    `Declare ${port.symbol} in the component of its consumers, or in a ring at least as inner as ${consumerRing}`,
  signature: (port, type) =>
    `Replace ${type.symbol} in the signature of ${port.symbol} with a type declared on the policy side`,
  beside: (from, to, shared) =>
    `Have ${from} depend on the port ${shared} and let ${to} be handed in through it`,
};

function ringIndex(context, ring) {
  return context.graph.rings.indexOf(ring);
}

function innermostRingIndex(context, componentName) {
  const indexes = context.graph.units
    .filter((unit) => unit.component === componentName)
    .map((unit) => ringIndex(context, unit.ring))
    .filter((index) => index >= 0);
  return indexes.length === 0 ? null : Math.min(...indexes);
}

function portOwnerBelowConsumer(context) {
  return context.model.ports.flatMap((port) => {
    const ownerRing = innermostRingIndex(context, port.owner);
    if (ownerRing === null) return [];
    return edgePairs(context.graph)
      .filter((pair) => pair.to === port.path && !touchesBarrel(context, pair.from, pair.to))
      .filter((pair) => {
        const consumerRing = ringIndex(context, context.unitOf(pair.from)?.ring);
        return consumerRing >= 0 && consumerRing < ownerRing;
      })
      .map((pair) => {
        const consumer = context.unitOf(pair.from);
        return unitEdgeRow({
          ...pair,
          evidence:
            `port ${port.at} is owned by ${port.owner}, whose innermost ring is ${context.graph.rings[ownerRing]}, ` +
            `outside the ring of its consumer ${describeUnit(consumer)}`,
          correction: CORRECTIONS.owner(port, consumer.ring),
        });
      });
  });
}

function detailTypesNamedBy(context, port) {
  const signatures = (context.unitOf(port.path)?.signatures ?? []).filter((entry) => entry.symbol === port.symbol);
  const types = signatures.flatMap((entry) => entry.types);
  const detail = types.filter((type) => context.roleOf(type.path) === "detail");
  return [...new Map(detail.map((type) => [type.path, type])).values()];
}

function portSignatureDetailType(context) {
  return context.model.ports.flatMap((port) =>
    detailTypesNamedBy(context, port).map((type) =>
      unitEdgeRow({
        from: port.path,
        to: type.path,
        evidence:
          `signature of port ${port.at} names ${type.symbol}, declared in the detail unit ` +
          describeUnit(context.unitOf(type.path)),
        correction: CORRECTIONS.signature(port, type),
      }),
    ),
  );
}

function policyDetailEdgeBesidePort(context) {
  return edgePairs(context.graph)
    .filter((pair) => !touchesBarrel(context, pair.from, pair.to))
    .filter((pair) => context.roleOf(pair.from) === "policy" && context.roleOf(pair.to) === "detail")
    .flatMap((pair) => {
      const owned = portSymbolsOwnedBy(context, context.componentOf(pair.from));
      const shared = (context.unitOf(pair.to).implements ?? []).filter((symbol) => owned.has(symbol));
      if (shared.length === 0) return [];
      return [
        unitEdgeRow({
          ...pair,
          evidence:
            `${describeUnit(context.unitOf(pair.from))} depends directly on ` +
            `${describeUnit(context.unitOf(pair.to))}, which implements ${shared.join(", ")}, ` +
            `a port ${context.componentOf(pair.from)} owns`,
          correction: CORRECTIONS.beside(pair.from, pair.to, shared[0]),
        }),
      ];
    });
}

export const PORT_OWNERSHIP_CHECKS = [
  {
    id: "port-owner-below-consumer",
    rules: ["R5"],
    group: GROUP,
    defect: "port-on-wrong-side",
    severity: "blocker",
    facts: [],
    needsBase: false,
    run: portOwnerBelowConsumer,
  },
  {
    id: "port-signature-detail-type",
    rules: ["R5"],
    group: GROUP,
    defect: "port-carries-detail-type",
    severity: "blocker",
    facts: ["signatures"],
    needsBase: false,
    run: portSignatureDetailType,
  },
  {
    id: "policy-detail-edge-beside-port",
    rules: ["R5"],
    group: GROUP,
    defect: "policy-depends-on-detail",
    severity: "blocker",
    facts: ["implements"],
    needsBase: false,
    run: policyDetailEdgeBesidePort,
  },
];
