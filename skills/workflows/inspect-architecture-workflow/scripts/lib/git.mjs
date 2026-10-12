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

export async function nameStatus(root, ref) {
  const stdout = await git(root, ["diff", "--name-status", "-M", ref]);
  return stdout.split("\n").filter(Boolean).map((line) => {
    const [code, ...paths] = line.split("\t");
    const status = code[0];
    if (status === "R") return { status, path: paths[1], oldPath: paths[0] };
    return { status, path: paths[0] };
  });
}

export async function logNames(root, ref) {
  const stdout = await git(root, ["log", "--name-only", "--format=%H", ref]);
  const commits = [];
  let current = null;
  for (const line of stdout.split("\n")) {
    if (line === "") continue;
    if (/^[0-9a-f]{40}$/.test(line)) { current = { hash: line, files: [] }; commits.push(current); }
    else if (current) current.files.push(line);
  }
  return commits;
}
