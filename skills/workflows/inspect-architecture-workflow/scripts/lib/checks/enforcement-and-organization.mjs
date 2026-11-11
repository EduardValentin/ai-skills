import { matchesAny } from "../glob.mjs";
import { relativeToComponent } from "../model/classify.mjs";
import { publishingComponents } from "./context.mjs";
import { endMatches, subjectOf } from "./exceptions.mjs";
import { componentRow, unitEdgeRow } from "./rows.mjs";
import { edgePairs, edgeTarget } from "./targets.mjs";

const GROUP = "enforcement-and-organization";
const NOT_ENFORCING = new Set(["none", "review"]);

const CORRECTIONS = {
  enforcement: (name) =>
    `If something already stops code outside ${name} from importing its internals, record that mechanism with ` +
    `arch model set-component ${name} enforcement="<mechanism>"; otherwise add the cheapest enforcement the ` +
    "project has, such as a visibility rule, an export list, or an import rule that fails the build, and record " +
    "it the same way; make it a separate build unit only when none of those is available",
  deepImport: (from, component) =>
    `Import through the published surface of ${component.name} (${component.published.join(", ")}) instead of ` +
    `from ${from}, or publish the module on purpose with arch model set-component ${component.name} ` +
    `published=${[...component.published, relativeToComponent(component, from)].join(",")}`,
  forbidden: (from, to) =>
    `Remove the dependency of ${from} on ${to}, which the model forbids, and make the edge uncompilable`,
  unconsumed: (symbol, component) =>
    `Stop publishing ${symbol} from ${component}: drop it from the published surface, and when that leaves a ` +
    `file out of it, record the narrower surface with arch model set-component ${component} published=<globs>; ` +
    `or delete it if nothing inside ${component} uses it`,
};

const CONSEQUENCES = {
  unenforced: ({ target }) =>
    `Nothing fails when code outside ${target} imports one of its internal modules, so such imports pile up ` +
    `unnoticed and any internal change to ${target} can break code outside it.`,
  deepImport: ({ edge }) =>
    `${edge.from} depends on an internal module of another component, ${edge.to}, so internal changes there ` +
    "break it.",
  forbidden: ({ edge }) =>
    `A change to ${edge.to} reaches ${edge.from}, which the model meant to keep apart from it.`,
  unconsumed: ({ target }) =>
    `${target} must stay stable for consumers that do not exist, which makes changing it harder for no gain.`,
};

function componentNamed(context, name) {
  return context.model.components.find((component) => component.name === name) ?? null;
}

function incomingComponents(context, name) {
  return context.graph.componentEdges.filter((edge) => edge.to === name).map((edge) => edge.from);
}

function unenforcedComponent(context) {
  return context.model.components
    .filter((component) => NOT_ENFORCING.has(component.enforcement))
    .flatMap((component) => {
      const dependents = incomingComponents(context, component.name);
      if (dependents.length === 0) return [];
      return [
        componentRow(
          component.name,
          `${component.name} has enforcement "${component.enforcement}", which the build does not check, ` +
            `and ${dependents.join(", ")} depend on it`,
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
        correction: CORRECTIONS.deepImport(pair.to, component),
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
    consequence: CONSEQUENCES.unenforced,
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
    consequence: CONSEQUENCES.deepImport,
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
    consequence: CONSEQUENCES.forbidden,
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
    consequence: CONSEQUENCES.unconsumed,
    undecided: unconsumedExportUndecided,
  },
];
