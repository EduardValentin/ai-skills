import { matchesAny } from "./glob.mjs";
import { classify, componentOf } from "./model.mjs";
import { listUntracked, logNames, nameStatus } from "./git.mjs";
import { loadOrBuildGraph } from "./graph.mjs";

function unitsByPath(graph) {
  return new Map(graph.units.map((u) => [u.path, u]));
}

function metrics(graph) {
  const rows = graph.components.map((c) => [`${c.id} ${c.name}`, c.units, c.fanIn, c.fanOut, c.instability, c.abstractness, c.distance, c.inZone ?? "none"]);
  return { columns: ["Component", "Units", "Fan-in", "Fan-out", "I", "A", "D", "Zone"], rows, undefinedColumns: ["I", "A", "D"] };
}

function componentGraph(graph) {
  const rows = [...graph.componentEdges]
    .sort((a, b) => a.from.localeCompare(b.from, undefined, { numeric: true }) || a.to.localeCompare(b.to, undefined, { numeric: true }))
    .map((e) => [e.from, e.to, e.modules]);
  return { columns: ["From", "To", "Importing modules"], rows };
}

function cycles(graph) {
  const rows = [
    ...graph.cycles.modules.map((members) => ["module", members]),
    ...graph.cycles.components.map((members) => ["component", members]),
  ];
  return { columns: ["Level", "Members"], rows };
}

function ringCrossings(graph, model, { flags }) {
  const direction = flags.direction ?? "outward";
  const byPath = unitsByPath(graph);
  const rows = graph.edges
    .filter((e) => e.crossesRing && e.direction === direction)
    .map((e) => [e.from, byPath.get(e.from)?.ring ?? null, e.to, byPath.get(e.to)?.ring ?? null, e.kind]);
  return { columns: ["From", "From ring", "To", "To ring", "Kind"], rows };
}

function fanIn(graph, model, { positional }) {
  const target = positional[0];
  const byPath = unitsByPath(graph);
  const rows = graph.edges
    .filter((e) => e.to === target)
    .map((e) => [e.from, byPath.get(e.from)?.component ?? null, e.kind]);
  return { columns: ["Importer", "Component", "Kind"], rows };
}

function edges(graph, model, { positional }) {
  const [target] = positional;
  if (!target) throw new Error("usage: arch query edges <path>");
  const outgoing = graph.edges.filter((e) => e.from === target).map((e) => ["out", e.to, e.kind, e.direction]);
  const incoming = graph.edges.filter((e) => e.to === target).map((e) => ["in", e.from, e.kind, e.direction]);
  return { columns: ["Direction", "Other", "Kind", "Ring direction"], rows: [...outgoing, ...incoming] };
}

function units(graph, model, { flags }) {
  const { component, kind, ring } = flags;
  const rows = graph.units
    .filter((u) => (!component || u.component === component) && (!kind || u.kind === kind) && (!ring || u.ring === ring))
    .map((u) => [u.path, u.kind, u.ring, u.actors, u.exports.abstract, u.exports.concrete]);
  return { columns: ["Path", "Kind", "Ring", "Actors", "Abstract", "Concrete"], rows };
}

const CHANGE_LABELS = { A: "added", C: "added", M: "modified", T: "modified", D: "deleted" };

async function baseUnitPaths(root, flags) {
  try {
    const base = await loadOrBuildGraph(root, { commit: flags.base, cruiseJsonPath: flags["cruise-json"], exportsJsonPath: flags["exports-json"] });
    return new Set(base.units.map((u) => u.path));
  } catch {
    return null;
  }
}

async function touched(graph, model, { flags }, root) {
  if (!flags.base || flags.base === true) throw new Error("usage: arch query touched --base <ref>");
  const changes = await nameStatus(root, flags.base);
  const listed = new Set(changes.map((change) => change.path));
  for (const untracked of await listUntracked(root)) if (!listed.has(untracked)) changes.push({ status: "A", path: untracked });
  const byPath = unitsByPath(graph);
  const neighborsOf = new Map();
  for (const e of graph.edges) {
    if (!neighborsOf.has(e.from)) neighborsOf.set(e.from, new Set());
    if (!neighborsOf.has(e.to)) neighborsOf.set(e.to, new Set());
    neighborsOf.get(e.from).add(e.to);
    neighborsOf.get(e.to).add(e.from);
  }
  const deletions = changes.some((change) => change.status === "D");
  const baseUnits = deletions ? await baseUnitPaths(root, flags) : null;
  const wasUnit = (filePath) => (baseUnits ? baseUnits.has(filePath) : classify(model, filePath).component !== null);
  const rows = [];
  for (const change of changes) {
    const deleted = change.status === "D";
    if (deleted ? !wasUnit(change.path) : !byPath.has(change.path)) continue;
    const info = classify(model, change.path);
    const label = CHANGE_LABELS[change.status] ?? `moved from ${change.oldPath}`;
    const neighbors = deleted ? [] : [...(neighborsOf.get(change.path) ?? [])].sort();
    rows.push([change.path, info.component, info.kind, info.ring, label, neighbors.join(", ")]);
  }
  return { columns: ["Path", "Component", "Kind", "Ring", "Change", "Neighbors"], rows };
}

