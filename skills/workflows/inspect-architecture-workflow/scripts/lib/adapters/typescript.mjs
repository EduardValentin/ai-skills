import { spawn } from "node:child_process";
import { access, readFile, realpath } from "node:fs/promises";
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
      if (isExternalEntry(d)) {
        const name = packageName(d.module);
        const tag = types.includes("core") ? "runtime" : frameworks.includes(name) ? "framework" : "vendor";
        edges.push({ from: m.source, external: { name, tag } });
        continue;
      }
      const outsideName = outsideRootName(d.resolved ?? "");
      if (outsideName !== null) {
        warnOutside(d.resolved);
        edges.push({ from: m.source, external: { name: outsideName, tag: "vendor" } });
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

const ALL_CAPABILITIES = { exports: true, implements: true, constructs: true, signatures: true };
const PER_FILE_CAPABILITIES = { exports: true, implements: true, constructs: false, signatures: false };
const EMPTY_EXPORTS = { abstract: 0, concrete: 0 };
const EMPTY_FACTS = { exports: EMPTY_EXPORTS, implements: [], constructs: [], signatures: [] };

function hasModifier(ts, node, kind) {
  return (ts.canHaveModifiers(node) ? ts.getModifiers(node) ?? [] : []).some((mod) => mod.kind === kind);
}

function scanDeclarations(ts, source) {
  const exports = { abstract: 0, concrete: 0 };
  const implemented = [];
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
    if (!hasModifier(ts, statement, ts.SyntaxKind.ExportKeyword)) continue;
    const abstract = ts.isInterfaceDeclaration(statement) || ts.isTypeAliasDeclaration(statement)
      || (ts.isClassDeclaration(statement) && hasModifier(ts, statement, ts.SyntaxKind.AbstractKeyword));
    if (abstract) exports.abstract += 1;
    else if (ts.isVariableStatement(statement)) exports.concrete += statement.declarationList.declarations.length;
    else exports.concrete += 1;
  }
  return { exports, implements: implemented };
}

function uniqueBy(items, key) {
  const seen = new Set();
  return items.filter((item) => (seen.has(key(item)) ? false : (seen.add(key(item)), true)));
}

const symbolKey = (ref) => `${ref.symbol}\u0000${ref.path}`;

function resolveAlias(ts, checker, symbol) {
  return symbol && symbol.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(symbol) : symbol;
}

function moduleReference(analysis, symbol, fromPath) {
  const { ts, checker, root, modules } = analysis;
  const resolved = resolveAlias(ts, checker, symbol);
  const declaration = resolved?.declarations?.[0];
  if (!declaration) return null;
  const declaredIn = path.relative(root, declaration.getSourceFile().fileName).split(path.sep).join("/");
  if (declaredIn === fromPath || !modules.has(declaredIn)) return null;
  return { symbol: resolved.name, path: declaredIn };
}

