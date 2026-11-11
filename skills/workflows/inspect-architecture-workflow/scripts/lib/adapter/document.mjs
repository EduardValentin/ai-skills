import { readFileSync } from "node:fs";
import { ToolingError } from "../cli/errors.mjs";
import { validateShape } from "../model/validate-shape.mjs";

const SCHEMA_URL = new URL("../../../assets/adapter-document.schema.json", import.meta.url);
const FACT_CAPABILITIES = ["exports", "implements", "constructs", "signatures", "symbolImports", "typeChecks"];
const FACT_DEFAULTS = {
  exports: () => ({ abstract: 0, concrete: 0 }),
  implements: () => [],
  constructs: () => [],
  signatures: () => [],
  typeChecks: () => [],
};

export function readDocumentSchema() {
  return JSON.parse(readFileSync(SCHEMA_URL, "utf8"));
}

function parseJson(output, command) {
  try {
    return JSON.parse(output);
  } catch (error) {
    throw new ToolingError(
      `The adapter command \`${command}\` printed output that is not valid JSON (${error.message}). ` +
        "Make it print only the adapter document on standard output and send logs to standard error.",
    );
  }
}

export function edgeProblems(edges = []) {
  return edges.flatMap((edge, index) => {
    const at = `edges[${index}]`;
    if (edge.external && edge.to) return [`${at}: give either "to" or "external", not both`];
    if (!edge.external && !edge.to) return [`${at}: needs "to" with "kind", or "external"`];
    if (edge.to && !edge.kind) return [`${at}.kind: is required when "to" is given`];
    return [];
  });
}

function documentProblems(document) {
  if (document === null || typeof document !== "object" || Array.isArray(document)) {
    return ["document: expected an object"];
  }
  const shapeProblems = validateShape(document, readDocumentSchema());
  return shapeProblems.length > 0 ? shapeProblems : edgeProblems(document.edges);
}

function normalizeCapabilities(declared = {}) {
  return Object.fromEntries(FACT_CAPABILITIES.map((name) => [name, declared[name] === true]));
}

export function normalizeModule(module, capabilities) {
  const facts = Object.entries(FACT_DEFAULTS).map(([name, empty]) => {
    const provided = capabilities[name] && module[name] !== undefined;
    return [name, provided ? module[name] : empty()];
  });
  return { path: module.path, ...Object.fromEntries(facts) };
}

export function normalizeEdge(edge, capabilities) {
  const { symbols, ...rest } = edge;
  return capabilities.symbolImports && symbols ? { ...rest, symbols } : rest;
}

export function readAdapterDocument(output, command) {
  const document = parseJson(output, command);
  const problems = documentProblems(document);
  if (problems.length > 0) {
    throw new ToolingError(
      `The adapter command \`${command}\` printed a document with problems:\n` +
        `${problems.map((problem) => `  ${problem}`).join("\n")}\n` +
        "Fix the adapter so its output matches the adapter contract in the adapter-contract reference.",
    );
  }
  const capabilities = normalizeCapabilities(document.capabilities);
  return {
    version: document.version,
    capabilities,
    modules: (document.modules ?? []).map((module) => normalizeModule(module, capabilities)),
    edges: (document.edges ?? []).map((edge) => normalizeEdge(edge, capabilities)),
    warnings: document.warnings ?? [],
  };
}
