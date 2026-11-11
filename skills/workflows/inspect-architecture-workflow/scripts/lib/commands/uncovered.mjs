import { parseArgs } from "../cli/flags.mjs";
import { loadGraph } from "../graph/load.mjs";
import { requireModel } from "../model/load.mjs";

export const UNCOVERED_SPEC = { flags: {}, positional: { min: 0, max: 0 } };

export async function run(args, { root }) {
  const { flags } = parseArgs(UNCOVERED_SPEC, args);
  const model = requireModel(root, flags);
  const graph = await loadGraph(root, model, { flags });
  if (flags.json) console.log(JSON.stringify(graph.uncovered));
  else for (const path of graph.uncovered) console.log(path);
  return graph.uncovered.length > 0 ? 1 : 0;
}
