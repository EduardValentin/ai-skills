import { MODEL_DIR } from "./model.mjs";

export const ASSESS_COLUMNS = ["Workflow", "Target", "Rule", "Origin", "Verdict", "Severity", "Evidence", "Change", "Escalation"];

const POLICY_KINDS = new Set(["entity", "use-case", "port", "boundary-data"]);
const DETAIL_KINDS = new Set(["controller", "presenter", "gateway", "adapter", "composition-root", "entry-point", "test", "config", "ui"]);
const SEVERITY_ORDER = ["minor", "major", "blocker"];
const ESCALATION_FAN_IN = 3;
const GROUPS_TARGET = `${MODEL_DIR}/boundaries.json`;

const CHANGES = {
  ring: "Invert the dependency: declare a port in the inner ring that the outer unit implements, or move the code to the ring it belongs to",
  cycle: "Break the cycle: define the needed interface in the side that needs it and have the other implement it, or extract a cohesive leaf both depend on",
  stability: "Reverse the dependency through a port the stable component owns, or move what it needs into a component at least as stable",
  pain: "Shield the dependents behind a port the component owns, or move them onto an interface-only component",
  unused: "Delete the unused abstractions or fold them into their one consumer",
  groups: "Record the cohesion groups with model add-group, proposed from the change history",
  spread: "Split the change along the recorded groups, or record a group covering these components if they change together",
};

function edgeTarget(from, to) { return `${from} -> ${to}`; }
function cycleTarget(members) { return [...members].sort().join(" -> "); }
function describeUnit(unit) { return `${unit.path} (${unit.ring ?? "no ring"}, ${unit.kind ?? "no kind"})`; }
function sameMembers(a, b) { return cycleTarget(a) === cycleTarget(b); }

function edgePairs(graph) {
  const pairs = new Map();
  for (const edge of graph.edges) {
    const key = edgeTarget(edge.from, edge.to);
    if (!pairs.has(key)) pairs.set(key, { from: edge.from, to: edge.to, direction: edge.direction, kinds: [] });
    pairs.get(key).kinds.push(edge.kind);
  }
  return [...pairs.values()];
}

function ringFindings(graph) {
  const byPath = new Map(graph.units.map((u) => [u.path, u]));
  const findings = [];
  for (const pair of edgePairs(graph)) {
    const from = byPath.get(pair.from), to = byPath.get(pair.to);
    const policyToDetail = POLICY_KINDS.has(from?.kind) && DETAIL_KINDS.has(to?.kind);
    if (!policyToDetail && pair.direction !== "outward") continue;
    const reason = policyToDetail ? "policy unit depends on a detail unit" : "edge crosses rings outward";
    findings.push({
      workflow: "W1", target: edgeTarget(pair.from, pair.to), rule: "R4", severity: "blocker",
      evidence: `${reason}: ${describeUnit(from)} -> ${describeUnit(to)} by ${pair.kinds.join(", ")}`,
      change: CHANGES.ring, origin: { edge: pair }, escalationComponent: to?.component ?? null,
    });
  }
  for (const external of graph.externals ?? []) {
    for (const importer of external.importers) {
      const from = byPath.get(importer);
      if (!POLICY_KINDS.has(from?.kind)) continue;
      findings.push({
        workflow: "W1", target: edgeTarget(importer, `external:${external.name}`), rule: "R4", severity: "blocker",
        evidence: `policy unit depends on a ${external.tag} external: ${describeUnit(from)} imports ${external.name}`,
        change: CHANGES.ring, origin: { external: { from: importer, name: external.name } }, escalationComponent: null,
      });
    }
  }
  return findings;
}

function edgesAmong(graph, inCycle) {
  return edgePairs(graph).filter((pair) => inCycle(pair)).map((pair) => edgeTarget(pair.from, pair.to));
}

function cycleFindings(graph) {
  const componentOf = new Map(graph.units.map((u) => [u.path, u.component]));
  const componentCycles = graph.cycles.components.map((members) => {
    const set = new Set(members);
    const crossing = edgesAmong(graph, (p) => {
      const a = componentOf.get(p.from), b = componentOf.get(p.to);
      return a !== b && set.has(a) && set.has(b);
    });
    return {
      workflow: "W6", target: cycleTarget(members), rule: "R30", severity: "blocker",
      evidence: `component cycle through ${crossing.join(", ")}`,
      change: CHANGES.cycle, origin: { componentCycle: members }, escalationComponent: null,
    };
  });
  const moduleCycles = graph.cycles.modules.map((members) => {
    const set = new Set(members);
    const inside = edgesAmong(graph, (p) => set.has(p.from) && set.has(p.to));
    return {
      workflow: "W6", target: cycleTarget(members), rule: "R30", severity: "blocker",
      evidence: `module cycle through ${inside.join(", ")}`,
      change: CHANGES.cycle, origin: { moduleCycle: members }, escalationComponent: null,
    };
  });
  return [...componentCycles, ...moduleCycles];
}

function stabilityFindings(graph) {
  const byId = new Map(graph.components.map((c) => [c.id, c]));
  const componentOf = new Map(graph.units.map((u) => [u.path, u.component]));
  return graph.componentEdges.flatMap((edge) => {
    const from = byId.get(edge.from), to = byId.get(edge.to);
    if (from?.instability == null || to?.instability == null || from.instability >= to.instability) return [];
    const importers = edgesAmong(graph, (p) => componentOf.get(p.from) === edge.from && componentOf.get(p.to) === edge.to);
    return [{
      workflow: "W6", target: edgeTarget(edge.from, edge.to), rule: "R31", severity: "major",
      evidence: `I(${edge.from}) ${from.instability} < I(${edge.to}) ${to.instability}: ${importers.join(", ")}`,
      change: CHANGES.stability, origin: { componentEdge: edge }, escalationComponent: edge.to,
    }];
  });
}