function ports(graph, model) {
  const byPath = unitsByPath(graph);
  const rows = model.boundaries.ports.map((port) => {
    const implementers = graph.units.filter((u) => (u.implements ?? []).includes(port.symbol)).map((u) => u.path).sort();
    const consumerCounts = new Map();
    for (const e of graph.edges) {
      if (e.to !== port.path) continue;
      const importer = byPath.get(e.from);
      if (!importer?.component || importer.component === port.owner) continue;
      if (!consumerCounts.has(importer.component)) consumerCounts.set(importer.component, new Set());
      consumerCounts.get(importer.component).add(e.from);
    }
    const consumers = [...consumerCounts.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([id, modules]) => `${id} (${modules.size})`)
      .join(", ");
    return [`${port.path}:${port.symbol}`, port.owner, port.humbleSide ?? null, implementers.join(", "), consumers];
  });
  return { columns: ["Port", "Owner", "Humble side", "Implementers", "Consumers (by component)"], rows };
}

function entryPoints(graph, model) {
  const rows = [];
  for (const component of model.components.components) {
    const globs = component.entryPoints ?? [];
    if (globs.length === 0) continue;
    for (const unit of graph.units.filter((u) => matchesAny(u.path, globs))) {
      const constructs = graph.edges.filter((e) => e.from === unit.path).map((e) => e.to).sort();
      rows.push([unit.path, component.id, constructs]);
    }
  }
  return { columns: ["Path", "Component", "Constructs"], rows };
}

function externals(graph, model, { flags }) {
  const byPath = unitsByPath(graph);
  const rows = graph.externals
    .filter((x) => !flags.tag || x.tag === flags.tag)
    .map((x) => {
      const components = [...new Set(x.importers.map((p) => byPath.get(p)?.component).filter(Boolean))].sort();
      return [x.name, x.tag, components, [...x.importers].sort()];
    });
  return { columns: ["Name", "Tag", "Importing components", "Importing modules"], rows };
}

async function volatility(graph, model, { flags }, root) {
  if (!flags.since || flags.since === true) throw new Error("usage: arch query volatility --since <ref>");
  const commits = await logNames(root, `${flags.since}..HEAD`);
  const commitsByComponent = new Map();
  const modulesByComponent = new Map();
  for (const commit of commits) {
    const touchedComponents = new Set();
    for (const file of commit.files) {
      const id = componentOf(model, file);
      if (!id) continue;
      touchedComponents.add(id);
      if (!modulesByComponent.has(id)) modulesByComponent.set(id, new Set());
      modulesByComponent.get(id).add(file);
    }
    for (const id of touchedComponents) {
      if (!commitsByComponent.has(id)) commitsByComponent.set(id, new Set());
      commitsByComponent.get(id).add(commit.hash);
    }
  }
  const rows = model.components.components.map((c) => [
    `${c.id} ${c.name}`,
    commitsByComponent.get(c.id)?.size ?? 0,
    modulesByComponent.get(c.id)?.size ?? 0,
  ]);
  return { columns: ["Component", "Commits", "Modules touched"], rows };
}

export const QUERIES = {
  metrics,
  "component-graph": componentGraph,
  cycles,
  "ring-crossings": ringCrossings,
  "fan-in": fanIn,
  edges,
  units,
  touched,
  ports,
  "entry-points": entryPoints,
  externals,
  volatility,
};

export function renderValue(value, missing = "") {
  if (value === null || value === undefined) return missing;
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

export function renderMarkdown({ columns, rows, undefinedColumns = [] }) {
  const missing = columns.map((column) => (undefinedColumns.includes(column) ? "undefined" : ""));
  const header = `| ${columns.join(" | ")} |`;
  const separator = `|${columns.map(() => "---").join("|")}|`;
  const body = rows.map((row) => `| ${row.map((value, i) => renderValue(value, missing[i])).join(" | ")} |`);
  return [header, separator, ...body].join("\n");
}
