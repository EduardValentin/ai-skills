import { execFile } from "node:child_process";
import { mkdir, mkdtemp, readdir, rm, stat, symlink } from "node:fs/promises";
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

async function linkNodeModules(root, worktreeSubdir) {
  const found = [];
  await findNodeModules(root, "", 0, found);
  for (const rel of found) {
    const dest = path.join(worktreeSubdir, rel);
    await mkdir(path.dirname(dest), { recursive: true });
    try { await symlink(path.join(root, rel), dest, "dir"); }
    catch (error) { if (error.code !== "EEXIST") throw error; }
  }
}

async function showPrefix(root) {
  return (await git(root, ["rev-parse", "--show-prefix"])).trim();
}

async function linkAncestorNodeModules(root, prefix, worktreeTop) {
  const segments = prefix.split("/").filter(Boolean);
  for (let depth = 0; depth < segments.length; depth += 1) {
    const rel = segments.slice(0, depth).join("/");
    const source = path.join(path.resolve(root, ...segments.slice(depth).map(() => "..")), "node_modules");
    if (!(await isDirectory(source))) continue;
    const dest = path.join(worktreeTop, rel, "node_modules");
    await mkdir(path.dirname(dest), { recursive: true });
    try { await symlink(source, dest, "dir"); }
    catch (error) { if (error.code !== "EEXIST") throw error; }
  }
}

async function isDirectory(file) {
  try { return (await stat(file)).isDirectory(); }
  catch { return false; }
}

export async function withBaseWorktree(root, ref, fn) {
  const dir = await mkdtemp(path.join(os.tmpdir(), "arch-base-"));
  try {
    await git(root, ["worktree", "add", "--detach", dir, ref]);
    const prefix = await showPrefix(root);
    const subdir = path.join(dir, prefix);
    await linkNodeModules(root, subdir);
    await linkAncestorNodeModules(root, prefix, dir);
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
