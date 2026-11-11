import { implementedPorts } from "./ports.mjs";
import { unitEdgeRow } from "./rows.mjs";
import { edgeTarget } from "./targets.mjs";

const GROUP = "reasons-to-change";

function typeCheckSites(context) {
  return context.graph.units.flatMap((unit) =>
    (unit.typeChecks ?? []).map((site) => ({ unit, site, ports: implementedPorts(context, site.path) })),
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
    return unitEdgeRow({
      from: unit.path,
      to: site.path,
      evidence: `type check for an implementation of ${ports.join(", ")} at ${where.join(", ")}`,
      correction:
        `Remove the type check in ${unit.path}: let the implementation carry the behavior behind ${ports[0]}, ` +
        "or give consumers a separate port for the special case",
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
    facts: ["typeChecks"],
    needsBase: false,
    run: typeCheckOnImplementation,
  },
];
