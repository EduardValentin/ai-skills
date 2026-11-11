import { gitText } from "../graph/tree.mjs";

const COMMIT_HASH = /^[0-9a-f]{40}$/;

function lines(text) {
  return text.split("\n").filter(Boolean);
}

function parseChange(line) {
  const [code, ...paths] = line.split("\t");
  const status = code[0];
  if (status === "R" || status === "C") return { status, path: paths[1], oldPath: paths[0] };
  return { status, path: paths[0] };
}

export async function nameStatus(root, ref) {
  return lines(await gitText(root, ["diff", "--name-status", "-M", "--relative", ref])).map(parseChange);
}

export async function listUntracked(root) {
  return lines(await gitText(root, ["ls-files", "--others", "--exclude-standard"]));
}

export async function changedPaths(root, base) {
  const changes = await nameStatus(root, base);
  const listed = new Set(changes.map((change) => change.path));
  const untracked = (await listUntracked(root)).filter((path) => !listed.has(path));
  return [...changes, ...untracked.map((path) => ({ status: "A", path }))];
}

export async function logNames(root, selection) {
  const output = await gitText(root, ["log", "--name-only", "--format=%H", "--relative", ...selection]);
  const commits = [];
  for (const line of lines(output)) {
    if (COMMIT_HASH.test(line)) commits.push({ hash: line, files: [] });
    else commits.at(-1)?.files.push(line);
  }
  return commits;
}
