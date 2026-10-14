import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseFlags } from "../args.mjs";
import { git } from "../git.mjs";
import { GRAPH_DIR, resolveWorkingTreeKey } from "../graph.mjs";
import { loadModel } from "../model.mjs";
import {
  LEDGER_PATH, MODES, accept, addRun, buildMap, contractLines, lastRun, parseLedger, parseRows, refreshRunLog, renderRunLogRow, templateText, writeLedger,
} from "../ledger.mjs";

const USAGE = "usage: arch ledger <add-run|accept|map>";
const SUB_USAGE = {
  "add-run": "usage: arch ledger add-run --mode <audit|change-review|plan-review> --scope <text> --rows <file> [--base <ref>] [--plan <path>] [--skipped W1,W6] [--evaluated <file>] [--removed <file>]; --base is required in change-review, --plan in plan-review",
  accept: "usage: arch ledger accept <F-id> --one-off|--standing --by <who> --reason <text>",
  map: 'usage: arch ledger map [--agents "<n> mapping, <n> fact, <n> evaluation"]',
};
const AGENTS_PLACEHOLDER = "<n> dispatched (<n> mapping, <n> fact, <n> evaluation)";

async function loadLedger(root) {
  try { return parseLedger(await readFile(path.join(root, LEDGER_PATH), "utf8")); }
  catch (error) {
    if (error.code !== "ENOENT") throw error;
    return parseLedger(templateText());
  }
}

async function saveLedger(root, ledger) {
  const file = path.join(root, LEDGER_PATH);
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, writeLedger(ledger));
}

async function listFile(root, file) {
  if (typeof file !== "string") return [];
  const text = await readFile(path.resolve(root, file), "utf8");
  return text.split("\n").map((line) => line.trim()).filter((line) => line && !line.startsWith("#"));
}

const KEY_FLAG = { audit: null, "change-review": "base", "plan-review": "plan" };

async function runKey(root, mode, flags) {
  if (mode === "change-review") return (await git(root, ["rev-parse", "--short=8", flags.base])).trim();
  if (mode === "plan-review") return path.relative(root, path.resolve(root, flags.plan)).split(path.sep).join("/");
  return "audit";
}

async function addRunCommand(root, flags) {
  const keyFlag = KEY_FLAG[flags.mode];
  const valid = MODES.includes(flags.mode) && typeof flags.scope === "string" && typeof flags.rows === "string"
    && (keyFlag === null || typeof flags[keyFlag] === "string");
  if (!valid) { console.error(SUB_USAGE["add-run"]); return 1; }
  const ledger = addRun(await loadLedger(root), {
    mode: flags.mode,
    scope: flags.scope,
    key: await runKey(root, flags.mode, flags),
    commit: await resolveWorkingTreeKey(root),
    rows: parseRows(await readFile(path.resolve(root, flags.rows), "utf8")),
    skippedWorkflows: typeof flags.skipped === "string" ? flags.skipped.split(",").map((w) => w.trim()).filter(Boolean) : [],
    evaluatedTargets: await listFile(root, flags.evaluated),
    removedTargets: await listFile(root, flags.removed),
  });
  await saveLedger(root, ledger);
  console.log(renderRunLogRow(lastRun(ledger)));
  return 0;
}

async function componentsByPath(root) {
  try {
    const key = await resolveWorkingTreeKey(root);
    const graph = JSON.parse(await readFile(path.join(root, GRAPH_DIR, `${key}.json`), "utf8"));
    return new Map(graph.units.map((unit) => [unit.path, unit.component]));
  } catch {
    return null;
  }
}

async function cohesionGroups(root) {
  try { return (await loadModel(root)).boundaries?.groups ?? []; }
  catch { return []; }
}

async function acceptCommand(root, positional, flags) {
  const kind = flags["one-off"] === true ? "one-off" : flags.standing === true ? "standing" : null;
  const valid = positional.length === 1 && kind && typeof flags.by === "string" && typeof flags.reason === "string" && !(flags["one-off"] && flags.standing);
  if (!valid) { console.error(SUB_USAGE.accept); return 1; }
  const { ledger, suggestion } = accept(await loadLedger(root), positional[0], {
    kind, by: flags.by, reason: flags.reason,
    componentOf: kind === "standing" ? await componentsByPath(root) : null,
    groups: kind === "standing" ? await cohesionGroups(root) : [],
  });
  await saveLedger(root, ledger);
  console.log(`${positional[0]} ACCEPTED (${kind})`);
  if (suggestion) console.log(suggestion);
  return 0;
}

function agentsLine(flag) {
  if (typeof flag !== "string") return AGENTS_PLACEHOLDER;
  const total = (flag.match(/\d+/g) ?? []).reduce((sum, n) => sum + Number(n), 0);
  return `${total} dispatched (${flag})`;
}

async function mapCommand(root, flags) {
  if (flags.agents === true) { console.error(SUB_USAGE.map); return 1; }
  let ledger = buildMap(await loadLedger(root));
  const run = lastRun(ledger);
  if (!run) { console.error("the ledger has no run; run arch ledger add-run first"); return 1; }
  ledger = refreshRunLog(ledger, run.run);
  await saveLedger(root, ledger);
  console.log(contractLines(ledger, run.run, agentsLine(flags.agents)).join("\n"));
  return 0;
}

export async function run(args, ctx) {
  const [sub, ...rest] = args;
  const { positional, flags } = parseFlags(rest);
  if (sub === "add-run") return addRunCommand(ctx.root, flags);
  if (sub === "accept") return acceptCommand(ctx.root, positional, flags);
  if (sub === "map") return mapCommand(ctx.root, flags);
  console.error(USAGE);
  return 1;
}
