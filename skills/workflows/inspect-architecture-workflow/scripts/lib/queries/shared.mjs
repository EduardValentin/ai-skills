export const NOT_PROVIDED = "not provided by the adapter";

export function unitsByPath(graph) {
  return new Map(graph.units.map((unit) => [unit.path, unit]));
}

export function provides(graph, fact) {
  return Boolean(graph.capabilities?.[fact]);
}

export function notProvided(fact) {
  return { notProvided: fact };
}

export function table(columns, rows, extra = {}) {
  return { columns, rows, ...extra };
}
