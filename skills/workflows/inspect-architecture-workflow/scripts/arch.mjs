#!/usr/bin/env node
import process from "node:process";
import { ArchError, UsageError } from "./lib/cli/errors.mjs";
import { run as runApplicable } from "./lib/commands/applicable.mjs";
import { run as runCheck } from "./lib/commands/check.mjs";
import { run as runCollect } from "./lib/commands/collect.mjs";
import { run as runFindings } from "./lib/commands/findings.mjs";
import { run as runModel } from "./lib/commands/model.mjs";
import { run as runQuery } from "./lib/commands/query.mjs";
import { run as runUncovered } from "./lib/commands/uncovered.mjs";

const handlers = {
  collect: runCollect,
  check: runCheck,
  applicable: runApplicable,
  findings: runFindings,
  query: runQuery,
  uncovered: runUncovered,
  model: runModel,
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
