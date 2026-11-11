import { matchesAny } from "../glob.mjs";
import { relativeToComponent } from "../model/classify.mjs";
import { publishingComponents } from "./context.mjs";
import { endMatches, subjectOf } from "./exceptions.mjs";
import { componentRow, unitEdgeRow } from "./rows.mjs";
import { edgePairs, edgeTarget } from "./targets.mjs";

const GROUP = "enforcement-and-organization";
const NO_ENFORCEMENT = "none";

const CORRECTIONS = {
  enforcement: (name) =>
    `Enforce the boundary of ${name} with the compiler or the build, then record how in its enforcement field`,
  deepImport: (from, component, globs) =>
    `Import through the published surface of ${component} (${globs}) instead of from ${from}, ` +
    "or publish the module on purpose by adding it to published",
  forbidden: (from, to) => `Remove the dependency of ${from} on ${to}, and make the edge uncompilable`,
  unconsumed: (symbol, component) =>
    `Stop publishing ${symbol}, or add the consumer that needs it; ${component} publishes only what is used`,
};

function componentNamed(context, name) {
  return context.model.components.find((component) => component.name === name) ?? null;
}

function incomingComponents(context, name) {
  return context.graph.componentEdges.filter((edge) => edge.to === name).map((edge) => edge.from);
}

function unenforcedComponent(context) {
  return context.model.components
    .filter((component) => component.enforcement === NO_ENFORCEMENT)
    .flatMap((component) => {
      const dependents = incomingComponents(context, component.name);
      if (dependents.length === 0) return [];
      return [
        componentRow(
          component.name,
          `${component.name} has no enforcement and ${dependents.join(", ")} depend on it`,
          CORRECTIONS.enforcement(component.name),
        ),
      ];
    });
}

function isOutsidePublishedSurface(context, path) {
  const unit = context.unitOf(path);
  const component = unit?.component ? componentNamed(context, unit.component) : null;
  if (!component || component.published.length === 0) return false;
  return !matchesAny(relativeToComponent(component, path), component.published);
}

function crossesComponents(context, pair) {
  const from = context.componentOf(pair.from);
  const to = context.componentOf(pair.to);
  return from !== null && to !== null && from !== to;
}

function deepImport(context) {
  return edgePairs(context.graph)
    .filter((pair) => crossesComponents(context, pair) && isOutsidePublishedSurface(context, pair.to))
    .map((pair) => {
      const component = componentNamed(context, context.componentOf(pair.to));
      return unitEdgeRow({
        ...pair,
        evidence:
          `${pair.from} reaches ${pair.to} in ${component.name}, ` +
          `outside its published surface ${component.published.join(", ")}`,
        correction: CORRECTIONS.deepImport(pair.to, component.name, component.published.join(", ")),
      });
    });
}

function forbiddenEntryFor(context, pair) {
  const from = subjectOf("unit", pair.from, context);
  const to = subjectOf("unit", pair.to, context);
  return context.model.forbidden.find((entry) => endMatches(entry.from, from) && endMatches(entry.to, to));
}

function forbiddenEdgePresent(context) {
  return edgePairs(context.graph).flatMap((pair) => {
    const entry = forbiddenEntryFor(context, pair);
    if (!entry) return [];
    return [
      unitEdgeRow({
        ...pair,
        evidence:
          `${edgeTarget(pair.from, pair.to)} matches the forbidden edge ${entry.from} -> ${entry.to}: ` +
          entry.reason,
        correction: CORRECTIONS.forbidden(pair.from, pair.to),
      }),
    ];
  });
}

function outsideEdgesInto(context, name) {
  return context.graph.edges.filter(
    (edge) => context.componentOf(edge.to) === name && context.componentOf(edge.from) !== name,
  );
}

function publishedUnits(context, component) {
  return context.graph.units
    .filter((unit) => unit.component === component.name && unit.kind !== "barrel")
    .filter((unit) => matchesAny(relativeToComponent(component, unit.path), component.published));
}

function symbolsUsedOutside(context, name) {
  const edges = outsideEdgesInto(context, name).filter((edge) => edge.kind !== "constructs");
  if (edges.some((edge) => !edge.symbols)) return null;
  return edges.flatMap((edge) => edge.symbols.map((symbol) => ({ symbol, via: context.unitOf(edge.to) })));
}

function isConsumed(used, unit, symbol) {
  return used.some((entry) => entry.symbol === symbol && (entry.via === unit || entry.via?.kind === "barrel"));
}

function unconsumedExport(context) {
  return publishingComponents(context).flatMap((component) => {
    const used = symbolsUsedOutside(context, component.name);
    if (used === null) return [];
    return publishedUnits(context, component).flatMap((unit) =>
      [...new Set(unit.signatures.map((signature) => signature.symbol))]
        .filter((symbol) => !isConsumed(used, unit, symbol))
        .map((symbol) => ({
          target: `${unit.path}#${symbol}`,
          evidence: `${symbol} is published by ${component.name} and no unit outside it imports it`,
          correction: CORRECTIONS.unconsumed(symbol, component.name),
          units: [unit.path],
          components: [component.name],
          edge: null,
        })),
    );
  });
}

function unconsumedExportUndecided(context) {
  return publishingComponents(context)
    .filter((component) => symbolsUsedOutside(context, component.name) === null)
    .map((component) => ({
      target: component.name,
      reason:
        `edges into ${component.name} from outside it name no imported symbols, so its unused exports are unknown. ` +
        "Make the adapter report symbols on every edge.",
    }));
}

export const ENFORCEMENT_AND_ORGANIZATION_CHECKS = [
  {
    id: "unenforced-component",
    rules: ["R38"],
    group: GROUP,
    defect: "boundary-not-enforced",
    severity: "major",
    facts: [],
    needsBase: false,
    run: unenforcedComponent,
  },
  {
    id: "deep-import",
    rules: ["R38"],
    group: GROUP,
    defect: "deep-import",
    severity: "major",
    facts: [],
    needsBase: false,
    run: deepImport,
  },
  {
    id: "forbidden-edge-present",
    rules: ["R39"],
    group: GROUP,
    defect: "forbidden-edge",
    severity: "major",
    facts: [],
    needsBase: false,
    run: forbiddenEdgePresent,
  },
  {
    id: "unconsumed-export",
    rules: ["R38"],
    group: GROUP,
    defect: "published-without-consumer",
    severity: "major",
    facts: ["signatures", "symbolImports"],
    needsBase: false,
    applies: (context) => publishingComponents(context).length > 0,
    run: unconsumedExport,
    undecided: unconsumedExportUndecided,
  },
];
