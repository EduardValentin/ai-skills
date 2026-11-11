import { highestSeverity } from "../checks/escalate.mjs";
import { ruleNumber } from "../checks/rule-titles.mjs";
import { strictest } from "../checks/status.mjs";
import { naturalOrder } from "../checks/targets.mjs";
import { componentOfTarget, isInScope, unitsOfTarget } from "./targets.mjs";

export const CODE_SCOPE = "code";

export function scopeTag(flow, plan) {
  return flow === "plan-review" ? `plan:${plan}` : CODE_SCOPE;
}

export function checkFinding(row, graph) {
  return {
    target: row.target,
    defect: row.defect,
    rules: row.rules,
    severity: row.severity,
    baseSeverity: row.baseSeverity,
    lifts: row.lifts,
    status: row.status,
    origin: row.origin,
    provenance: "check",
    consequence: row.consequence,
    correction: row.correction,
    evidence: [row.evidence],
    wider: false,
    component: componentOfTarget(graph, row.target),
    units: unitsOfTarget(graph, row.target, row.defect),
  };
}

function union(lists) {
  return [...new Set(lists.flat())];
}

function mergeGroup(group) {
  const [first] = group;
  const origin = (group.find((finding) => finding.provenance === "check") ?? first).origin;
  const provenances = new Set(group.map((finding) => finding.provenance));
  const liftedBy = group.find((finding) => finding.liftedBy)?.liftedBy;
  const judgedFiles = union(group.map((finding) => finding.judgedFiles ?? []));
  return {
    ...first,
    rules: union(group.map((finding) => finding.rules)).sort((a, b) => ruleNumber(a) - ruleNumber(b)),
    severity: group.map((finding) => finding.severity).reduce(highestSeverity),
    baseSeverity: group.map((finding) => finding.baseSeverity).reduce(highestSeverity),
    lifts: union(group.map((finding) => finding.lifts)).sort((a, b) => a - b),
    status: strictest(group.map((finding) => finding.status)),
    origin,
    provenance: provenances.size > 1 ? "both" : first.provenance,
    consequence: (group.find((finding) => finding.provenance === "judged") ?? first).consequence,
    evidence: union(group.map((finding) => finding.evidence)),
    wider: group.every((finding) => finding.wider),
    ...(liftedBy && { liftedBy }),
    ...(judgedFiles.length > 0 && { judgedFiles }),
  };
}

export function findingKey(finding) {
  return JSON.stringify([finding.target, finding.defect]);
}

export function mergeFindings(findings) {
  const groups = new Map();
  for (const finding of findings) {
    const key = findingKey(finding);
    groups.set(key, [...(groups.get(key) ?? []), finding]);
  }
  return [...groups.values()].map(mergeGroup);
}

function byRuleThenTarget(a, b) {
  return ruleNumber(a.rules[0]) - ruleNumber(b.rules[0]) || naturalOrder(a.target, b.target);
}

export function replaceStored({ stored, incoming, flow, tag, scope }) {
  const incomingKeys = new Set(incoming.map((finding) => `${tag}${findingKey(finding)}`));
  const replaced = (finding) => {
    if (finding.scope !== tag) return false;
    if (incomingKeys.has(`${finding.scope}${findingKey(finding)}`)) return true;
    return flow !== "change-review" || isInScope(scope, finding.target);
  };
  const tagged = incoming.map((finding) => ({ ...finding, scope: tag }));
  return [...stored.filter((finding) => !replaced(finding)), ...tagged].sort(byRuleThenTarget);
}
