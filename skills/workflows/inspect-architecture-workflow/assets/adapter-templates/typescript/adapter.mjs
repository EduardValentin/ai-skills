#!/usr/bin/env node
import { spawn } from "node:child_process";
import { access, lstat, mkdir, readdir, readFile, realpath, symlink, unlink } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export const settings = {
  roots: ["src"],
  tsConfig: "tsconfig.json",
  dependencyCruiserConfig: "cruise-config.cjs",
};

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DOCUMENT_VERSION = 1;
const MAX_NODE_MODULES_DEPTH = 3;
const NODE_MODULES_PATH = /(^|\/)node_modules\//;
const OUTSIDE_ROOT = /^(\.\.\/)+/;
const SCRIPT_EXTENSIONS = new Set([".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"]);
const EMPTY_EXPORTS = { abstract: 0, concrete: 0 };
const EMPTY_FACTS = { exports: EMPTY_EXPORTS, implements: [], constructs: [], signatures: [], typeChecks: [] };
const FULL_CAPABILITIES = {
  exports: true, implements: true, constructs: true, signatures: true, symbolImports: true, typeChecks: true,
};
const DECLARATION_CAPABILITIES = {
  exports: true, implements: true, constructs: false, signatures: false, symbolImports: false, typeChecks: false,
};

async function exists(file) {
  try {
    await access(file);
    return true;
  } catch {
    return false;
  }
}

