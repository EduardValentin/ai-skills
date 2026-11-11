import {
  NO_ADDITIONS,
  changeAdditions,
  judgmentScope,
  judgmentTargets,
  reviewReasons,
} from "../checks/applicability.mjs";
import { titledRule } from "../checks/rule-titles.mjs";
import { touchedScope } from "../checks/scope.mjs";
import { proposalComparison } from "../checks/proposal.mjs";
import { UsageError } from "../cli/errors.mjs";
import { parseArgs } from "../cli/flags.mjs";
import { loadGraph } from "../graph/load.mjs";
import { requireWorkPlacement } from "../findings/placement.mjs";
import { createClassifier } from "../model/classify.mjs";
import { NO_MODEL_LINE, loadModel } from "../model/load.mjs";

export const APPLICABLE_SPEC = {
  flags: { base: "git-ref", files: "value", proposal: "value", all: "boolean", full: "boolean" },
  positional: { min: 0, max: 0 },
};

const CONTAINED = "contained in one component; adds no component, port, cross-component edge, or external";

const MODES = ["base", "files", "proposal", "all"];

function requireOneMode(flags) {
  if (MODES.filter((mode) => flags[mode]).length === 1) return;
  throw new UsageError(
    "pass exactly one of --base <ref> (a change against a commit), --files <a,b,...> (paths from the project root), " +
      "--proposal <file> (a plan review), or --all (an audit).",
  );
}

async function scopeFromBase(root, model, flags) {
  const graph = await loadGraph(root, model, { flags });
  for (const warning of graph.warnings) console.error(warning);
  const baseGraph = await loadGraph(root, model, { ref: flags.base, flags });
  const touched = await touchedScope(root, graph, flags.base);
  const unitOf = new Map(graph.units.map((unit) => [unit.path, unit]));
  return {
    units: touched.units.map((path) => unitOf.get(path)),
    components: touched.components,
    uncovered: touched.uncovered,
    additions: changeAdditions({ model, baseGraph, graph, renames: touched.renames }),
  };
}

function listedPaths(files) {
  const paths = files.split(",").map((path) => path.trim().replace(/^\.\//, ""));
  return [...new Set(paths.filter(Boolean))];
}

function scopeFromFiles(model, flags) {
  const classify = createClassifier(model);
  const units = listedPaths(flags.files).map((path) => ({ path, ...classify(path) }));
  const covered = units.filter((unit) => unit.component && unit.kind);
  return {
    units: covered,
    components: [...new Set(units.map((unit) => unit.component).filter(Boolean))],
    uncovered: units.filter((unit) => !covered.includes(unit)).map((unit) => unit.path),
    additions: NO_ADDITIONS,
  };
}

async function scopeFromProposal(root, model, flags) {
  const { graph, baseGraph, touched } = await proposalComparison({ root, model, file: flags.proposal });
  const unitOf = new Map(graph.units.map((unit) => [unit.path, unit]));
  return {
    units: touched.units.map((path) => unitOf.get(path)),
    components: touched.components,
    uncovered: touched.uncovered,
    additions: changeAdditions({ model, baseGraph, graph, renames: touched.renames }),
  };
}

async function scopeFromAll(root, model, flags) {
  const graph = await loadGraph(root, model, { flags });
  for (const warning of graph.warnings) console.error(warning);
  return {
    units: graph.units,
    components: graph.components.map((component) => component.name),
    uncovered: graph.uncovered,
    additions: { ...NO_ADDITIONS, components: graph.components.map((component) => component.name) },
  };
}

function auditApplicability(model, scope) {
  const groups = judgmentScope(model, judgmentTargets(model, scope));
  const inScope = judgmentCount(groups);
  const uncovered = scope.uncovered;
  if (inScope === 0) {
    return { review: false, reasons: ["no judgment condition is in scope"], groups, uncovered, notReviewed: 0 };
  }
  const reasons = [`audit: every unit and component is in scope and ${inScope} judgment conditions apply`];
  return { review: true, reasons, groups, uncovered, notReviewed: 0 };
}

function judgmentCount(groups) {
  return groups.reduce((sum, entry) => sum + entry.judgments.length, 0);
}

function applicability(model, scope, flags) {
  if (flags.all) return auditApplicability(model, scope);
  const structural = reviewReasons(scope);
  const groups = judgmentScope(model, judgmentTargets(model, scope));
  const inScope = judgmentCount(groups);
  const uncovered = scope.uncovered;
  if (structural.length > 0) return { review: true, reasons: structural, groups, uncovered, notReviewed: 0 };
  if (flags.full && inScope > 0) {
    const reasons = [`--full was passed and ${inScope} judgment conditions are in scope`];
    return { review: true, reasons, groups, uncovered, notReviewed: 0 };
  }
  return { review: false, reasons: [CONTAINED], groups: [], uncovered, notReviewed: inScope };
}

function jsonOutput(result) {
  return {
    model: true,
    review: result.review,
    reasons: result.reasons,
    groups: result.groups.map((entry) => entry.group),
    uncovered: result.uncovered,
    judgments: Object.fromEntries(result.groups.map((entry) => [entry.group, entry.judgments])),
    notReviewed: result.notReviewed,
  };
}

function notReviewedLines(result) {
  if (result.notReviewed === 0) return [];
  return [
    `Judgment conditions not reviewed for a contained change: ${result.notReviewed}. Pass --full to review them.`,
  ];
}

function bulleted(lines) {
  return lines.length > 0 ? lines.map((line) => `- ${line}`) : ["- none"];
}

function renderProse(result) {
  const groupLines = result.groups.map((entry) => `${entry.group}: ${entry.rules.map(titledRule).join("; ")}`);
  return [
    `Review needed: ${result.review ? "yes" : "no"}`,
    "Reasons:",
    ...bulleted(result.reasons),
    "Rule groups with judgment conditions:",
    ...bulleted(groupLines),
    "Uncovered files:",
    ...bulleted(result.uncovered),
    ...notReviewedLines(result),
  ].join("\n");
}

function printNoModel(flags) {
  const output = { model: false, review: false, reasons: [NO_MODEL_LINE] };
  console.log(flags.json ? JSON.stringify(output) : NO_MODEL_LINE);
}

async function scopeOf(root, model, flags) {
  if (flags.base) return scopeFromBase(root, model, flags);
  if (flags.proposal) return scopeFromProposal(root, model, flags);
  if (flags.all) return scopeFromAll(root, model, flags);
  return scopeFromFiles(model, flags);
}

export async function run(args, { root }) {
  const { flags } = parseArgs(APPLICABLE_SPEC, args);
  requireOneMode(flags);
  if (flags.proposal) requireWorkPlacement(root, flags.proposal, "proposal");
  const model = loadModel(root, flags);
  if (!model) {
    printNoModel(flags);
    return 0;
  }
  const scope = await scopeOf(root, model, flags);
  const result = applicability(model, scope, flags);
  console.log(flags.json ? JSON.stringify(jsonOutput(result), null, 2) : renderProse(result));
  return 0;
}
