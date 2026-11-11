import { touched } from "./change.mjs";
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
