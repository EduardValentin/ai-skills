import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { classify, loadModel, validateModel, DEFAULT_RINGS, HARD_PROBLEM, MODEL_DIR } from "./model.mjs";
import { selectAdapter } from "./adapters/index.mjs";
import { git, headCommit, isClean, withBaseWorktree } from "./git.mjs";

export const GRAPH_DIR = ".architecture/graph";
export const GRAPH_VERSION = 3;
export function graphPath(root, commit) { return path.join(root, GRAPH_DIR, `${commit}.json`); }

export function stronglyConnected(nodes, edges) {
  const out = new Map(nodes.map((n) => [n, []]));
  for (const [from, to] of edges) if (out.has(from) && out.has(to)) out.get(from).push(to);
  let index = 0; const stack = []; const onStack = new Set(); const idx = new Map(); const low = new Map(); const result = [];
  function visit(v) {
    idx.set(v, index); low.set(v, index); index += 1; stack.push(v); onStack.add(v);
    for (const w of out.get(v)) {
      if (!idx.has(w)) { visit(w); low.set(v, Math.min(low.get(v), low.get(w))); }
      else if (onStack.has(w)) low.set(v, Math.min(low.get(v), idx.get(w)));
    }
    if (low.get(v) === idx.get(v)) {
      const scc = []; let w;
      do { w = stack.pop(); onStack.delete(w); scc.push(w); } while (w !== v);
      if (scc.length > 1) result.push(scc.sort());
    }
  }
  for (const n of nodes) if (!idx.has(n)) visit(n);
  return result.sort((a, b) => a[0].localeCompare(b[0]));
}

function round(x) { return x === null ? null : Math.round(x * 100) / 100; }

export function metricsFor(units, edges, components) {
  const unitByPath = new Map(units.map((u) => [u.path, u]));
  return components.map((component) => {
    const inside = units.filter((u) => u.component === component.id);
    const insidePaths = new Set(inside.map((u) => u.path));
    const importers = new Set(); const exporters = new Set();
    for (const e of edges) {
      if (!e.to) continue;
      const fromIn = insidePaths.has(e.from), toIn = insidePaths.has(e.to);
      if (!fromIn && toIn && unitByPath.get(e.from)?.component) importers.add(e.from);
      if (fromIn && !toIn && unitByPath.get(e.to)?.component) exporters.add(e.from);
    }
    const fanIn = importers.size, fanOut = exporters.size;
    const exportsKnown = inside.every((u) => u.exports);
    const abstractExports = exportsKnown ? inside.reduce((n, u) => n + u.exports.abstract, 0) : null;
    const totalExports = exportsKnown ? inside.reduce((n, u) => n + u.exports.abstract + u.exports.concrete, 0) : null;
    const instability = fanIn + fanOut === 0 ? null : fanOut / (fanIn + fanOut);
    const abstractness = !totalExports ? null : abstractExports / totalExports;
    const distance = instability === null || abstractness === null ? null : Math.abs(abstractness + instability - 1);
    let inZone = null;
    if (distance !== null && instability <= 0.2 && abstractness <= 0.2 && fanIn >= 3) inZone = "pain";
    if (distance !== null && abstractness >= 0.8 && instability >= 0.8) inZone = "uselessness";
    return { id: component.id, name: component.name, units: inside.length, fanIn, fanOut, instability: round(instability), abstractness: round(abstractness), distance: round(distance), abstractExports, totalExports, inZone };
  });
}

export const CAPABILITIES = ["exports", "implements", "constructs", "signatures"];

function providedFact(capabilities, module, fact) {
  return capabilities[fact] ? module[fact] ?? null : null;
}

function constructsEdges(extracted, capabilities) {
  if (!capabilities.constructs) return [];
  const modulePaths = new Set(extracted.modules.map((m) => m.path));
  return extracted.modules.flatMap((m) => [...new Set((m.constructs ?? []).map((c) => c.path))]
    .filter((target) => modulePaths.has(target))
    .map((target) => ({ from: m.path, to: target, kind: "constructs" })));
}

