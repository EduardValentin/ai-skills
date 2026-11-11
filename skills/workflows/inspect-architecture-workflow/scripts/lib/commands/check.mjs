import { UsageError } from "../cli/errors.mjs";
import { parseArgs } from "../cli/flags.mjs";
import { concernsEnforcedRule } from "../checks/status.mjs";
import { renderCheckMarkdown } from "../checks/render.mjs";
import { proposalComparison } from "../checks/proposal.mjs";
import { runChecks } from "../checks/run.mjs";
import { touchedScope } from "../checks/scope.mjs";
import { requireWorkPlacement, writeWorkFile } from "../findings/placement.mjs";
import { runRecord } from "../findings/binding.mjs";
import { loadGraph } from "../graph/load.mjs";
import { NO_MODEL_LINE, loadModel } from "../model/load.mjs";

export const CHECK_EXCLUSIVE = ["base", "proposal"];

export const CHECK_SPEC = {
  flags: { base: "git-ref", out: "value", proposal: "value", strict: "boolean" },
  positional: { min: 0, max: 0 },
};

function printWarnings(graph) {
  for (const warning of graph.warnings) console.error(warning);
}

async function subjectOf(root, model, flags) {
  if (flags.proposal) return proposalComparison({ root, model, file: flags.proposal });
  const graph = await loadGraph(root, model, { flags });
  if (!flags.base) return { graph, clarifications: [] };
  const baseGraph = await loadGraph(root, model, { ref: flags.base, flags });
  return { graph, baseGraph, touched: await touchedScope(root, graph, flags.base), clarifications: [] };
}

function breaches(result, flags) {
  const compared = flags.base || flags.proposal;
  return result.rows.some((row) => row.status === "enforced" && (!compared || row.origin === "introduced"));
}

function leavesEnforcedRuleUndecided(result, model, flags) {
  return flags.strict && result.incomplete.some((entry) => concernsEnforcedRule(model, entry.rules));
}

async function emit(output, flags, root) {
  if (!flags.out) {
    console.log(flags.json ? JSON.stringify(output, null, 2) : renderCheckMarkdown(output));
    return;
  }
  await writeWorkFile(root, flags.out, `${JSON.stringify(output, null, 2)}\n`);
  const counts = output.model ? `${output.rows.length} findings, ${output.incomplete.length} incomplete` : "no model";
  console.log(`wrote ${flags.out}: ${counts}`);
}

export async function run(args, { root }) {
  const { flags } = parseArgs(CHECK_SPEC, args);
  for (const name of ["proposal", "out"]) if (flags[name]) requireWorkPlacement(root, flags[name], name);
  if (CHECK_EXCLUSIVE.every((name) => flags[name])) {
    throw new UsageError(
      "--proposal cannot be combined with --base: a plan has no commits to compare with. " +
        "Use --base to review a diff, or --proposal to review a plan.",
    );
  }
  const model = loadModel(root, flags);
  if (!model) {
    if (flags.json || flags.out) await emit({ model: false }, flags, root);
    else console.log(NO_MODEL_LINE);
    return 0;
  }
  const { clarifications, ...subject } = await subjectOf(root, model, flags);
  printWarnings(subject.graph);
  const result = runChecks({ model, ...subject });
  const incomplete = [...result.incomplete, ...clarifications];
  const output = { model: true, run: await runRecord({ root, model, flags }), ...result, incomplete };
  await emit(output, flags, root);
  return breaches(result, flags) || leavesEnforcedRuleUndecided(output, model, flags) ? 1 : 0;
}