function positionFindings(graph, touchedComponents) {
  const touched = new Set(touchedComponents ?? []);
  return graph.components.flatMap((c) => {
    if (c.inZone === "pain" && touched.has(c.id)) {
      return [{
        workflow: "W6", target: c.id, rule: "R31, R32", severity: "major",
        evidence: `zone of pain and changed by this change: concrete (A ${c.abstractness}), depended on by ${c.fanIn} modules (I ${c.instability})`,
        change: CHANGES.pain, origin: { component: c.id }, escalationComponent: c.id,
      }];
    }
    if (c.abstractExports > 0 && c.fanIn === 0) {
      return [{
        workflow: "W6", target: c.id, rule: "R31, R32", severity: "minor",
        evidence: `${c.abstractExports} abstract exports and no consumer outside the component (fan-in 0)`,
        change: CHANGES.unused, origin: { component: c.id }, escalationComponent: c.id,
      }];
    }
    return [];
  });
}

function bestGroup(groups, touched) {
  const covered = (g) => touched.filter((id) => (g.components ?? []).includes(id)).length;
  return groups.reduce((best, g) => (best === null || covered(g) > covered(best) ? g : best), null);
}

function cohesionFindings(model, touchedComponents) {
  const touched = [...new Set((touchedComponents ?? []).filter(Boolean))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  if (touched.length < 2) return [];
  const groups = model.boundaries?.groups ?? [];
  if (groups.length === 0) {
    return [{
      workflow: "W6", target: GROUPS_TARGET, rule: "R28", severity: "minor",
      evidence: `the change touches ${touched.join(", ")} and the model records no cohesion groups`,
      change: CHANGES.groups, origin: { change: true }, escalationComponent: null,
    }];
  }
  if (groups.some((g) => touched.every((id) => (g.components ?? []).includes(id)))) return [];
  const best = bestGroup(groups, touched);
  const inBest = new Set(best.components ?? []);
  return touched.filter((id) => !inBest.has(id)).map((id) => ({
    workflow: "W6", target: id, rule: "R27", severity: "major",
    evidence: `the change touches ${touched.join(", ")}; no recorded group holds them all, and ${id} is outside group ${best.name} (${[...inBest].join(", ")})`,
    change: CHANGES.spread, origin: { change: true }, escalationComponent: id,
  }));
}

function originResolver({ baseGraph, diff, touchedComponents }) {
  if (!diff) return () => (touchedComponents ? "left" : "introduced");
  const movedTo = new Map(diff.units.moved.map((m) => [m.from, m.to]));
  const addedEdges = new Set(diff.edges.added.map((e) => edgeTarget(e.from, e.to)));
  const baseExternalImports = new Set((baseGraph.externals ?? []).flatMap((x) => x.importers.map((p) => `${movedTo.get(p) ?? p}\u0000${x.name}`)));
  const baseComponentEdges = new Set(baseGraph.componentEdges.map((e) => edgeTarget(e.from, e.to)));
  const baseComponents = new Set(baseGraph.components.map((c) => c.id));
  const tests = {
    edge: (e) => addedEdges.has(edgeTarget(e.from, e.to)),
    external: (x) => !baseExternalImports.has(`${x.from}\u0000${x.name}`),
    componentCycle: (members) => diff.cycles.new.some((c) => sameMembers(c, members)),
    moduleCycle: (members) => diff.cycles.modules.new.some((c) => sameMembers(c, members)),
    componentEdge: (e) => !baseComponentEdges.has(edgeTarget(e.from, e.to)),
    component: (id) => !baseComponents.has(id),
    change: () => true,
  };
  return (origin) => {
    const [kind, value] = Object.entries(origin)[0];
    return tests[kind](value) ? "introduced" : "left";
  };
}

function escalate(finding, fanInOf) {
  const fanIn = finding.escalationComponent ? fanInOf.get(finding.escalationComponent) ?? 0 : 0;
  if (fanIn < ESCALATION_FAN_IN) return { severity: finding.severity, escalation: [] };
  const severity = SEVERITY_ORDER.indexOf(finding.severity) < SEVERITY_ORDER.indexOf("major") ? "major" : finding.severity;
  return { severity, escalation: ["rule 3"] };
}

function ruleNumber(rule) { return Number(rule.match(/\d+/)[0]); }

export function assess({ graph, model, baseGraph = null, diff = null, touchedComponents = null }) {
  const originOf = originResolver({ baseGraph, diff, touchedComponents });
  const fanInOf = new Map(graph.components.map((c) => [c.id, c.fanIn]));
  const findings = [
    ...ringFindings(graph),
    ...cycleFindings(graph),
    ...stabilityFindings(graph),
    ...positionFindings(graph, touchedComponents),
    ...cohesionFindings(model, touchedComponents),
  ];
  return findings
    .map((f) => {
      const { severity, escalation } = escalate(f, fanInOf);
      return { workflow: f.workflow, target: f.target, rule: f.rule, origin: originOf(f.origin), verdict: "SHOULD_CHANGE", severity, evidence: f.evidence, change: f.change, escalation };
    })
    .sort((a, b) => a.workflow.localeCompare(b.workflow) || ruleNumber(a.rule) - ruleNumber(b.rule) || a.target.localeCompare(b.target));
}

export function assessTable(rows) {
  return {
    columns: ASSESS_COLUMNS,
    rows: rows.map((r) => [r.workflow, r.target, r.rule, r.origin, r.verdict, r.severity, r.evidence, r.change, r.escalation]),
  };
}
