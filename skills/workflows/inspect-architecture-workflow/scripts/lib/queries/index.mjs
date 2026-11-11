import { requireBase, touched } from "./change.mjs";
import { cycles, componentGraph, components, groups, metrics } from "./components.mjs";
import { volatility } from "./history.mjs";
import { entryPoints, ports, signatures } from "./ports.mjs";
import { edges, externals, fanIn, ringCrossings, units } from "./units-and-edges.mjs";

export const QUERIES = {
  metrics,
  "component-graph": componentGraph,
  cycles,
  "ring-crossings": ringCrossings,
  "fan-in": fanIn,
  edges,
  units,
  components,
  groups,
  touched,
  ports,
  "entry-points": entryPoints,
  signatures,
  externals,
  volatility,
};

export const QUERY_REQUIRED_FLAGS = {
  touched: ["base"],
};

const REQUIRED_FLAG_CHECKS = {
  touched: requireBase,
};

export function requireQueryFlags(name, flags) {
  if ((QUERY_REQUIRED_FLAGS[name] ?? []).some((flag) => !flags[flag])) REQUIRED_FLAG_CHECKS[name](flags);
}

export const QUERY_FLAGS = {
  "ring-crossings": ["direction", "include-barrels"],
  edges: ["kind"],
  units: ["component", "kind", "ring"],
  touched: ["base", "with-neighbors"],
  externals: ["tag"],
  volatility: ["since"],
};
