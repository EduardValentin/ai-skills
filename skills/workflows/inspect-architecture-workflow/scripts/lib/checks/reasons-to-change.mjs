import { movingOutward } from "./corrections.mjs";
import { existingPort, portsImplementedBy } from "./ports.mjs";
import { unitEdgeRow } from "./rows.mjs";
import { edgeTarget } from "./targets.mjs";

const GROUP = "reasons-to-change";

function typeCheckConsequence({ edge }) {
  return `Adding or changing an implementation of the port means editing ${edge.from}, which checks for ${edge.to}.`;
}

function typeCheckSites(context) {
  return context.graph.units.flatMap((unit) =>
    (unit.typeChecks ?? []).map((site) => ({ unit, site, ports: portsImplementedBy(context, site.path) })),
  );
}

function groupedByEdge(sites) {
  const groups = new Map();
  for (const entry of sites) {
    const key = edgeTarget(entry.unit.path, entry.site.path);
    groups.set(key, [...(groups.get(key) ?? []), entry]);
  }
  return [...groups.values()];
}

function typeCheckOnImplementation(context) {
  const onImplementations = typeCheckSites(context).filter((entry) => entry.ports.length > 0);
  return groupedByEdge(onImplementations).map((entries) => {
    const [{ unit, site, ports }] = entries;
    const where = entries.map((entry) => `${entry.unit.path}:${entry.site.line} (${entry.site.symbol})`);
    const symbols = ports.map((port) => port.symbol).join(", ");
    return unitEdgeRow({
      from: unit.path,
      to: site.path,
      evidence: `type check for an implementation of ${symbols} at ${where.join(", ")}`,
      correction: movingOutward(
        `Remove the type check for ${site.symbol} in ${unit.path}, and move the special-case behavior into ` +
          `${site.path} behind ${existingPort(ports[0])}`,
      ),
    });
  });
}

export const REASONS_TO_CHANGE_CHECKS = [
  {
    id: "type-check-on-implementation",
    rules: ["R13"],
    group: GROUP,
    defect: "consumer-checks-implementation",
    severity: "major",
    facts: ["typeChecks", "implements"],
    needsBase: false,
    run: typeCheckOnImplementation,
    consequence: typeCheckConsequence,
  },
];