function constructedTypes(analysis, source, filePath) {
  const { ts, checker } = analysis;
  const found = [];
  const visit = (node) => {
    if (ts.isNewExpression(node)) {
      const reference = moduleReference(analysis, checker.getSymbolAtLocation(node.expression), filePath);
      if (reference) found.push(reference);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return uniqueBy(found, symbolKey);
}

function isHidden(ts, member) {
  return hasModifier(ts, member, ts.SyntaxKind.PrivateKeyword) || hasModifier(ts, member, ts.SyntaxKind.ProtectedKeyword)
    || (member.name !== undefined && ts.isPrivateIdentifier(member.name));
}

function surfaceTypeNodes(ts, declaration) {
  const nodes = [];
  const ofFunction = (fn) => { for (const parameter of fn.parameters) nodes.push(parameter.type); nodes.push(fn.type); };
  const ofMember = (member) => {
    if (ts.isConstructorDeclaration(member)) { ofFunction(member); return; }
    if (isHidden(ts, member)) return;
    if (ts.isFunctionLike(member)) ofFunction(member);
    else if (member.type) nodes.push(member.type);
    else if (member.initializer && ts.isFunctionLike(member.initializer)) ofFunction(member.initializer);
  };
  if (ts.isClassDeclaration(declaration) || ts.isInterfaceDeclaration(declaration)) declaration.members.forEach(ofMember);
  else if (ts.isTypeAliasDeclaration(declaration)) nodes.push(declaration.type);
  else if (ts.isFunctionDeclaration(declaration)) ofFunction(declaration);
  else if (ts.isVariableDeclaration(declaration)) {
    const { type, initializer } = declaration;
    if (type) nodes.push(type);
    else if (initializer && ts.isObjectLiteralExpression(initializer)) initializer.properties.forEach(ofMember);
    else if (initializer && ts.isFunctionLike(initializer)) ofFunction(initializer);
  }
  return nodes.filter(Boolean);
}

function referencedTypes(analysis, typeNodes, filePath) {
  const { ts, checker } = analysis;
  const found = [];
  const visit = (node) => {
    if (ts.isTypeReferenceNode(node)) {
      const reference = moduleReference(analysis, checker.getSymbolAtLocation(node.typeName), filePath);
      if (reference) found.push(reference);
    }
    ts.forEachChild(node, visit);
  };
  typeNodes.forEach(visit);
  return uniqueBy(found, symbolKey);
}

function localExports(analysis, source) {
  const { ts, checker } = analysis;
  const moduleSymbol = checker.getSymbolAtLocation(source);
  if (!moduleSymbol) return [];
  return checker.getExportsOfModule(moduleSymbol).filter((symbol) => !(symbol.flags & ts.SymbolFlags.Alias) && symbol.declarations?.length);
}

function exportedValueType(analysis, symbol) {
  const { ts, checker } = analysis;
  if (!(symbol.flags & ts.SymbolFlags.Value)) return null;
  const type = symbol.flags & ts.SymbolFlags.Class
    ? checker.getDeclaredTypeOfSymbol(symbol)
    : checker.getTypeOfSymbolAtLocation(symbol, symbol.declarations[0]);
  return type.flags & ts.TypeFlags.Any ? null : type;
}

function structuralImplements(analysis, exported, filePath) {
  const implemented = [];
  for (const port of analysis.portTypes) {
    if (port.path === filePath) continue;
    const matches = exported.some((symbol) => {
      const type = exportedValueType(analysis, symbol);
      return type !== null && analysis.checker.isTypeAssignableTo(type, port.type);
    });
    if (matches) implemented.push(port.symbol);
  }
  return implemented;
}

export function scanFacts(analysis, filePath) {
  const source = analysis.program.getSourceFile(path.resolve(analysis.root, filePath));
  if (!source) return null;
  const declared = scanDeclarations(analysis.ts, source);
  const exported = localExports(analysis, source);
  const signatures = exported.map((symbol) => ({
    symbol: symbol.name,
    types: referencedTypes(analysis, symbol.declarations.flatMap((d) => surfaceTypeNodes(analysis.ts, d)), filePath),
  }));
  return {
    exports: declared.exports,
    implements: [...new Set([...declared.implements, ...structuralImplements(analysis, exported, filePath)])],
    constructs: constructedTypes(analysis, source, filePath),
    signatures,
  };
}

function resolvePortTypes(analysis, ports) {
  const resolved = [];
  for (const port of ports) {
    if (!analysis.modules.has(port.path)) continue;
    const source = analysis.program.getSourceFile(path.resolve(analysis.root, port.path));
    const symbol = source && localExports(analysis, source).find((s) => s.name === port.symbol);
    if (!symbol) continue;
    const type = analysis.checker.getDeclaredTypeOfSymbol(symbol);
    if (analysis.checker.getPropertiesOfType(type).length > 0) resolved.push({ ...port, type });
  }
  return resolved;
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

const FACT_FIELDS = ["exports", "implements", "constructs", "signatures"];

function factsFileShape(json) {
  if (json.capabilities && json.modules) return { capabilities: { ...Object.fromEntries(FACT_FIELDS.map((f) => [f, false])), ...json.capabilities }, modules: json.modules };
  return { capabilities: PER_FILE_CAPABILITIES, modules: json };
}

async function extractFromFactsJson(root, factsJsonPath, normalized) {
  const { capabilities, modules: entries } = factsFileShape(JSON.parse(await readFile(path.resolve(root, factsJsonPath), "utf8")));
  const provided = FACT_FIELDS.filter((field) => capabilities[field]);
  const modules = [...normalized.modules].sort().map((modulePath) => {
    const entry = entries[modulePath];
    if (!entry) normalized.warnings.push(`no facts entry for ${modulePath}`);
    return { path: modulePath, ...Object.fromEntries(provided.map((field) => [field, entry?.[field] ?? EMPTY_FACTS[field]])) };
  });
  return { capabilities, modules };
}

async function compilerOptions(ts, root, tooling) {
  const configFile = await tsConfigFor(root, tooling);
  if (!configFile) return {};
  const { config, error } = ts.readConfigFile(configFile, ts.sys.readFile);
  if (error) throw new Error(ts.flattenDiagnosticMessageText(error.messageText, "\n"));
  return ts.parseJsonConfigFileContent(config, ts.sys, path.dirname(configFile)).options;
}

async function createAnalysis(ts, root, tooling, modulePaths) {
  const options = { ...(await compilerOptions(ts, root, tooling)), noEmit: true };
  const resolvedRoot = await realpath(root);
  const program = ts.createProgram(modulePaths.map((p) => path.resolve(resolvedRoot, p)), options);
  return { ts, program, checker: program.getTypeChecker(), root: resolvedRoot, modules: new Set(modulePaths) };
}

async function extractPerFile(ts, root, modulePaths, warnings) {
  const modules = [];
  for (const modulePath of modulePaths) {
    let text;
    try { text = await readFile(path.join(root, modulePath), "utf8"); }
    catch { warnings.push(`cannot read ${modulePath}`); modules.push({ path: modulePath, exports: EMPTY_EXPORTS, implements: [] }); continue; }
    modules.push({ path: modulePath, ...scanDeclarations(ts, ts.createSourceFile(modulePath, text, ts.ScriptTarget.Latest, true)) });
  }
  return { capabilities: PER_FILE_CAPABILITIES, modules };
}

async function extractFromTypescript(root, tooling, normalized, ports) {
  const ts = loadTypescript(root);
  const modulePaths = [...normalized.modules].sort();
  let analysis;
  try {
    analysis = await createAnalysis(ts, root, tooling, modulePaths);
  } catch (error) {
    normalized.warnings.push(`cannot build a TypeScript program (${error instanceof Error ? error.message : String(error)}); constructs and signatures are not provided`);
    return extractPerFile(ts, root, modulePaths, normalized.warnings);
  }
  const structural = typeof analysis.checker.isTypeAssignableTo === "function";
  if (!structural && ports.length > 0) normalized.warnings.push("this TypeScript version cannot test assignability; implements lists nominal implementations only");
  analysis.portTypes = structural ? resolvePortTypes(analysis, ports) : [];
  const modules = modulePaths.map((modulePath) => {
    const facts = scanFacts(analysis, modulePath);
    if (!facts) normalized.warnings.push(`cannot read ${modulePath}`);
    return { path: modulePath, ...(facts ?? EMPTY_FACTS) };
  });
  return { capabilities: ALL_CAPABILITIES, modules };
}

export function createTypescriptAdapter({ root, tooling }) {
  return {
    language: "typescript",
    async extract({ roots, cruiseJsonPath, factsJsonPath, exportsJsonPath, frameworks = [], ports = [] }) {
      const cruise = cruiseJsonPath
        ? JSON.parse(await readFile(path.resolve(root, cruiseJsonPath), "utf8"))
        : await runCruise(root, tooling, roots);
      const normalized = normalizeCruise(cruise, frameworks);
      const savedFacts = factsJsonPath ?? exportsJsonPath;
      const { capabilities, modules } = savedFacts
        ? await extractFromFactsJson(root, savedFacts, normalized)
        : await extractFromTypescript(root, tooling, normalized, ports);
      return { capabilities, modules, edges: normalized.edges, warnings: normalized.warnings };
    },
  };
}
