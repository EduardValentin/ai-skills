import { readFileSync } from "node:fs";
import { DEFAULT_KINDS, DEFAULT_RINGS, DEFAULT_THRESHOLDS, RULE_COUNT } from "./defaults.mjs";
import { validateShape } from "./validate-shape.mjs";

const SCHEMA_URL = new URL("../../../assets/architecture.schema.json", import.meta.url);
const RING_PREFIX = "ring:";
const RULE_KEY = /^R([0-9]+)(?:@(.+))?$/;

export function readSchema() {
  return JSON.parse(readFileSync(SCHEMA_URL, "utf8"));
}

function literalPrefix(glob) {
  return glob.split(/[*?{]/)[0];
}

function globsOverlap(a, b) {
  if (a === b) return true;
  if (!a.endsWith("**") || !b.endsWith("**")) return false;
  const prefixA = literalPrefix(a);
  const prefixB = literalPrefix(b);
  return prefixA.startsWith(prefixB) || prefixB.startsWith(prefixA);
}

function duplicates(names) {
  return names.filter((name, index) => names.indexOf(name) !== index);
}

function componentProblems(components) {
  const problems = duplicates(components.map((component) => component.name))
    .map((name) => `components: duplicate component name "${name}". Give each component a unique name.`);
  components.forEach((a, indexA) => {
    components.slice(indexA + 1).forEach((b) => {
      const clash = a.paths.flatMap((pathA) => b.paths.map((pathB) => [pathA, pathB]))
        .find(([pathA, pathB]) => globsOverlap(pathA, pathB));
      if (clash) {
        problems.push(
          `components: path globs overlap between "${a.name}" (${clash[0]}) and "${b.name}" (${clash[1]}). ` +
            "Narrow one glob so a file belongs to one component.",
        );
      }
    });
  });
  return problems;
}

function knownKinds(doc) {
  return { ...DEFAULT_KINDS, ...(doc.kinds ?? {}) };
}

function kindProblems(doc) {
  const rings = doc.rings ?? DEFAULT_RINGS;
  return Object.entries(doc.kinds ?? {})
    .filter(([, kind]) => kind.role !== "neutral" && !rings.includes(kind.ring))
    .map(([name, kind]) => `kinds.${name}.ring: "${kind.ring ?? ""}" must be one of the rings: ${rings.join(", ")}.`);
}

function pairProblems(doc) {
  const kinds = knownKinds(doc);
  const rings = doc.rings ?? DEFAULT_RINGS;
  const problems = [];
  (doc.components ?? []).forEach((component, componentIndex) => {
    (component.classify ?? []).forEach((pair, pairIndex) => {
      const at = `components[${componentIndex}].classify[${pairIndex}]`;
      if (!Object.hasOwn(kinds, pair[1])) {
        problems.push(
          `${at}: unknown kind "${pair[1]}". Use one of ${Object.keys(kinds).join(", ")} or declare it under kinds.`,
        );
      }
      const ring = pair[2]?.ring;
      if (ring !== undefined && !rings.includes(ring)) {
        problems.push(`${at}.ring: "${ring}" is not one of the rings: ${rings.join(", ")}.`);
      }
    });
  });
  return problems;
}

function ruleProblems(doc) {
  const names = new Set((doc.components ?? []).map((component) => component.name));
  const problems = [];
  for (const key of Object.keys(doc.rules ?? {})) {
    const match = RULE_KEY.exec(key);
    const number = match ? Number(match[1]) : 0;
    if (!match || number < 1 || number > RULE_COUNT) {
      problems.push(
        `rules.${key}: not a rule key. Use R1 to R${RULE_COUNT}, optionally followed by @<component>.`,
      );
    } else if (match[2] && !names.has(match[2])) {
      problems.push(`rules.${key}: "${match[2]}" is not a component. Use one of ${[...names].join(", ")}.`);
    }
  }
  return problems;
}

function thresholdProblems(doc) {
  const knobs = Object.keys(DEFAULT_THRESHOLDS);
  return Object.keys(doc.thresholds ?? {})
    .filter((key) => !knobs.includes(key))
    .map((key) => `thresholds.${key}: not a known threshold. Use one of ${knobs.join(", ")}.`);
}

function edgeProblems(doc) {
  const rings = doc.rings ?? DEFAULT_RINGS;
  const edges = [...(doc.forbidden ?? []), ...(doc.exceptions ?? [])];
  const ends = edges.flatMap((edge) => [edge.from, edge.to]);
  return ends
    .filter((end) => end.startsWith(RING_PREFIX) && !rings.includes(end.slice(RING_PREFIX.length)))
    .map((end) => `${end}: not a ring. Use ${RING_PREFIX}<ring> with one of ${rings.join(", ")}.`);
}

function referenceProblems(doc) {
  const names = new Set((doc.components ?? []).map((component) => component.name));
  const problems = [];
  (doc.ports ?? []).forEach((port, index) => {
    if (!names.has(port.owner)) {
      problems.push(`ports[${index}].owner: "${port.owner}" is not a component. Use one of ${[...names].join(", ")}.`);
    }
  });
  (doc.groups ?? []).forEach((group, index) => {
    const missing = group.members.filter((member) => !names.has(member));
    if (missing.length > 0) {
      problems.push(`groups[${index}].members: ${missing.join(", ")} not a component. Use component names.`);
    }
  });
  return problems;
}

export function modelProblems(doc) {
  const shape = validateShape(doc, readSchema());
  if (shape.length > 0) return shape;
  return [
    ...componentProblems(doc.components),
    ...kindProblems(doc),
    ...pairProblems(doc),
    ...ruleProblems(doc),
    ...thresholdProblems(doc),
    ...referenceProblems(doc),
    ...edgeProblems(doc),
  ];
}
