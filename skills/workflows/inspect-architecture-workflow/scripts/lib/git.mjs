import { execFile } from "node:child_process";
import { mkdir, mkdtemp, readdir, readlink, rm, stat, symlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

const run = promisify(execFile);
const MAX_NODE_MODULES_DEPTH = 3;

export async function git(root, args) {
  const { stdout } = await run("git", args, { cwd: root, maxBuffer: 64 * 1024 * 1024 });
  return stdout;
}

export async function headCommit(root) {
  return (await git(root, ["rev-parse", "--short=8", "HEAD"])).trim();
}

export async function isClean(root) {
  try { return (await git(root, ["status", "--porcelain", "--", ".", ":!.architecture"])).trim() === ""; }
  catch { return false; }
}

export async function listTracked(root) {
  const stdout = await git(root, ["ls-files"]);
  return stdout.split("\n").filter(Boolean);
}

export async function listUntracked(root) {
  const stdout = await git(root, ["ls-files", "--others", "--exclude-standard"]);
  return stdout.split("\n").filter(Boolean);
}

export async function nameStatus(root, ref) {
  const stdout = await git(root, ["diff", "--name-status", "-M", "--relative", ref]);
  return stdout.split("\n").filter(Boolean).map((line) => {
    const [code, ...paths] = line.split("\t");
    const status = code[0];
    if (status === "R" || status === "C") return { status, path: paths[1], oldPath: paths[0] };
    return { status, path: paths[0] };
  });
}

export async function renames(root, ref) {
  const changes = await nameStatus(root, ref);
  return new Map(changes.filter((change) => change.status === "R").map((change) => [change.oldPath, change.path]));
}

async function findNodeModules(absDir, relDir, depth, results) {
  if (depth > MAX_NODE_MODULES_DEPTH) return;
  let entries;
  try { entries = await readdir(absDir, { withFileTypes: true }); }
  catch { return; }
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name === ".git") continue;
    const rel = path.join(relDir, entry.name);
    if (entry.name === "node_modules") { results.push(rel); continue; }
    await findNodeModules(path.join(absDir, entry.name), rel, depth + 1, results);
  }
}

async function linkEntry(sourceEntry, destEntry, top) {
  let target = sourceEntry;
  try {
    const link = await readlink(sourceEntry);
    const resolved = path.resolve(path.dirname(sourceEntry), link);
    target = !path.isAbsolute(link) && resolved.startsWith(`${top}${path.sep}`) ? link : resolved;
  } catch (error) {
    if (error.code !== "EINVAL") throw error;
  }
  try { await symlink(target, destEntry); }
  catch (error) { if (error.code !== "EEXIST") throw error; }
}

export async function mirrorNodeModules(source, dest, top) {
  await mkdir(dest, { recursive: true });
  for (const entry of await readdir(source, { withFileTypes: true })) {
    const sourceEntry = path.join(source, entry.name);
    const destEntry = path.join(dest, entry.name);
    if (entry.name.startsWith("@") && entry.isDirectory()) {
      await mkdir(destEntry, { recursive: true });
      for (const scoped of await readdir(sourceEntry)) await linkEntry(path.join(sourceEntry, scoped), path.join(destEntry, scoped), top);
      continue;
    }
    await linkEntry(sourceEntry, destEntry, top);
  }
}

async function showPrefix(root) {
  return (await git(root, ["rev-parse", "--show-prefix"])).trim();
}

async function isDirectory(file) {
  try { return (await stat(file)).isDirectory(); }
  catch { return false; }
}

async function linkAllNodeModules(root, prefix, worktreeTop) {
  const segments = prefix.split("/").filter(Boolean);
  const top = path.resolve(root, ...segments.map(() => ".."));
  const found = [];
  await findNodeModules(root, "", 0, found);
  for (const rel of found) await mirrorNodeModules(path.join(root, rel), path.join(worktreeTop, prefix, rel), top);
  for (let depth = 0; depth < segments.length; depth += 1) {
    const rel = segments.slice(0, depth).join("/");
    const source = path.join(top, rel, "node_modules");
    if (await isDirectory(source)) await mirrorNodeModules(source, path.join(worktreeTop, rel, "node_modules"), top);
  }
}

export async function withBaseWorktree(root, ref, fn) {
  const dir = await mkdtemp(path.join(os.tmpdir(), "arch-base-"));
  try {
    await git(root, ["worktree", "add", "--detach", dir, ref]);
    const prefix = await showPrefix(root);
    await linkAllNodeModules(root, prefix, dir);
    const subdir = path.join(dir, prefix);
    return await fn(subdir);
  } finally {
    try { await git(root, ["worktree", "remove", "--force", dir]); }
    catch { await rm(dir, { recursive: true, force: true }).catch(() => {}); }
    try { await git(root, ["worktree", "prune"]); } catch { /* best-effort cleanup, never masks the original error */ }
  }
}

export async function logNames(root, ref) {
  const stdout = await git(root, ["log", "--name-only", "--format=%H", "--relative", ref]);
  const commits = [];
  let current = null;
  for (const line of stdout.split("\n")) {
    if (line === "") continue;
    if (/^[0-9a-f]{40}$/.test(line)) { current = { hash: line, files: [] }; commits.push(current); }
    else if (current) current.files.push(line);
  }
  return commits;
}
