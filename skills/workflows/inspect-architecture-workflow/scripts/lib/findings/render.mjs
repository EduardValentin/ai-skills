import { highestSeverity } from "../checks/escalate.mjs";
import { ruleNumber, titledRule } from "../checks/rule-titles.mjs";
import { naturalOrder } from "../checks/targets.mjs";
import { plural } from "../text.mjs";
import { SEVERITIES, classifyFindings, computeVerdict } from "./verdict.mjs";

export const NO_COMPONENT = "no component";
const COVERED_REASON = "covered by an exception";

function sentence(text) {
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

function bySeverityThenTarget(a, b) {
  return SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(b.severity) || naturalOrder(a.target, b.target);
}

function groupCorrections(findings) {
  const groups = new Map();
  for (const finding of [...findings].sort(bySeverityThenTarget)) {
    groups.set(finding.correction, [...(groups.get(finding.correction) ?? []), finding]);
  }
  return [...groups.entries()]
    .map(([correction, group]) => ({
      severity: group.map((finding) => finding.severity).reduce(highestSeverity),
      rules: [...new Set(group.flatMap((finding) => finding.rules))].sort((a, b) => ruleNumber(a) - ruleNumber(b)),
      targets: group.map((finding) => finding.target),
      consequence: sentence(group[0].consequence || group[0].evidence[0]),
      correction,
      findings: group.length,
    }))
    .sort((a, b) => SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(b.severity) || b.findings - a.findings);
}

function incompleteReasons(incomplete) {
  const labelOf = (entry) => {
    if (entry.clarification) return "clarification requests";
    return entry.check === "classification" ? "unclassified units" : "missing facts";
  };
  const counts = new Map();
  for (const entry of incomplete) counts.set(labelOf(entry), (counts.get(labelOf(entry)) ?? 0) + 1);
  return [...counts.entries()].map(([label, count]) => `${count} ${label}`).join(", ");
}

function notEnforcedEntry(entry) {
  return { rule: titledRule(entry.rule), status: entry.status, reason: entry.reason, component: entry.component };
}

function runFindings(store) {
  const keys = new Set(store.lastRun.findingKeys.map((key) => JSON.stringify(key)));
  return store.findings.filter((finding) => keys.has(JSON.stringify([finding.target, finding.defect, finding.scope])));
}

function overlapEntry(finding) {
  return { target: finding.target, defect: finding.defect, rules: finding.rules, correction: finding.correction };
}

function overlappingFindings(findings) {
  const byUnit = new Map();
  for (const finding of findings) {
    for (const unit of finding.units ?? []) byUnit.set(unit, [...(byUnit.get(unit) ?? []), finding]);
  }
  return [...byUnit.entries()]
    .filter(([, group]) => new Set(group.map((finding) => finding.correction)).size > 1)
    .sort(([a], [b]) => naturalOrder(a, b))
    .map(([unit, group]) => ({ unit, findings: group.map(overlapEntry) }));
}

export function contractData(store) {
  const { lastRun } = store;
  const findings = runFindings(store);
  const summary = computeVerdict({
    rows: findings, incomplete: lastRun.incomplete, flow: lastRun.flow, modelPresent: true,
  });
  const groups = classifyFindings(findings, lastRun.flow);
  return {
    flow: lastRun.flow,
    scope: lastRun.scope,
    ...summary,
    incompleteReasons: incompleteReasons(lastRun.incomplete),
    notRun: lastRun.notRun,
    notEnforced: lastRun.skipped.map(notEnforcedEntry),
    corrections: groupCorrections(groups.blocking),
    questions: lastRun.questions,
    covered: lastRun.covered ?? 0,
    dropped: lastRun.dropped ?? [],
    overlaps: overlappingFindings(findings),
    findings,
  };
}

export function noModelData(flow) {
  return { flow, verdict: "OK", noModel: true };
}

function countsLine(counts) {
  return SEVERITIES.map((severity) => `${counts[severity]} ${severity}`).join(", ");
}

function notEnforcedLine(entry) {
  const place = entry.component ? ` in ${entry.component}` : "";
  return `${entry.rule}${place} (${entry.status}: ${entry.reason})`;
}

function notRunLine(entry) {
  return `${entry.check} (${entry.reason})`;
}

function correctionLine(correction, index) {
  const rules = rulesText(correction.rules);
  const where = correction.targets.join("; ");
  return `${index + 1}. ${rules}: ${where}: ${correction.consequence} Fix: ${correction.correction}`;
}

function rulesText(rules) {
  return rules.map(titledRule).join("; ");
}

function findingLine(finding) {
  const consequence = sentence(finding.consequence);
  return `- ${rulesText(finding.rules)}: ${finding.target}: ${consequence} Fix: ${finding.correction}`;
}

function overlapLine(entry) {
  return `  - ${rulesText(entry.rules)}: ${entry.target}: Fix: ${entry.correction}`;
}

function overlapLines(overlap) {
  return [`- ${overlap.unit}:`, ...overlap.findings.map(overlapLine)];
}

function sectionOf(title, lines) {
  return lines.length > 0 ? [[`${title}:`, ...lines].join("\n")] : [];
}

function findingSections(data) {
  const groups = classifyFindings(data.findings, data.flow);
  return [
    ...sectionOf("Inherited findings", groups.inherited.map(findingLine)),
    ...sectionOf("Wider observations", groups.wider.map(findingLine)),
    ...sectionOf("Overlapping findings", data.overlaps.flatMap(overlapLines)),
  ];
}

function droppedLine(data) {
  const reasons = new Map();
  const tally = (reason, count) => reasons.set(reason, (reasons.get(reason) ?? 0) + count);
  tally(COVERED_REASON, data.covered);
  for (const entry of data.dropped) tally(entry.reason, 1);
  const parts = [...reasons.entries()].filter(([, count]) => count > 0).map(([reason, count]) => `${count} ${reason}`);
  const total = data.covered + data.dropped.length;
  return `Dropped: ${total}${parts.length > 0 ? ` (${parts.join(", ")})` : ""}`;
}

function listOrNone(items) {
  return items.length > 0 ? items.join(", ") : "none";
}

export function renderContract(data) {
  if (data.noModel) {
    return [
      `# Architecture ${data.flow}: no model`,
      `Verdict: ${data.verdict}`,
      "no architecture model; run a baseline audit to enable the full review",
    ].join("\n");
  }
  const reasons = data.incompleteReasons ? ` (${data.incompleteReasons})` : "";
  const corrections = data.corrections.map(correctionLine);
  return [
    `# Architecture ${data.flow}: ${data.scope}`,
    `Verdict: ${data.verdict}: ${countsLine(data.blocking)} blocking`,
    `Inherited: ${countsLine(data.inherited)} (not blocking)`,
    `Incomplete: ${data.incompleteCount} conditions${reasons}`,
    `Not run: ${listOrNone(data.notRun.map(notRunLine))}`,
    `Advisory: ${plural(data.advisory, "finding")}`,
    droppedLine(data),
    `Rules not enforced: ${listOrNone(data.notEnforced.map(notEnforcedLine))}`,
    corrections.length > 0 ? ["Corrections:", ...corrections].join("\n") : "Corrections: none",
    ...findingSections(data),
    `Questions for the user: ${data.questions.length}`,
    ...data.questions.map((question) => `- ${question}`),
  ].join("\n");
}

function rankedLine(finding, index) {
  const rules = finding.rules.map(titledRule).join("; ");
  const what = sentence(finding.consequence || finding.evidence[0]);
  return `${index + 1}. [${finding.severity}] ${rules}: ${finding.target}: ${what}`;
}

function ruleCounts(findings) {
  const counts = new Map();
  for (const finding of findings) {
    for (const rule of finding.rules) counts.set(rule, (counts.get(rule) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort(([a], [b]) => ruleNumber(a) - ruleNumber(b))
    .map(([rule, count]) => `${titledRule(rule)} x${count}`)
    .join(", ");
}

export function rankData({ findings, commits, window }) {
  const componentOf = (finding) => finding.component ?? NO_COMPONENT;
  const names = [...new Set(findings.map(componentOf))];
  const volatile = names
    .filter((name) => (commits.get(name) ?? 0) > 0)
    .sort((a, b) => commits.get(b) - commits.get(a) || naturalOrder(a, b));
  const quiet = names.filter((name) => !volatile.includes(name)).sort(naturalOrder);
  const inComponent = (name) => findings.filter((finding) => componentOf(finding) === name);
  return {
    window,
    volatile: volatile.map((name) => ({
      component: name,
      commits: commits.get(name),
      findings: inComponent(name).sort(bySeverityThenTarget),
    })),
    quiet: quiet.map((name) => ({ component: name, counts: ruleCounts(inComponent(name)) })),
  };
}

export function renderRank(rank) {
  const volatile = rank.volatile.flatMap((entry) => [
    `### ${entry.component} (${plural(entry.commits, "commit")})`,
    ...entry.findings.map(rankedLine),
  ]);
  const quiet = rank.quiet.length > 0
    ? [`### Components with no commits in ${rank.window}`, ...rank.quiet.map((e) => `- ${e.component}: ${e.counts}`)]
    : [];
  return ["## Ranked by change volatility", ...volatile, ...quiet].join("\n");
}
