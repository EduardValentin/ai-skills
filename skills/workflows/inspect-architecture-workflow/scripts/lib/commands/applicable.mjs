import {
  NO_ADDITIONS,
  changeAdditions,
  judgmentScope,
  judgmentTargets,
  plainAdditions,
} from "../checks/applicability.mjs";
import { titledRule } from "../checks/rule-titles.mjs";
import { touchedScope } from "../checks/scope.mjs";
import { proposalComparison } from "../checks/proposal.mjs";
import { UsageError } from "../cli/errors.mjs";
import { parseArgs } from "../cli/flags.mjs";
import { loadGraph } from "../graph/load.mjs";
import { requireWorkPlacement, writeWorkFile } from "../findings/placement.mjs";
import { createClassifier } from "../model/classify.mjs";
import { NO_MODEL_LINE, loadModel } from "../model/load.mjs";
import { plural } from "../text.mjs";

export const APPLICABLE_SPEC = {
  flags: { base: "git-ref", files: "value", proposal: "value", all: "boolean", out: "value" },
  positional: { min: 0, max: 0 },
};

export const APPLICABLE_MODES = ["base", "files", "proposal", "all"];

function requireOneMode(flags) {
  if (APPLICABLE_MODES.filter((mode) => flags[mode]).length === 1) return;
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
    plan: true,
  };
}

async function scopeFromAll(root, model, flags) {
  const graph = await loadGraph(root, model, { flags });
  for (const warning of graph.warnings) console.error(warning);
  return {
    units: graph.units,
    components: graph.components.map((component) => component.name),
    uncovered: graph.uncovered,
    additions: NO_ADDITIONS,
    everyComponent: true,
  };
}

function judgmentCount(groups) {
  return groups.reduce((sum, entry) => sum + entry.judgments.length, 0);
}

function unitEntry(unit) {
  return { path: unit.path, kind: unit.kind ?? null, component: unit.component ?? null };
}

function jsonOutput(scope, groups, flags) {
  const uncovered = new Set(scope.uncovered);
  return {
    model: true,
    mode: APPLICABLE_MODES.find((mode) => flags[mode]),
    units: scope.units.filter((unit) => !uncovered.has(unit.path)).map(unitEntry),
    components: scope.components,
    uncovered: scope.uncovered,
    adds: plainAdditions(scope.additions),
    groups: groups.map((entry) => entry.group),
    judgments: Object.fromEntries(groups.map((entry) => [entry.group, entry.judgments])),
    inScope: judgmentCount(groups),
  };
}

function componentsText(components) {
  const names = components.length > 0 ? ` (${components.join(", ")})` : "";
  return `${plural(components.length, "component")}${names}`;
}

function touchedText(output) {
  if (output.units.length === 0 && output.uncovered.length === 0) return "no unit touched";
  const uncovered = output.uncovered.length > 0 ? `, ${plural(output.uncovered.length, "uncovered file")}` : "";
  return `${plural(output.units.length, "unit")} in ${componentsText(output.components)}${uncovered}`;
}

function scopeSummary(output) {
  if (!output.model) return "no model";
  const conditions = `${plural(output.inScope, "judgment condition")} in ${plural(output.groups.length, "rule group")}`;
  return `${touchedText(output)}; ${conditions}`;
}

function additionLines(adds) {
  return [
    ...adds.components.map((name) => `component ${name}`),
    ...adds.ports.map((at) => `port ${at}`),
    ...adds.componentEdges.map((edge) => `component edge ${edge}`),
    ...adds.externals.map((name) => `external ${name}`),
  ];
}

function bulleted(lines) {
  return lines.length > 0 ? lines.map((line) => `- ${line}`) : ["- none"];
}

function renderProse(output, groups) {
  const groupLines = groups.map((entry) => `${entry.group}: ${entry.rules.map(titledRule).join("; ")}`);
  return [
    `Scope of the review: ${scopeSummary(output)}`,
    "Adds:",
    ...bulleted(additionLines(output.adds)),
    "Rule groups with judgment conditions:",
    ...bulleted(groupLines),
    "Uncovered files:",
    ...bulleted(output.uncovered),
  ].join("\n");
}

const NO_MODEL_OUTPUT = { model: false, reasons: [NO_MODEL_LINE] };

async function emit(output, text, { root, flags }) {
  if (flags.out) {
    await writeWorkFile(root, flags.out, `${JSON.stringify(output, null, 2)}\n`);
    console.log(`wrote ${flags.out}: ${scopeSummary(output)}`);
  } else {
    console.log(flags.json ? JSON.stringify(output, null, 2) : text);
  }
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
  for (const name of ["proposal", "out"]) if (flags[name]) requireWorkPlacement(root, flags[name], name);
  const model = loadModel(root, flags);
  if (!model) {
    await emit(NO_MODEL_OUTPUT, NO_MODEL_LINE, { root, flags });
    return 0;
  }
  const scope = await scopeOf(root, model, flags);
  const groups = judgmentScope(model, judgmentTargets(model, scope));
  const output = jsonOutput(scope, groups, flags);
  await emit(output, renderProse(output, groups), { root, flags });
  return 0;
}
