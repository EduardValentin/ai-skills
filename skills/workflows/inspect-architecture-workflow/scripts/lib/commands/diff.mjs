import { parseFlags } from "../args.mjs";
import { diffGraphs } from "../diff.mjs";
import { renames } from "../git.mjs";
import { loadOrBuildGraph, modelExistsAt } from "../graph.mjs";
import { renderMarkdown as renderTable, renderValue } from "../queries.mjs";

const METRIC_PAIRS = ["instability", "abstractness", "distance"];

function renderPair(pair, missing) { return `${renderValue(pair[0], missing)} -> ${renderValue(pair[1], missing)}`; }

function componentsTable(components) {
  const rows = components.map((c) => [
    c.id,
    renderPair(c.fanIn, ""),
    renderPair(c.fanOut, ""),
    ...METRIC_PAIRS.map((key) => renderPair(c[key], "undefined")),
    c.movedPastThreshold,
  ]);
  return renderTable({ columns: ["Component", "Fan-in", "Fan-out", "I", "A", "D", "Moved"], rows });
}

function renderMarkdown(diff) {
  const lines = ["## Units"];
  for (const p of diff.units.added) lines.push(`+ ${p}`);
  for (const p of diff.units.removed) lines.push(`- ${p}`);
  for (const m of diff.units.moved) lines.push(`~ ${m.from} -> ${m.to}`);
  for (const m of diff.units.modifiedClassification) lines.push(`! ${m.path} (ring: ${renderValue(m.from.ring)} -> ${renderValue(m.to.ring)}, kind: ${renderValue(m.from.kind)} -> ${renderValue(m.to.kind)})`);
  lines.push("", "## Edges");
  for (const e of diff.edges.added) lines.push(`+ ${e.from} -> ${e.to} (${e.kind}, ${e.direction})`);
  for (const e of diff.edges.removed) lines.push(`- ${e.from} -> ${e.to} (${e.kind}, ${e.direction})`);
  lines.push("", "## Components", componentsTable(diff.components));
  lines.push("", "## Cycles");
  for (const cycle of [...diff.cycles.new, ...diff.cycles.modules.new]) lines.push(`+ ${cycle.join(" -> ")}`);
  for (const cycle of [...diff.cycles.gone, ...diff.cycles.modules.gone]) lines.push(`- ${cycle.join(" -> ")}`);
  return lines.join("\n");
}

export async function run(args, ctx) {
  const { positional, flags } = parseFlags(args);
  const [base] = positional;
  if (!base) {
    console.error("usage: arch diff <base> [--cruise-json <file>] [--exports-json <file>] [--json]");
    return 1;
  }
  if (!(await modelExistsAt(ctx.root, base))) {
    console.error(`no architecture model at ${base}; evaluate the working tree with "arch query touched --base ${base}" (change-review.md, Map step 4)`);
    return 1;
  }
  const cruiseJsonPath = flags["cruise-json"];
  const exportsJsonPath = flags["exports-json"];
  const baseGraph = await loadOrBuildGraph(ctx.root, { commit: base, cruiseJsonPath, exportsJsonPath });
  const headGraph = await loadOrBuildGraph(ctx.root, { cruiseJsonPath, exportsJsonPath, force: true });
  const renameMap = await renames(ctx.root, base);
  const diff = diffGraphs(baseGraph, headGraph, renameMap);
  console.log(flags.json ? JSON.stringify(diff, null, 2) : renderMarkdown(diff));
  return 0;
}
