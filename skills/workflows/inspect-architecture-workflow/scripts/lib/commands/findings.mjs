import { readFileSync } from "node:fs";
import { ModelError, UsageError } from "../cli/errors.mjs";
import { parseArgs } from "../cli/flags.mjs";
import { proposalComparison } from "../checks/proposal.mjs";
import { touchedScope } from "../checks/scope.mjs";
import { loadGraph } from "../graph/load.mjs";
import { NO_MODEL_LINE, loadModel } from "../model/load.mjs";
import { componentCommitCounts } from "../queries/history.mjs";
import { checkBinding } from "../findings/binding.mjs";
import { requireWorkPlacement } from "../findings/placement.mjs";
import { judgedFindings, judgedQuestions, readJudged } from "../findings/intake.mjs";
import { checkFinding, mergeFindings, replaceStored, scopeTag } from "../findings/merge.mjs";
import { contractData, noModelData, rankData, renderContract, renderRank } from "../findings/render.mjs";
import { readStore, storeOf, writeStore } from "../findings/store.mjs";
import { withEnforcement } from "../findings/verdict.mjs";

const FLOWS = ["audit", "change-review", "plan-review"];
const SUBCOMMANDS = ["add", "list"];
export const ADD_SPEC = {
  flags: {
    flow: "value", check: "value", judged: "list", base: "git-ref", plan: "value", proposal: "value",
    upcoming: "list",
  },
  positional: { min: 0, max: 0 },
};
export const LIST_SPEC = { flags: { rank: "boolean" }, positional: { min: 0, max: 0 } };

function requireFlag(flags, name, reason) {
  if (flags[name]) return;
  throw new UsageError(`--${name} is required ${reason}. Pass --${name} <value>.`);
}

function checkAddFlags(flags, root) {
  requireFlag(flags, "flow", "to say which review this is");
  if (!FLOWS.includes(flags.flow)) {
    throw new UsageError(`--flow ${flags.flow} is not a flow. Use one of: ${FLOWS.join(", ")}.`);
  }
  requireFlag(flags, "check", "to name the arch check --json output");
  if (flags.flow === "change-review") requireFlag(flags, "base", "in change-review, the ref the diff is against");
  if (flags.flow === "plan-review") {
    requireFlag(flags, "plan", "in plan-review, the plan file that was reviewed");
    requireFlag(flags, "proposal", "in plan-review, the proposal file the check ran on");
  }
  for (const name of ["check", "proposal"]) if (flags[name]) requireWorkPlacement(root, flags[name], name);
  for (const file of flags.judged ?? []) requireWorkPlacement(root, file, "judged");
}

const CHECK_COMMAND = "arch check <the same scope flags> --out .architecture/work/check.json";

function readCheckOutput(file) {
  let output;
  try {
    output = JSON.parse(readFileSync(file, "utf8"));
  } catch (error) {
    throw new UsageError(
      `check file ${file} cannot be read as JSON: ${error.message}. Create it with ${CHECK_COMMAND}.`,
    );
  }
  if (output.model === false) return output;
  const lists = ["rows", "incomplete", "notRun", "skipped"];
  if (output.model !== true || lists.some((name) => !Array.isArray(output[name]))) {
    throw new UsageError(`check file ${file} is not arch check --json output. Create it with ${CHECK_COMMAND}.`);
  }
  return output;
}

async function reviewSubject({ root, model, flags }) {
  if (flags.flow === "plan-review") {
    const { graph, touched } = await proposalComparison({ root, model, file: flags.proposal });
    return { graph, scope: touched, scopeLabel: flags.plan };
  }
  const graph = await loadGraph(root, model, { flags });
  if (flags.flow === "audit") return { graph, scope: null, scopeLabel: "all components" };
  return { graph, scope: await touchedScope(root, graph, flags.base), scopeLabel: `changes since ${flags.base}` };
}

function confirmedUpcoming(model, flags) {
  return [...new Set([...model.upcoming, ...(flags.upcoming ?? [])])];
}

function lastRunOf({ flags, subject, check, model, judged, findings, upcoming, tag, dropped }) {
  return {
    flow: flags.flow,
    scope: subject.scopeLabel,
    base: flags.base ?? null,
    plan: flags.plan ?? null,
    incomplete: withEnforcement(model, check.incomplete),
    skipped: check.skipped,
    notRun: check.notRun,
    upcoming,
    questions: judged.questions ?? [],
    covered: check.covered ?? 0,
    dropped,
    findingKeys: findings.map((finding) => [finding.target, finding.defect, tag]),
  };
}

function print(data, flags) {
  console.log(flags.json ? JSON.stringify(data, null, 2) : renderContract(data));
}

async function add(args, { root }) {
  const { flags } = parseArgs(ADD_SPEC, args);
  checkAddFlags(flags, root);
  const check = readCheckOutput(flags.check);
  if (check.model === false) {
    print(noModelData(flags.flow), flags);
    return 0;
  }
  const model = loadModel(root, flags);
  if (!model) {
    throw new ModelError(`${flags.check} was made with a model, but none is found now. Run from the same project.`);
  }
  await checkBinding({ check, flags, root, model });
  const subject = await reviewSubject({ root, model, flags });
  const upcoming = confirmedUpcoming(model, flags);
  const documents = readJudged(flags.judged ?? []);
  const { findings: fromJudgment, dropped } = judgedFindings({
    documents, ...flags, root, model, graph: subject.graph, scope: subject.scope, upcoming,
  });
  const judged = { questions: judgedQuestions(documents) };
  const merged = mergeFindings([...check.rows.map((row) => checkFinding(row, subject.graph)), ...fromJudgment]);
  const tag = scopeTag(flags.flow, flags.plan);
  const stored = replaceStored({
    stored: readStore(root).findings,
    incoming: merged,
    flow: flags.flow,
    tag,
    scope: subject.scope,
  });
  const run = { flags, subject, check, model, judged, findings: merged, upcoming, tag, dropped };
  const store = storeOf(stored, lastRunOf(run));
  await writeStore(root, store);
  print(contractData(store), flags);
  return 0;
}

async function ranking(root, store, flags) {
  if (store.lastRun.flow !== "audit") {
    throw new UsageError("--rank applies to an audit. Run arch findings add --flow audit first.");
  }
  const model = loadModel(root, flags);
  if (!model) throw new UsageError("--rank needs the architecture model. Run arch model init, then rank again.");
  const commits = await componentCommitCounts({ model, root });
  return rankData({ findings: contractData(store).findings, commits, window: model.thresholds.historyWindow });
}

async function list(args, { root }) {
  const { flags } = parseArgs(LIST_SPEC, args);
  const store = readStore(root);
  if (!store.lastRun) {
    if (!loadModel(root, flags)) {
      console.log(NO_MODEL_LINE);
      return 0;
    }
    throw new UsageError("no findings are stored. Run arch findings add after a review, then list them.");
  }
  const data = contractData(store);
  const rank = flags.rank ? await ranking(root, store, flags) : null;
  if (flags.json) console.log(JSON.stringify({ ...data, ...(rank && { ranking: rank }) }, null, 2));
  else console.log([renderContract(data), ...(rank ? [renderRank(rank)] : [])].join("\n\n"));
  return 0;
}

export async function run(args, context) {
  const [name, ...rest] = args;
  if (!SUBCOMMANDS.includes(name)) {
    throw new UsageError(`findings needs a subcommand: ${SUBCOMMANDS.join(" or ")}. Run arch findings add or list.`);
  }
  return name === "add" ? add(rest, context) : list(rest, context);
}
