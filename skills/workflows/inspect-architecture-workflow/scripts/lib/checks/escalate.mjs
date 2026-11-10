import { dependedOnComponents } from "./context.mjs";

const SEVERITY_ORDER = ["minor", "major", "blocker"];
const CYCLE_DEFECT = "cycle";

export function highestSeverity(a, b) {
  return SEVERITY_ORDER.indexOf(a) >= SEVERITY_ORDER.indexOf(b) ? a : b;
}

function liftedTo(severity, floor) {
  return SEVERITY_ORDER.indexOf(severity) < SEVERITY_ORDER.indexOf(floor) ? floor : severity;
}

function startsInPolicyUnit(row, context) {
  return row.edge?.level === "unit" && context.roleOf(row.edge.from) === "policy";
}

function reachesWidelyDependedOnComponent(row, context) {
  const bound = context.model.thresholds.escalationFanIn;
  const names = new Set(dependedOnComponents(row, context));
  return context.graph.components.some((component) => names.has(component.name) && component.fanIn >= bound);
}

const ESCALATIONS = [
  { rule: 1, floor: "major", applies: startsInPolicyUnit },
  { rule: 3, floor: "major", applies: reachesWidelyDependedOnComponent },
  { rule: 4, floor: "blocker", applies: (row) => row.defect === CYCLE_DEFECT },
];

export function escalateRow(row, context) {
  let severity = row.severity;
  const lifts = [];
  for (const { rule, floor, applies } of ESCALATIONS) {
    const lifted = liftedTo(severity, floor);
    if (lifted === severity || !applies(row, context)) continue;
    severity = lifted;
    lifts.push(rule);
  }
  return { severity, lifts };
}
