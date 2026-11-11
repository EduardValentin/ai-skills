import { UsageError } from "../cli/errors.mjs";
import { parseArgs } from "../cli/flags.mjs";
import { loadGraph } from "../graph/load.mjs";
import { requireModel } from "../model/load.mjs";
import { FLAG_CHECKS, QUERIES } from "../queries/index.mjs";
import { renderJson, renderMarkdown } from "../render.mjs";

export const QUERY_SPEC = {
  flags: {
    direction: "value",
    "include-barrels": "boolean",
    kind: "value",
    component: "value",
    ring: "value",
    tag: "value",
    base: "git-ref",
    "with-neighbors": "boolean",
    since: "git-ref",
  },
  positional: { min: 1, max: 2 },
};

function selectQuery(name) {
  if (Object.hasOwn(QUERIES, name)) return QUERIES[name];
  throw new UsageError(`unknown query: ${name}. Known queries: ${Object.keys(QUERIES).sort().join(", ")}.`);
}

export async function run(args, { root }) {
  const { positional, flags } = parseArgs(QUERY_SPEC, args);
  const [name, ...rest] = positional;
  const query = selectQuery(name);
  FLAG_CHECKS[name]?.(flags);
  const model = requireModel(root, flags);
  const graph = await loadGraph(root, model, { flags });
  const result = await query({ graph, model, positional: rest, flags, root });
  console.log(flags.json ? renderJson(result) : renderMarkdown(result));
  return 0;
}
