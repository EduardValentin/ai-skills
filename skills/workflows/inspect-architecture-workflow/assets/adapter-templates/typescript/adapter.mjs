#!/usr/bin/env node
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { extractFromProgram, loadTypescript, withSymbols } from "./compiler.mjs";
import { normalizeCruise, runCruise } from "./dependency-tool.mjs";
import { linkSourceModules, removeLinks } from "./link-packages.mjs";

export { cruiseArguments, locateCruiserBin, normalizeCruise } from "./dependency-tool.mjs";

export const settings = {
  roots: ["src"],
  tsConfig: "tsconfig.json",
  dependencyCruiserConfig: "cruise-config.cjs",
};

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DOCUMENT_VERSION = 1;

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
    await removeLinks(links);
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
