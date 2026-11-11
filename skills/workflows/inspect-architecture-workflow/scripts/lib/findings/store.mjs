import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import path from "node:path";
import { ToolingError } from "../cli/errors.mjs";
import { ensureIgnored } from "../graph/cache.mjs";

const STORE_FILE = ".architecture/findings.json";
const STORE_VERSION = 1;

export function emptyStore() {
  return { version: STORE_VERSION, findings: [], lastRun: null };
}

export function readStore(root) {
  const file = path.join(root, STORE_FILE);
  if (!existsSync(file)) return emptyStore();
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch (error) {
    throw new ToolingError(
      `${STORE_FILE} is not valid JSON: ${error.message}. Delete it and run arch findings add again.`,
    );
  }
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
