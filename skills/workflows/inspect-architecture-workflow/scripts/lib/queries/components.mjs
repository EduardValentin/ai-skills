import { table } from "./shared.mjs";

export function metrics({ graph }) {
  const rows = graph.components.map((c) => [
    c.name, c.units, c.fanIn, c.fanOut, c.instability, c.abstractness, c.distance, c.zone ?? "none",
  ]);
  return table(["Component", "Units", "Fan-in", "Fan-out", "I", "A", "D", "Zone"], rows, {
    notDefinedColumns: ["I", "A", "D"],
  });
}

export function componentGraph({ graph }) {
  const rows = graph.componentEdges.map((edge) => [edge.from, edge.to, edge.modules]);
  return table(["From", "To", "Importing modules"], rows);
}

export function cycles({ graph }) {
  const rows = [
    ...graph.cycles.modules.map((members) => ["module", members]),
    ...graph.cycles.components.map((members) => ["component", members]),
  ];
  return table(["Level", "Members"], rows);
}

export function components({ graph, model }) {
  const unitCounts = new Map(graph.components.map((component) => [component.name, component.units]));
  const rows = model.components.map((c) => [
    c.name, c.enforcement, c.release, c.entry, c.published, unitCounts.get(c.name) ?? 0,
  ]);
  return table(["Component", "Enforcement", "Release", "Entry points", "Published", "Units"], rows);
}

export function groups({ model }) {
  const rows = model.groups.map((group) => [group.name, group.members, group.absorbs ?? ""]);
  return table(["Group", "Members", "Absorbs"], rows);
}
