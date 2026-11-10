import { execFile } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { ToolingError } from "../cli/errors.mjs";

const run = promisify(execFile);
const MAX_BUFFER = 256 * 1024 * 1024;

export async function gitText(root, args) {
  const { stdout } = await run("git", args, { cwd: root, maxBuffer: MAX_BUFFER });
  return stdout;
}

export async function isGitRepository(root) {
  try {
    await gitText(root, ["rev-parse", "--git-dir"]);
    return true;
  } catch {
    return false;
  }
}

export async function resolveCommit(root, ref) {
  try {
    return (await gitText(root, ["rev-parse", "--verify", `${ref}^{commit}`])).trim();
  } catch {
    throw new ToolingError(
      `"${ref}" is not a commit in this repository. Pass a branch, tag, or commit that git can resolve.`,
    );
  }
}

async function removeTree(root, directory) {
  try {
    await gitText(root, ["worktree", "remove", "--force", directory]);
  } catch {
    await rm(directory, { recursive: true, force: true });
  }
  await gitText(root, ["worktree", "prune"]).catch(() => {});
}

export async function withTree(root, ref, work) {
  const commit = await resolveCommit(root, ref);
  const directory = await mkdtemp(path.join(os.tmpdir(), "arch-tree-"));
  try {
    await gitText(root, ["worktree", "add", "--detach", directory, commit]);
    const prefix = (await gitText(root, ["rev-parse", "--show-prefix"])).trim();
    return await work(path.join(directory, prefix));
  } finally {
    await removeTree(root, directory);
  }
}
