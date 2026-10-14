import { naturalOrder } from "./graph.mjs";
import { MODEL_DIR } from "./model.mjs";

export const ASSESS_COLUMNS = ["Workflow", "Target", "Rule", "Origin", "Verdict", "Severity", "Evidence", "Change", "Escalation"];

export const NOT_PROVIDED_LINES = {
  abstractness: "abstractness rows not provided by the adapter; evaluate R31 and R32 from a fact slice",
  constructs: "construction rows not provided by the adapter; evaluate R7 from a fact slice",
};

const POLICY_KINDS = new Set(["entity", "use-case", "port", "boundary-data"]);
const DETAIL_KINDS = new Set(["controller", "presenter", "gateway", "adapter", "composition-root", "entry-point", "test", "config", "ui"]);
const DETAIL_RING_COUNT = 2;
const SEVERITY_ORDER = ["minor", "major", "blocker"];
const ESCALATION_FAN_IN = 3;
const GROUPS_TARGET = `${MODEL_DIR}/boundaries.json`;

const CHANGES = {
  ring: "Invert the dependency: declare a port in the inner ring that the outer unit implements, or move the code to the ring it belongs to",
  construction: "Construct the detail in a composition root and hand it in through the port its user declares",
  cycle: "Break the cycle: define the needed interface in the side that needs it and have the other implement it, or extract a cohesive leaf both depend on",
  stability: "Reverse the dependency through a port the stable component owns, or move what it needs into a component at least as stable",
  pain: "Shield the dependents behind a port the component owns, or move them onto an interface-only component",
  unused: "Delete the unused abstractions or fold them into their one consumer",
  groups: "Record the cohesion groups with model add-group, proposed from the change history",
  spread: "Split the change along the recorded groups, or record a group covering these components if they change together",
};

function edgeTarget(from, to) { return `${from} -> ${to}`; }
function cycleTarget(members) { return [...members].sort(naturalOrder).join(" -> "); }
function describeUnit(unit) { return `${unit.path} (${unit.ring ?? "no ring"}, ${unit.kind ?? "no kind"})`; }

function edgePairs(graph) {
  const pairs = new Map();
  for (const edge of graph.edges) {
    const key = edgeTarget(edge.from, edge.to);
    if (!pairs.has(key)) pairs.set(key, { from: edge.from, to: edge.to, direction: edge.direction, kinds: [] });
    pairs.get(key).kinds.push(edge.kind);
  }
  return [...pairs.values()];
}

function ringFindings(graph, byPath) {
  const findings = [];
  for (const pair of edgePairs(graph)) {
    const from = byPath.get(pair.from), to = byPath.get(pair.to);
    const policyToDetail = POLICY_KINDS.has(from?.kind) && DETAIL_KINDS.has(to?.kind);
    if (!policyToDetail && pair.direction !== "outward") continue;
    const reason = policyToDetail ? "policy unit depends on a detail unit" : "edge crosses rings outward";
    findings.push({
      workflow: "W1", target: edgeTarget(pair.from, pair.to), rule: "R4", severity: "blocker",
      evidence: `${reason}: ${describeUnit(from)} -> ${describeUnit(to)} by ${pair.kinds.join(", ")}`,
      change: CHANGES.ring, origin: { edge: pair }, scope: { units: [pair.from, pair.to] }, escalationComponent: to?.component ?? null,
    });
  }
  for (const external of graph.externals ?? []) {
    for (const importer of external.importers) {
      const from = byPath.get(importer);
      if (!POLICY_KINDS.has(from?.kind)) continue;
      findings.push({
        workflow: "W1", target: edgeTarget(importer, `external:${external.name}`), rule: "R4", severity: "blocker",
        evidence: `policy unit depends on a ${external.tag} external: ${describeUnit(from)} imports ${external.name}`,
        change: CHANGES.ring, origin: { external: { from: importer, name: external.name } }, scope: { units: [importer] }, escalationComponent: null,
      });
    }
  }
  return findings;
}

