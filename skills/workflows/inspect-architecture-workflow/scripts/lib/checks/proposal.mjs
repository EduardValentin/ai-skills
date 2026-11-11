import { readFileSync } from "node:fs";
import { UsageError } from "../cli/errors.mjs";
import { edgeProblems, normalizeEdge, normalizeModule, readDocumentSchema } from "../adapter/document.mjs";
import { runAdapter } from "../adapter/run.mjs";
import { buildGraph } from "../graph/build.mjs";
import { createClassifier } from "../model/classify.mjs";
import { validateShape } from "../model/validate-shape.mjs";

const CLARIFICATION_CHECK = "clarification";
const NAME = { type: "string", minLength: 1 };

export function proposalSchema() {
  const { modules, edges } = readDocumentSchema().properties;
  const object = (properties) => ({
    type: "object",
    required: Object.keys(properties),
    additionalProperties: false,
    properties,
  });
  return {
    type: "object",
    required: ["version"],
    additionalProperties: false,
    properties: {
      version: { type: "integer", enum: [1] },
      modules,
      edges,
      removedModules: { type: "array", items: NAME },
      removedEdges: { type: "array", items: object({ from: NAME, to: NAME }) },
      classify: { type: "array", items: object({ path: NAME, kind: NAME, component: NAME }) },
      unknown: { type: "array", items: object({ task: NAME, fact: NAME }) },
    },
  };
}

function readProposalFile(file) {
  let text;
  try {
    text = readFileSync(file, "utf8");
  } catch {
    throw new UsageError(`proposal file ${file} cannot be read. Pass the path of the proposal JSON with --proposal.`);
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new UsageError(`proposal file ${file} is not valid JSON: ${error.message}. Fix the syntax and run again.`);
  }
}

function modelProblems(model, proposal) {
  const components = new Set(model.components.map((component) => component.name));
  return (proposal.classify ?? []).flatMap((entry, index) => {
    const at = `classify[${index}]`;
    return [
      ...(model.kinds[entry.kind] ? [] : [`${at}.kind: "${entry.kind}" is not a kind in the model`]),
      ...(components.has(entry.component) ? [] : [`${at}.component: "${entry.component}" is not a component`]),
    ];
  });
}

function edgeProblemsOf(edges) {
  const wellFormed = Array.isArray(edges) && edges.every((edge) => edge !== null && typeof edge === "object");
  return wellFormed ? edgeProblems(edges) : [];
}

export function readProposal(file, model) {
  const proposal = readProposalFile(file);
  const problems = [...validateShape(proposal, proposalSchema())];
  problems.push(...edgeProblemsOf(proposal.edges));
  if (problems.length === 0) problems.push(...modelProblems(model, proposal));
  if (problems.length > 0) {
    throw new UsageError(
      `proposal file ${file} has problems:\n${problems.map((problem) => `  ${problem}`).join("\n")}\n` +
        "Fix the proposal so it matches the adapter document shape, then run again.",
    );
  }
  return proposal;
}

function edgeKey(edge) {
  return JSON.stringify([edge.from, edge.to]);
}

function mergedDocument(document, proposal) {
  const removed = new Set(proposal.removedModules ?? []);
  const replaced = new Set((proposal.modules ?? []).map((module) => module.path));
  const removedEdges = new Set((proposal.removedEdges ?? []).map(edgeKey));
  const keepsModule = (path) => !removed.has(path) && !replaced.has(path);
  const keepsEdge = (edge) =>
    !removed.has(edge.from) && !removed.has(edge.to) && !removedEdges.has(edgeKey(edge));
  const { capabilities } = document;
  return {
    ...document,
    modules: [
      ...document.modules.filter((module) => keepsModule(module.path)),
      ...(proposal.modules ?? []).map((module) => normalizeModule(module, capabilities)),
    ],
    edges: [
      ...document.edges.filter(keepsEdge),
      ...(proposal.edges ?? []).map((edge) => normalizeEdge(edge, capabilities)),
    ],
  };
}

function classificationsFor(model, proposal) {
  const classify = createClassifier(model);
  const entries = new Map((proposal.classify ?? []).map((entry) => [entry.path, entry]));
  const result = {};
  for (const module of proposal.modules ?? []) {
    const byModel = classify(module.path);
    const entry = entries.get(module.path);
    if ((byModel.component && byModel.kind) || !entry) continue;
    result[module.path] = {
      component: entry.component,
      kind: entry.kind,
      ring: model.kinds[entry.kind].ring ?? null,
      actors: null,
      valueType: false,
    };
  }
  return result;
}

function touchedByProposal(graph, proposal) {
  const known = new Map(graph.units.map((unit) => [unit.path, unit]));
  const added = (proposal.modules ?? []).map((module) => module.path);
  const paths = [...added, ...(proposal.edges ?? []).map((edge) => edge.from)];
  const units = [...new Set(paths)].filter((path) => known.has(path));
  const uncovered = new Set(graph.uncovered);
  return {
    units,
    components: [...new Set(units.map((path) => known.get(path).component).filter(Boolean))],
    uncovered: units.filter((path) => uncovered.has(path)),
    renames: new Map(),
  };
}

function clarificationEntries(proposal) {
  return (proposal.unknown ?? []).map(({ task, fact }) => ({
    check: CLARIFICATION_CHECK,
    rules: [],
    target: null,
    clarification: true,
    task,
    fact,
    reason: `${task} does not state ${fact}. Ask the plan author to state it, then review the plan again.`,
  }));
}

export async function proposalComparison({ root, model, file }) {
  const proposal = readProposal(file, model);
  const document = await runAdapter(model, root, root);
  const graph = buildGraph(model, mergedDocument(document, proposal), {
    classifications: classificationsFor(model, proposal),
  });
  return {
    graph,
    baseGraph: buildGraph(model, document),
    touched: touchedByProposal(graph, proposal),
    clarifications: clarificationEntries(proposal),
  };
}
