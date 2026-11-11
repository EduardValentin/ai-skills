import path from "node:path";
import { UsageError } from "../cli/errors.mjs";
import { cacheKey } from "../graph/cache.mjs";
import { isGitRepository, resolveCommit } from "../graph/tree.mjs";

export async function runRecord({ root, model, flags }) {
  const mode = flags.proposal ? "proposal" : flags.base ? "base" : "audit";
  return {
    mode,
    base: flags.base ? await resolveCommit(root, flags.base) : null,
    proposal: flags.proposal ? path.resolve(root, flags.proposal) : null,
    state: (await isGitRepository(root)) ? await cacheKey(root, model, null, flags) : null,
  };
}

function auditProblems(run) {
  if (run.mode === "audit") return [];
  return [
    `the check was made with a ${run.mode}, but an audit checks the whole codebase. ` +
      "Rerun arch check --json without --base or --proposal.",
  ];
}

function changeReviewProblems(run, current) {
  if (run.mode !== "base") return ["the check was not made with --base. Rerun arch check --base <ref> --json."];
  if (run.base === current.base) return [];
  return [
    `the check compared against ${run.base}, but --base is ${current.base}. Rerun arch check with the same --base.`,
  ];
}

function planReviewProblems(run, current) {
  if (run.mode !== "proposal") {
    return ["the check was not made with --proposal. Rerun arch check --proposal <file> --json."];
  }
  if (run.proposal === current.proposal) return [];
  return [
    `the check ran on proposal ${run.proposal}, but --proposal is ${current.proposal}. ` +
      "Rerun arch check with the same --proposal.",
  ];
}

const MODE_PROBLEMS = {
  audit: auditProblems,
  "change-review": changeReviewProblems,
  "plan-review": planReviewProblems,
};

export async function checkBinding({ check, flags, root, model }) {
  const refuse = (problems) => {
    throw new UsageError(
      `the check file does not match this run:\n${problems.map((problem) => `  ${problem}`).join("\n")}\n` +
        "Nothing was stored.",
    );
  };
  if (!check.run) refuse(["the check file has no run record. Recreate it with arch check --json."]);
  const current = await runRecord({ root, model, flags });
  const problems = MODE_PROBLEMS[flags.flow](check.run, current);
  if (problems.length === 0 && check.run.state !== null && check.run.state !== current.state) {
    problems.push("the check is stale: the working tree changed after it ran. Rerun arch check with the same flags.");
  }
  if (problems.length > 0) refuse(problems);
}