function constructionFindings(graph, byPath) {
  const detailRings = new Set((graph.rings ?? []).slice(-DETAIL_RING_COUNT));
  return graph.edges.filter((e) => e.kind === "constructs").flatMap((edge) => {
    const from = byPath.get(edge.from), to = byPath.get(edge.to);
    if (!from || !to || from.kind === "composition-root" || !detailRings.has(to.ring)) return [];
    return [{
      workflow: "W1", target: edgeTarget(edge.from, edge.to), rule: "R7", severity: "blocker",
      evidence: `concrete detail constructed outside a composition root: ${describeUnit(from)} constructs ${describeUnit(to)}`,
      change: CHANGES.construction, origin: { edge }, scope: { units: [edge.from, edge.to] }, escalationComponent: to.component ?? null,
    }];
  });
}

function edgesAmong(graph, inCycle) {
  return edgePairs(graph).filter((pair) => inCycle(pair)).map((pair) => edgeTarget(pair.from, pair.to));
}

function cycleFindings(graph, byPath) {
  const componentOf = (p) => byPath.get(p)?.component;
  const componentCycles = graph.cycles.components.map((members) => {
    const set = new Set(members);
    const crossing = edgesAmong(graph, (p) => componentOf(p.from) !== componentOf(p.to) && set.has(componentOf(p.from)) && set.has(componentOf(p.to)));
    return {
      workflow: "W6", target: cycleTarget(members), rule: "R30", severity: "blocker",
      evidence: `component cycle through ${crossing.join(", ")}`,
      change: CHANGES.cycle, origin: { componentCycle: members }, scope: { components: members }, escalationComponent: null,
    };
  });
  const moduleCycles = graph.cycles.modules.map((members) => {
    const set = new Set(members);
    const inside = edgesAmong(graph, (p) => set.has(p.from) && set.has(p.to));
    return {
      workflow: "W6", target: cycleTarget(members), rule: "R30", severity: "blocker",
      evidence: `module cycle through ${inside.join(", ")}`,
      change: CHANGES.cycle, origin: { moduleCycle: members }, scope: { units: members }, escalationComponent: null,
    };
  });
  return [...componentCycles, ...moduleCycles];
}

function stabilityFindings(graph, byPath) {
  const byId = new Map(graph.components.map((c) => [c.id, c]));
  const componentOf = (p) => byPath.get(p)?.component;
  return graph.componentEdges.flatMap((edge) => {
    const from = byId.get(edge.from), to = byId.get(edge.to);
    if (from?.instability == null || to?.instability == null || from.instability >= to.instability) return [];
    const importers = edgesAmong(graph, (p) => componentOf(p.from) === edge.from && componentOf(p.to) === edge.to);
    return [{
      workflow: "W6", target: edgeTarget(edge.from, edge.to), rule: "R31", severity: "major",
      evidence: `I(${edge.from}) ${from.instability} < I(${edge.to}) ${to.instability}: ${importers.join(", ")}`,
      change: CHANGES.stability, origin: { componentEdge: edge }, scope: { components: [edge.from, edge.to] }, escalationComponent: edge.to,
    }];
  });
}

function positionFindings(graph, touched) {
  const touchedComponents = new Set(touched?.components ?? []);
  return graph.components.flatMap((c) => {
    const base = { workflow: "W6", target: c.id, rule: "R31, R32", origin: { component: c.id }, scope: { components: [c.id] }, escalationComponent: c.id };
    if (c.inZone === "pain" && touchedComponents.has(c.id)) {
      return [{ ...base, severity: "major", change: CHANGES.pain,
        evidence: `zone of pain and changed by this change: concrete (A ${c.abstractness}), depended on by ${c.fanIn} modules (I ${c.instability})` }];
    }
    if (c.abstractExports > 0 && c.fanIn === 0) {
      return [{ ...base, severity: "minor", change: CHANGES.unused,
        evidence: `${c.abstractExports} abstract exports and no consumer outside the component (fan-in 0)` }];
    }
    return [];
  });
}

function cohesionFindings(model, touched) {
  const components = [...new Set((touched?.components ?? []).filter(Boolean))].sort(naturalOrder);
  if (components.length < 2) return [];
  const groups = model.boundaries?.groups ?? [];
  const base = { workflow: "W6", origin: { change: true }, scope: null };
  if (groups.length === 0) {
    return [{ ...base, target: GROUPS_TARGET, rule: "R28", severity: "minor", escalationComponent: null, change: CHANGES.groups,
      evidence: `the change touches ${components.join(", ")} and the model records no cohesion groups` }];
  }
  if (groups.some((g) => components.every((id) => (g.components ?? []).includes(id)))) return [];
  return components.map((id) => ({ ...base, target: id, rule: "R27", severity: "major", escalationComponent: id, change: CHANGES.spread,
    evidence: `the change touches ${components.join(", ")}; no recorded group holds ${id} together with every other touched component` }));
}

