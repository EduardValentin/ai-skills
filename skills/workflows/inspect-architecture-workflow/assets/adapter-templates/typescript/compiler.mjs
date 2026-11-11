import { readFile, realpath } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { isScript, resolvePortTypes, scanDeclarations, scanFacts } from "./compiler-facts.mjs";
import { tsConfigFile } from "./files.mjs";

const SUPPORTED_MAJORS = [5, 6];
const EMPTY_EXPORTS = { abstract: 0, concrete: 0 };
const EMPTY_FACTS = { exports: EMPTY_EXPORTS, implements: [], constructs: [], signatures: [], typeChecks: [] };
export const FULL_CAPABILITIES = {
  exports: true, implements: true, constructs: true, signatures: true, symbolImports: true, typeChecks: true,
};
const DECLARATION_CAPABILITIES = {
  exports: true, implements: true, constructs: false, signatures: false, symbolImports: false, typeChecks: false,
};

function unsupportedVersionMessage(sourceRoot, version) {
  return `The TypeScript found in ${sourceRoot} is version ${version}, which has no JavaScript compiler API. ` +
    `This adapter supports TypeScript ${SUPPORTED_MAJORS.map((major) => `${major}.x`).join(" and ")}. ` +
    `Install a supported version in ${sourceRoot}.`;
}

export function loadTypescript(sourceRoot) {
  const require = createRequire(path.join(sourceRoot, "package.json"));
  let ts;
  try {
    ts = require("typescript");
  } catch {
    throw new Error(`typescript is not installed in ${sourceRoot}; the TypeScript adapter needs it`);
  }
  const major = Number.parseInt(ts.version ?? "", 10);
  if (Number.isFinite(major) && !SUPPORTED_MAJORS.includes(major)) {
    throw new Error(unsupportedVersionMessage(sourceRoot, ts.version));
  }
  return ts;
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

export async function extractFromProgram(ts, treeRoot, tsConfig, normalized, ports) {
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

export function withSymbols(edges, importedSymbols) {
  return edges.map((edge) => {
    const names = edge.to && edge.kind !== "dynamic" ? importedSymbols.get(edge.from)?.get(edge.to) : null;
    return names ? { ...edge, symbols: [...names].sort() } : edge;
  });
}
