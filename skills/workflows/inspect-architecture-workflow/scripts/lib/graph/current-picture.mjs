import { distanceOutliers } from "./metrics.mjs";

const TITLE = "# Architecture: current picture";
const NOTE = "This file is rewritten by `arch collect` and is never edited by hand.";

function cell(value) {
  return value === null ? "undefined" : String(value);
}

function table(header, rows) {
  const lines = [`| ${header.join(" | ")} |`, `|${header.map(() => "---").join("|")}|`];
  return [...lines, ...rows.map((row) => `| ${row.join(" | ")} |`)];
}

export function thresholdBreaches(graph, thresholds) {
  const zones = graph.components
    .filter((component) => component.zone !== null)
    .map((component) => `${component.name}: zone of ${component.zone}`);
  const distances = distanceOutliers(graph.components, thresholds.distanceDeviations).map(
    (outlier) => `${outlier.name}: distance ${outlier.distance} beyond the project threshold`,
  );
  return [...zones, ...distances];
}

function countLines(graph) {
  return [
    `- Components: ${graph.components.length}`,
    `- Units: ${graph.units.length}`,
    `- Edges: ${graph.edges.length}`,
    `- Module cycles: ${graph.cycles.modules.length}`,
    `- Component cycles: ${graph.cycles.components.length}`,
    `- Uncovered units: ${graph.uncovered.length}`,
  ];
}

function metricsTable(graph) {
  const header = ["Component", "Units", "Fan-in", "Fan-out", "Instability", "Abstractness", "Distance", "Zone"];
  const rows = graph.components.map((c) => [
    c.name, c.units, c.fanIn, c.fanOut, cell(c.instability), cell(c.abstractness), cell(c.distance), c.zone ?? "none",
  ]);
  return table(header, rows);
}

function componentGraphTable(graph) {
  return table(["From", "To", "Modules"], graph.componentEdges.map((edge) => [edge.from, edge.to, edge.modules]));
}

function breachLines(graph, thresholds) {
  const breaches = thresholdBreaches(graph, thresholds);
  return breaches.length === 0 ? ["None"] : breaches.map((breach) => `- ${breach}`);
}

export function renderCurrentPicture(graph, thresholds) {
  const sections = [
    [TITLE, "", NOTE],
    ["## Counts", "", ...countLines(graph)],
    ["## Metrics", "", ...metricsTable(graph)],
    ["## Component graph", "", ...componentGraphTable(graph)],
    ["## Threshold breaches", "", ...breachLines(graph, thresholds)],
  ];
  return `${sections.map((lines) => lines.join("\n")).join("\n\n")}\n`;
}
