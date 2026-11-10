import { writeFileSync } from "node:fs";
import { ModelError } from "../cli/errors.mjs";
import { DEFAULT_RINGS, DEFAULT_THRESHOLDS } from "./defaults.mjs";
import { adapterHint, documentProblems } from "./load.mjs";

const COMPONENT_FIELDS = ["name", "paths", "entry", "published", "enforcement", "release"];
const COMPONENT_DEFAULTS = { entry: [], published: [], enforcement: "none", release: "" };
const PAIR_EXTRAS = ["ring", "actors", "reason", "valueType"];
const ENTRY_FIELDS = {
  ports: ["at", "owner", "humble", "defers"],
  groups: ["name", "members", "absorbs"],
  forbidden: ["from", "to", "reason"],
  exceptions: ["from", "to", "rule", "reason"],
};
const LIST_SECTIONS = ["components", "ports", "shapes", "groups", "forbidden", "exceptions"];
const MAP_SECTIONS = ["kinds", "rules", "thresholds"];
const SCALAR_SECTIONS = ["version", "adapter", "record", "rings", "frameworks", "upcoming"];
const SECTION_ORDER = [
  "version", "adapter", "record", "rings", "kinds", "frameworks", "components", "ports",
  "shapes", "groups", "rules", "thresholds", "forbidden", "exceptions", "upcoming",
];

function isEmpty(value) {
  if (value === undefined) return true;
  if (Array.isArray(value)) return value.length === 0;
  if (value !== null && typeof value === "object") return Object.keys(value).length === 0;
  return false;
}

function inline(value) {
  if (Array.isArray(value)) return `[${value.map(inline).join(", ")}]`;
  if (value !== null && typeof value === "object") {
    const fields = Object.entries(value).map(([key, child]) => `${JSON.stringify(key)}: ${inline(child)}`);
    return fields.length === 0 ? "{}" : `{ ${fields.join(", ")} }`;
  }
  return JSON.stringify(value);
}

function pick(object, keys) {
  const picked = {};
  for (const key of keys) {
    if (!isEmpty(object[key])) picked[key] = object[key];
  }
  return picked;
}

function canonicalPair([pattern, kind, extras]) {
  const kept = pick(extras ?? {}, PAIR_EXTRAS);
  if (kept.valueType === false) delete kept.valueType;
  return isEmpty(kept) ? [pattern, kind] : [pattern, kind, kept];
}

function differsFromDefault(component, key) {
  const value = component[key];
  if (isEmpty(value)) return false;
  return JSON.stringify(value) !== JSON.stringify(COMPONENT_DEFAULTS[key]);
}

function isRequiredField(key) {
  return key === "name" || key === "paths";
}

function componentText(component) {
  const fields = COMPONENT_FIELDS.filter((key) => isRequiredField(key) || differsFromDefault(component, key));
  const head = fields.map((key) => `${JSON.stringify(key)}: ${inline(component[key])}`).join(", ");
  const pairs = (component.classify ?? []).map(canonicalPair);
  if (pairs.length === 0) return `{ ${head} }`;
  const lines = pairs.map((pair) => `        ${inline(pair)}`).join(",\n");
  return `{ ${head}, "classify": [\n${lines} ] }`;
}

function entryText(section, entry) {
  if (section === "components") return componentText(entry);
  const fields = ENTRY_FIELDS[section];
  return inline(fields ? pick(entry, fields) : entry);
}

function listText(section, entries) {
  const lines = entries.map((entry) => `    ${entryText(section, entry)}`).join(",\n");
  return `[\n${lines}\n  ]`;
}

function ruleOrder(key) {
  const [rule, component = ""] = key.split("@");
  return [Number(rule.slice(1)), component];
}

function compareRuleKeys(a, b) {
  const [numberA, componentA] = ruleOrder(a);
  const [numberB, componentB] = ruleOrder(b);
  return numberA - numberB || componentA.localeCompare(componentB);
}

function orderedEntries(section, map) {
  const keys = Object.keys(map);
  if (section === "rules") return keys.sort(compareRuleKeys).map((key) => [key, map[key]]);
  if (section === "thresholds") {
    return Object.keys(DEFAULT_THRESHOLDS).filter((key) => key in map).map((key) => [key, map[key]]);
  }
  return keys.map((key) => [key, map[key]]);
}

function mapText(section, map) {
  const lines = orderedEntries(section, map).map(([key, value]) => `    ${JSON.stringify(key)}: ${inline(value)}`);
  return `{\n${lines.join(",\n")}\n  }`;
}

function sectionText(section, value) {
  if (LIST_SECTIONS.includes(section)) return listText(section, value);
  if (MAP_SECTIONS.includes(section)) return mapText(section, value);
  return inline(value);
}

function isDefaultRings(section, value) {
  return section === "rings" && JSON.stringify(value) === JSON.stringify(DEFAULT_RINGS);
}

function isKept(section, value) {
  if (section === "components") return true;
  if (SCALAR_SECTIONS.includes(section) && !Array.isArray(value)) return true;
  return !isEmpty(value) && !isDefaultRings(section, value);
}

export function canonicalJson(doc) {
  const lines = SECTION_ORDER
    .filter((section) => doc[section] !== undefined && isKept(section, doc[section]))
    .map((section) => `  ${JSON.stringify(section)}: ${sectionText(section, doc[section])}`);
  return `{\n${lines.join(",\n")}\n}\n`;
}

export function writeCanonical(file, doc) {
  writeFileSync(file, canonicalJson(doc));
}

export function writeDocument(file, doc) {
  const problems = documentProblems(doc);
  if (problems.length > 0) {
    const listed = problems.join("\n- ");
    const advice = `Correct the arguments and run again.${adapterHint(problems)}`;
    throw new ModelError(`edit refused, ${file} left unchanged:\n- ${listed}\n${advice}`);
  }
  writeCanonical(file, doc);
}
