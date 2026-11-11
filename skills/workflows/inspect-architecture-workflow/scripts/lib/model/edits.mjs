import { UsageError } from "../cli/errors.mjs";
import { ANY_DESTINATION, DEFAULT_THRESHOLDS } from "./defaults.mjs";

function splitList(text) {
  return text.split(",").map((item) => item.trim()).filter((item) => item.length > 0);
}

function names(items) {
  return items.map((item) => item.name).join(", ");
}

function section(doc, name) {
  doc[name] ??= [];
  return doc[name];
}

function dropEmptySection(doc, name) {
  if (Array.isArray(doc[name]) && doc[name].length === 0) delete doc[name];
  if (doc[name] && !Array.isArray(doc[name]) && Object.keys(doc[name]).length === 0) delete doc[name];
}

function upsert(list, matches, entry) {
  const index = list.findIndex(matches);
  if (index === -1) list.push(entry);
  else list[index] = entry;
}

function removeOrRefuse(doc, name, matches, description) {
  const list = doc[name] ?? [];
  const kept = list.filter((entry) => !matches(entry));
  if (kept.length === list.length) throw new UsageError(`there is no ${description}. Nothing was changed.`);
  doc[name] = kept;
  dropEmptySection(doc, name);
}

function findComponent(doc, name) {
  const component = doc.components.find((candidate) => candidate.name === name);
  if (component) {
    component.classify ??= [];
    return component;
  }
  throw new UsageError(`there is no component "${name}". Components: ${names(doc.components)}.`);
}

function addComponent(doc, [name], { paths }) {
  if (doc.components.some((component) => component.name === name)) {
    throw new UsageError(`component "${name}" already exists. Choose another name or remove it first.`);
  }
  doc.components.push({ name, paths: splitList(paths), classify: [] });
}

function removeComponent(doc, [name]) {
  findComponent(doc, name);
  doc.components = doc.components.filter((component) => component.name !== name);
}

function parseValueType(text) {
  if (text === "true" || text === "false") return text === "true";
  throw new UsageError(`value-type must be true or false, got "${text}". Pass value-type=true or value-type=false.`);
}

function pairExtras(keys) {
  const extras = {};
  if (keys.ring) extras.ring = keys.ring;
  if (keys.actors) extras.actors = splitList(keys.actors);
  if (keys.reason) extras.reason = keys.reason;
  if (keys["value-type"] !== undefined && parseValueType(keys["value-type"])) extras.valueType = true;
  return extras;
}

function indexOfPattern(classify, pattern) {
  return classify.findIndex(([existing]) => existing === pattern);
}

function pairPosition(classify, pattern, before) {
  if (before === undefined) return classify.length;
  const index = indexOfPattern(classify, before);
  if (index === -1) throw new UsageError(`before=${before} matches no pattern of the component. Nothing was changed.`);
  return index;
}

function classify(doc, [componentName, pattern, kind], keys) {
  const component = findComponent(doc, componentName);
  const extras = pairExtras(keys);
  const pair = Object.keys(extras).length === 0 ? [pattern, kind] : [pattern, kind, extras];
  const current = indexOfPattern(component.classify, pattern);
  if (current !== -1 && keys.before === undefined) {
    component.classify[current] = pair;
    return;
  }
  const others = component.classify.filter(([existing]) => existing !== pattern);
  others.splice(pairPosition(others, pattern, keys.before), 0, pair);
  component.classify = others;
}

function unclassify(doc, [componentName, pattern]) {
  const component = findComponent(doc, componentName);
  const kept = component.classify.filter(([existing]) => existing !== pattern);
  if (kept.length === component.classify.length) {
    throw new UsageError(`component "${componentName}" has no pattern "${pattern}". Nothing was changed.`);
  }
  component.classify = kept;
}

function addPort(doc, [at], keys) {
  const entry = { at, owner: keys.owner };
  if (keys.humble) entry.humble = keys.humble;
  if (keys.defers) entry.defers = keys.defers;
  upsert(section(doc, "ports"), (port) => port.at === at, entry);
}

