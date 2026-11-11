import { UsageError } from "../cli/errors.mjs";
import { matchesAny } from "../glob.mjs";
import { relativeToComponent } from "../model/classify.mjs";
import { notProvided, NOT_PROVIDED, provides, table, unitsByPath } from "./shared.mjs";

function implementersOf(graph, symbol) {
  if (!provides(graph, "implements")) return NOT_PROVIDED;
  return graph.units.filter((unit) => (unit.implements ?? []).includes(symbol)).map((u) => u.path).sort().join(", ");
}

function consumersOf(graph, port) {
  const byPath = unitsByPath(graph);
  const modulesByComponent = new Map();
  for (const edge of graph.edges.filter((candidate) => candidate.to === port.path)) {
    const importer = byPath.get(edge.from);
    if (!importer?.component || importer.component === port.owner) continue;
    if (!modulesByComponent.has(importer.component)) modulesByComponent.set(importer.component, new Set());
    modulesByComponent.get(importer.component).add(edge.from);
  }
  return [...modulesByComponent.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, modules]) => `${name} (${modules.size})`)
    .join(", ");
}

export function ports({ graph, model }) {
  const rows = model.ports.map((port) => [
    `${port.path}:${port.symbol}`, port.owner, port.humble ?? null, implementersOf(graph, port.symbol),
    consumersOf(graph, port),
  ]);
  return table(["Port", "Owner", "Humble side", "Implementers", "Consumers (by component)"], rows);
}

function constructedBy(graph, path) {
  return [...new Set(graph.edges.filter((edge) => edge.from === path).map((edge) => edge.to))].sort();
}

function isEntryPoint(component, unit) {
  return unit.component === component.name && matchesAny(relativeToComponent(component, unit.path), component.entry);
}

export function entryPoints({ graph, model }) {
  const rows = model.components
    .filter((component) => component.entry.length > 0)
    .flatMap((component) =>
      graph.units
        .filter((unit) => isEntryPoint(component, unit))
        .map((unit) => [unit.path, component.name, constructedBy(graph, unit.path)]),
    );
  return table(["Path", "Component", "Constructs"], rows);
}

export function signatures({ graph, positional }) {
  const [target] = positional;
  if (!target) throw new UsageError("usage: arch query signatures <path>");
  if (!provides(graph, "signatures")) return notProvided("signatures");
  const unit = graph.units.find((candidate) => candidate.path === target);
  const rows = (unit?.signatures ?? []).flatMap((s) => s.types.map((type) => [s.symbol, type.symbol, type.path]));
  return table(["Symbol", "Type", "From"], rows);
}
