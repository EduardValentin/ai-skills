import { spawn } from "node:child_process";
import { access, readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const DEFAULT_CONFIG = path.join(path.dirname(fileURLToPath(import.meta.url)), "default-cruise-config.cjs");
const CONFIG_CANDIDATES = [".dependency-cruiser.cjs", ".dependency-cruiser.js", ".dependency-cruiser.json"];

async function exists(file) { try { await access(file); return true; } catch { return false; } }

export function packageName(specifier) {
  const parts = specifier.split("/");
  return specifier.startsWith("@") ? parts.slice(0, 2).join("/") : parts[0];
}

const NODE_MODULES_PATH = /(^|\/)node_modules\//;
const OUTSIDE_ROOT = /^(\.\.\/)+/;

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

export function normalizeCruise(cruise, frameworks = []) {
  const modules = new Set();
  const edges = [];
  const warnings = new Set();
  const warnOutside = (entryPath) => warnings.add(`module outside the root: ${entryPath}`);
  for (const m of cruise.modules) {
    if (m.couldNotResolve || isExternalEntry(m)) continue;
    if (outsideRootName(m.source) !== null) { warnOutside(m.source); continue; }
    modules.add(m.source);
  }
  for (const m of cruise.modules) {
    if (!modules.has(m.source)) continue;
    for (const d of m.dependencies ?? []) {
      const types = d.dependencyTypes ?? [];
      if (d.couldNotResolve) { warnings.add(`unresolved import ${d.module} in ${m.source}`); continue; }
      const outsideName = outsideRootName(d.resolved ?? "");
      if (outsideName !== null) {
        warnOutside(d.resolved);
        edges.push({ from: m.source, external: { name: outsideName, tag: "vendor" } });
        continue;
      }
      if (isExternalEntry(d)) {
        const name = packageName(d.module);
        const tag = types.includes("core") ? "runtime" : frameworks.includes(name) ? "framework" : "vendor";
        edges.push({ from: m.source, external: { name, tag } });
        continue;
      }
      const kind = types.includes("type-only") ? "type-import" : d.dynamic ? "dynamic" : "import";
      edges.push({ from: m.source, to: d.resolved, kind });
      modules.add(d.resolved);
    }
  }
  return { modules, edges, warnings: [...warnings] };
}

function loadTypescript(root) {
  const require = createRequire(path.join(root, "package.json"));
  try { return require("typescript"); }
  catch { throw new Error(`typescript is not installed in ${root}; the TypeScript adapter needs it`); }
}

export function scanExports(ts, filePath, text) {
  const source = ts.createSourceFile(filePath, text, ts.ScriptTarget.Latest, true);
  const exports = { abstract: 0, concrete: 0 };
  const implemented = [];
  const hasModifier = (node, kind) => (ts.canHaveModifiers(node) ? ts.getModifiers(node) ?? [] : []).some((mod) => mod.kind === kind);
  for (const statement of source.statements) {
    if (ts.isExportDeclaration(statement)) {
      const named = statement.exportClause && ts.isNamedExports(statement.exportClause) ? statement.exportClause.elements.length : 1;
      exports.concrete += named;
      continue;
    }
    if (ts.isExportAssignment(statement)) { exports.concrete += 1; continue; }
    if (ts.isClassDeclaration(statement)) {
      for (const clause of statement.heritageClauses ?? []) {
        if (ts.SyntaxKind.ImplementsKeyword === clause.token) for (const type of clause.types) implemented.push(type.expression.getText(source));
      }
    }
    if (!hasModifier(statement, ts.SyntaxKind.ExportKeyword)) continue;
    const abstract = ts.isInterfaceDeclaration(statement) || ts.isTypeAliasDeclaration(statement)
      || (ts.isClassDeclaration(statement) && hasModifier(statement, ts.SyntaxKind.AbstractKeyword));
    if (abstract) exports.abstract += 1;
    else if (ts.isVariableStatement(statement)) exports.concrete += statement.declarationList.declarations.length;
    else exports.concrete += 1;
  }
  return { exports, implements: implemented };
}

async function resolveConfig(root, tooling) {
  if (tooling.dependencyCruiserConfig && (await exists(path.join(root, tooling.dependencyCruiserConfig)))) return path.join(root, tooling.dependencyCruiserConfig);
  for (const candidate of CONFIG_CANDIDATES) if (await exists(path.join(root, candidate))) return path.join(root, candidate);
  return DEFAULT_CONFIG;
}

async function readPackageJson(file) {
  try { return JSON.parse(await readFile(file, "utf8")); }
  catch { return null; }
}

async function findDependencyCruiserPackage(startDir) {
  let dir = startDir;
  while (true) {
    const candidate = path.join(dir, "package.json");
    const pkg = await readPackageJson(candidate);
    if (pkg?.name === "dependency-cruiser") return { dir, pkg };
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

export async function locateCruiserBin(root) {
  const binShim = path.join(root, "node_modules", ".bin", "depcruise");
  if (await exists(binShim)) return binShim;
  let mainEntry = null;
  try { mainEntry = createRequire(path.join(root, "package.json")).resolve("dependency-cruiser"); }
  catch { mainEntry = null; }
  if (mainEntry) {
    const found = await findDependencyCruiserPackage(path.dirname(mainEntry));
    const bin = found?.pkg.bin?.["dependency-cruise"] ?? found?.pkg.bin?.depcruise;
    if (found && bin) return path.join(found.dir, bin);
  }
  throw new Error(`dependency-cruiser is not installed in ${root}; the TypeScript adapter needs it`);
}

async function tsConfigFor(root, tooling) {
  for (const candidate of [tooling.tsConfig, "tsconfig.json"]) {
    if (candidate && (await exists(path.join(root, candidate)))) return path.join(root, candidate);
  }
  return null;
}

export async function cruiseArguments(root, tooling, config, roots) {
  const tsConfig = config === DEFAULT_CONFIG ? await tsConfigFor(root, tooling) : null;
  return ["--output-type", "json", "--config", config, ...(tsConfig ? ["--ts-config", tsConfig] : []), ...roots];
}

async function runCruise(root, tooling, roots) {
  const bin = await locateCruiserBin(root);
  const cruiseArgs = await cruiseArguments(root, tooling, await resolveConfig(root, tooling), roots);
  const isBinShim = path.basename(path.dirname(bin)) === ".bin";
  const command = isBinShim ? bin : process.execPath;
  const args = isBinShim ? cruiseArgs : [bin, ...cruiseArgs];
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: root });
    let stdout = "", stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", () => {
      try { resolve(JSON.parse(stdout)); }
      catch { reject(new Error(`dependency-cruiser produced no JSON: ${stderr.slice(0, 400)}`)); }
    });
  });
}

