import { touchesBarrel } from "./context.mjs";
import { removeForExistingPort } from "./corrections.mjs";
import { implementedPorts, portsImplementedBy } from "./ports.mjs";
import { unitEdgeRow } from "./rows.mjs";
import { describeUnit, edgePairs } from "./targets.mjs";

const GROUP = "deferral-and-boundaries";

function isPlugin(context, path) {
  return implementedPorts(context, path).length > 0;
}

function bothArePluginsOfDifferentComponents(context, pair) {
  const from = context.componentOf(pair.from);
  const to = context.componentOf(pair.to);
  return from !== null && to !== null && from !== to && isPlugin(context, pair.from) && isPlugin(context, pair.to);
}

function pluginImportsPlugin(context) {
  return edgePairs(context.graph)
    .filter((pair) => !touchesBarrel(context, pair.from, pair.to))
    .filter((pair) => bothArePluginsOfDifferentComponents(context, pair))
    .map((pair) =>
      unitEdgeRow({
        ...pair,
        evidence:
          `${describeUnit(context.unitOf(pair.from))} implements ${implementedPorts(context, pair.from).join(", ")} ` +
          `and depends on ${describeUnit(context.unitOf(pair.to))}, which implements ` +
          `${implementedPorts(context, pair.to).join(", ")}`,
        correction: removeForExistingPort(portsImplementedBy(context, pair.to)[0], pair.from, pair.to),
      }),
    );
}

export const DEFERRAL_AND_BOUNDARIES_CHECKS = [
  {
    id: "plugin-imports-plugin",
    rules: ["R25"],
    group: GROUP,
    defect: "plugins-coupled",
    severity: "major",
    facts: ["implements"],
    needsBase: false,
    run: pluginImportsPlugin,
    consequence: ({ edge }) =>
      `Replacing or removing ${edge.to} forces a change to ${edge.from}, so the two plugins cannot change apart.`,
  },
];
