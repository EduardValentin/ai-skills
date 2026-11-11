import { distanceOutliers } from "../graph/metrics.mjs";
import { componentEdgeRow, componentRow } from "./rows.mjs";
import { edgeTarget } from "./targets.mjs";
import { unitsWithoutExports } from "./undecided.mjs";

const GROUP = "components-and-stability";
const TOLERANCE = 1e-9;

const CORRECTIONS = {
  distance: (name) =>
    `Move ${name} toward the main sequence: make it more abstract if it is stable, or more concrete if it is not`,
  thin: (from, to) =>
    `Depend on a smaller component than ${to}, or narrow ${to} to what ${from} uses, or fold what ${from} uses into it`,
};

function movedComponents(context) {
  if (!context.baseGraph) return new Map();
  const before = new Map(context.baseGraph.components.map((component) => [component.name, component.distance]));
  const jump = context.model.thresholds.distanceJump;
  return new Map(
    context.graph.components
      .filter((component) => component.distance !== null && before.get(component.name) != null)
      .filter((component) => component.distance - before.get(component.name) >= jump - TOLERANCE)
      .map((component) => [component.name, before.get(component.name)]),
  );
}

function distanceOverThreshold(context) {
  const { distanceDeviations } = context.model.thresholds;
  const outliers = new Map(
    distanceOutliers(context.graph.components, distanceDeviations).map((outlier) => [outlier.name, outlier]),
  );
  const moved = movedComponents(context);
  return context.graph.components
    .filter((component) => outliers.has(component.name) || moved.has(component.name))
    .map((component) => {
      const reasons = [];
      if (outliers.has(component.name)) {
        reasons.push(
          `distance ${component.distance} is more than ${distanceDeviations} standard deviations ` +
            `above the mean ${outliers.get(component.name).mean}`,
        );
      }
      if (moved.has(component.name)) {
        reasons.push(`distance moved from ${moved.get(component.name)} to ${component.distance} since the base`);
      }
      const row = componentRow(component.name, reasons.join("; "), CORRECTIONS.distance(component.name));
      return moved.has(component.name) ? { ...row, originKey: { type: "change" } } : row;
    });
}

function distanceUndecided(context) {
  return unitsWithoutExports(context, new Set(context.graph.components.map((component) => component.name)));
}

function importEdgesBetween(context, from, to) {
  return context.graph.edges.filter(
    (edge) =>
      edge.kind !== "constructs" && context.componentOf(edge.from) === from && context.componentOf(edge.to) === to,
  );
}

function exportedSymbolsOf(context, name) {
  const declaring = context.graph.units.filter((unit) => unit.component === name && unit.kind !== "barrel");
  if (!declaring.every((unit) => unit.exports)) return null;
  return declaring.reduce((sum, unit) => sum + unit.exports.abstract + unit.exports.concrete, 0);
}

function distinctSymbols(edges) {
  return new Set(edges.flatMap((edge) => edge.symbols.map((symbol) => `${edge.to}#${symbol}`)));
}

function thinComponentUse(context) {
  const { componentUseShare } = context.model.thresholds;
  return context.graph.componentEdges.flatMap(({ from, to }) => {
    const edges = importEdgesBetween(context, from, to);
    const total = exportedSymbolsOf(context, to);
    if (edges.length === 0 || edges.some((edge) => !edge.symbols) || !(total > 0)) return [];
    const used = distinctSymbols(edges).size;
    if (used / total >= componentUseShare) return [];
    const percent = Math.round((used / total) * 100);
    return [
      componentEdgeRow({
        from,
        to,
        evidence: `${from} uses ${used} of the ${total} exported symbols of ${to} (${percent}%)`,
        correction: CORRECTIONS.thin(from, to),
      }),
    ];
  });
}

function thinComponentUseUndecided(context) {
  const targets = new Set(context.graph.componentEdges.map((edge) => edge.to));
  const withoutSymbols = context.graph.componentEdges
    .filter(({ from, to }) => importEdgesBetween(context, from, to).some((edge) => !edge.symbols))
    .map(({ from, to }) => ({
      target: edgeTarget(from, to),
      reason:
        `edges from ${from} into ${to} name no imported symbols, so its use of ${to} is unknown. ` +
        "Make the adapter report symbols on every edge.",
    }));
  return [...withoutSymbols, ...unitsWithoutExports(context, targets)];
}

export const COMPONENT_METRIC_CHECKS = [
  {
    id: "distance-over-threshold",
    rules: ["R32"],
    group: GROUP,
    defect: "off-balance",
    severity: "minor",
    facts: ["exports"],
    needsBase: false,
    run: distanceOverThreshold,
    undecided: distanceUndecided,
  },
  {
    id: "thin-component-use",
    rules: ["R27"],
    group: GROUP,
    defect: "thin-component-use",
    severity: "minor",
    facts: ["symbolImports"],
    needsBase: false,
    run: thinComponentUse,
    undecided: thinComponentUseUndecided,
  },
];
