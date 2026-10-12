import { parseFlags } from "../args.mjs";
import { GRAPH_DIR, loadOrBuildGraph } from "../graph.mjs";

export async function run(args, ctx) {
  const { flags } = parseFlags(args);
  const graph = await loadOrBuildGraph(ctx.root, {
    commit: typeof flags.commit === "string" ? flags.commit : undefined,
    cruiseJsonPath: flags["cruise-json"],
    exportsJsonPath: flags["exports-json"],
    force: Boolean(flags.force),
  });
  for (const warning of graph.warnings) console.error(warning);
  if (flags.json) {
    console.log(JSON.stringify(graph, null, 2));
  } else {
    console.log(`graph: ${graph.units.length} units, ${graph.edges.length} edges, ${graph.components.length} components, ${graph.cycles.components.length} component cycles, ${graph.uncovered.length} uncovered -> ${GRAPH_DIR}/${graph.commit}.json`);
  }
  return 0;
}
