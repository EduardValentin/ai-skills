import { ToolingError } from "../cli/errors.mjs";
import { runAdapter } from "../adapter/run.mjs";
import { buildGraph } from "./build.mjs";
import { cacheKey, documentKey, readCachedGraph, writeCachedGraph } from "./cache.mjs";
import { isGitRepository, withTree } from "./tree.mjs";

const NOT_A_REPOSITORY =
  "not a git repository: the graph cache is keyed by the adapter document, so the adapter runs on every command.";

async function graphForRef(root, model, ref) {
  const document = await withTree(root, ref, (treeRoot) => runAdapter(model, treeRoot, root));
  return buildGraph(model, document);
}

async function graphOutsideRepository(root, model) {
  const document = await runAdapter(model, root, root);
  const key = documentKey(model, document);
  const cached = readCachedGraph(root, key);
  if (cached) return cached;
  const graph = buildGraph(model, document);
  graph.warnings.push(NOT_A_REPOSITORY);
  await writeCachedGraph(root, key, graph);
  return graph;
}

export async function loadGraph(root, model, { ref, flags = {} } = {}) {
  if (!(await isGitRepository(root))) {
    if (ref) throw new ToolingError(`--ref ${ref} needs a git repository, and ${root} is not inside one.`);
    return graphOutsideRepository(root, model);
  }
  const key = await cacheKey(root, model, ref, flags);
  const cached = readCachedGraph(root, key);
  if (cached) return cached;
  const graph = ref ? await graphForRef(root, model, ref) : buildGraph(model, await runAdapter(model, root, root));
  await writeCachedGraph(root, key, graph);
  return graph;
}
