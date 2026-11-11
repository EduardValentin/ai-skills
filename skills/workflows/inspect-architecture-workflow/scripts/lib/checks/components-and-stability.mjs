import { COMPONENT_METRIC_CHECKS } from "./component-metrics.mjs";
import { componentRow } from "./rows.mjs";
import { cycleTarget, edgeTarget, naturalOrder, pairTargetsWhere } from "./targets.mjs";
import { unitsWithoutExports } from "./undecided.mjs";

const GROUP = "components-and-stability";
const GROUPS_TARGET = "groups";

const CORRECTIONS = {
  cycle: (target) =>
    `Break the cycle ${target}: define the needed interface in the side that needs it and have the other ` +
    "implement it, or extract a cohesive leaf both depend on",
  stability: (from, to) =>
    `Reverse the dependency ${from} -> ${to} through a port ${from} owns, ` +
    `or move what ${from} needs into a component at least as stable`,
  pain: (name) =>
    `Shield the dependents of ${name} behind a port ${name} owns, or move them onto an interface-only component`,
  unused: (name) => `Delete the unused abstractions of ${name} or fold them into their one consumer`,
  groups: "Record the cohesion groups with arch model add-group, proposed from the change history",
  spread: (components) =>
    `Split the change along the recorded groups, or record a group covering ${components.join(", ")} ` +
    "if they change together",
};

function componentCycleRows(context) {
  return context.graph.cycles.components.map((members) => {
    const inCycle = new Set(members);
    const crossing = pairTargetsWhere(context.graph, (pair) => {
      const from = context.componentOf(pair.from);
      const to = context.componentOf(pair.to);
      return from !== to && inCycle.has(from) && inCycle.has(to);
    });
    const target = cycleTarget(members);
    return {
      target,
      evidence: `component cycle through ${crossing.join(", ")}`,
      correction: CORRECTIONS.cycle(target),
      units: [],
      components: members,
      originKey: { type: "componentCycle", members },
      edge: null,
    };
  });
}

function moduleCycleRows(context) {
  return context.graph.cycles.modules.map((members) => {
    const inCycle = new Set(members);
    const inside = pairTargetsWhere(context.graph, (pair) => inCycle.has(pair.from) && inCycle.has(pair.to));
    const target = cycleTarget(members);
    return {
      target,
      evidence: `module cycle through ${inside.join(", ")}`,
      correction: CORRECTIONS.cycle(target),
      units: members,
      components: [],
      originKey: { type: "moduleCycle", members },
      edge: null,
    };
  });
}

function unstableDependencyRows(context) {
  const byName = new Map(context.graph.components.map((component) => [component.name, component]));
  return context.graph.componentEdges.flatMap((edge) => {
    const from = byName.get(edge.from);
    const to = byName.get(edge.to);
    if (from?.instability == null || to?.instability == null || from.instability >= to.instability) return [];
    const importers = pairTargetsWhere(
      context.graph,
      (pair) => context.componentOf(pair.from) === edge.from && context.componentOf(pair.to) === edge.to,
    );
    return [
      {
        target: edgeTarget(edge.from, edge.to),
        evidence: `I(${edge.from}) ${from.instability} < I(${edge.to}) ${to.instability}: ${importers.join(", ")}`,
        correction: CORRECTIONS.stability(edge.from, edge.to),
        units: [],
        components: [edge.from, edge.to],
        edge: { level: "component", from: edge.from, to: edge.to },
      },
    ];
  });
}

function zoneOfPainRows(context) {
  const touched = new Set(context.touched.components);
  return context.graph.components
    .filter((component) => component.zone === "pain" && touched.has(component.name))
    .map((component) =>
      componentRow(
        component.name,
        `zone of pain and changed by this change: concrete (A ${component.abstractness}), ` +
          `depended on by ${component.fanIn} modules (I ${component.instability})`,
        CORRECTIONS.pain(component.name),
      ),
    );
}

function abstractExportsOf(context, name) {
  const declaring = context.graph.units.filter((unit) => unit.component === name && unit.kind !== "barrel");
  if (!declaring.every((unit) => unit.exports)) return null;
  return declaring.reduce((sum, unit) => sum + unit.exports.abstract, 0);
}