export function packageName(specifier) {
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

async function findNodeModules(absoluteDir, relativeDir, depth, found) {
  if (depth > MAX_NODE_MODULES_DEPTH) return;
  let entries;
  try {
    entries = await readdir(absoluteDir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name === ".git") continue;
    const relative = path.join(relativeDir, entry.name);
    if (entry.name === "node_modules") found.push(relative);
    else await findNodeModules(path.join(absoluteDir, entry.name), relative, depth + 1, found);
  }
}

async function isMissing(file) {
  try {
    await lstat(file);
    return false;
  } catch {
    return true;
  }
}

async function realpathOrNull(dir) {
  try {
    return await realpath(dir);
  } catch {
    return null;
  }
}

async function linkSourceModules(sourceRoot, treeRoot) {
  const realSource = await realpathOrNull(sourceRoot);
  if (realSource === null || realSource === (await realpathOrNull(treeRoot))) return [];
  const relatives = [];
  await findNodeModules(sourceRoot, "", 0, relatives);
  const links = [];
  for (const relative of relatives) {
    const link = path.join(treeRoot, relative);
    if (!(await isMissing(link))) continue;
    await mkdir(path.dirname(link), { recursive: true });
    await symlink(path.join(sourceRoot, relative), link);
    links.push(link);
  }
  return links;
}

function loadTypescript(sourceRoot) {
  const require = createRequire(path.join(sourceRoot, "package.json"));
  try {
    return require("typescript");
  } catch {
    throw new Error(`typescript is not installed in ${sourceRoot}; the TypeScript adapter needs it`);
  }
}

function isScript(modulePath) {
  return SCRIPT_EXTENSIONS.has(path.extname(modulePath).toLowerCase());
}

function hasModifier(ts, node, kind) {
  const modifiers = ts.canHaveModifiers(node) ? ts.getModifiers(node) ?? [] : [];
  return modifiers.some((modifier) => modifier.kind === kind);
}

function exportedNames(ts, statement) {
  const clause = statement.exportClause;
  return clause && ts.isNamedExports(clause) ? clause.elements.length : 1;
}

function implementedNames(ts, source, statement) {
  const names = [];
  for (const clause of statement.heritageClauses ?? []) {
    if (clause.token !== ts.SyntaxKind.ImplementsKeyword) continue;
    for (const type of clause.types) names.push(type.expression.getText(source));
  }
  return names;
}

function isAbstractExport(ts, statement) {
  if (ts.isInterfaceDeclaration(statement) || ts.isTypeAliasDeclaration(statement)) return true;
  return ts.isClassDeclaration(statement) && hasModifier(ts, statement, ts.SyntaxKind.AbstractKeyword);
}

function scanDeclarations(ts, source) {
  const exports = { abstract: 0, concrete: 0 };
  const implemented = [];
  for (const statement of source.statements) {
    if (ts.isExportDeclaration(statement)) {
      exports.concrete += exportedNames(ts, statement);
      continue;
    }
    if (ts.isExportAssignment(statement)) {
      exports.concrete += 1;
      continue;
    }
    if (ts.isClassDeclaration(statement)) implemented.push(...implementedNames(ts, source, statement));
    if (!hasModifier(ts, statement, ts.SyntaxKind.ExportKeyword)) continue;
    if (isAbstractExport(ts, statement)) exports.abstract += 1;
    else if (ts.isVariableStatement(statement)) exports.concrete += statement.declarationList.declarations.length;
    else exports.concrete += 1;
  }
  return { exports, implements: implemented };
}

function uniqueBy(items, key) {
  const seen = new Set();
  return items.filter((item) => {
    if (seen.has(key(item))) return false;
    seen.add(key(item));
    return true;
  });
}

const referenceKey = (reference) => `${reference.symbol}\u0000${reference.path}\u0000${reference.line ?? ""}`;

function relativeModulePath(analysis, fileName) {
  return path.relative(analysis.root, fileName).split(path.sep).join("/");
}

function resolveAlias(ts, checker, symbol) {
  return symbol && symbol.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(symbol) : symbol;
}

function moduleReference(analysis, symbol, fromPath) {
  const resolved = resolveAlias(analysis.ts, analysis.checker, symbol);
  const declaration = resolved?.declarations?.[0];
  if (!declaration) return null;
  const declaredIn = relativeModulePath(analysis, declaration.getSourceFile().fileName);
  if (declaredIn === fromPath || !analysis.modules.has(declaredIn)) return null;
  return { symbol: resolved.name, path: declaredIn };
}

function collectNodes(ts, root, collect) {
  const found = [];
  const visit = (node) => {
    const item = collect(node);
    if (item) found.push(item);
    ts.forEachChild(node, visit);
  };
  visit(root);
  return found;
}

function constructedTypes(analysis, source, filePath) {
  const { ts, checker } = analysis;
  const found = collectNodes(ts, source, (node) => {
    if (!ts.isNewExpression(node)) return null;
    return moduleReference(analysis, checker.getSymbolAtLocation(node.expression), filePath);
  });
  return uniqueBy(found, referenceKey);
}

function typeChecks(analysis, source, filePath) {
  const { ts, checker } = analysis;
  const found = collectNodes(ts, source, (node) => {
    if (!ts.isBinaryExpression(node) || node.operatorToken.kind !== ts.SyntaxKind.InstanceOfKeyword) return null;
    const reference = moduleReference(analysis, checker.getSymbolAtLocation(node.right), filePath);
    if (!reference) return null;
    const { line } = source.getLineAndCharacterOfPosition(node.getStart(source));
    return { ...reference, line: line + 1 };
  });
  return uniqueBy(found, referenceKey);
}

function isHidden(ts, member) {
  return hasModifier(ts, member, ts.SyntaxKind.PrivateKeyword)
    || hasModifier(ts, member, ts.SyntaxKind.ProtectedKeyword)
    || (member.name !== undefined && ts.isPrivateIdentifier(member.name));
}

function functionTypeNodes(fn) {
  return [...fn.parameters.map((parameter) => parameter.type), fn.type];
}

function memberTypeNodes(ts, member) {
  if (ts.isConstructorDeclaration(member)) return functionTypeNodes(member);
  if (isHidden(ts, member)) return [];
  if (ts.isFunctionLike(member)) return functionTypeNodes(member);
  if (member.type) return [member.type];
  if (member.initializer && ts.isFunctionLike(member.initializer)) return functionTypeNodes(member.initializer);
  return [];
}

function variableTypeNodes(ts, declaration) {
  const { type, initializer } = declaration;
  if (type) return [type];
  if (initializer && ts.isObjectLiteralExpression(initializer)) {
    return initializer.properties.flatMap((member) => memberTypeNodes(ts, member));
  }
  if (initializer && ts.isFunctionLike(initializer)) return functionTypeNodes(initializer);
  return [];
}

function surfaceTypeNodes(ts, declaration) {
  let nodes = [];
  if (ts.isClassDeclaration(declaration) || ts.isInterfaceDeclaration(declaration)) {
    nodes = declaration.members.flatMap((member) => memberTypeNodes(ts, member));
  } else if (ts.isTypeAliasDeclaration(declaration)) {
    nodes = [declaration.type];
  } else if (ts.isFunctionDeclaration(declaration)) {
    nodes = functionTypeNodes(declaration);
  } else if (ts.isVariableDeclaration(declaration)) {
    nodes = variableTypeNodes(ts, declaration);
  }
  return nodes.filter(Boolean);
}

function referencedTypes(analysis, typeNodes, filePath) {
  const { ts, checker } = analysis;
  const found = typeNodes.flatMap((root) => collectNodes(ts, root, (node) => {
    if (!ts.isTypeReferenceNode(node)) return null;
    return moduleReference(analysis, checker.getSymbolAtLocation(node.typeName), filePath);
  }));
  return uniqueBy(found, referenceKey);
}

function localExports(analysis, source) {
  const { ts, checker } = analysis;
  const moduleSymbol = checker.getSymbolAtLocation(source);
  if (!moduleSymbol) return [];
  return checker.getExportsOfModule(moduleSymbol)
    .filter((symbol) => !(symbol.flags & ts.SymbolFlags.Alias) && symbol.declarations?.length);
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

function importedNames(ts, statement) {
  if (ts.isExportDeclaration(statement)) {
    const clause = statement.exportClause;
    if (!clause || ts.isNamespaceExport(clause)) return ["*"];
    return clause.elements.map((element) => (element.propertyName ?? element.name).text);
  }
  const clause = statement.importClause;
  if (!clause) return [];
  const names = clause.name ? ["default"] : [];
  const bindings = clause.namedBindings;
  if (bindings && ts.isNamespaceImport(bindings)) names.push("*");
  if (bindings && ts.isNamedImports(bindings)) {
    names.push(...bindings.elements.map((element) => (element.propertyName ?? element.name).text));
  }
  return names;
}

function importedSymbolsByTarget(analysis, source, filePath) {
  const { ts, checker } = analysis;
  const byTarget = new Map();
  for (const statement of source.statements) {
    const isImport = ts.isImportDeclaration(statement) || ts.isExportDeclaration(statement);
    if (!isImport || !statement.moduleSpecifier) continue;
    const target = checker.getSymbolAtLocation(statement.moduleSpecifier)?.declarations?.[0];
    if (!target) continue;
    const targetPath = relativeModulePath(analysis, target.getSourceFile().fileName);
    if (targetPath === filePath || !analysis.modules.has(targetPath)) continue;
    const names = byTarget.get(targetPath) ?? new Set();
    importedNames(ts, statement).forEach((name) => names.add(name));
    byTarget.set(targetPath, names);
  }
  return byTarget;
}

export function scanFacts(analysis, filePath) {
  const source = analysis.program.getSourceFile(path.resolve(analysis.root, filePath));
  if (!source) return null;
  const declared = scanDeclarations(analysis.ts, source);
  const exported = localExports(analysis, source);
  const signatures = exported.map((symbol) => ({
    symbol: symbol.name,
    types: referencedTypes(
      analysis,
      symbol.declarations.flatMap((declaration) => surfaceTypeNodes(analysis.ts, declaration)),
      filePath,
    ),
  }));
  return {
    exports: declared.exports,
    implements: [...new Set([...declared.implements, ...structuralImplements(analysis, exported, filePath)])],
    constructs: constructedTypes(analysis, source, filePath),
    signatures,
    typeChecks: typeChecks(analysis, source, filePath),
    importedSymbols: importedSymbolsByTarget(analysis, source, filePath),
  };
}

function resolvePortTypes(analysis, ports) {
  const resolved = [];
  for (const port of ports) {
    if (!analysis.modules.has(port.path)) continue;
    const source = analysis.program.getSourceFile(path.resolve(analysis.root, port.path));
    const symbol = source && localExports(analysis, source).find((candidate) => candidate.name === port.symbol);
    if (!symbol) continue;
    const type = analysis.checker.getDeclaredTypeOfSymbol(symbol);
    if (analysis.checker.getPropertiesOfType(type).length > 0) resolved.push({ ...port, type });
  }
  return resolved;
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

async function tsConfigFile(treeRoot, tsConfig) {
  const file = tsConfig ? path.join(treeRoot, tsConfig) : null;
  return file && (await exists(file)) ? file : null;
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

async function runCruise(sourceRoot, treeRoot, tooling) {
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
    throw new Error(`dependency-cruiser produced no JSON: ${stderr.slice(0, 400)}`);
  }
}

async function compilerOptions(ts, treeRoot, tsConfig) {
  const configFile = await tsConfigFile(treeRoot, tsConfig);
  if (!configFile) return {};
  const { config, error } = ts.readConfigFile(configFile, ts.sys.readFile);
  if (error) throw new Error(ts.flattenDiagnosticMessageText(error.messageText, "\n"));
  return ts.parseJsonConfigFileContent(config, ts.sys, path.dirname(configFile)).options;
}

async function createAnalysis(ts, treeRoot, tsConfig, modulePaths) {
  const options = { ...(await compilerOptions(ts, treeRoot, tsConfig)), allowJs: true, checkJs: false, noEmit: true };
  const root = await realpath(treeRoot);
  const program = ts.createProgram(modulePaths.map((modulePath) => path.resolve(root, modulePath)), options);
  return { ts, program, checker: program.getTypeChecker(), root, modules: new Set(modulePaths) };
}

async function scanFile(ts, treeRoot, modulePath, warnings) {
  if (!isScript(modulePath)) return { exports: EMPTY_EXPORTS, implements: [] };
  let text;
  try {
    text = await readFile(path.join(treeRoot, modulePath), "utf8");
  } catch {
    warnings.push(`cannot read ${modulePath}`);
    return { exports: EMPTY_EXPORTS, implements: [] };
  }
  return scanDeclarations(ts, ts.createSourceFile(modulePath, text, ts.ScriptTarget.Latest, true));
}

async function extractPerFile(ts, treeRoot, modulePaths, warnings) {
  const modules = [];
  for (const modulePath of modulePaths) {
    modules.push({ path: modulePath, ...(await scanFile(ts, treeRoot, modulePath, warnings)) });
  }
  return { capabilities: DECLARATION_CAPABILITIES, modules, importedSymbols: new Map() };
}

async function factsOutsideTheProgram(ts, treeRoot, modulePath, warnings) {
  if (isScript(modulePath)) warnings.push(`facts for ${modulePath} come from the per-file scan`);
  return { ...EMPTY_FACTS, ...(await scanFile(ts, treeRoot, modulePath, warnings)) };
}

async function extractFromProgram(ts, treeRoot, tsConfig, normalized, ports) {
  const modulePaths = [...normalized.modules].sort();
  let analysis;
  try {
    analysis = await createAnalysis(ts, treeRoot, tsConfig, modulePaths);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    normalized.warnings.push(
      `cannot build a TypeScript program (${reason}); ` +
        "constructs, signatures, symbolImports and typeChecks are not provided",
    );
    return extractPerFile(ts, treeRoot, modulePaths, normalized.warnings);
  }
  const structural = typeof analysis.checker.isTypeAssignableTo === "function";
  if (!structural && ports.length > 0) {
    normalized.warnings.push(
      "this TypeScript version cannot test assignability; implements lists nominal implementations only",
    );
  }
  analysis.portTypes = structural ? resolvePortTypes(analysis, ports) : [];
  const modules = [];
  const importedSymbols = new Map();
  for (const modulePath of modulePaths) {
    const scanned = scanFacts(analysis, modulePath);
    if (!scanned) {
      const facts = await factsOutsideTheProgram(ts, treeRoot, modulePath, normalized.warnings);
      modules.push({ path: modulePath, ...facts });
      continue;
    }
    const { importedSymbols: imported, ...facts } = scanned;
    importedSymbols.set(modulePath, imported);
    modules.push({ path: modulePath, ...facts });
  }
  return { capabilities: FULL_CAPABILITIES, modules, importedSymbols };
}

function withSymbols(edges, importedSymbols) {
  return edges.map((edge) => {
    const names = edge.to && edge.kind !== "dynamic" ? importedSymbols.get(edge.from)?.get(edge.to) : null;
    return names ? { ...edge, symbols: [...names].sort() } : edge;
  });
}

async function readDocumentFacts(request, sourceRoot, treeRoot, tooling) {
  const ts = loadTypescript(sourceRoot);
  const cruise = await runCruise(sourceRoot, treeRoot, {
    ...tooling,
    dependencyCruiserConfig: path.resolve(HERE, tooling.dependencyCruiserConfig),
  });
  const normalized = normalizeCruise(cruise, request.frameworks ?? []);
  const extracted = await extractFromProgram(ts, treeRoot, tooling.tsConfig, normalized, request.ports ?? []);
  return {
    version: DOCUMENT_VERSION,
    capabilities: extracted.capabilities,
    modules: extracted.modules,
    edges: withSymbols(normalized.edges, extracted.importedSymbols),
    warnings: normalized.warnings,
  };
}

export async function buildDocument(request, sourceRoot, treeRoot, tooling = settings) {
  const links = await linkSourceModules(sourceRoot, treeRoot);
  try {
    return await readDocumentFacts(request, sourceRoot, treeRoot, tooling);
  } finally {
    for (const link of links) await unlink(link);
  }
}

async function readStdin() {
  let text = "";
  for await (const chunk of process.stdin) text += chunk;
  return text;
}

async function main() {
  const request = JSON.parse((await readStdin()) || "{}");
  const sourceRoot = process.env.ARCH_SOURCE_ROOT ?? process.cwd();
  process.stdout.write(JSON.stringify(await buildDocument(request, sourceRoot, process.cwd())));
}

const isEntryPoint = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isEntryPoint) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exit(1);
  });
}
