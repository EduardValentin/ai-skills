import { parseArgs } from "../cli/flags.mjs";
import { concernsEnforcedRule } from "../checks/status.mjs";
import { renderCheckMarkdown } from "../checks/render.mjs";
import { runChecks } from "../checks/run.mjs";
import { touchedScope } from "../checks/scope.mjs";
import { loadGraph } from "../graph/load.mjs";
import { loadModel } from "../model/load.mjs";

export const CHECK_SPEC = { flags: { base: "value", strict: "boolean" }, positional: { min: 0, max: 0 } };

const NO_MODEL_LINE = "no architecture model; run a baseline audit to enable the full review";

function printWarnings(graph) {
  for (const warning of graph.warnings) console.error(warning);
}

async function comparisonWithBase(root, model, graph, flags) {
  if (!flags.base) return {};
  const baseGraph = await loadGraph(root, model, { ref: flags.base, flags });
  return { baseGraph, touched: await touchedScope(root, graph, model, flags.base) };
}

function breaches(result, flags) {
  return result.rows.some((row) => row.status === "enforced" && (!flags.base || row.origin === "introduced"));
}

function leavesEnforcedRuleUndecided(result, model, flags) {
  return flags.strict && result.incomplete.some((entry) => concernsEnforcedRule(model, entry.rules));
}

export async function run(args, { root }) {
  const { flags } = parseArgs(CHECK_SPEC, args);
  const model = loadModel(root, flags);
  if (!model) {
    console.log(flags.json ? JSON.stringify({ model: false }) : NO_MODEL_LINE);
    return 0;
  }
  const graph = await loadGraph(root, model, { flags });
  printWarnings(graph);
  const result = runChecks({ graph, model, ...(await comparisonWithBase(root, model, graph, flags)) });
  const output = { model: true, ...result };
  console.log(flags.json ? JSON.stringify(output, null, 2) : renderCheckMarkdown(output));
  return breaches(result, flags) || leavesEnforcedRuleUndecided(result, model, flags) ? 1 : 0;
}