function removePort(doc, [at]) {
  removeOrRefuse(doc, "ports", (port) => port.at === at, `port ${at}`);
}

function addGroup(doc, [name], keys) {
  const entry = { name, members: splitList(keys.members), absorbs: keys.absorbs };
  upsert(section(doc, "groups"), (group) => group.name === name, entry);
}

function removeGroup(doc, [name]) {
  removeOrRefuse(doc, "groups", (group) => group.name === name, `group "${name}"`);
}

function setRule(doc, [key, status], { reason }) {
  doc.rules ??= {};
  doc.rules[key] = [status, reason];
}

function unsetRule(doc, [key]) {
  if (!doc.rules || !Object.hasOwn(doc.rules, key)) {
    throw new UsageError(`rule ${key} has no entry in the model, so it already has its default status.`);
  }
  delete doc.rules[key];
  dropEmptySection(doc, "rules");
}

function knobList() {
  return Object.keys(DEFAULT_THRESHOLDS).join(", ");
}

function requireKnob(knob) {
  if (Object.hasOwn(DEFAULT_THRESHOLDS, knob)) return;
  throw new UsageError(`unknown threshold "${knob}". Use one of ${knobList()}.`);
}

function parseThresholdValue(knob, text) {
  if (typeof DEFAULT_THRESHOLDS[knob] === "string") return text;
  const value = Number(text);
  if (text.trim() === "" || !Number.isFinite(value)) {
    throw new UsageError(`threshold "${knob}" needs a number, got "${text}". Pass a number.`);
  }
  return value;
}

function setThreshold(doc, [knob, text]) {
  requireKnob(knob);
  doc.thresholds ??= {};
  doc.thresholds[knob] = parseThresholdValue(knob, text);
}

function unsetThreshold(doc, [knob]) {
  requireKnob(knob);
  if (!doc.thresholds || !Object.hasOwn(doc.thresholds, knob)) {
    throw new UsageError(`threshold "${knob}" is not set in the model, so it already uses its default.`);
  }
  delete doc.thresholds[knob];
  dropEmptySection(doc, "thresholds");
}

function sameEnds(from, to) {
  return (entry) => entry.from === from && entry.to === to;
}

function addForbiddenEdge(doc, [from, to], { reason }) {
  upsert(section(doc, "forbidden"), sameEnds(from, to), { from, to, reason });
}

function removeForbiddenEdge(doc, [from, to]) {
  removeOrRefuse(doc, "forbidden", sameEnds(from, to), `forbidden edge ${from} -> ${to}`);
}

const EXTERNAL_PREFIX = "external:";

function requireValidExceptionEnds(from, to) {
  if (from === ANY_DESTINATION) {
    throw new UsageError(
      `an exception cannot start at "${ANY_DESTINATION}": only its "to" end may be "${ANY_DESTINATION}". ` +
        "Put the unit, port, component, or ring it accepts first.",
    );
  }
  if (from.startsWith(EXTERNAL_PREFIX)) {
    throw new UsageError(
      `an exception cannot start at ${from}: only its "to" end may be an external. ` +
        "Put the importing component, ring, or path first.",
    );
  }
  if (to.startsWith(EXTERNAL_PREFIX) && to.length === EXTERNAL_PREFIX.length) {
    throw new UsageError(`"${to}" names no external. Write external:<name>, for example external:lodash.`);
  }
}

function addException(doc, [from, to], keys) {
  requireValidExceptionEnds(from, to);
  const entry = { from, to, ...(keys.rule && { rule: keys.rule }), reason: keys.reason };
  const matches = (existing) => sameEnds(from, to)(existing) && existing.rule === keys.rule;
  upsert(section(doc, "exceptions"), matches, entry);
}

function describeException(exception) {
  return `${exception.from} -> ${exception.to}${exception.rule ? ` rule=${exception.rule}` : " (no rule)"}`;
}

