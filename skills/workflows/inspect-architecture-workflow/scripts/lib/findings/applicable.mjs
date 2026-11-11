import { readFileSync } from "node:fs";
import { UsageError } from "../cli/errors.mjs";

const MODE_OF_FLOW = { audit: "all", "change-review": "base", "plan-review": "proposal" };
const APPLICABLE_COMMAND = "arch applicable <the same scope flags> --out .architecture/work/applicable.json";

function readJson(file) {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch (error) {
    throw new UsageError(
      `applicable file ${file} cannot be read as JSON: ${error.message}. Create it with ${APPLICABLE_COMMAND}.`,
    );
  }
}

function isCount(value) {
  return Number.isInteger(value) && value >= 0;
}

export function readApplicable(file, flow) {
  const output = readJson(file);
  if (output.model !== true || !isCount(output.inScope) || !Array.isArray(output.units)) {
    throw new UsageError(
      `applicable file ${file} is not arch applicable output. Create it with ${APPLICABLE_COMMAND}.`,
    );
  }
  const mode = MODE_OF_FLOW[flow];
  if (output.mode !== mode) {
    throw new UsageError(
      `applicable file ${file} was made with --${output.mode}, but ${flow} needs --${mode}. ` +
        `Create it with ${APPLICABLE_COMMAND}.`,
    );
  }
  return output;
}

export function judgmentConditions(applicable, judgedFiles = []) {
  if (!applicable) return null;
  return { inScope: applicable.inScope, reviewed: judgedFiles.length > 0 ? applicable.inScope : 0 };
}

export const REVIEW_NOT_DONE = "judgment-review";

export function reviewNotDone(applicable, judgedFiles = []) {
  if (!applicable || applicable.inScope === 0 || judgedFiles.length > 0) return [];
  return [{
    check: REVIEW_NOT_DONE,
    rules: [],
    target: `${applicable.inScope} judgment conditions in scope`,
    reason:
      "no judged file was passed, so no reviewer judged them. Dispatch architecture-reviewer with the conditions " +
      "arch applicable lists, then run arch findings add again with --judged.",
  }];
}
