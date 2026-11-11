import { existsSync } from "node:fs";
import { ModelError, UsageError } from "../cli/errors.mjs";
import { parseArgs } from "../cli/flags.mjs";
import { loadGraph } from "../graph/load.mjs";
import { EDITS } from "../model/edits.mjs";
import { explainPath, renderExplanation, renderThresholds, thresholdRows } from "../model/explain.mjs";
import { graphProblems } from "../model/graph-problems.mjs";
import { RECORD_MODES, STARTS, initModel } from "../model/init.mjs";
import { loadModel, modelFile, readDocument, recordDir } from "../model/load.mjs";
import { migrateOldModel } from "../model/migrate.mjs";
import { writeDocument } from "../model/write.mjs";

const MAX_POSITIONAL = 12;
const KEY_VALUE = /^([a-z][a-z-]*)=([\s\S]*)$/;
const INIT_FLAGS = ["start", "adapter", "record-mode"];
const INIT_USAGE =
  'arch model init --start <greenfield|legacy> --adapter "<command>" [--record-mode committed|local]';
const GLOBAL_FLAGS = ["json", "record"];

function missingModel(root, flags) {
  return new ModelError(
    `no architecture model found at ${modelFile(root, flags)}. ` +
      'Create one with arch model init --start <greenfield|legacy> --adapter "<command>", ' +
      "or convert the old files with arch model migrate.",
  );
}

function requireModel(root, flags) {
  const model = loadModel(root, flags);
  if (model) return model;
  throw missingModel(root, flags);
}

function requireDocument(root, flags) {
  if (existsSync(modelFile(root, flags))) return readDocument(modelFile(root, flags));
  throw missingModel(root, flags);
}

function print(flags, data, text) {
  console.log(flags.json ? JSON.stringify(data, null, 2) : text);
}

async function validate({ root, flags }) {
  const model = requireModel(root, flags);
  print(flags, { ok: true }, "model: ok");
  const graph = await loadGraph(root, model, { flags });
  const problems = graphProblems(model, graph);
  if (problems.length === 0) return 0;
  const listed = problems.join("\n- ");
  const advice = "Fix these entries and run arch model validate again.";
  throw new ModelError(`the model does not fit the code:\n- ${listed}\n${advice}`);
}

function explain({ root, flags, positional: [path] }) {
  const result = explainPath(requireModel(root, flags), path.replace(/^\.\//, ""));
  print(flags, result, renderExplanation(result));
  return 0;
}

function explainThresholds({ root, flags }) {
  const rows = thresholdRows(loadModel(root, flags));
  print(flags, rows, renderThresholds(rows));
  return 0;
}

function requireChoice(flags, name, choices) {
  const value = flags[name];
  if (choices.includes(value)) return value;
  throw new UsageError(`--${name} must be one of ${choices.join(", ")}. Pass it as --${name} <value>.`);
}

async function init({ root, flags }) {
  const start = requireChoice(flags, "start", STARTS);
  if (!flags.adapter) {
    throw new UsageError('init needs --adapter "<command>", the command that prints the adapter document.');
  }
  const modeFlags = { "record-mode": flags["record-mode"] ?? RECORD_MODES[0] };
  const recordMode = requireChoice(modeFlags, "record-mode", RECORD_MODES);
  const file = modelFile(root, flags);
  await initModel({ root, directory: recordDir(root, flags), file, start, adapter: flags.adapter, recordMode });
  console.log(`wrote ${file}. Check it with arch model validate.`);
  return 0;
}

function migrate({ root, flags }) {
  const file = modelFile(root, flags);
  migrateOldModel({ root, flags, file });
  console.log(`wrote ${file}. The old files under the record path were left in place.`);
  console.log(
    "The adapter is empty. Copy an adapter template for your language from the skill's adapter-templates " +
      'directory into the project, then run arch model set-adapter "<command>".',
  );
  return 0;
}

function applyEdit(edit) {
  return ({ root, flags, positional, keys }) => {
    const file = modelFile(root, flags);
    const document = requireDocument(root, flags);
    edit.apply(document, positional, keys);
    writeDocument(file, document);
    console.log(`updated ${file}`);
    return 0;
  };
}

function command(usage, positional, run, extra = {}) {
  return { usage, positional, required: [], optional: [], flags: [], run, ...extra };
}

function directCommands() {
  return {
    init: command(INIT_USAGE, 0, init, { flags: INIT_FLAGS }),
    validate: command("arch model validate", 0, validate),
    explain: command("arch model explain <path>", 1, explain),
    "explain-thresholds": command("arch model explain-thresholds", 0, explainThresholds),
    migrate: command("arch model migrate", 0, migrate),
  };
}

function editCommands() {
  return Object.fromEntries(
    Object.entries(EDITS).map(([name, edit]) => [name, { ...edit, flags: [], run: applyEdit(edit) }]),
  );
}

export const MODEL_SUBCOMMANDS = { ...directCommands(), ...editCommands() };

function chooseSubcommand(name) {
  if (Object.hasOwn(MODEL_SUBCOMMANDS, name)) return MODEL_SUBCOMMANDS[name];
  const known = Object.keys(MODEL_SUBCOMMANDS).join(", ");
  throw new UsageError(`unknown model subcommand: ${name ?? "(none)"}. Known subcommands: ${known}.`);
}

function rejectForeignFlags(subcommand, flags) {
  const allowed = [...GLOBAL_FLAGS, ...subcommand.flags];
  const foreign = Object.keys(flags).filter((name) => !allowed.includes(name));
  if (foreign.length > 0) {
    throw new UsageError(`--${foreign[0]} does not apply to this subcommand. usage: ${subcommand.usage}`);
  }
}

function splitKeyValues(subcommand, args) {
  const positional = [];
  const keys = {};
  const allowed = [...subcommand.required, ...subcommand.optional];
  for (const arg of args) {
    const match = KEY_VALUE.exec(arg);
    if (!match) {
      positional.push(arg);
    } else if (allowed.includes(match[1])) {
      keys[match[1]] = match[2];
    } else {
      throw new UsageError(`unknown argument "${match[1]}=". usage: ${subcommand.usage}`);
    }
  }
  return { positional, keys };
}

function checkArguments(subcommand, { positional, keys }) {
  const missing = subcommand.required.filter((name) => !keys[name]);
  if (positional.length !== subcommand.positional || missing.length > 0) {
    const detail = missing.length > 0 ? ` Missing: ${missing.map((name) => `${name}=`).join(", ")}.` : "";
    throw new UsageError(`wrong arguments.${detail} usage: ${subcommand.usage}`);
  }
}

export const MODEL_SPEC = {
  flags: { start: "value", adapter: "value", "record-mode": "value" },
  positional: { min: 0, max: MAX_POSITIONAL },
};

export async function run(args, { root }) {
  const { positional: all, flags } = parseArgs(MODEL_SPEC, args);
  const [name, ...rest] = all;
  const subcommand = chooseSubcommand(name);
  rejectForeignFlags(subcommand, flags);
  const parsed = splitKeyValues(subcommand, rest);
  checkArguments(subcommand, parsed);
  return subcommand.run({ root, flags, ...parsed });
}
