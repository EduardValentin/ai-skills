import { parseFlags, savedInputs } from "../args.mjs";
import { loadOrBuildGraph } from "../graph.mjs";
import { loadModel } from "../model.mjs";
import { QUERIES, renderJson, renderMarkdown } from "../queries.mjs";

export async function run(args, ctx) {
  const { positional, flags } = parseFlags(args);
  const [name, ...rest] = positional;
  const query = QUERIES[name];
  if (!query) {
    console.error(`unknown query: ${name}; known: ${Object.keys(QUERIES).sort().join(", ")}`);
    return 1;
  }
  const graph = await loadOrBuildGraph(ctx.root, savedInputs(flags));
  const model = await loadModel(ctx.root);
  const result = await query(graph, model, { positional: rest, flags }, ctx.root);
  console.log(flags.json ? renderJson(result) : renderMarkdown(result));
  return 0;
}
