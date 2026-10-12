import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { globToRegExp, matchesAny } from "./glob.mjs";

export const MODEL_DIR = "docs/architecture/model";
export const DEFAULT_RINGS = ["entities", "use-cases", "adapters", "frameworks"];
export const KINDS = ["entity", "use-case", "port", "boundary-data", "controller", "presenter", "gateway", "adapter", "composition-root", "entry-point", "test", "config", "ui", "mixed"];
const FILES = ["components", "rules", "overrides", "boundaries"];
export const HARD_PROBLEM = /overlap|unknown ring|unknown kind|duplicate component|not a component|rings must/;

async function readJson(file) {
  try { return JSON.parse(await readFile(file, "utf8")); }
  catch (error) { throw new Error(`cannot read ${file}: ${error.message}`); }
}

export async function loadModel(root) {
  const dir = path.join(root, MODEL_DIR);
  const [components, rules, overrides, boundaries] = await Promise.all(FILES.map((name) => readJson(path.join(dir, `${name}.json`))));
  return { dir, components, rules, overrides, boundaries };
}

export function componentOf(model, filePath) {
  const hit = model.components.components.find((component) => matchesAny(filePath, component.paths));
  return hit ? hit.id : null;
}

export function classify(model, filePath) {
  const component = componentOf(model, filePath);
  const override = model.overrides.overrides.find((entry) => entry.path === filePath);
  if (override) return { component, ring: override.ring, kind: override.kind, actors: override.actors ?? [], source: "override" };
  const rule = model.rules.rules.find((entry) => globToRegExp(entry.match).test(filePath));
  if (rule) return { component, ring: rule.ring, kind: rule.kind, actors: rule.actors ?? [], source: "rule" };
  return { component, ring: null, kind: null, actors: [], source: null };
}

export function validateModel(model, existingPaths) {
  const problems = [];
  const rings = model.rules.rings ?? DEFAULT_RINGS;
  if (rings.length < 2 || new Set(rings).size !== rings.length) problems.push("rules.json: rings must list at least two distinct rings");
  const ids = new Set();
  for (const component of model.components.components) {
    if (ids.has(component.id)) problems.push(`duplicate component id: ${component.id}`);
    ids.add(component.id);
  }
  const components = model.components.components;
  for (let i = 0; i < components.length; i += 1) {
    for (let j = i + 1; j < components.length; j += 1) {
      const a = components[i], b = components[j];
      const overlapping = existingPaths
        ? [...existingPaths].some((p) => matchesAny(p, a.paths) && matchesAny(p, b.paths))
        : a.paths.some((ga) => b.paths.some((gb) => prefixOverlap(ga, gb)));
      if (overlapping) problems.push(`component globs overlap: ${a.id} and ${b.id}`);
    }
  }
  const checkEntry = (entry, where) => {
    if (!rings.includes(entry.ring)) problems.push(`${where}: unknown ring: ${entry.ring}`);
    if (!KINDS.includes(entry.kind)) problems.push(`${where}: unknown kind: ${entry.kind}`);
  };
  model.rules.rules.forEach((rule, index) => {
    checkEntry(rule, `rule ${index} (${rule.match})`);
    if (existingPaths && ![...existingPaths].some((p) => globToRegExp(rule.match).test(p))) problems.push(`unused rule: ${rule.match}`);
  });
  for (const override of model.overrides.overrides) {
    checkEntry(override, `override ${override.path}`);
    if (existingPaths && !existingPaths.has(override.path)) problems.push(`stale override: ${override.path}`);
  }
  for (const port of model.boundaries.ports) {
    if (!ids.has(port.owner)) problems.push(`port ${port.path}:${port.symbol}: owner is not a component: ${port.owner}`);
    if (port.humbleSide && !rings.includes(port.humbleSide)) problems.push(`port ${port.path}:${port.symbol}: unknown ring: ${port.humbleSide}`);
  }
  for (const shape of model.boundaries.shapes) {
    for (const id of [shape.owner, ...(shape.components ?? [])]) if (!ids.has(id)) problems.push(`shape ${shape.name}: not a component: ${id}`);
  }
  return problems;
}

function literalPrefix(glob) { return glob.split(/[*?{]/)[0]; }
function prefixOverlap(a, b) {
  const pa = literalPrefix(a), pb = literalPrefix(b);
  return a.endsWith("**") && b.endsWith("**") && (pa.startsWith(pb) || pb.startsWith(pa));
}

const SORT_KEYS = { components: ["components", "id"], rules: null, overrides: ["overrides", "path"], boundaries: null };

function inline(value) { return JSON.stringify(value, null, 1).replace(/\n\s*/g, " "); }

export function canonicalJson(name, data) {
  const lines = ["{"];
  const keys = Object.keys(data);
  keys.forEach((key, index) => {
    const value = data[key];
    const comma = index < keys.length - 1 ? "," : "";
    if (Array.isArray(value) && value.length > 0 && typeof value[0] === "object") {
      const sortKey = SORT_KEYS[name] && SORT_KEYS[name][0] === key ? SORT_KEYS[name][1] : null;
      const entries = sortKey ? [...value].sort((a, b) => String(a[sortKey]).localeCompare(String(b[sortKey]), undefined, { numeric: true })) : value;
      lines.push(`  "${key}": [`);
      entries.forEach((entry, i) => lines.push(`    ${inline(entry)}${i < entries.length - 1 ? "," : ""}`));
      lines.push(`  ]${comma}`);
    } else {
      lines.push(`  "${key}": ${inline(value)}${comma}`);
    }
  });
  lines.push("}");
  return `${lines.join("\n")}\n`;
}

export async function writeModelFile(model, name, data) {
  await writeFile(path.join(model.dir, `${name}.json`), canonicalJson(name, data), "utf8");
  model[name] = data;
}
