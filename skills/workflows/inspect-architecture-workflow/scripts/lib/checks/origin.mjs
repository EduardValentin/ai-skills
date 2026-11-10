import { edgeTarget } from "./targets.mjs";

const SEPARATOR = "\u0000";

function pairKey(from, to) {
  return `${from}${SEPARATOR}${to}`;
}

export function createOriginResolver({ graph, baseGraph, touched }) {
  if (!baseGraph) return () => "none";
  const renames = touched?.renames ?? new Map();
  const mapped = (path) => renames.get(path) ?? path;
  const basePairs = new Set(baseGraph.edges.map((edge) => pairKey(mapped(edge.from), mapped(edge.to))));
  const isNewPair = (from, to) => !basePairs.has(pairKey(from, to));
  const baseImports = new Set(
    baseGraph.externals.flatMap((external) => external.importers.map((path) => pairKey(mapped(path), external.name))),
  );
  const baseComponentEdges = new Set(baseGraph.componentEdges.map((edge) => edgeTarget(edge.from, edge.to)));
  const isNewComponentEdge = ({ from, to }) => !baseComponentEdges.has(edgeTarget(from, to));
  const baseComponents = new Set(baseGraph.components.map((component) => component.name));
  const insideMembers = (members, edge) => members.includes(edge.from) && members.includes(edge.to);

  const isNew = {
    edge: ({ from, to }) => isNewPair(from, to),
    external: ({ from, name }) => !baseImports.has(pairKey(from, name)),
    moduleCycle: ({ members }) =>
      graph.edges.some((edge) => insideMembers(members, edge) && isNewPair(edge.from, edge.to)),
    componentCycle: ({ members }) =>
      graph.componentEdges.some((edge) => insideMembers(members, edge) && isNewComponentEdge(edge)),
    componentEdge: isNewComponentEdge,
    component: ({ name }) => !baseComponents.has(name),
    change: () => true,
  };
  return (originKey) => (isNew[originKey.type](originKey) ? "introduced" : "inherited");
}
