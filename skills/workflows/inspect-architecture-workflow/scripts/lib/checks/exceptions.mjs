import { ANY_DESTINATION } from "../model/defaults.mjs";

const RING_PREFIX = "ring:";
const PORT_SEPARATOR = "#";
const CYCLE_DEFECT = "cycle";

export function subjectOf(level, name, context) {
  if (level === "component") return { path: null, component: name, ring: null, port: null };
  const unit = context.unitOf(name);
  return { path: name, component: unit?.component ?? null, ring: unit?.ring ?? null, port: null };
}

function subjectOfTarget(target, context) {
  const [path, symbol] = target.split(PORT_SEPARATOR);
  if (symbol !== undefined) return { ...subjectOf("unit", path, context), port: target };
  if (context.unitOf(target)) return subjectOf("unit", target, context);
  if (context.graph.components.some((component) => component.name === target)) {
    return subjectOf("component", target, context);
  }
  return null;
}

export function endMatches(end, subject) {
  if (end.startsWith(RING_PREFIX)) return end.slice(RING_PREFIX.length) === subject.ring;
  return end === subject.path || end === subject.component || end === subject.port;
}

function coversEdge(exception, edge, context) {
  const from = subjectOf(edge.level, edge.from, context);
  const to = subjectOf(edge.level, edge.to, context);
  return endMatches(exception.from, from) && endMatches(exception.to, to);
}

function coversTarget(exception, subject) {
  return exception.to === ANY_DESTINATION && endMatches(exception.from, subject);
}

function covers(exception, row, context) {
  if (exception.rule && !row.rules.includes(exception.rule)) return false;
  if (row.edge) return coversEdge(exception, row.edge, context);
  if (row.defect === CYCLE_DEFECT) return false;
  const subject = subjectOfTarget(row.target, context);
  return subject !== null && coversTarget(exception, subject);
}

export function isCoveredByException(row, context) {
  return context.model.exceptions.some((exception) => covers(exception, row, context));
}