function unusedAbstractionRows(context) {
  return context.graph.components.flatMap((component) => {
    const abstractExports = abstractExportsOf(context, component.name);
    if (!(abstractExports > 0) || component.fanIn !== 0) return [];
    return [
      componentRow(
        component.name,
        `${abstractExports} abstract exports and no consumer outside the component (fan-in 0)`,
        CORRECTIONS.unused(component.name),
      ),
    ];
  });
}

function zoneOfPainUndecided(context) {
  return unitsWithoutExports(context, new Set(context.touched.components));
}

function unusedAbstractionUndecided(context) {
  return unitsWithoutExports(context, new Set(context.graph.components.map((component) => component.name)));
}

function touchedComponents(context) {
  return [...new Set(context.touched.components.filter(Boolean))].sort(naturalOrder);
}

function noCohesionGroupsRows(context) {
  const components = touchedComponents(context);
  if (components.length < 2 || context.model.groups.length > 0) return [];
  return [
    {
      target: GROUPS_TARGET,
      evidence: `the change touches ${components.join(", ")} and the model records no cohesion groups`,
      correction: CORRECTIONS.groups,
      units: [],
      components: [],
      originKey: { type: "change" },
      edge: null,
    },
  ];
}

function changeSpansGroupsRows(context) {
  const components = touchedComponents(context);
  const { groups } = context.model;
  if (components.length < 2 || groups.length === 0) return [];
  const holds = (group, name) => group.members.includes(name);
  const sharesGroup = (a, b) => groups.some((group) => holds(group, a) && holds(group, b));
  return components.flatMap((name) => {
    const partners = components.filter((other) => other !== name && !sharesGroup(name, other));
    if (partners.length === 0) return [];
    const holding = groups.filter((group) => holds(group, name)).map((group) => group.name);
    return [
      {
        ...componentRow(
          name,
          `${name} shares no recorded group with ${partners.join(", ")}; ` +
            `groups holding ${name}: ${holding.length > 0 ? holding.join(", ") : "none"}`,
          CORRECTIONS.spread(components),
        ),
        originKey: { type: "change" },
      },
    ];
  });
}

export const COMPONENTS_AND_STABILITY_CHECKS = [
  {
    id: "component-cycle",
    rules: ["R30"],
    group: GROUP,
    defect: "cycle",
    severity: "blocker",
    facts: [],
    needsBase: false,
    run: componentCycleRows,
  },
  {
    id: "module-cycle",
    rules: ["R30"],
    group: GROUP,
    defect: "cycle",
    severity: "blocker",
    facts: [],
    needsBase: false,
    run: moduleCycleRows,
  },
  {
    id: "unstable-dependency",
    rules: ["R31"],
    group: GROUP,
    defect: "depends-on-less-stable",
    severity: "major",
    facts: [],
    needsBase: false,
    run: unstableDependencyRows,
  },
  {
    id: "zone-of-pain",
    rules: ["R31", "R32"],
    group: GROUP,
    defect: "zone-of-pain",
    severity: "major",
    facts: ["exports"],
    needsBase: true,
    run: zoneOfPainRows,
    undecided: zoneOfPainUndecided,
  },
  {
    id: "unused-abstractions",
    rules: ["R31", "R32"],
    group: GROUP,
    defect: "unused-abstraction",
    severity: "minor",
    facts: ["exports"],
    needsBase: false,
    run: unusedAbstractionRows,
    undecided: unusedAbstractionUndecided,
  },
  {
    id: "no-cohesion-groups",
    rules: ["R28"],
    group: GROUP,
    defect: "no-cohesion-groups",
    severity: "minor",
    facts: [],
    needsBase: true,
    run: noCohesionGroupsRows,
  },
  {
    id: "change-spans-groups",
    rules: ["R27"],
    group: GROUP,
    defect: "change-spans-groups",
    severity: "major",
    facts: [],
    needsBase: true,
    run: changeSpansGroupsRows,
  },
  ...COMPONENT_METRIC_CHECKS,
];
