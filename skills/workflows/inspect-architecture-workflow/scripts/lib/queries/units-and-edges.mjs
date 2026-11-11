import { UsageError } from "../cli/errors.mjs";
import { ringDirection, THROUGH_BARREL } from "../graph/build.mjs";
import { table, unitsByPath } from "./shared.mjs";

export function ringCrossings({ graph, flags }) {
  const direction = flags.direction ?? "outward";
  const byPath = unitsByPath(graph);
  const ringOf = (path) => byPath.get(path)?.ring ?? null;
  const directionOf = (edge) => {
    const reclassify = edge.direction === THROUGH_BARREL && flags["include-barrels"];
    return reclassify ? ringDirection(graph.rings, ringOf(edge.from), ringOf(edge.to)) : edge.direction;
  };
  const rows = graph.edges
    .filter((edge) => directionOf(edge) === direction)
    .map((edge) => [edge.from, ringOf(edge.from), edge.to, ringOf(edge.to), edge.kind]);
  return table(["From", "From ring", "To", "To ring", "Kind"], rows);
}

export function fanIn({ graph, positional }) {
  const [target] = positional;
  if (!target) throw new UsageError("usage: arch query fan-in <path>");
  const byPath = unitsByPath(graph);
  const rows = graph.edges
    .filter((edge) => edge.to === target)
    .map((edge) => [edge.from, byPath.get(edge.from)?.component ?? null, edge.kind]);
  return table(["Importer", "Component", "Kind"], rows);
}

function edgesOfPath(graph, target, edges) {
  const outgoing = edges.filter((edge) => edge.from === target).map((e) => ["out", e.to, e.kind, e.direction]);
  const incoming = edges.filter((edge) => edge.to === target).map((e) => ["in", e.from, e.kind, e.direction]);
  return table(["Direction", "Other", "Kind", "Ring direction"], [...outgoing, ...incoming]);
}

export function edges({ graph, positional, flags }) {
  const [target] = positional;
  if (!target && !flags.kind) throw new UsageError("usage: arch query edges <path> | --kind <kind>");
  const ofKind = graph.edges.filter((edge) => !flags.kind || edge.kind === flags.kind);
  if (target) return edgesOfPath(graph, target, ofKind);
  return table(["From", "To", "Kind", "Ring direction"], ofKind.map((e) => [e.from, e.to, e.kind, e.direction]));
}

export const UNIT_COLUMNS = ["Path", "Kind", "Ring", "Actors", "Abstract", "Concrete"];

export function units({ graph, flags }) {
  const { component, kind, ring } = flags;
  const matches = (unit) =>
    (!component || unit.component === component) && (!kind || unit.kind === kind) && (!ring || unit.ring === ring);
  const rows = graph.units
    .filter(matches)
    .map((u) => [u.path, u.kind, u.ring, u.actors, u.exports?.abstract ?? null, u.exports?.concrete ?? null]);
  return table(UNIT_COLUMNS, rows);
}

export function externals({ graph, flags }) {
  const byPath = unitsByPath(graph);
  const rows = graph.externals
    .filter((external) => !flags.tag || external.tag === flags.tag)
    .map((external) => {
      const importing = external.importers.map((path) => byPath.get(path)?.component).filter(Boolean);
      return [external.name, external.tag, [...new Set(importing)].sort(), [...external.importers].sort()];
    });
  return table(["Name", "Tag", "Importing components", "Importing modules"], rows);
}
