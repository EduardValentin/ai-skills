import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { appendFileSync, existsSync, lstatSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import path from "node:path";
import { recordDir } from "../model/load.mjs";
import { GRAPH_VERSION } from "./build.mjs";
import { resolveCommit, gitText, isGitRepository } from "./tree.mjs";

const CACHE_DIRECTORY = ".architecture/graph";
const IGNORED_DIRECTORY = ".architecture/";
const CURRENT_PICTURE = "current.md";
const MAX_BUFFER = 256 * 1024 * 1024;
const RENAME_OR_COPY = /[RC]/;

function sha256(text) {
  return createHash("sha256").update(text).digest("hex");
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const members = Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`);
    return `{${members.join(",")}}`;
  }
  return JSON.stringify(value);
}

function statusEntries(output) {
  const fields = output.split("\0").filter(Boolean);
  const entries = [];
  for (let index = 0; index < fields.length; index += 1) {
    const code = fields[index].slice(0, 2);
    const entry = { code, path: fields[index].slice(3) };
    if (RENAME_OR_COPY.test(code)) {
      index += 1;
      entry.origin = fields[index];
    }
    entries.push(entry);
  }
  return entries;
}

function isOwnOutput(absolute, root, flags) {
  const cache = path.resolve(root, ".architecture");
  const picture = path.resolve(recordDir(root, flags), CURRENT_PICTURE);
  return absolute === picture || absolute === cache || absolute.startsWith(`${cache}${path.sep}`);
}

function isFile(top, file) {
  const absolute = path.join(top, file);
  return existsSync(absolute) && !lstatSync(absolute).isDirectory();
}

function contentHashes(top, paths) {
  const present = paths.filter((file) => isFile(top, file));
  if (present.length === 0) return [];
  const output = execFileSync("git", ["hash-object", "--stdin-paths"], {
    cwd: top,
    input: present.join("\n"),
    maxBuffer: MAX_BUFFER,
    encoding: "utf8",
  });
  return present.map((file, index) => `${file}\0${output.split("\n")[index]}`);
}

async function workingTreeState(root, flags) {
  const top = (await gitText(root, ["rev-parse", "--show-toplevel"])).trim();
  const head = (await gitText(root, ["rev-parse", "--verify", "HEAD"]).catch(() => "no-commit")).trim();
  const status = await gitText(top, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]);
  const entries = statusEntries(status).filter((entry) => !isOwnOutput(path.resolve(top, entry.path), root, flags));
  const changed = entries.map((entry) => entry.path).sort();
  const lines = entries.map((entry) => `${entry.code} ${entry.path}\0${entry.origin ?? ""}`).sort();
  return `${head}\n${sha256(lines.join("\n"))}\n${sha256(contentHashes(top, changed).join("\n"))}`;
}

export async function sourceState(root, ref, flags = {}) {
  if (ref) return `commit ${await resolveCommit(root, ref)}`;
  return `working-tree ${await workingTreeState(root, flags)}`;
}

function keyOf(model, state) {
  return sha256(stableJson({ model, adapter: model.adapter, graphVersion: GRAPH_VERSION, state }));
}

export async function cacheKey(root, model, ref, flags = {}) {
  return keyOf(model, await sourceState(root, ref, flags));
}

export function documentKey(model, document) {
  return keyOf(model, `document ${sha256(stableJson(document))}`);
}

function cacheFile(root, key) {
  return path.join(root, CACHE_DIRECTORY, `${key}.json`);
}

export function readCachedGraph(root, key) {
  try {
    const graph = JSON.parse(readFileSync(cacheFile(root, key), "utf8"));
    return graph.version === GRAPH_VERSION ? graph : null;
  } catch {
    return null;
  }
}

async function isIgnored(root) {
  try {
    await gitText(root, ["check-ignore", "-q", `${CACHE_DIRECTORY}/probe.json`]);
    return true;
  } catch {
    return false;
  }
}

async function ensureIgnored(root) {
  if (!(await isGitRepository(root)) || (await isIgnored(root))) return;
  const excludeFile = path.resolve(root, (await gitText(root, ["rev-parse", "--git-path", "info/exclude"])).trim());
  mkdirSync(path.dirname(excludeFile), { recursive: true });
  const current = existsSync(excludeFile) ? readFileSync(excludeFile, "utf8") : "";
  if (current.split("\n").includes(IGNORED_DIRECTORY)) return;
  const separator = current === "" || current.endsWith("\n") ? "" : "\n";
  appendFileSync(excludeFile, `${separator}${IGNORED_DIRECTORY}\n`);
}

export async function writeCachedGraph(root, key, graph) {
  await ensureIgnored(root);
  const file = cacheFile(root, key);
  mkdirSync(path.dirname(file), { recursive: true });
  const partial = `${file}.${process.pid}.tmp`;
  writeFileSync(partial, `${JSON.stringify(graph, null, 2)}\n`);
  renameSync(partial, file);
}
