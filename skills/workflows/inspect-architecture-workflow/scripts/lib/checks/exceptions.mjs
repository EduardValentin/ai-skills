const RING_PREFIX = "ring:";

export function subjectOf(level, name, context) {
  if (level === "component") return { path: null, component: name, ring: null };
  const unit = context.unitOf(name);
  return { path: name, component: unit?.component ?? null, ring: unit?.ring ?? null };
}

export function endMatches(end, subject) {
  if (end.startsWith(RING_PREFIX)) return end.slice(RING_PREFIX.length) === subject.ring;
  return end === subject.path || end === subject.component;
}

function covers(exception, row, context) {
  if (exception.rule && !row.rules.includes(exception.rule)) return false;
  const from = subjectOf(row.edge.level, row.edge.from, context);
  const to = subjectOf(row.edge.level, row.edge.to, context);
  return endMatches(exception.from, from) && endMatches(exception.to, to);
}

export function isCoveredByException(row, context) {
  if (!row.edge) return false;
  return context.model.exceptions.some((exception) => covers(exception, row, context));
}
