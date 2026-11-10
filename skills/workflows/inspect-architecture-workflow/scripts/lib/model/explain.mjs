import { createClassifier } from "./classify.mjs";
import { DEFAULT_THRESHOLDS, THRESHOLD_DESCRIPTIONS } from "./defaults.mjs";

export function explainPath(model, path) {
  const result = createClassifier(model)(path);
  if (!result.matched) return { path, ...result };
  const component = model.components.find((candidate) => candidate.name === result.matched.component);
  const pattern = component.classify[result.matched.index].pattern;
  return { path, ...result, matched: { ...result.matched, pattern } };
}

function describeMatch(result) {
  if (!result.matched) return "none";
  const { component, index, pattern } = result.matched;
  return `${component}, pair ${index + 1}: ${pattern} -> ${result.kind}`;
}

export function renderExplanation(result) {
  const lines = [
    `path: ${result.path}`,
    `component: ${result.component ?? "none"}`,
    `kind: ${result.kind ?? "unknown"}`,
    `ring: ${result.ring ?? "unknown"}`,
    `actors: ${result.actors ? result.actors.join(", ") : "unknown"}`,
    `matched: ${describeMatch(result)}`,
  ];
  return lines.join("\n");
}

export function thresholdRows(model) {
  return Object.keys(DEFAULT_THRESHOLDS).map((knob) => ({
    knob,
    default: DEFAULT_THRESHOLDS[knob],
    project: model ? model.thresholds[knob] : DEFAULT_THRESHOLDS[knob],
    description: THRESHOLD_DESCRIPTIONS[knob],
  }));
}

export function renderThresholds(rows) {
  const width = Math.max(...rows.map((row) => row.knob.length));
  return rows
    .map((row) => `${row.knob.padEnd(width)}  default ${row.default}  project ${row.project}  ${row.description}`)
    .join("\n");
}
