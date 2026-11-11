import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import path from "node:path";
import { ToolingError } from "../cli/errors.mjs";
import { ensureIgnored } from "../graph/cache.mjs";
import { validateShape } from "../model/validate-shape.mjs";

const STORE_FILE = ".architecture/findings.json";
const STORE_VERSION = 1;

export function emptyStore() {
  return { version: STORE_VERSION, findings: [], lastRun: null };
}

const TEXT = { type: "string" };
const LIST = { type: "array" };
const STORE_SCHEMA = {
  type: "object",
  required: ["version", "findings", "lastRun"],
  properties: {
    version: { type: "integer", enum: [STORE_VERSION] },
    findings: {
      type: "array",
      items: {
        type: "object",
        required: [
          "target", "defect", "rules", "severity", "status", "origin", "provenance", "corrections", "evidence", "scope",
        ],
        properties: {
          target: TEXT, defect: TEXT, rules: LIST, severity: TEXT, status: TEXT, origin: TEXT, provenance: TEXT,
          corrections: LIST, evidence: LIST, scope: TEXT,
        },
      },
    },
    lastRun: {
      type: ["object", "null"],
      required: [
        "flow", "scope", "incomplete", "skipped", "notRun", "judgmentConditions", "upcoming", "questions",
        "findingKeys",
      ],
      properties: {
        flow: TEXT, scope: TEXT, incomplete: LIST, skipped: LIST, notRun: LIST, judgmentConditions: { type: "object" },
        upcoming: LIST, questions: LIST, findingKeys: LIST,
      },
    },
  },
};

function invalidStore(detail) {
  return new ToolingError(
    `${STORE_FILE} is not a valid findings store (${detail}). Delete ${STORE_FILE} and rerun the flow.`,
  );
}

export function readStore(root) {
  const file = path.join(root, STORE_FILE);
  if (!existsSync(file)) return emptyStore();
  let store;
  try {
    store = JSON.parse(readFileSync(file, "utf8"));
  } catch (error) {
    throw invalidStore(`not valid JSON: ${error.message}`);
  }
  const problems = validateShape(store, STORE_SCHEMA);
  if (problems.length > 0) throw invalidStore(problems.slice(0, 3).join("; "));
  return store;
}

export async function writeStore(root, store) {
  await ensureIgnored(root);
  const file = path.join(root, STORE_FILE);
  mkdirSync(path.dirname(file), { recursive: true });
  const partial = `${file}.${process.pid}.tmp`;
  writeFileSync(partial, `${JSON.stringify(store, null, 2)}\n`);
  renameSync(partial, file);
}

export function storeOf(findings, lastRun) {
  return { version: STORE_VERSION, findings, lastRun };
}
