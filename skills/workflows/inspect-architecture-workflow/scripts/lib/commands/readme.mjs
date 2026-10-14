import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseFlags, savedInputs } from "../args.mjs";
import { loadOrBuildGraph } from "../graph.mjs";
import { loadModel } from "../model.mjs";
import { QUERIES, renderMarkdown } from "../queries.mjs";
import { replaceSummary } from "../readme.mjs";

const README_PATH = "docs/architecture/README.md";

function summaryLine(graph) {
  return `Components: ${graph.components.length}, units: ${graph.units.length}, edges: ${graph.edges.length}, component cycles: ${graph.cycles.components.length}, uncovered modules: ${graph.uncovered.length}.`;
}

export async function run(args, ctx) {
  const { flags } = parseFlags(args);
  const graph = await loadOrBuildGraph(ctx.root, savedInputs(flags));
  const model = await loadModel(ctx.root);
  const metrics = renderMarkdown(await QUERIES.metrics(graph, model, { positional: [], flags: {} }, ctx.root));
  const componentGraph = renderMarkdown(await QUERIES["component-graph"](graph, model, { positional: [], flags: {} }, ctx.root));
  const block = [summaryLine(graph), "", metrics, "", componentGraph].join("\n");

  const file = path.join(ctx.root, README_PATH);
  const text = await readFile(file, "utf8");
  let updated;
  try {
    updated = replaceSummary(text, block);
  } catch (error) {
    console.error(error.message);
    return 1;
  }
  await writeFile(file, updated, "utf8");
  return 0;
}