export function buildGraph({ model, extracted, commit }) {
  const rings = model.rules.rings ?? DEFAULT_RINGS;
  const ringIndex = (ring) => (ring === null ? null : rings.indexOf(ring));
  const capabilities = Object.fromEntries(CAPABILITIES.map((fact) => [fact, Boolean(extracted.capabilities?.[fact])]));
  const units = extracted.modules.map((m) => ({ path: m.path, ...classify(model, m.path), module: m }))
    .sort((a, b) => a.path.localeCompare(b.path))
    .map((u, i) => ({ id: `U${i + 1}`, path: u.path, component: u.component, ring: u.ring, kind: u.kind, actors: u.actors,
      exports: providedFact(capabilities, u.module, "exports"), implements: providedFact(capabilities, u.module, "implements"), signatures: providedFact(capabilities, u.module, "signatures") }));
  const byPath = new Map(units.map((u) => [u.path, u]));
  const edges = [...extracted.edges.filter((e) => e.to), ...constructsEdges(extracted, capabilities)].map((e) => {
    const from = byPath.get(e.from), to = byPath.get(e.to);
    const fi = ringIndex(from?.ring ?? null), ti = ringIndex(to?.ring ?? null);
    const direction = fi === null || ti === null || fi < 0 || ti < 0 ? "unknown" : ti < fi ? "inward" : ti > fi ? "outward" : "same";
    return { from: e.from, to: e.to, kind: e.kind, crossesComponent: (from?.component ?? null) !== (to?.component ?? null), crossesRing: direction !== "same" && direction !== "unknown", direction };
  }).sort((a, b) => a.from.localeCompare(b.from) || a.to.localeCompare(b.to) || a.kind.localeCompare(b.kind))
    .map((e, i) => ({ id: `E${i + 1}`, ...e }));
  const externalMap = new Map();
  for (const e of extracted.edges.filter((x) => x.external)) {
    const key = e.external.name;
    if (!externalMap.has(key)) externalMap.set(key, { name: key, tag: e.external.tag, importers: new Set() });
    externalMap.get(key).importers.add(e.from);
  }
  const externals = [...externalMap.values()].map((x) => ({ name: x.name, tag: x.tag, importers: [...x.importers].sort() })).sort((a, b) => a.name.localeCompare(b.name));
  const components = metricsFor(units, edges, model.components.components);
  const compEdgeMap = new Map();
  for (const e of edges) {
    const a = byPath.get(e.from)?.component, b = byPath.get(e.to)?.component;
    if (!a || !b || a === b) continue;
    const key = `${a}>${b}`;
    if (!compEdgeMap.has(key)) compEdgeMap.set(key, { from: a, to: b, modules: new Set() });
    compEdgeMap.get(key).modules.add(e.from);
  }
  const componentEdges = [...compEdgeMap.values()].map((x) => ({ from: x.from, to: x.to, modules: x.modules.size }))
    .sort((a, b) => a.from.localeCompare(b.from, undefined, { numeric: true }) || a.to.localeCompare(b.to, undefined, { numeric: true }));
  const cycles = {
    modules: stronglyConnected(units.map((u) => u.path), edges.map((e) => [e.from, e.to])),
    components: stronglyConnected(model.components.components.map((c) => c.id), componentEdges.map((e) => [e.from, e.to])),
  };
  const uncovered = units.filter((u) => u.component === null || u.ring === null).map((u) => u.path);
  return { version: GRAPH_VERSION, commit, language: extracted.language ?? "typescript", generatedAt: new Date().toISOString(), capabilities, rings, units, edges, externals, components, componentEdges, cycles, uncovered, warnings: [...extracted.warnings] };
}

async function resolveWorkingTreeKey(root) {
  if (!(await isClean(root))) return "working-tree";
  try { return await headCommit(root); }
  catch { return "working-tree"; }
}

async function resolveCommitKey(root, ref) {
  return (await git(root, ["rev-parse", "--short=8", ref])).trim();
}

export function sourceRoots(model) {
  const roots = model.components.tooling?.roots;
  return Array.isArray(roots) && roots.length > 0 ? roots : ["."];
}

async function readCachedGraph(file) {
  try {
    const graph = JSON.parse(await readFile(file, "utf8"));
    return graph.version === GRAPH_VERSION ? graph : null;
  } catch { return null; }
}

async function buildIn(buildRoot, { cruiseJsonPath, factsJsonPath, commit }) {
  const model = await loadModel(buildRoot);
  const adapter = await selectAdapter(model, buildRoot);
  const ports = model.boundaries.ports.map((port) => ({ path: port.path, symbol: port.symbol }));
  const extracted = await adapter.extract({ roots: sourceRoots(model), cruiseJsonPath, factsJsonPath, frameworks: model.rules.frameworks ?? [], ports });
  extracted.language = adapter.language;
  const problems = validateModel(model, new Set(extracted.modules.map((m) => m.path)));
  const hard = problems.filter((p) => HARD_PROBLEM.test(p));
  if (hard.length) {
    for (const problem of problems) console.error(problem);
    throw new Error(`model is invalid:\n${hard.join("\n")}`);
  }
  const graph = buildGraph({ model, extracted, commit });
  graph.warnings.push(...problems);
  return graph;
}

export async function modelExistsAt(root, ref) {
  try { await git(root, ["cat-file", "-e", `${ref}:./${MODEL_DIR}/components.json`]); return true; }
  catch { return false; }
}

export async function loadOrBuildGraph(root, { commit, cruiseJsonPath, factsJsonPath, force } = {}) {
  if (commit && !(await modelExistsAt(root, commit))) throw new Error(`no architecture model at ${commit}`);
  const key = commit ? await resolveCommitKey(root, commit) : await resolveWorkingTreeKey(root);
  const file = graphPath(root, key);
  const useCache = !force && !cruiseJsonPath && !factsJsonPath && key !== "working-tree";
  const cached = useCache ? await readCachedGraph(file) : null;
  if (cached) return cached;
  const needsWorktree = Boolean(commit) && (key !== (await headCommit(root)) || !(await isClean(root)));
  const graph = needsWorktree
    ? await withBaseWorktree(root, commit, (dir) => buildIn(dir, { cruiseJsonPath, factsJsonPath, commit: key }))
    : await buildIn(root, { cruiseJsonPath, factsJsonPath, commit: key });
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, `${JSON.stringify(graph, null, 2)}\n`, "utf8");
  return graph;
}
