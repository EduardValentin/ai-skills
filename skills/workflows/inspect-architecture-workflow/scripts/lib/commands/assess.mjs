import { parseFlags, savedInputs } from "../args.mjs";
import { assess, assessTable, NOT_PROVIDED_LINES } from "../assess.mjs";
import { diffGraphs } from "../diff.mjs";
import { renames } from "../git.mjs";
import { loadOrBuildGraph, modelExistsAt } from "../graph.mjs";
import { loadModel } from "../model.mjs";
import { QUERIES, renderMarkdown } from "../queries.mjs";

const USAGE = "usage: arch assess [--base <ref>] [--cruise-json <file>] [--facts-json <file>] [--json]";

async function touchedScope(graph, model, flags, root) {
  const table = await QUERIES.touched(graph, model, { positional: [], flags: { ...flags, "with-neighbors": false } }, root);
  const column = (name) => table.columns.indexOf(name);
  return {
    units: table.rows.map((row) => row[column("Path")]),
    components: [...new Set(table.rows.map((row) => row[column("Component")]).filter(Boolean))],
  };
}

async function baseComparison(root, base, graph, inputs) {
  if (!(await modelExistsAt(root, base))) {
    console.error(`no architecture model at ${base}; every assessed row is marked left; set Origin from "arch query touched --base ${base}" (verdicts.md)`);
    return { baseGraph: null, diff: null };
  }
  const baseGraph = await loadOrBuildGraph(root, { commit: base, ...inputs });
  return { baseGraph, diff: diffGraphs(baseGraph, graph, await renames(root, base)) };
}

export async function run(args, ctx) {
  const { flags } = parseFlags(args);
  if (flags.base === true) { console.error(USAGE); return 1; }
  const inputs = savedInputs(flags);
  const graph = await loadOrBuildGraph(ctx.root, { ...inputs, force: Boolean(flags.base) });
  const model = await loadModel(ctx.root);
  const comparison = flags.base
    ? { ...(await baseComparison(ctx.root, flags.base, graph, inputs)), touched: await touchedScope(graph, model, flags, ctx.root) }
    : {};
  const { rows, notProvided } = assess({ graph, model, ...comparison });
  for (const fact of notProvided) console.error(NOT_PROVIDED_LINES[fact]);
  console.log(flags.json ? JSON.stringify({ rows, notProvided }, null, 2) : renderMarkdown(assessTable(rows)));
  return 0;
}
