import { ToolingError } from "../cli/errors.mjs";
import { logNames } from "../git/changes.mjs";
import { createClassifier } from "../model/classify.mjs";
import { table } from "./shared.mjs";

function selectionFor(flags, model) {
  if (flags.since) return [`${flags.since}..HEAD`];
  return [`--since=${model.thresholds.historyWindow}`];
}

async function readHistory(root, selection) {
  try {
    return await logNames(root, selection);
  } catch (error) {
    throw new ToolingError(
      `volatility needs git history: ${error.message.split("\n")[0]}. ` +
        "Run it inside a git repository and pass a --since ref that exists.",
    );
  }
}

function tally(commits, classify) {
  const commitsOf = new Map();
  const modulesOf = new Map();
  const add = (map, name, value) => map.set(name, (map.get(name) ?? new Set()).add(value));
  for (const commit of commits) {
    for (const file of commit.files) {
      const { component } = classify(file);
      if (!component) continue;
      add(commitsOf, component, commit.hash);
      add(modulesOf, component, file);
    }
  }
  return { commitsOf, modulesOf };
}

async function tallyHistory({ model, root, flags }) {
  const commits = await readHistory(root, selectionFor(flags, model));
  return tally(commits, createClassifier(model));
}

export async function componentCommitCounts({ model, root, flags = {} }) {
  const { commitsOf } = await tallyHistory({ model, root, flags });
  return new Map(model.components.map((component) => [component.name, commitsOf.get(component.name)?.size ?? 0]));
}

export async function volatility({ model, flags, root }) {
  const { commitsOf, modulesOf } = await tallyHistory({ model, root, flags });
  const rows = model.components.map((component) => [
    component.name,
    commitsOf.get(component.name)?.size ?? 0,
    modulesOf.get(component.name)?.size ?? 0,
  ]);
  return table(["Component", "Commits", "Modules touched"], rows);
}