function originResolver({ graph, baseGraph, diff, touched }) {
  if (!diff) return () => (touched ? "left" : "introduced");
  const movedTo = new Map(diff.units.moved.map((m) => [m.from, m.to]));
  const mapped = (p) => movedTo.get(p) ?? p;
  const basePairs = new Set(baseGraph.edges.map((e) => edgeTarget(mapped(e.from), mapped(e.to))));
  const isNewPair = (from, to) => !basePairs.has(edgeTarget(from, to));
  const baseExternalImports = new Set((baseGraph.externals ?? []).flatMap((x) => x.importers.map((p) => `${mapped(p)}\u0000${x.name}`)));
  const baseComponentEdges = new Set(baseGraph.componentEdges.map((e) => edgeTarget(e.from, e.to)));
  const isNewComponentEdge = (e) => !baseComponentEdges.has(edgeTarget(e.from, e.to));
  const baseComponents = new Set(baseGraph.components.map((c) => c.id));
  const tests = {
    edge: (e) => isNewPair(e.from, e.to),
    external: (x) => !baseExternalImports.has(`${x.from}\u0000${x.name}`),
    moduleCycle: (members) => graph.edges.some((e) => members.includes(e.from) && members.includes(e.to) && isNewPair(e.from, e.to)),
    componentCycle: (members) => graph.componentEdges.some((e) => members.includes(e.from) && members.includes(e.to) && isNewComponentEdge(e)),
    componentEdge: isNewComponentEdge,
    component: (id) => !baseComponents.has(id),
    change: () => true,
  };
  return (origin) => {
    const [kind, value] = Object.entries(origin)[0];
    return tests[kind](value) ? "introduced" : "left";
  };
}

function inScope(finding, touched) {
  if (!touched || finding.scope === null) return true;
  const units = new Set(touched.units), components = new Set(touched.components);
  return (finding.scope.units ?? []).some((p) => units.has(p)) || (finding.scope.components ?? []).some((id) => components.has(id));
}

function escalate(finding, fanInOf) {
  const fanIn = finding.escalationComponent ? fanInOf.get(finding.escalationComponent) ?? 0 : 0;
  const lifts = fanIn >= ESCALATION_FAN_IN && SEVERITY_ORDER.indexOf(finding.severity) < SEVERITY_ORDER.indexOf("major");
  return lifts ? { severity: "major", escalation: ["rule 3"] } : { severity: finding.severity, escalation: [] };
}

function ruleNumber(rule) { return Number(rule.match(/\d+/)[0]); }

export function assess({ graph, model, baseGraph = null, diff = null, touched = null }) {
  const byPath = new Map(graph.units.map((u) => [u.path, u]));
  const provides = (fact) => Boolean(graph.capabilities?.[fact]);
  const notProvided = [...(provides("exports") ? [] : ["abstractness"]), ...(provides("constructs") ? [] : ["constructs"])];
  const originOf = originResolver({ graph, baseGraph, diff, touched });
  const fanInOf = new Map(graph.components.map((c) => [c.id, c.fanIn]));
  const findings = [
    ...ringFindings(graph, byPath),
    ...(provides("constructs") ? constructionFindings(graph, byPath) : []),
    ...cycleFindings(graph, byPath),
    ...stabilityFindings(graph, byPath),
    ...(provides("exports") ? positionFindings(graph, touched) : []),
    ...cohesionFindings(model, touched),
  ];
  const rows = findings
    .filter((f) => inScope(f, touched))
    .map((f) => {
      const { severity, escalation } = escalate(f, fanInOf);
      return { workflow: f.workflow, target: f.target, rule: f.rule, origin: originOf(f.origin), verdict: "SHOULD_CHANGE", severity, evidence: f.evidence, change: f.change, escalation };
    })
    .sort((a, b) => a.workflow.localeCompare(b.workflow) || ruleNumber(a.rule) - ruleNumber(b.rule) || naturalOrder(a.target, b.target));
  return { rows, notProvided };
}

export function assessTable(rows) {
  return {
    columns: ASSESS_COLUMNS,
    rows: rows.map((r) => [r.workflow, r.target, r.rule, r.origin, r.verdict, r.severity, r.evidence, r.change, r.escalation]),
  };
}
