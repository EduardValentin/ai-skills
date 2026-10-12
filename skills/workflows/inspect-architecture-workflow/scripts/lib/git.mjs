import { execFile } from "node:child_process";
import { promisify } from "node:util";

const run = promisify(execFile);

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
