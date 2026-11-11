import { changedPaths } from "../git/changes.mjs";

const CREATING_STATUSES = new Set(["A", "C"]);

function renameMap(changes) {
  return new Map(changes.filter((change) => change.status === "R").map((change) => [change.oldPath, change.path]));
}

export async function touchedScope(root, graph, base) {
  const changes = await changedPaths(root, base);
  const unitOf = new Map(graph.units.map((unit) => [unit.path, unit]));
  const touchedUnits = changes.filter((change) => change.status !== "D" && unitOf.has(change.path));
  const uncovered = new Set(graph.uncovered);
  return {
    units: touchedUnits.map((change) => change.path),
    components: [...new Set(touchedUnits.map((change) => unitOf.get(change.path).component).filter(Boolean))],
    uncovered: touchedUnits.map((change) => change.path).filter((path) => uncovered.has(path)),
    renames: renameMap(changes),
    created: touchedUnits.filter((change) => CREATING_STATUSES.has(change.status)).map((change) => change.path),
  };
}
