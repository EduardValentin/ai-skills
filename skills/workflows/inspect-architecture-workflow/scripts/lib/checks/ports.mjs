export function declaredPortSymbols(context) {
  return new Set(context.model.ports.map((port) => port.symbol));
}

export function implementedPorts(context, path) {
  const declared = declaredPortSymbols(context);
  return (context.unitOf(path)?.implements ?? []).filter((symbol) => declared.has(symbol));
}

export function portSymbolsOwnedBy(context, componentName) {
  return new Set(context.model.ports.filter((port) => port.owner === componentName).map((port) => port.symbol));
}

export function portsImplementedBy(context, path) {
  const implemented = new Set(context.unitOf(path)?.implements ?? []);
  return context.model.ports.filter((port) => implemented.has(port.symbol));
}

export function portDeclaredIn(context, path) {
  return context.model.ports.find((port) => port.path === path) ?? null;
}

export function existingPort(port) {
  return `the existing port \`${port.symbol}\` in \`${port.path}\``;
}
