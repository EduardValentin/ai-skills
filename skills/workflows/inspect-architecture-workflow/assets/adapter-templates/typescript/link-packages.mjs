import { lstat, mkdir, readdir, realpath, symlink, unlink } from "node:fs/promises";
import path from "node:path";

const MAX_NODE_MODULES_DEPTH = 3;

async function findNodeModules(absoluteDir, relativeDir, depth, found) {
  if (depth > MAX_NODE_MODULES_DEPTH) return;
  let entries;
  try {
    entries = await readdir(absoluteDir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name === ".git") continue;
    const relative = path.join(relativeDir, entry.name);
    if (entry.name === "node_modules") found.push(relative);
    else await findNodeModules(path.join(absoluteDir, entry.name), relative, depth + 1, found);
  }
}

async function isMissing(file) {
  try {
    await lstat(file);
    return false;
  } catch {
    return true;
  }
}

async function realpathOrNull(dir) {
  try {
    return await realpath(dir);
  } catch {
    return null;
  }
}

export async function linkSourceModules(sourceRoot, treeRoot) {
  const realSource = await realpathOrNull(sourceRoot);
  if (realSource === null || realSource === (await realpathOrNull(treeRoot))) return [];
  const relatives = [];
  await findNodeModules(sourceRoot, "", 0, relatives);
  const links = [];
  for (const relative of relatives) {
    const link = path.join(treeRoot, relative);
    if (!(await isMissing(link))) continue;
    await mkdir(path.dirname(link), { recursive: true });
    await symlink(path.join(sourceRoot, relative), link);
    links.push(link);
  }
  return links;
}

export async function removeLinks(links) {
  for (const link of links) {
    try {
      await unlink(link);
    } catch {
      // already gone; removal must not mask the run's own error
    }
  }
}
