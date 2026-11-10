import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { ModelError, ToolingError } from "../cli/errors.mjs";
import { git } from "../git.mjs";
import { DEFAULT_STATUSES } from "./defaults.mjs";
import { writeDocument } from "./write.mjs";

const TEMPLATE = new URL("../../../assets/architecture.json", import.meta.url);
const GUIDANCE_REASON = "guidance on sequencing, topology, or release practice, so it informs and does not block";
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
  const document = JSON.parse(readFileSync(TEMPLATE, "utf8"));
  const rules = startingRules(start);
  const withRules = Object.keys(rules).length > 0 ? { rules } : {};
  return { ...document, adapter, record: recordMode, ...withRules };
}

async function excludeLocally(root, directory) {
  const out = await git(root, ["rev-parse", "--show-toplevel", "--git-path", "info/exclude"]);
  const [top, excludePath] = out.trim().split("\n");
  const exclude = resolve(root, excludePath);
  const entry = `/${relative(top, directory).split("\\").join("/")}/`;
  mkdirSync(dirname(exclude), { recursive: true });
  appendFileSync(exclude, `${entry}\n`);
}

async function excludeOrExplain(root, directory) {
  try {
    await excludeLocally(root, directory);
  } catch {
    throw new ToolingError("--record-mode local needs a git repository. Run git init first or use committed.");
  }
}

export async function initModel({ root, directory, file, ...choices }) {
  if (existsSync(file)) {
    throw new ModelError(`${file} already exists. Edit it with arch model subcommands instead of running init again.`);
  }
  mkdirSync(directory, { recursive: true });
  if (choices.recordMode === "local") await excludeOrExplain(root, directory);
  writeDocument(file, initialDocument(choices));
}
