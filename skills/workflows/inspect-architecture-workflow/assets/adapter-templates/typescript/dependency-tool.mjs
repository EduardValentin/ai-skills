import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { exists, tsConfigFile } from "./files.mjs";

const NODE_MODULES_PATH = /(^|\/)node_modules\//;
const OUTSIDE_ROOT = /^(\.\.\/)+/;

function lastLines(text, count) {
  return text.trimEnd().split("\n").slice(-count).join("\n");
}

function packageName(specifier) {
  const parts = specifier.split("/");
  return specifier.startsWith("@") ? parts.slice(0, 2).join("/") : parts[0];
}

function isExternalEntry(entry) {
  const types = entry.dependencyTypes ?? [];
  const entryPath = entry.resolved ?? entry.source ?? "";
  return Boolean(entry.coreModule)
    || types.some((type) => type === "core" || type.startsWith("npm"))
    || NODE_MODULES_PATH.test(entryPath);
}

function outsideRootName(entryPath) {
  const match = OUTSIDE_ROOT.exec(entryPath);
  return match ? entryPath.slice(match[0].length).split("/")[0] : null;
}

function externalTag(types, name, frameworks) {
  if (types.includes("core")) return "runtime";
  return frameworks.includes(name) ? "framework" : "vendor";
}

function importKind(dependency) {
  if ((dependency.dependencyTypes ?? []).includes("type-only")) return "type-import";
  return dependency.dynamic ? "dynamic" : "import";
}

function internalModules(cruise, warnings) {
  const modules = new Set();
  for (const entry of cruise.modules) {
    if (entry.couldNotResolve || isExternalEntry(entry)) continue;
    if (outsideRootName(entry.source) !== null) {
      warnings.add(`module outside the root: ${entry.source}`);
      continue;
    }
    modules.add(entry.source);
  }
  return modules;
}

export function normalizeCruise(cruise, frameworks = []) {
  const warnings = new Set();
  const modules = internalModules(cruise, warnings);
  const edges = [];
  for (const entry of cruise.modules) {
    if (!modules.has(entry.source)) continue;
    for (const dependency of entry.dependencies ?? []) {
      const types = dependency.dependencyTypes ?? [];
      if (dependency.couldNotResolve) {
        warnings.add(`unresolved import ${dependency.module} in ${entry.source}`);
        continue;
      }
      if (isExternalEntry(dependency)) {
        const name = packageName(dependency.module);
        edges.push({ from: entry.source, external: { name, tag: externalTag(types, name, frameworks) } });
        continue;
      }
      const outsideName = outsideRootName(dependency.resolved ?? "");
      if (outsideName !== null) {
        warnings.add(`module outside the root: ${dependency.resolved}`);
        edges.push({ from: entry.source, external: { name: outsideName, tag: "vendor" } });
        continue;
      }
      edges.push({ from: entry.source, to: dependency.resolved, kind: importKind(dependency) });
      modules.add(dependency.resolved);
    }
  }
  return { modules, edges, warnings: [...warnings] };
}

async function readPackageJson(file) {
  try {
    return JSON.parse(await readFile(file, "utf8"));
  } catch {
    return null;
  }
}

async function findDependencyCruiserPackage(startDir) {
  let dir = startDir;
  while (true) {
    const pkg = await readPackageJson(path.join(dir, "package.json"));
    if (pkg?.name === "dependency-cruiser") return { dir, pkg };
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

export async function locateCruiserBin(sourceRoot) {
  const binShim = path.join(sourceRoot, "node_modules", ".bin", "depcruise");
  if (await exists(binShim)) return binShim;
  let mainEntry = null;
  try {
    mainEntry = createRequire(path.join(sourceRoot, "package.json")).resolve("dependency-cruiser");
  } catch {
    mainEntry = null;
  }
  if (mainEntry) {
    const found = await findDependencyCruiserPackage(path.dirname(mainEntry));
    const bin = found?.pkg.bin?.["dependency-cruise"] ?? found?.pkg.bin?.depcruise;
    if (found && bin) return path.join(found.dir, bin);
  }
  throw new Error(`dependency-cruiser is not installed in ${sourceRoot}; the TypeScript adapter needs it`);
}

export async function cruiseArguments(treeRoot, { roots, tsConfig, dependencyCruiserConfig }) {
  const tsConfigPath = await tsConfigFile(treeRoot, tsConfig);
  const tsArguments = tsConfigPath ? ["--ts-config", tsConfigPath] : [];
  return ["--output-type", "json", "--config", dependencyCruiserConfig, ...tsArguments, ...roots];
}

function collectOutput(command, args, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", () => resolve({ stdout, stderr }));
  });
}

export async function runCruise(sourceRoot, treeRoot, tooling) {
  const bin = await locateCruiserBin(sourceRoot);
  const cruiseArgs = await cruiseArguments(treeRoot, tooling);
  const isBinShim = path.basename(path.dirname(bin)) === ".bin";
  const { stdout, stderr } = await collectOutput(
    isBinShim ? bin : process.execPath,
    isBinShim ? cruiseArgs : [bin, ...cruiseArgs],
    treeRoot,
  );
  try {
    return JSON.parse(stdout);
  } catch {
    throw new Error(`dependency-cruiser produced no JSON. Last lines of its error output:\n${lastLines(stderr, 8)}`);
  }
}
