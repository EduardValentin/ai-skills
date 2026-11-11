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
  if (output.model !== true || !isCount(output.inScope) || !isCount(output.notReviewed)) {
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
  const notReviewed = judgedFiles.length > 0 ? applicable.notReviewed : applicable.inScope;
  return { inScope: applicable.inScope, notReviewed };
}
