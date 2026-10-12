import { parseFlags } from "../args.mjs";
import { diffGraphs } from "../diff.mjs";
import { renames } from "../git.mjs";
import { loadOrBuildGraph } from "../graph.mjs";

function renderPair(pair) { return `${pair[0] ?? "-"} -> ${pair[1] ?? "-"}`; }

function renderMarkdown(diff) {
  const lines = ["## Units"];
  for (const p of diff.units.added) lines.push(`+ ${p}`);
  for (const p of diff.units.removed) lines.push(`- ${p}`);
  for (const m of diff.units.moved) lines.push(`~ ${m.from} -> ${m.to}`);
  for (const m of diff.units.modifiedClassification) lines.push(`! ${m.path} (ring: ${m.from.ring} -> ${m.to.ring}, kind: ${m.from.kind} -> ${m.to.kind})`);
  lines.push("", "## Edges");
  for (const e of diff.edges.added) lines.push(`+ ${e.from} -> ${e.to} (${e.kind}, ${e.direction})`);
  for (const e of diff.edges.removed) lines.push(`- ${e.from} -> ${e.to} (${e.kind}, ${e.direction})`);
  lines.push("", "## Components");
  lines.push("| Component | Fan-in | Fan-out | I | A | D | Moved |");
  lines.push("|---|---|---|---|---|---|---|");
  for (const c of diff.components) {
    lines.push(`| ${c.id} | ${renderPair(c.fanIn)} | ${renderPair(c.fanOut)} | ${renderPair(c.instability)} | ${renderPair(c.abstractness)} | ${renderPair(c.distance)} | ${c.movedPastThreshold} |`);
  }
  lines.push("", "## Cycles");
  for (const cycle of diff.cycles.new) lines.push(`+ ${cycle.join(" -> ")}`);
  for (const cycle of diff.cycles.gone) lines.push(`- ${cycle.join(" -> ")}`);
  return lines.join("\n");
}

export async function run(args, ctx) {
  const { positional, flags } = parseFlags(args);
  const [base] = positional;
  if (!base) {
    console.error("usage: arch diff <base> [--cruise-json <file>] [--exports-json <file>] [--json]");
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
