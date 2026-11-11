import {
  NO_ADDITIONS,
  changeAdditions,
  judgmentScope,
  judgmentTargets,
  reviewReasons,
} from "../checks/applicability.mjs";
import { titledRule } from "../checks/rule-titles.mjs";
import { touchedScope } from "../checks/scope.mjs";
import { UsageError } from "../cli/errors.mjs";
import { parseArgs } from "../cli/flags.mjs";
import { loadGraph } from "../graph/load.mjs";
import { createClassifier } from "../model/classify.mjs";
import { NO_MODEL_LINE, loadModel } from "../model/load.mjs";

export const APPLICABLE_SPEC = { flags: { base: "git-ref", files: "value" }, positional: { min: 0, max: 0 } };

function requireOneScope(flags) {
  if (Boolean(flags.base) !== Boolean(flags.files)) return;
  throw new UsageError(
    "pass exactly one of --base <ref> (a change against a commit) or --files <a,b,...> (paths from the project root).",
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
  const covered = units.filter((unit) => unit.component);
  return {
    units: covered,
    components: [...new Set(covered.map((unit) => unit.component))],
    uncovered: units.filter((unit) => !unit.component).map((unit) => unit.path),
    additions: NO_ADDITIONS,
  };
}

function applicability(model, scope) {
  const reasons = reviewReasons(scope);
  return { reasons, groups: judgmentScope(model, judgmentTargets(scope)), uncovered: scope.uncovered };
}

function jsonOutput(result) {
  return {
    model: true,
    review: result.reasons.length > 0,
    reasons: result.reasons,
    groups: result.groups.map((entry) => entry.group),
    uncovered: result.uncovered,
    judgments: Object.fromEntries(result.groups.map((entry) => [entry.group, entry.judgments])),
  };
}

function bulleted(lines) {
  return lines.length > 0 ? lines.map((line) => `- ${line}`) : ["- none"];
}

function renderProse(result) {
  const groupLines = result.groups.map((entry) => `${entry.group}: ${entry.rules.map(titledRule).join("; ")}`);
  return [
    `Review needed: ${result.reasons.length > 0 ? "yes" : "no"}`,
    "Reasons:",
    ...bulleted(result.reasons),
    "Rule groups with judgment conditions:",
    ...bulleted(groupLines),
    "Uncovered files:",
    ...bulleted(result.uncovered),
  ].join("\n");
}

function printNoModel(flags) {
  const output = { model: false, review: false, reasons: [NO_MODEL_LINE] };
  console.log(flags.json ? JSON.stringify(output) : NO_MODEL_LINE);
}

export async function run(args, { root }) {
  const { flags } = parseArgs(APPLICABLE_SPEC, args);
  requireOneScope(flags);
  const model = loadModel(root, flags);
  if (!model) {
    printNoModel(flags);
    return 0;
  }
  const scope = flags.base ? await scopeFromBase(root, model, flags) : scopeFromFiles(model, flags);
  const result = applicability(model, scope);
  console.log(flags.json ? JSON.stringify(jsonOutput(result), null, 2) : renderProse(result));
  return 0;
}
