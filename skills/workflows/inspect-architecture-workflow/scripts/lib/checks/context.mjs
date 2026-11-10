export function createContext({ graph, model, baseGraph = null, touched = null }) {
  const units = new Map(graph.units.map((unit) => [unit.path, unit]));
  const unitOf = (path) => units.get(path);
  const componentOf = (path) => units.get(path)?.component ?? null;
  const roleOf = (path) => {
    const kind = units.get(path)?.kind;
    return kind ? (model.kinds[kind]?.role ?? null) : null;
  };
  return { graph, model, baseGraph, touched, unitOf, componentOf, roleOf };
}

export function touchesBarrel(context, fromPath, toPath) {
  return context.unitOf(fromPath)?.kind === "barrel" || context.unitOf(toPath)?.kind === "barrel";
}

function unique(values) {
  return [...new Set(values)];
}

export function rowComponents(row, context) {
  if (row.edge?.level === "unit") return unique([context.componentOf(row.edge.from)].filter(Boolean));
  const ofUnits = row.units.map(context.componentOf).filter(Boolean);
  return unique([...row.components, ...ofUnits]);
}
