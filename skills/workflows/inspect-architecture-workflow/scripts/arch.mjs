#!/usr/bin/env node
import process from "node:process";
import { ArchError, UsageError } from "./lib/cli/errors.mjs";
import { parseArgs } from "./lib/cli/flags.mjs";
import { run as runCheck } from "./lib/commands/check.mjs";
import { run as runCollect } from "./lib/commands/collect.mjs";
import { run as runModel } from "./lib/commands/model.mjs";

const NOT_IMPLEMENTED_EXIT = 2;

function legacy(file) {
  return async (args, ctx) => {
    const module = await import(`./lib/commands/${file}.mjs`);
    return module.run(args, ctx);
  };
}

function pending(name, spec) {
  return async (args) => {
    parseArgs(spec, args);
    console.error(`arch ${name}: not implemented`);
    return NOT_IMPLEMENTED_EXIT;
  };
}

const NO_POSITIONAL = { min: 0, max: 0 };

const handlers = {
  collect: runCollect,
  check: runCheck,
  applicable: pending("applicable", { flags: {}, positional: NO_POSITIONAL }),
  findings: pending("findings", { flags: {}, positional: { min: 0, max: 2 } }),
  query: legacy("query"),
  uncovered: legacy("uncovered"),
  model: runModel,
  ledger: legacy("ledger"),
};

function usageText() {
  return `usage: arch <${Object.keys(handlers).join("|")}> [options]`;
}

function selectHandler(name) {
  if (!name) throw new UsageError(`missing subcommand. ${usageText()}`);
  if (!Object.hasOwn(handlers, name)) {
    throw new UsageError(`unknown subcommand: ${name}. Known subcommands: ${Object.keys(handlers).join(", ")}.`);
  }
  return handlers[name];
}

async function main() {
  const [name, ...rest] = process.argv.slice(2);
  try {
    return await selectHandler(name)(rest, { root: process.cwd() });
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    return error instanceof ArchError ? error.exitCode : 2;
  }
}

process.exitCode = await main();
