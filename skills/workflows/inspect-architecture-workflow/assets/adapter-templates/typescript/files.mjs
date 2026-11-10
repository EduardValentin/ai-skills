import { access } from "node:fs/promises";
import path from "node:path";

export async function exists(file) {
  try {
    await access(file);
    return true;
  } catch {
    return false;
  }
}

export async function tsConfigFile(treeRoot, tsConfig) {
  const file = tsConfig ? path.join(treeRoot, tsConfig) : null;
  return file && (await exists(file)) ? file : null;
}
