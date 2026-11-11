export function edgeTarget(from, to) {
  return `${from} -> ${to}`;
}

export function cycleTarget(members) {
  return [...members].sort(naturalOrder).join(" -> ");
}

export function naturalOrder(a, b) {
  return a.localeCompare(b, undefined, { numeric: true });
}

export function describeUnit(unit) {
  return `${unit.path} (${unit.ring ?? "no ring"}, ${unit.kind ?? "no kind"})`;
}

export function edgePairs(graph) {
  const pairs = new Map();
  for (const edge of graph.edges) {
    const key = edgeTarget(edge.from, edge.to);
    if (!pairs.has(key)) pairs.set(key, { from: edge.from, to: edge.to, direction: edge.direction, kinds: [] });
    pairs.get(key).kinds.push(edge.kind);
  }
  return [...pairs.values()];
}

export function pairTargetsWhere(graph, accepts) {
  return edgePairs(graph)
    .filter(accepts)
    .map((pair) => edgeTarget(pair.from, pair.to));
}
