import { describeUnit, edgeTarget } from "./targets.mjs";

export function unitEdgeRow({ from, to, evidence, correction }) {
  return {
    target: edgeTarget(from, to),
    evidence,
    correction,
    units: [from, to],
    components: [],
    edge: { level: "unit", from, to },
  };
}

export function externalEdgeRow({ from, name, evidence, correction }) {
  return { ...unitEdgeRow({ from, to: `external:${name}`, evidence, correction }), units: [from] };
}

export function componentRow(name, evidence, correction) {
  return {
    target: name,
    evidence,
    correction,
    units: [],
    components: [name],
    edge: null,
  };
}

export function componentEdgeRow({ from, to, evidence, correction }) {
  return {
    target: edgeTarget(from, to),
    evidence,
    correction,
    units: [],
    components: [from, to],
    edge: { level: "component", from, to },
  };
}

export function describedPair(context, pair) {
  const from = describeUnit(context.unitOf(pair.from) ?? { path: pair.from });
  const to = describeUnit(context.unitOf(pair.to) ?? { path: pair.to });
  return `${from} -> ${to} by ${pair.kinds.join(", ")}`;
}
