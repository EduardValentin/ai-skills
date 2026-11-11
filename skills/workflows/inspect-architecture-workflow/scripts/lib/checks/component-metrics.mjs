import { distanceOutliers } from "../graph/metrics.mjs";
import { matchesAny } from "../glob.mjs";
import { relativeToComponent } from "../model/classify.mjs";
import { publishingComponents } from "./context.mjs";
import { componentEdgeRow, componentRow } from "./rows.mjs";
import { edgeTarget } from "./targets.mjs";
import { unitsWithoutExports } from "./undecided.mjs";

const GROUP = "components-and-stability";
const TOLERANCE = 1e-9;

const CORRECTIONS = {
  distance: (name) =>
    `Move ${name} toward the main sequence: make it more abstract if it is stable, or more concrete if it is not`,
  thin: (from, to) =>
    `Narrow what ${to} publishes to what ${from} uses, or fold what ${from} uses into ${from}`,
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

function fewerComponentsThanCompared(context) {
  const { distanceMinComponents } = context.model.thresholds;
  if (context.graph.components.length >= distanceMinComponents) return null;
  return `fewer than ${distanceMinComponents} components`;
}

function distanceOverThreshold(context) {
  const { distanceDeviations } = context.model.thresholds;
  const outliers = new Map(
    distanceOutliers(context.graph.components, context.model.thresholds).map((outlier) => [outlier.name, outlier]),
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

function publishedUnitsOf(context, name) {
  const component = context.model.components.find((candidate) => candidate.name === name);
  if (!component || component.published.length === 0) return null;
  return context.graph.units.filter(
    (unit) => unit.component === name && matchesAny(relativeToComponent(component, unit.path), component.published),
  );
}

function importEdgesIntoPublished(context, from, published) {
  const paths = new Set(published.map((unit) => unit.path));
  return context.graph.edges.filter(
    (edge) => edge.kind !== "constructs" && context.componentOf(edge.from) === from && paths.has(edge.to),
  );
}

function exportedSymbolsOf(published) {
  const declaring = published.filter((unit) => unit.kind !== "barrel");
  if (!declaring.every((unit) => unit.exports)) return null;
  return declaring.reduce((sum, unit) => sum + unit.exports.abstract + unit.exports.concrete, 0);
}

function distinctSymbols(edges) {
  return new Set(edges.flatMap((edge) => edge.symbols.map((symbol) => `${edge.to}#${symbol}`)));
}

function publishedPairs(context) {
  return context.graph.componentEdges.flatMap(({ from, to }) => {
    const published = publishedUnitsOf(context, to);
    return published ? [{ from, to, published, edges: importEdgesIntoPublished(context, from, published) }] : [];
  });
}

function thinComponentUse(context) {
  const { componentUseShare } = context.model.thresholds;
  return publishedPairs(context).flatMap(({ from, to, published, edges }) => {
    const total = exportedSymbolsOf(published);
    if (edges.length === 0 || edges.some((edge) => !edge.symbols) || !(total > 0)) return [];
    const used = distinctSymbols(edges).size;
    if (used / total >= componentUseShare) return [];
    const percent = Math.round((used / total) * 100);
    return [
      componentEdgeRow({
        from,
        to,
        evidence: `${from} uses ${used} of the ${total} symbols ${to} publishes (${percent}%)`,
        correction: CORRECTIONS.thin(from, to),
      }),
    ];
  });
}

function thinComponentUseUndecided(context) {
  const pairs = publishedPairs(context);
  const withoutSymbols = pairs
    .filter(({ edges }) => edges.some((edge) => !edge.symbols))
    .map(({ from, to }) => ({
      target: edgeTarget(from, to),
      reason:
        `edges from ${from} into ${to} name no imported symbols, so its use of ${to} is unknown. ` +
        "Make the adapter report symbols on every edge.",
    }));
  const targets = new Set(pairs.map((pair) => pair.to));
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
    notRunReason: fewerComponentsThanCompared,
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
    applies: (context) => publishingComponents(context).length > 0,
    run: thinComponentUse,
    undecided: thinComponentUseUndecided,
  },
];
