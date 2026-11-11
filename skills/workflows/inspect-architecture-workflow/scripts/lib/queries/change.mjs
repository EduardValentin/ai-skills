import { UsageError } from "../cli/errors.mjs";
import { changedPaths } from "../git/changes.mjs";
import { loadGraph } from "../graph/load.mjs";
import { createClassifier } from "../model/classify.mjs";
import { table, unitsByPath } from "./shared.mjs";

const CHANGE_LABELS = { A: "added", C: "added", M: "modified", T: "modified", D: "deleted" };

function labelOf(change) {
  return CHANGE_LABELS[change.status] ?? `moved from ${change.oldPath}`;
}

function neighborIndex(graph) {
  const neighbors = new Map();
  const link = (from, to) => {
    if (!neighbors.has(from)) neighbors.set(from, new Set());
    neighbors.get(from).add(to);
  };
  for (const edge of graph.edges) {
    link(edge.from, edge.to);
    link(edge.to, edge.from);
  }
  return neighbors;
}

async function pathsOfBaseUnits(root, model, flags, changes) {
  if (!changes.some((change) => change.status === "D")) return new Set();
  const baseGraph = await loadGraph(root, model, { ref: flags.base, flags });
  return new Set(baseGraph.units.map((unit) => unit.path));
}

function isUnitChange(change, currentUnits, baseUnits) {
  return change.status === "D" ? baseUnits.has(change.path) : currentUnits.has(change.path);
}

function touchedRow(change, classify, neighbors) {
  const info = classify(change.path);
  const around = change.status === "D" ? [] : [...(neighbors.get(change.path) ?? [])].sort();
  return [change.path, info.component, info.kind, info.ring, labelOf(change), around.join(", ")];
}

function neighborTable(graph, touchedPaths, neighbors) {
  const byPath = unitsByPath(graph);
  const untouched = new Set();
  for (const path of touchedPaths) {
    for (const neighbor of neighbors.get(path) ?? []) {
      if (!touchedPaths.has(neighbor) && byPath.has(neighbor)) untouched.add(neighbor);
    }
  }
  const rows = [...untouched].sort().map((path) => {
    const unit = byPath.get(path);
    const { abstract = null, concrete = null } = unit.exports ?? {};
    return [unit.path, unit.component, unit.kind, unit.ring, unit.actors, abstract, concrete];
  });
  return table(["Path", "Component", "Kind", "Ring", "Actors", "Abstract", "Concrete"], rows);
}

export function requireBase(flags) {
  if (!flags.base) throw new UsageError("usage: arch query touched --base <ref>");
}

export async function touched({ graph, model, flags, root }) {
  requireBase(flags);
  const changes = await changedPaths(root, flags.base);
  const baseUnits = await pathsOfBaseUnits(root, model, flags, changes);
  const currentUnits = new Set(graph.units.map((unit) => unit.path));
  const neighbors = neighborIndex(graph);
  const classify = createClassifier(model);
  const rows = changes
    .filter((change) => isUnitChange(change, currentUnits, baseUnits))
    .map((change) => touchedRow(change, classify, neighbors));
  const touchedTable = table(["Path", "Component", "Kind", "Ring", "Change", "Neighbors"], rows);
  if (!flags["with-neighbors"]) return touchedTable;
  const touchedPaths = new Set(rows.map((row) => row[0]));
  return { sections: { touched: touchedTable, neighbors: neighborTable(graph, touchedPaths, neighbors) } };
}
