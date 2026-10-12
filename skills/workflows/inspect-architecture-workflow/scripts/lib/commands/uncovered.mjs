import { parseFlags } from "../args.mjs";
import { loadOrBuildGraph } from "../graph.mjs";

export async function run(args, ctx) {
  const { flags } = parseFlags(args);
  const graph = await loadOrBuildGraph(ctx.root, { cruiseJsonPath: flags["cruise-json"], exportsJsonPath: flags["exports-json"] });
  if (flags.json) {
    console.log(JSON.stringify(graph.uncovered));
  } else {
    for (const path of graph.uncovered) console.log(path);
  }
  return graph.uncovered.length > 0 ? 1 : 0;
}
