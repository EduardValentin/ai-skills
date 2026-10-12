import { parseFlags } from "../args.mjs";
import { listTracked } from "../git.mjs";
import { loadOrBuildGraph } from "../graph.mjs";
import { HARD_PROBLEM, loadModel, validateModel, writeModelFile } from "../model.mjs";

const USAGE = "usage: arch model <validate|add-override|remove-override|add-port|remove-port|add-component|remove-component|add-rule|remove-rule>";
const EDIT_USAGE = {
  "add-override": "usage: arch model add-override <path> ring=<r> kind=<k> [actors=a,b] [reason=<text>]",
  "add-component": "usage: arch model add-component <id> <name> paths=<glob,...> [enforcement=<text>] [release=<text>] [entry=<glob,...>]",
  "add-rule": "usage: arch model add-rule match=<glob> ring=<r> kind=<k> [actors=a,b] [before=<glob>]",
};

const LIST_KEYS = new Set(["actors", "paths", "entry"]);

function splitArgs(args) {
  const kv = {};
  const plain = [];
  for (const arg of args) {
    const eq = arg.indexOf("=");
    if (eq < 0) { plain.push(arg); continue; }
    const key = arg.slice(0, eq);
    const raw = arg.slice(eq + 1);
    kv[key] = LIST_KEYS.has(key) ? raw.split(",").filter((s) => s.length > 0) : raw;
  }
  return { kv, plain };
}

function upsert(array, matches, entry) {
  const index = array.findIndex(matches);
  if (index >= 0) array[index] = entry; else array.push(entry);
}

function refuseOrWrite(model, name, data, existingPaths) {
  const problems = validateModel(model, existingPaths);
  const hard = problems.filter((p) => HARD_PROBLEM.test(p));
  if (hard.length) {
    for (const problem of problems) console.error(problem);
    return 1;
  }
  return writeModelFile(model, name, data).then(() => 0);
}

