import { listUntracked, nameStatus } from "../git.mjs";

const ADDED_STATUSES = new Set(["A", "C"]);

async function changedPaths(root, base) {
  const changes = await nameStatus(root, base);
  const listed = new Set(changes.map((change) => change.path));
  const untracked = (await listUntracked(root)).filter((path) => !listed.has(path));
  return [...changes, ...untracked.map((path) => ({ status: "A", path }))];
}

function renameMap(changes) {
  return new Map(changes.filter((change) => change.status === "R").map((change) => [change.oldPath, change.path]));
}

export async function touchedScope(root, graph, model, base) {
  const changes = await changedPaths(root, base);
  const unitOf = new Map(graph.units.map((unit) => [unit.path, unit]));
  const touchedUnits = changes.filter((change) => change.status !== "D" && unitOf.has(change.path));
  const uncovered = new Set(graph.uncovered);
  return {
    units: touchedUnits.map((change) => change.path),
    added: touchedUnits.filter((change) => ADDED_STATUSES.has(change.status)).map((change) => change.path),
    components: [...new Set(touchedUnits.map((change) => unitOf.get(change.path).component).filter(Boolean))],
    uncovered: touchedUnits.map((change) => change.path).filter((path) => uncovered.has(path)),
    renames: renameMap(changes),
  };
}
