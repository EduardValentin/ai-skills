import { UsageError } from "../cli/errors.mjs";
import { parseArgs } from "../cli/flags.mjs";
import { concernsEnforcedRule } from "../checks/status.mjs";
import { renderCheckMarkdown } from "../checks/render.mjs";
import { proposalComparison } from "../checks/proposal.mjs";
import { runChecks } from "../checks/run.mjs";
import { touchedScope } from "../checks/scope.mjs";
import { runRecord } from "../findings/binding.mjs";
import { loadGraph } from "../graph/load.mjs";
import { NO_MODEL_LINE, loadModel } from "../model/load.mjs";

export const CHECK_SPEC = {
  flags: { base: "git-ref", proposal: "value", strict: "boolean" },
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

export async function run(args, { root }) {
  const { flags } = parseArgs(CHECK_SPEC, args);
  if (flags.proposal && flags.base) {
    throw new UsageError(
      "--proposal cannot be combined with --base: a plan has no commits to compare with. " +
        "Use --base to review a diff, or --proposal to review a plan.",
    );
  }
  const model = loadModel(root, flags);
  if (!model) {
    console.log(flags.json ? JSON.stringify({ model: false }) : NO_MODEL_LINE);
    return 0;
  }
  const { clarifications, ...subject } = await subjectOf(root, model, flags);
  printWarnings(subject.graph);
  const result = runChecks({ model, ...subject });
  const incomplete = [...result.incomplete, ...clarifications];
  const output = { model: true, run: await runRecord({ root, model, flags }), ...result, incomplete };
  console.log(flags.json ? JSON.stringify(output, null, 2) : renderCheckMarkdown(output));
  return breaches(result, flags) || leavesEnforcedRuleUndecided(output, model, flags) ? 1 : 0;
}
