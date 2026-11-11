import { appendFileSync, existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { ModelError, ToolingError } from "../cli/errors.mjs";
import { gitText } from "../graph/tree.mjs";
import { DEFAULT_STATUSES } from "./defaults.mjs";
import { writeDocument } from "./write.mjs";

const MODEL_VERSION = 2;
const GUIDANCE_REASON = "guidance rather than a structural invariant, so it informs and does not block";
const LEGACY_REASON = "legacy code: promote this rule to enforced per component as the code allows";

export const STARTS = Object.keys(DEFAULT_STATUSES);
export const RECORD_MODES = ["committed", "local"];

function nonEnforced(statuses) {
  return Object.entries(statuses).filter(([, status]) => status !== "enforced");
}

function startingRules(start) {
  const guidance = new Set(nonEnforced(DEFAULT_STATUSES.greenfield).map(([id]) => id));
  const entries = nonEnforced(DEFAULT_STATUSES[start]).map(([id, status]) => {
    return [id, [status, guidance.has(id) ? GUIDANCE_REASON : LEGACY_REASON]];
  });
  return Object.fromEntries(entries);
}

function initialDocument({ start, adapter, recordMode }) {
  const rules = startingRules(start);
  const withRules = Object.keys(rules).length > 0 ? { rules } : {};
  return { version: MODEL_VERSION, adapter, record: recordMode, components: [], ...withRules };
}

async function excludeFile(root, directory) {
  const out = await gitText(root, ["rev-parse", "--show-toplevel", "--git-path", "info/exclude"]);
  const [top, excludePath] = out.trim().split("\n");
  const entry = `/${relative(realpathSync(top), realpathSync(directory)).split("\\").join("/")}/`;
  return { exclude: resolve(root, excludePath), entry };
}

function excludedLines(exclude) {
  return existsSync(exclude) ? readFileSync(exclude, "utf8").split("\n") : [];
}

async function excludeLocally(root, directory) {
  const { exclude, entry } = await excludeFile(root, directory);
  mkdirSync(dirname(exclude), { recursive: true });
  if (!excludedLines(exclude).includes(entry)) appendFileSync(exclude, `${entry}\n`);
}

async function excludeOrExplain(root, directory) {
  try {
    await excludeLocally(root, directory);
  } catch {
    throw new ToolingError("record mode local needs a git repository. Run git init first or use committed.");
  }
}

async function stopExcluding(root, directory) {
  const found = await excludeFile(root, directory).catch(() => null);
  if (!found) return;
  const lines = excludedLines(found.exclude);
  if (!lines.includes(found.entry)) return;
  writeFileSync(found.exclude, lines.filter((line) => line !== found.entry).join("\n"));
}

export async function applyRecordMode({ root, directory, recordMode }) {
  if (recordMode === "local") await excludeOrExplain(root, directory);
  else await stopExcluding(root, directory);
}

export async function initModel({ root, directory, file, ...choices }) {
  if (existsSync(file)) {
    throw new ModelError(`${file} already exists. Edit it with arch model subcommands instead of running init again.`);
  }
  mkdirSync(directory, { recursive: true });
  writeDocument(file, initialDocument(choices));
  await applyRecordMode({ root, directory, recordMode: choices.recordMode });
}