function selectException(doc, from, to, rule) {
  const matching = (doc.exceptions ?? []).filter(sameEnds(from, to));
  if (matching.length === 0) throw new UsageError(`there is no exception ${from} -> ${to}. Nothing was changed.`);
  if (rule !== undefined) return (exception) => sameEnds(from, to)(exception) && exception.rule === rule;
  if (matching.length > 1 && matching.every((exception) => exception.rule)) {
    const listed = matching.map(describeException).join("; ");
    throw new UsageError(`several exceptions match: ${listed}. Choose one with rule=<R>.`);
  }
  return (exception) => sameEnds(from, to)(exception) && !exception.rule;
}

function removeException(doc, [from, to], { rule }) {
  const matches = selectException(doc, from, to, rule);
  removeOrRefuse(doc, "exceptions", matches, `exception ${from} -> ${to}${rule ? ` rule=${rule}` : ""}`);
}

function addUpcoming(doc, [text]) {
  if ((doc.upcoming ?? []).includes(text)) {
    throw new UsageError(`the upcoming change "${text}" is already recorded. Nothing was changed.`);
  }
  section(doc, "upcoming").push(text);
}

function removeUpcoming(doc, [text]) {
  removeOrRefuse(doc, "upcoming", (entry) => entry === text, `upcoming change "${text}"`);
}

function setAdapter(doc, [command]) {
  doc.adapter = command;
}

function edit(usage, positional, keys, apply) {
  return { usage, positional, required: keys.required ?? [], optional: keys.optional ?? [], apply };
}

export const EDITS = {
  "add-component": edit("arch model add-component <name> paths=<globs>", 1, { required: ["paths"] }, addComponent),
  "remove-component": edit("arch model remove-component <name>", 1, {}, removeComponent),
  classify: edit(
    "arch model classify <component> <pattern> <kind> [ring=<ring>] [actors=<a,b>] [reason=<text>] " +
      "[value-type=true] [before=<pattern>]",
    3,
    { optional: ["ring", "actors", "reason", "value-type", "before"] },
    classify,
  ),
  unclassify: edit("arch model unclassify <component> <pattern>", 2, {}, unclassify),
  "add-port": edit(
    "arch model add-port <path>#<Symbol> owner=<component> [humble=<ring>] [defers=<text>]",
    1,
    { required: ["owner"], optional: ["humble", "defers"] },
    addPort,
  ),
  "remove-port": edit("arch model remove-port <path>#<Symbol>", 1, {}, removePort),
  "add-group": edit(
    "arch model add-group <name> members=<a,b> absorbs=<text>",
    1,
    { required: ["members", "absorbs"] },
    addGroup,
  ),
  "remove-group": edit("arch model remove-group <name>", 1, {}, removeGroup),
  "set-rule": edit(
    "arch model set-rule <R>[@<component>] <enforced|advisory|off> reason=<text>",
    2,
    { required: ["reason"] },
    setRule,
  ),
  "set-threshold": edit("arch model set-threshold <knob> <value>", 2, {}, setThreshold),
  "unset-threshold": edit("arch model unset-threshold <knob>", 1, {}, unsetThreshold),
  "add-forbidden-edge": edit(
    "arch model add-forbidden-edge <from> <to> reason=<text>",
    2,
    { required: ["reason"] },
    addForbiddenEdge,
  ),
  "remove-forbidden-edge": edit("arch model remove-forbidden-edge <from> <to>", 2, {}, removeForbiddenEdge),
  "add-exception": edit(
    "arch model add-exception <from> <to> [rule=<R>] reason=<text>",
    2,
    { required: ["reason"], optional: ["rule"] },
    addException,
  ),
  "remove-exception": edit(
    "arch model remove-exception <from> <to> [rule=<R>]",
    2,
    { optional: ["rule"] },
    removeException,
  ),
  "unset-rule": edit("arch model unset-rule <R>[@<component>]", 1, {}, unsetRule),
  "add-upcoming": edit("arch model add-upcoming <text>", 1, {}, addUpcoming),
  "remove-upcoming": edit("arch model remove-upcoming <text>", 1, {}, removeUpcoming),
  "set-adapter": edit("arch model set-adapter <command>", 1, {}, setAdapter),
};
