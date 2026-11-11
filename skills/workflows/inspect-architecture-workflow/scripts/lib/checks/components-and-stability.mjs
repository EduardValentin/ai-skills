import { plural } from "../text.mjs";
import { COMPONENT_METRIC_CHECKS } from "./component-metrics.mjs";
import { componentRow } from "./rows.mjs";
import { portDeclaredIn } from "./ports.mjs";
import { cycleTarget, edgePairs, edgeTarget, naturalOrder, pairTargetsWhere } from "./targets.mjs";
import { unitsWithoutExports } from "./undecided.mjs";

const GROUP = "components-and-stability";
const GROUPS_TARGET = "groups";

const CORRECTIONS = {
  cycle: (target) =>
    `Break the cycle ${target} by removing one of its edges: move what that edge uses into the depending side, ` +
    "or merge the members if they always change together; only if the dependency must stay, have the side that " +
    "needs it declare an interface the other side implements",
  stability: (from, to) =>
    `Remove the dependency of ${from} on ${to}: move what ${from} uses from ${to} into ${from}, or into a component ` +
    `at least as stable as ${from}`,
  implementsPorts: (from, to, symbols, dependents) =>
    `Keep this dependency, since ${from} only implements ${symbols} that ${to} declares; make ${from} less ` +
    `depended on instead, by removing the dependencies of ${dependents} on it`,
  pain: (name, fanIn) =>
    `Move the part of ${name} that keeps changing out of it, into the component whose needs drive those changes, ` +
    `so its ${plural(fanIn, "dependent module")} stop re-verifying on every change; only if that part must stay ` +
    `shared, have the dependents use it through a port ${name} owns`,
  unused: (name) =>
    `Delete the abstract types in ${name} that nothing implements or uses, and inline any that one unit inside ` +
    `${name} uses`,
  groups: "Record the cohesion groups with arch model add-group, proposed from the change history",
  spread: (components) =>
    `If ${components.join(", ")} change together on purpose, record a group covering them with arch model ` +
    "add-group; otherwise split the change along the recorded groups",
};

const CONSEQUENCES = {
  componentCycle: ({ target }) =>
    `A change to any component in ${target} can force a change to all of them, so none can be released or tested ` +
    "alone.",
  moduleCycle: ({ target }) =>
    `A change to any unit in ${target} can force a change to all of them, so none can be tested or reused alone.`,
  unstableDependency: ({ edge }) =>
    `Each change to ${edge.to}, which changes more easily, reaches ${edge.from} and everything that depends on ` +
    `${edge.from}.`,
  zoneOfPain: ({ target }) =>
    `${target} is concrete, depended on, and changes often, so each change re-verifies every module that depends ` +
    "on it.",
  unusedAbstraction: ({ target }) =>
    `The abstract types of ${target} must be read and kept in step although nothing outside ${target} uses them.`,
  noCohesionGroups: () =>
    "Without recorded groups nobody can tell whether a change that spans components is expected or a sign the " +
    "boundaries are wrong.",
  changeSpansGroups: ({ target }) =>
    `This change spreads over ${target} and components the model says change for other reasons, so each such ` +
    "change costs more places to edit and review.",
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

function crossingPairs(context, edge) {
  return edgePairs(context.graph).filter(
    (pair) => context.componentOf(pair.from) === edge.from && context.componentOf(pair.to) === edge.to,
  );
}

function dependentsOf(context, name) {
  return context.graph.componentEdges.filter((edge) => edge.to === name).map((edge) => edge.from);
}

function stabilityCorrection(context, edge, pairs) {
  const ports = pairs.map((pair) => portDeclaredIn(context, pair.to));
  if (ports.some((port) => port === null)) return CORRECTIONS.stability(edge.from, edge.to);
  const symbols = [...new Set(ports.map((port) => `\`${port.symbol}\``))];
  const named = `${symbols.length === 1 ? "the port" : "the ports"} ${symbols.join(", ")}`;
  return CORRECTIONS.implementsPorts(edge.from, edge.to, named, dependentsOf(context, edge.from).join(", "));
}

function unstableDependencyRows(context) {
  const byName = new Map(context.graph.components.map((component) => [component.name, component]));
  return context.graph.componentEdges.flatMap((edge) => {
    const from = byName.get(edge.from);
    const to = byName.get(edge.to);
    if (from?.instability == null || to?.instability == null || from.instability >= to.instability) return [];
    const pairs = crossingPairs(context, edge);
    const importers = pairs.map((pair) => edgeTarget(pair.from, pair.to));
    return [
      {
        target: edgeTarget(edge.from, edge.to),
        evidence: `I(${edge.from}) ${from.instability} < I(${edge.to}) ${to.instability}: ${importers.join(", ")}`,
        correction: stabilityCorrection(context, edge, pairs),
        units: [],
        components: [edge.from, edge.to],
        edge: { level: "component", from: edge.from, to: edge.to },
      },
    ];
  });
}

function touchedInPain(context) {
  const touched = new Set(context.touched.components);
  return context.graph.components.filter((component) => component.zone === "pain" && touched.has(component.name));
}

function changesOften(context, component) {
  return (context.history.get(component.name) ?? 0) >= context.model.thresholds.painMinChanges;
}

function zoneOfPainRows(context) {
  if (!context.history) return [];
  const window = context.model.thresholds.historyWindow;
  return touchedInPain(context)
    .filter((component) => changesOften(context, component))
    .map((component) =>
      componentRow(
        component.name,
        `zone of pain and changed by this change: concrete (A ${component.abstractness}), ` +
          `depended on by ${plural(component.fanIn, "module")} (I ${component.instability}), ` +
          `changed in ${plural(context.history.get(component.name), "commit")} within ${window}`,
        CORRECTIONS.pain(component.name, component.fanIn),
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
        `${plural(abstractExports, "abstract export")} and no consumer outside the component (fan-in 0)`,
        CORRECTIONS.unused(component.name),
      ),
    ];
  });
}

function withoutHistory(context) {
  if (context.history) return [];
  return touchedInPain(context).map((component) => ({
    target: component.name,
    reason:
      `${component.name} is in the zone of pain, but the change history is unknown, so whether it changes often ` +
      "could not be decided. Run arch check inside the project's git repository.",
  }));
}

function zoneOfPainUndecided(context) {
  return [...unitsWithoutExports(context, new Set(context.touched.components)), ...withoutHistory(context)];
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
    consequence: CONSEQUENCES.componentCycle,
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
    consequence: CONSEQUENCES.moduleCycle,
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
    consequence: CONSEQUENCES.unstableDependency,
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
    consequence: CONSEQUENCES.zoneOfPain,
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
    consequence: CONSEQUENCES.unusedAbstraction,
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
    consequence: CONSEQUENCES.noCohesionGroups,
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
    consequence: CONSEQUENCES.changeSpansGroups,
  },
  ...COMPONENT_METRIC_CHECKS,
];
