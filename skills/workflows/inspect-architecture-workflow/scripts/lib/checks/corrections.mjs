import { existingPort, portDeclaredIn, portSymbolsOwnedBy, portsImplementedBy } from "./ports.mjs";

const EXTERNAL_PREFIX = "external:";

export function externalName(end) {
  return end.startsWith(EXTERNAL_PREFIX) ? end.slice(EXTERNAL_PREFIX.length) : end;
}

function existingPortInstead(port, from, to) {
  return `${existingPort(port)} instead of ${to}, and have the composition root pass ${to} to ${from}`;
}

export function dependOnExistingPort(port, from, to) {
  return `Depend on ${existingPortInstead(port, from, to)}`;
}

export function removeForExistingPort(port, from, to) {
  return `Remove the dependency of ${from} on ${to}: depend on ${existingPortInstead(port, from, to)}`;
}

export function movePortBesideConsumer(port, consumer, ring) {
  return (
    `Move the port \`${port.symbol}\` from ${port.path} beside its consumer ${consumer}, ` +
    `into a ring at least as inner as ${ring}`
  );
}

function portBehindExternal(context, from, name) {
  const owned = portSymbolsOwnedBy(context, context.componentOf(from));
  const importers = (context.graph.externals ?? []).find((external) => external.name === name)?.importers ?? [];
  const ports = importers.flatMap((path) => portsImplementedBy(context, path));
  return ports.find((port) => owned.has(port.symbol)) ?? null;
}

export function removeExternalImport(context, from, name) {
  const owner = context.componentOf(from) ?? from;
  const port = portBehindExternal(context, from, name);
  const throughPort = port
    ? `use ${existingPort(port)}, whose implementation already imports ${name}`
    : `reach ${name} through a port ${owner} declares and code outside it implements`;
  return (
    `Remove the import of ${name} from ${from}; or, when ${name} does no input or output and the project ` +
    `accepts it in its business rules, record it once with arch model add-exception ${owner} external:${name} ` +
    `reason=...; only otherwise ${throughPort}`
  );
}

function ringOf(context, path) {
  return context.unitOf(path)?.ring ?? "its own ring";
}

export function inwardDependencyCorrection(context, from, to) {
  const implemented = portsImplementedBy(context, to)[0];
  if (implemented) return dependOnExistingPort(implemented, from, to);
  const declared = portDeclaredIn(context, to);
  if (declared) return movePortBesideConsumer(declared, from, ringOf(context, from));
  return null;
}
