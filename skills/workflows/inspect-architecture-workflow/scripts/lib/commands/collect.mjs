import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { parseArgs } from "../cli/flags.mjs";
import { renderCurrentPicture } from "../graph/current-picture.mjs";
import { loadGraph } from "../graph/load.mjs";
import { recordDir, requireModel } from "../model/load.mjs";

export const COLLECT_SPEC = { flags: { ref: "git-ref" }, positional: { min: 0, max: 0 } };

function summaryLine(graph) {
  const cycles = graph.cycles.modules.length + graph.cycles.components.length;
  return (
    `collect: ${graph.units.length} units, ${graph.edges.length} edges, ${graph.components.length} components, ` +
    `${cycles} cycles, ${graph.uncovered.length} uncovered`
  );
}

function writeCurrentPicture(root, flags, graph, model) {
  const directory = recordDir(root, flags);
  mkdirSync(directory, { recursive: true });
  writeFileSync(path.join(directory, "current.md"), renderCurrentPicture(graph, model.thresholds));
}

export async function run(args, { root }) {
  const { flags } = parseArgs(COLLECT_SPEC, args);
  const model = requireModel(root, flags);
  const graph = await loadGraph(root, model, { ref: flags.ref, flags });
  for (const warning of graph.warnings) console.error(warning);
  if (!flags.ref) writeCurrentPicture(root, flags, graph, model);
  console.log(flags.json ? JSON.stringify(graph, null, 2) : summaryLine(graph));
  return 0;
}