async function validate(flags, ctx) {
  let graph;
  try {
    graph = await loadOrBuildGraph(ctx.root, { cruiseJsonPath: flags["cruise-json"], exportsJsonPath: flags["exports-json"], force: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (!message.startsWith("model is invalid")) console.error(message);
    return 1;
  }
  for (const warning of graph.warnings) console.error(warning);
  const problems = validateModel(await loadModel(ctx.root), new Set(graph.units.map((u) => u.path)));
  if (problems.length) return 1;
  console.log("model: ok");
  return 0;
}

function addOverride(model, plain, kv) {
  const [targetPath] = plain;
  const entry = { path: targetPath, ring: kv.ring, kind: kv.kind, actors: kv.actors ?? [] };
  if (kv.reason !== undefined) entry.reason = kv.reason;
  upsert(model.overrides.overrides, (o) => o.path === targetPath, entry);
  return refuseOrWrite(model, "overrides", model.overrides);
}

function removeOverride(model, plain) {
  const [targetPath] = plain;
  const index = model.overrides.overrides.findIndex((o) => o.path === targetPath);
  if (index < 0) { console.error(`no override for ${targetPath}`); return 1; }
  model.overrides.overrides.splice(index, 1);
  return refuseOrWrite(model, "overrides", model.overrides);
}

function nextPortId(ports) {
  const max = ports.reduce((n, port) => {
    const match = /^B(\d+)$/.exec(port.id);
    return match ? Math.max(n, Number(match[1])) : n;
  }, 0);
  return `B${max + 1}`;
}

function addPort(model, plain, kv) {
  const [targetPath, symbol] = plain;
  const ports = model.boundaries.ports;
  const matches = (port) => port.path === targetPath && port.symbol === symbol;
  const existing = ports.find(matches);
  const entry = { id: existing?.id ?? nextPortId(ports), path: targetPath, symbol, owner: kv.owner };
  if (kv.humble !== undefined) entry.humbleSide = kv.humble;
  upsert(ports, matches, entry);
  return refuseOrWrite(model, "boundaries", model.boundaries);
}

function removePort(model, plain) {
  const [targetPath, symbol] = plain;
  const ports = model.boundaries.ports;
  const index = ports.findIndex((port) => port.path === targetPath && port.symbol === symbol);
  if (index < 0) { console.error(`no port for ${targetPath}:${symbol}`); return 1; }
  ports.splice(index, 1);
  return refuseOrWrite(model, "boundaries", model.boundaries);
}

async function trackedPaths(root) {
  try { return new Set(await listTracked(root)); }
  catch { return undefined; }
}

async function addComponent(model, plain, kv, root) {
  const [id, name] = plain;
  const entry = {
    id,
    name,
    paths: kv.paths ?? [],
    enforcement: kv.enforcement ?? "none",
    releaseUnit: kv.release ?? "",
    entryPoints: kv.entry ?? [],
  };
  model.components.components.push(entry);
  return refuseOrWrite(model, "components", model.components, await trackedPaths(root));
}

function addRule(model, kv) {
  const entry = { match: kv.match, ring: kv.ring, kind: kv.kind, actors: kv.actors ?? [] };
  const rules = model.rules.rules;
  let insertAt = rules.length;
  if (kv.before !== undefined) {
    const index = rules.findIndex((rule) => rule.match === kv.before);
    if (index >= 0) insertAt = index;
  }
  rules.splice(insertAt, 0, entry);
  return refuseOrWrite(model, "rules", model.rules);
}

function removeRule(model, kv) {
  const rules = model.rules.rules;
  const index = rules.findIndex((rule) => rule.match === kv.match);
  if (index < 0) { console.error(`no rule matching ${kv.match}`); return 1; }
  rules.splice(index, 1);
  return refuseOrWrite(model, "rules", model.rules);
}

function componentReferences(model, id) {
  const references = [];
  for (const port of model.boundaries.ports) if (port.owner === id) references.push(`port ${port.path}:${port.symbol}`);
  for (const shape of model.boundaries.shapes) if (shape.owner === id || (shape.components ?? []).includes(id)) references.push(`shape ${shape.name}`);
  return references;
}

function removeComponent(model, plain) {
  const [id] = plain;
  const components = model.components.components;
  const index = components.findIndex((c) => c.id === id);
  if (index < 0) { console.error(`no component ${id}`); return 1; }
  const references = componentReferences(model, id);
  if (references.length) { console.error(`component ${id} is referenced by ${references.join(", ")}`); return 1; }
  components.splice(index, 1);
  return refuseOrWrite(model, "components", model.components);
}

const EDITS = {
  "add-override": addOverride,
  "remove-override": removeOverride,
  "add-port": addPort,
  "remove-port": removePort,
  "add-component": addComponent,
  "remove-component": removeComponent,
  "add-rule": (model, plain, kv) => addRule(model, kv),
  "remove-rule": (model, plain, kv) => removeRule(model, kv),
};

const REQUIRED = {
  "add-override": ({ plain }) => plain.length >= 1,
  "add-component": ({ plain, kv }) => plain.length >= 2 && kv.paths !== undefined && kv.paths.length > 0,
  "add-rule": ({ kv }) => Boolean(kv.match),
};

export async function run(args, ctx) {
  const { positional, flags } = parseFlags(args);
  const [sub, ...rest] = positional;
  if (!sub) { console.error(USAGE); return 1; }
  if (sub === "validate") return validate(flags, ctx);

  const edit = EDITS[sub];
  if (!edit) {
    console.error(`unknown model subcommand: ${sub}; known: validate, ${Object.keys(EDITS).join(", ")}`);
    return 1;
  }
  const { kv, plain } = splitArgs(rest);
  if (REQUIRED[sub] && !REQUIRED[sub]({ plain, kv })) { console.error(EDIT_USAGE[sub]); return 1; }
  const model = await loadModel(ctx.root);
  return edit(model, plain, kv, ctx.root);
}
