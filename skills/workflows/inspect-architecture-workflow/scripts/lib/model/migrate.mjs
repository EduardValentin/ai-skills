import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { ModelError } from "../cli/errors.mjs";
import { DEFAULT_KINDS, DEFAULT_RINGS } from "./defaults.mjs";
import { documentProblems, recordDir } from "./load.mjs";
import { writeCanonical } from "./write.mjs";

const OLD_FILES = ["components", "rules", "overrides", "boundaries"];
const PLACEHOLDER_ADAPTER = "placeholder";

function oldFile(directory, name) {
  return join(directory, "model", `${name}.json`);
}

function readOldModel(directory) {
  const missing = OLD_FILES.filter((name) => !existsSync(oldFile(directory, name)));
  if (missing.length > 0) {
    const listed = missing.map((name) => `${name}.json`).join(", ");
    throw new ModelError(
      `no old model to migrate: ${listed} not found under ${join(directory, "model")}. ` +
        "Check the record path (--record or ARCH_RECORD_DIR).",
    );
  }
  const read = (name) => JSON.parse(readFileSync(oldFile(directory, name), "utf8"));
  return Object.fromEntries(OLD_FILES.map((name) => [name, read(name)]));
}

function literalDirectory(glob) {
  const literal = glob.split(/[*?{]/)[0];
  return literal.slice(0, literal.lastIndexOf("/") + 1);
}

function relativeTo(component, path) {
  const prefix = component.paths.map(literalDirectory).find((directory) => path.startsWith(directory));
  return prefix === undefined ? null : path.slice(prefix.length);
}

function prefixLength(component, path) {
  const matching = component.paths.map(literalDirectory).filter((directory) => path.startsWith(directory));
  return Math.max(-1, ...matching.map((directory) => directory.length));
}

function owner(components, path) {
  const ranked = components
    .map((component) => ({ component, length: prefixLength(component, path) }))
    .filter((candidate) => candidate.length >= 0)
    .sort((a, b) => b.length - a.length);
  if (ranked.length > 0) {
    const { component } = ranked[0];
    return { component, relative: path.slice(ranked[0].length) };
  }
  throw new ModelError(
    `the old model has "${path}", which falls under no component. ` +
      "Add a component that covers it or remove that entry from the old files, then run migrate again.",
  );
}

function extrasOf(entry) {
  const extras = {};
  if (entry.ring !== DEFAULT_KINDS[entry.kind].ring) extras.ring = entry.ring;
  if ((entry.actors ?? []).length > 0) extras.actors = entry.actors;
  if (entry.reason) extras.reason = entry.reason;
  return extras;
}

function pairOf(entry, pattern) {
  if (!Object.hasOwn(DEFAULT_KINDS, entry.kind)) {
    throw new ModelError(
      `the old model uses kind "${entry.kind}", which is not a known kind. ` +
        "Change it to a known kind in the old files, then run migrate again.",
    );
  }
  const extras = extrasOf(entry);
  return Object.keys(extras).length === 0 ? [pattern, entry.kind] : [pattern, entry.kind, extras];
}

function pairsByComponent(components, entries, globOf) {
  const pairs = new Map(components.map((component) => [component.name, []]));
  for (const entry of entries) {
    const { component, relative } = owner(components, globOf(entry));
    pairs.get(component.name).push(pairOf(entry, relative));
  }
  return pairs;
}

function entryPaths(component, oldComponent) {
  return (oldComponent.entryPoints ?? []).map((path) => relativeTo(component, path) ?? path);
}

function convertComponents(old) {
  const base = old.components.components.map((component) => ({ name: component.name, paths: component.paths }));
  const overrides = pairsByComponent(base, old.overrides.overrides, (entry) => entry.path);
  const rules = pairsByComponent(base, old.rules.rules, (entry) => entry.match);
  return base.map((component, index) => {
    const oldComponent = old.components.components[index];
    return {
      ...component,
      entry: entryPaths(component, oldComponent),
      enforcement: oldComponent.enforcement,
      release: oldComponent.releaseUnit,
      classify: [...overrides.get(component.name), ...rules.get(component.name)],
    };
  });
}

function namesById(old) {
  return new Map(old.components.components.map((component) => [component.id, component.name]));
}

function convertPorts(old) {
  const names = namesById(old);
  return old.boundaries.ports.map((port) => ({
    at: `${port.path}#${port.symbol}`,
    owner: names.get(port.owner),
    ...(port.humbleSide && { humble: port.humbleSide }),
  }));
}

function convertShapes(old) {
  const names = namesById(old);
  return (old.boundaries.shapes ?? []).map((shape) => {
    const converted = { ...shape };
    if (shape.owner !== undefined) converted.owner = names.get(shape.owner) ?? shape.owner;
    if (shape.components !== undefined) converted.components = shape.components.map((id) => names.get(id) ?? id);
    return converted;
  });
}

function convertGroups(old) {
  const names = namesById(old);
  return (old.boundaries.groups ?? []).map((group) => ({
    name: group.name,
    members: group.components.map((id) => names.get(id)),
    absorbs: group.absorbs,
  }));
}

function convertOldModel(old, recordMode) {
  return {
    version: 2,
    adapter: "",
    record: recordMode,
    rings: old.rules.rings ?? DEFAULT_RINGS,
    frameworks: old.rules.frameworks ?? [],
    components: convertComponents(old),
    ports: convertPorts(old),
    shapes: convertShapes(old),
    groups: convertGroups(old),
  };
}

export function migrateOldModel({ root, flags, file, recordMode }) {
  if (existsSync(file)) {
    throw new ModelError(`${file} already exists. Delete it first if you want to convert the old files again.`);
  }
  const old = readOldModel(recordDir(root, flags));
  const document = convertOldModel(old, recordMode);
  const problems = documentProblems({ ...document, adapter: PLACEHOLDER_ADAPTER });
  if (problems.length > 0) {
    throw new ModelError(`the old model converts to an invalid model:\n- ${problems.join("\n- ")}\nFix the old files.`);
  }
  writeCanonical(file, document);
}
