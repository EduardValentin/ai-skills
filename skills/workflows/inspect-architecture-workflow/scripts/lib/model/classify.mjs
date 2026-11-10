import { compileGlob, matchesAny } from "../glob.mjs";

function literalDirectory(glob) {
  const literal = glob.split(/[*?{]/)[0];
  return literal.slice(0, literal.lastIndexOf("/") + 1);
}

function findComponent(model, path) {
  return model.components.find((component) => matchesAny(path, component.paths)) ?? null;
}

export function relativeToComponent(component, path) {
  const glob = component.paths.find((candidate) => matchesAny(path, [candidate]));
  return path.slice(literalDirectory(glob).length);
}

function siblingRings(model, component, pair) {
  const rings = component.classify
    .filter((other) => other !== pair)
    .map((other) => other.ring ?? model.kinds[other.kind].ring)
    .filter((ring) => ring !== null && ring !== undefined);
  return [...new Set(rings)];
}

export function resolvePairRing(model, component, pair) {
  if (pair.ring) return pair.ring;
  const kindRing = model.kinds[pair.kind].ring;
  if (kindRing) return kindRing;
  const shared = siblingRings(model, component, pair);
  return shared.length === 1 ? shared[0] : null;
}

function describe(model, component, pair, index) {
  return {
    component: component.name,
    kind: pair.kind,
    ring: resolvePairRing(model, component, pair),
    actors: pair.actors ?? null,
    matched: { component: component.name, index },
  };
}

const UNCLASSIFIED = { component: null, kind: null, ring: null, actors: null, matched: null };

export function createClassifier(model) {
  return (path) => {
    const component = findComponent(model, path);
    if (!component) return { ...UNCLASSIFIED };
    const relative = relativeToComponent(component, path);
    const index = component.classify.findIndex((pair) => compileGlob(pair.pattern).test(relative));
    if (index === -1) return { ...UNCLASSIFIED, component: component.name };
    return describe(model, component, component.classify[index], index);
  };
}
