import { concernsEnforcedRule } from "../checks/status.mjs";

export const SEVERITIES = ["blocker", "major", "minor"];
const STOPPING = ["blocker", "major"];

function blocks(finding, flow) {
  if (flow === "audit" || finding.origin === "introduced") return true;
  return finding.origin === "inherited" && Boolean(finding.liftedBy);
}

export function classifyFindings(findings, flow) {
  const groups = { blocking: [], inherited: [], advisory: [], wider: [] };
  for (const finding of findings) {
    if (finding.wider) groups.wider.push(finding);
    else if (finding.status !== "enforced") groups.advisory.push(finding);
    else if (blocks(finding, flow)) groups.blocking.push(finding);
    else groups.inherited.push(finding);
  }
  return groups;
}

export function countBySeverity(findings) {
  return Object.fromEntries(SEVERITIES.map((s) => [s, findings.filter((finding) => finding.severity === s).length]));
}

export function withEnforcement(model, incomplete) {
  return incomplete.map((entry) => ({ ...entry, enforced: concernsEnforcedRule(model, entry.rules) }));
}

function decide({ blocking, incomplete, modelPresent }) {
  if (STOPPING.some((severity) => blocking[severity] > 0)) return "SHOULD_CHANGE";
  if (modelPresent && incomplete.some((entry) => entry.enforced)) return "INCOMPLETE";
  return "OK";
}

export function computeVerdict({ rows, incomplete, flow, modelPresent }) {
  const groups = classifyFindings(rows, flow);
  const blocking = countBySeverity(groups.blocking);
  return {
    verdict: decide({ blocking, incomplete, modelPresent }),
    blocking,
    inherited: countBySeverity(groups.inherited),
    advisory: groups.advisory.length,
    wider: groups.wider.length,
    incompleteCount: incomplete.length,
  };
}
