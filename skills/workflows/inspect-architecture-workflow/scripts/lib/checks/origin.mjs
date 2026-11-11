import { edgeTarget } from "./targets.mjs";

const SEPARATOR = "\u0000";

function pairKey(from, to) {
  return `${from}${SEPARATOR}${to}`;
}

export function identityOf(row, mapPath = (path) => path) {
  if (row.edge?.level === "unit") return JSON.stringify([row.defect, mapPath(row.edge.from), mapPath(row.edge.to)]);
  return JSON.stringify([row.defect, row.target]);
}

function cycleTests({ graph, baseGraph, mapped }) {
  const basePairs = new Set(baseGraph.edges.map((edge) => pairKey(mapped(edge.from), mapped(edge.to))));
  const baseComponentEdges = new Set(baseGraph.componentEdges.map((edge) => edgeTarget(edge.from, edge.to)));
  const inside = (members, edge) => members.includes(edge.from) && members.includes(edge.to);
  return {
    moduleCycle: ({ members }) =>
      graph.edges.some((edge) => inside(members, edge) && !basePairs.has(pairKey(edge.from, edge.to))),
    componentCycle: ({ members }) =>
      graph.componentEdges.some(
        (edge) => inside(members, edge) && !baseComponentEdges.has(edgeTarget(edge.from, edge.to)),
      ),
    change: () => true,
  };
}

export function createOriginResolver({ graph, baseGraph, baseRows, touched }) {
  if (!baseGraph) return () => "none";
  const renames = touched?.renames ?? new Map();
  const mapped = (path) => renames.get(path) ?? path;
  const baseIdentities = new Set(baseRows.map((row) => identityOf(row, mapped)));
  const tests = cycleTests({ graph, baseGraph, mapped });
  return (row) => {
    const test = tests[row.originKey?.type];
    const introduced = test ? test(row.originKey) : !baseIdentities.has(identityOf(row));
    return introduced ? "introduced" : "inherited";
  };
}
