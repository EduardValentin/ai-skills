import path from "node:path";
import { UsageError } from "../cli/errors.mjs";
import { cacheKey } from "../graph/cache.mjs";
import { isGitRepository, resolveCommit } from "../graph/tree.mjs";

function modeOf(flags) {
  if (flags.proposal) return "proposal";
  if (flags.base) return "base";
  if (flags.files) return "files";
  return "audit";
}

export async function runRecord({ root, model, flags }) {
  return {
    mode: modeOf(flags),
    base: flags.base ? await resolveCommit(root, flags.base) : null,
    proposal: flags.proposal ? path.resolve(root, flags.proposal) : null,
    state: (await isGitRepository(root)) ? await cacheKey(root, model, null, flags) : null,
  };
}

const RERUN = {
  check: {
    audit: "Rerun arch check --json without --base or --proposal.",
    base: "Rerun arch check --base <ref> --json.",
    sameBase: "Rerun arch check with the same --base.",
    proposal: "Rerun arch check --proposal <file> --json.",
    sameProposal: "Rerun arch check with the same --proposal.",
    stale: "Rerun arch check with the same flags.",
    missing: "Recreate it with arch check --json.",
  },
  applicable: {
    audit: "Rerun arch applicable --all --out .architecture/work/applicable.json.",
    base: "Rerun arch applicable --base <ref> --out .architecture/work/applicable.json.",
    sameBase: "Rerun arch applicable with the same --base.",
    proposal: "Rerun arch applicable --proposal <file> --out .architecture/work/applicable.json.",
    sameProposal: "Rerun arch applicable with the same --proposal.",
    stale: "Rerun arch applicable with the same flags.",
    missing: "Recreate it with arch applicable <the same scope flags> --out .architecture/work/applicable.json.",
  },
};

function auditProblems(kind, run) {
  if (run.mode === "audit") return [];
  return [`the ${kind} was made with --${run.mode}, but an audit checks the whole codebase. ${RERUN[kind].audit}`];
}

function changeReviewProblems(kind, run, current) {
  if (run.mode !== "base") return [`the ${kind} was not made with --base. ${RERUN[kind].base}`];
  if (run.base === current.base) return [];
  return [`the ${kind} compared against ${run.base}, but --base is ${current.base}. ${RERUN[kind].sameBase}`];
}

function planReviewProblems(kind, run, current) {
  if (run.mode !== "proposal") return [`the ${kind} was not made with --proposal. ${RERUN[kind].proposal}`];
  if (run.proposal === current.proposal) return [];
  return [
    `the ${kind} ran on proposal ${run.proposal}, but --proposal is ${current.proposal}. ` +
      RERUN[kind].sameProposal,
  ];
}

const MODE_PROBLEMS = {
  audit: auditProblems,
  "change-review": changeReviewProblems,
  "plan-review": planReviewProblems,
};

function refuse(kind, problems) {
  throw new UsageError(
    `the ${kind} file does not match this run:\n${problems.map((problem) => `  ${problem}`).join("\n")}\n` +
      "Nothing was stored.",
  );
}

export async function requireBinding({ output, kind, flags, root, model }) {
  if (!output.run) refuse(kind, [`the ${kind} file has no run record. ${RERUN[kind].missing}`]);
  const current = await runRecord({ root, model, flags });
  const problems = MODE_PROBLEMS[flags.flow](kind, output.run, current);
  if (problems.length === 0 && output.run.state !== null && output.run.state !== current.state) {
    problems.push(`the ${kind} is stale: the working tree changed after it ran. ${RERUN[kind].stale}`);
  }
  if (problems.length > 0) refuse(kind, problems);
}
