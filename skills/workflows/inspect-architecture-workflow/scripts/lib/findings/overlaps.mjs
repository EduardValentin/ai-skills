import { naturalOrder } from "../checks/targets.mjs";
import { alternatives } from "../text.mjs";

function overlapEntry(finding) {
  return {
    target: finding.target,
    defect: finding.defect,
    rules: finding.rules,
    corrections: finding.corrections,
    files: finding.judgedFiles,
  };
}

function comesFromParallelReviewers(group) {
  const files = new Set(group.flatMap((finding) => finding.judgedFiles));
  const corrections = new Set(group.map((finding) => alternatives(finding.corrections)));
  return files.size > 1 && corrections.size > 1;
}

export function overlappingFindings(judgedFindings) {
  const byUnit = new Map();
  for (const finding of judgedFindings) {
    for (const unit of finding.units ?? []) byUnit.set(unit, [...(byUnit.get(unit) ?? []), finding]);
  }
  return [...byUnit.entries()]
    .filter(([, group]) => comesFromParallelReviewers(group))
    .sort(([a], [b]) => naturalOrder(a, b))
    .map(([unit, group]) => ({ unit, findings: group.map(overlapEntry) }));
}
