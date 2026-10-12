function edgeKey(e) { return `${e.from}\u0000${e.to}\u0000${e.kind}`; }
function mapPath(renames, p) { return renames.get(p) ?? p; }

export function diffGraphs(base, head, renames) {
  const basePaths = new Set(base.units.map((u) => mapPath(renames, u.path)));
  const headPaths = new Set(head.units.map((u) => u.path));
  const moved = [...renames].filter(([from, to]) => base.units.some((u) => u.path === from) && headPaths.has(to)).map(([from, to]) => ({ from, to }));
  const added = [...headPaths].filter((p) => !basePaths.has(p)).sort();
  const removed = base.units.map((u) => u.path).filter((p) => !renames.has(p) && !headPaths.has(p)).sort();
  const baseByPath = new Map(base.units.map((u) => [mapPath(renames, u.path), u]));
  const modifiedClassification = head.units.filter((u) => { const b = baseByPath.get(u.path); return b && (b.ring !== u.ring || b.kind !== u.kind); })
    .map((u) => { const b = baseByPath.get(u.path); return { path: u.path, from: { ring: b.ring, kind: b.kind }, to: { ring: u.ring, kind: u.kind } }; });
  const baseEdges = new Map(base.edges.map((e) => [edgeKey({ ...e, from: mapPath(renames, e.from), to: mapPath(renames, e.to) }), e]));
  const headEdges = new Map(head.edges.map((e) => [edgeKey(e), e]));
  const pick = (e) => ({ from: e.from, to: e.to, kind: e.kind, direction: e.direction, crossesComponent: e.crossesComponent });
  const edgesAdded = [...headEdges].filter(([k]) => !baseEdges.has(k)).map(([, e]) => pick(e));
  const edgesRemoved = [...baseEdges].filter(([k]) => !headEdges.has(k)).map(([, e]) => pick({ ...e, from: mapPath(renames, e.from), to: mapPath(renames, e.to) }));
  const baseComp = new Map(base.components.map((c) => [c.id, c]));
  const components = head.components.map((c) => {
    const b = baseComp.get(c.id) ?? {};
    const pair = (k) => [b[k] ?? null, c[k]];
    const [d0, d1] = pair("distance");
    return { id: c.id, fanIn: pair("fanIn"), fanOut: pair("fanOut"), instability: pair("instability"), abstractness: pair("abstractness"), distance: pair("distance"), movedPastThreshold: d0 !== null && d1 !== null && Math.abs(d1 - d0) >= 0.1 };
  });
  const key = (c) => c.join(",");
  const baseCycles = new Set(base.cycles.components.map(key)), headCycles = new Set(head.cycles.components.map(key));
  return { base: base.commit, head: head.commit, units: { added, removed, moved, modifiedClassification }, edges: { added: edgesAdded, removed: edgesRemoved }, components,
    cycles: { new: head.cycles.components.filter((c) => !baseCycles.has(key(c))), gone: base.cycles.components.filter((c) => !headCycles.has(key(c))) } };
}
