#!/usr/bin/env node
import process from "node:process";

const USAGE = "usage: arch <graph|diff|query|assess|uncovered|model|readme-summary> [options]";

const handlers = {
  async graph(args, ctx) { const m = await import("./lib/commands/graph.mjs"); return m.run(args, ctx); },
  async diff(args, ctx) { const m = await import("./lib/commands/diff.mjs"); return m.run(args, ctx); },
  async query(args, ctx) { const m = await import("./lib/commands/query.mjs"); return m.run(args, ctx); },
  async assess(args, ctx) { const m = await import("./lib/commands/assess.mjs"); return m.run(args, ctx); },
  async uncovered(args, ctx) { const m = await import("./lib/commands/uncovered.mjs"); return m.run(args, ctx); },
  async model(args, ctx) { const m = await import("./lib/commands/model.mjs"); return m.run(args, ctx); },
  async "readme-summary"(args, ctx) { const m = await import("./lib/commands/readme.mjs"); return m.run(args, ctx); },
};

async function main() {
  const [sub, ...rest] = process.argv.slice(2);
  if (!sub) { console.error(USAGE); return 1; }
  const handler = handlers[sub];
  if (!handler) { console.error(`unknown subcommand: ${sub}\n${USAGE}`); return 1; }
  try {
    return await handler(rest, { root: process.cwd() });
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    return 1;
  }
}

process.exitCode = await main();
