import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { UsageError } from "../cli/errors.mjs";
import { ensureIgnored } from "../graph/cache.mjs";

export const WORK_DIRECTORY = ".architecture/work";
const IGNORED_ROOT = ".architecture";

export function requireWorkPlacement(root, file, flagName) {
  const relative = path.relative(root, path.resolve(root, file));
  const outside = relative.startsWith("..") || path.isAbsolute(relative);
  if (outside) return;
  const [first] = relative.split(path.sep);
  if (first === IGNORED_ROOT) return;
  throw new UsageError(
    `--${flagName} ${file} is inside the project but not under ${IGNORED_ROOT}/. ` +
      "Files elsewhere in the project change the reviewed state and make the check look stale. " +
      `Put it under ${WORK_DIRECTORY}/, for example ${WORK_DIRECTORY}/${path.basename(file)}.`,
  );
}

export async function writeWorkFile(root, file, text) {
  await ensureIgnored(root);
  const absolute = path.resolve(root, file);
  mkdirSync(path.dirname(absolute), { recursive: true });
  writeFileSync(absolute, text);
}
