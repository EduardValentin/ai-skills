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