async function extractFromExportsJson(root, exportsJsonPath, normalized) {
  const exportsJson = JSON.parse(await readFile(path.resolve(root, exportsJsonPath), "utf8"));
  const modules = [];
  for (const modulePath of [...normalized.modules].sort()) {
    const entry = exportsJson[modulePath];
    if (!entry) {
      normalized.warnings.push(`no exports entry for ${modulePath}`);
      modules.push({ path: modulePath, exports: { abstract: 0, concrete: 0 }, implements: [] });
      continue;
    }
    modules.push({ path: modulePath, exports: entry.exports, implements: entry.implements ?? [] });
  }
  return modules;
}

async function extractFromTypescript(root, normalized) {
  const ts = loadTypescript(root);
  const modules = [];
  for (const modulePath of [...normalized.modules].sort()) {
    let text;
    try { text = await readFile(path.join(root, modulePath), "utf8"); }
    catch { normalized.warnings.push(`cannot read ${modulePath}`); modules.push({ path: modulePath, exports: { abstract: 0, concrete: 0 }, implements: [] }); continue; }
    modules.push({ path: modulePath, ...scanExports(ts, modulePath, text) });
  }
  return modules;
}

export function createTypescriptAdapter({ root, tooling }) {
  return {
    language: "typescript",
    async extract({ roots, cruiseJsonPath, exportsJsonPath, frameworks = [] }) {
      const cruise = cruiseJsonPath
        ? JSON.parse(await readFile(path.resolve(root, cruiseJsonPath), "utf8"))
        : await runCruise(root, tooling, roots);
      const normalized = normalizeCruise(cruise, frameworks);
      const modules = exportsJsonPath
        ? await extractFromExportsJson(root, exportsJsonPath, normalized)
        : await extractFromTypescript(root, normalized);
      return { modules, edges: normalized.edges, warnings: normalized.warnings };
    },
  };
}
