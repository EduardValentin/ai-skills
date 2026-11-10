import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { ModelError } from "../cli/errors.mjs";
import { resolvePairRing } from "./classify.mjs";
import { DEFAULT_KINDS, DEFAULT_RINGS, DEFAULT_THRESHOLDS } from "./defaults.mjs";
import { modelProblems } from "./schema.mjs";

const DEFAULT_RECORD_DIR = "docs/architecture";
const MODEL_FILE = "architecture.json";

export function recordDir(root, flags = {}) {
  const chosen = flags.record ?? process.env.ARCH_RECORD_DIR ?? DEFAULT_RECORD_DIR;
  return resolve(root, chosen);
}

export function modelFile(root, flags = {}) {
  return resolve(recordDir(root, flags), MODEL_FILE);
}

export function readDocument(file) {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch (error) {
    throw new ModelError(
      `${file} is not valid JSON: ${error.message}. Fix the syntax or restore it from version control.`,
    );
  }
}

function normalizePair([pattern, kind, extras = {}]) {
  return { pattern, kind, ...extras, valueType: extras.valueType ?? false };
}

function normalizeComponent(component) {
  return {
    name: component.name,
    paths: component.paths,
    entry: component.entry ?? [],
    published: component.published ?? [],
    enforcement: component.enforcement ?? "none",
    release: component.release ?? "",
    classify: (component.classify ?? []).map(normalizePair),
  };
}

function normalizePort(port) {
  const [path, symbol] = port.at.split("#");
  const optional = Object.fromEntries(["humble", "defers"].filter((key) => port[key]).map((key) => [key, port[key]]));
  return { at: port.at, path, symbol, owner: port.owner, ...optional };
}

function normalizeRules(rules = {}) {
  return Object.fromEntries(
    Object.entries(rules).map(([key, [status, reason]]) => {
      const component = key.split("@")[1];
      return [key, { status, reason, ...(component && { component }) }];
    }),
  );
}

function normalizeGroup(group) {
  return { name: group.name, members: group.members, absorbs: group.absorbs };
}

function normalize(doc) {
  return {
    version: doc.version,
    adapter: doc.adapter,
    record: doc.record ?? "committed",
    rings: doc.rings ?? [...DEFAULT_RINGS],
    kinds: { ...DEFAULT_KINDS, ...(doc.kinds ?? {}) },
    frameworks: doc.frameworks ?? [],
    components: doc.components.map(normalizeComponent),
    ports: (doc.ports ?? []).map(normalizePort),
    shapes: doc.shapes ?? [],
    groups: (doc.groups ?? []).map(normalizeGroup),
    rules: normalizeRules(doc.rules),
    thresholds: { ...DEFAULT_THRESHOLDS, ...(doc.thresholds ?? {}) },
    forbidden: doc.forbidden ?? [],
    exceptions: doc.exceptions ?? [],
    upcoming: doc.upcoming ?? [],
  };
}

function ringProblems(model) {
  const problems = [];
  model.components.forEach((component, componentIndex) => {
    component.classify.forEach((pair, pairIndex) => {
      if (resolvePairRing(model, component, pair)) return;
      problems.push(
        `components[${componentIndex}].classify[${pairIndex}]: kind "${pair.kind}" has no default ring and ` +
          `the other pairs of "${component.name}" do not share one. Add { "ring": "<ring>" } to the pair.`,
      );
    });
  });
  return problems;
}

export function documentProblems(doc) {
  const problems = modelProblems(doc);
  if (problems.length > 0) return problems;
  return ringProblems(normalize(doc));
}

export function loadModel(root, flags = {}) {
  const file = modelFile(root, flags);
  if (!existsSync(file)) return null;
  const doc = readDocument(file);
  const problems = documentProblems(doc);
  if (problems.length > 0) {
    const listed = problems.join("\n- ");
    throw new ModelError(`${file} is invalid:\n- ${listed}\nFix these entries and run the command again.`);
  }
  return normalize(doc);
}
