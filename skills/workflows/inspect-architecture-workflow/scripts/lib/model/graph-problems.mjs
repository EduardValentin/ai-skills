import { compileGlob, matchesAny } from "../glob.mjs";
import { shellWord } from "../text.mjs";
import { relativeToComponent } from "./classify.mjs";
import { ANY_DESTINATION } from "./defaults.mjs";

const RING_PREFIX = "ring:";

function modulePaths(graph) {
  return graph.units.map((unit) => unit.path);
}

function unmatchedPairs(model, paths) {
  return model.components.flatMap((component) => {
    const relatives = paths
      .filter((path) => matchesAny(path, component.paths))
      .map((path) => relativeToComponent(component, path));
    return component.classify
      .filter((pair) => !relatives.some((relative) => compileGlob(pair.pattern).test(relative)))
      .map((pair) => ({ component: component.name, pattern: pair.pattern, empty: relatives.length === 0 }));
  });
}

function unmatchedPairProblem({ component, pattern }) {
  return (
    `component "${component}": classification pattern "${pattern}" matches no module. ` +
    `Remove it with arch model unclassify ${component} "${pattern}" or correct the pattern.`
  );
}

function unmatchedPairWarning({ component, pattern }) {
  return (
    `component "${component}": classification pattern "${pattern}" matches no module yet. ` +
    `${component} has no modules, so the pattern is kept; it becomes an error once ${component} has modules.`
  );
}

function missingPortProblems(model, paths) {
  const known = new Set(paths);
  return model.ports
    .filter((port) => !known.has(port.path))
    .map(
      (port) =>
        `port "${port.at}": ${port.path} is not a module the adapter reports. ` +
        `Run arch model remove-port ${port.at} or restore the file.`,
    );
}

function overlapProblems(model, paths) {
  return paths.flatMap((path) => {
    const owners = model.components.filter((component) => matchesAny(path, component.paths));
    if (owners.length < 2) return [];
    const names = owners.map((component) => component.name).join(", ");
    return [
      `module ${path} is matched by the paths of several components: ${names}. ` +
        "Narrow the path globs of one component so each module has one owner.",
    ];
  });
}

const EXTERNAL_PREFIX = "external:";

function isPathEnd(model, end) {
  const isComponent = model.components.some((component) => component.name === end);
  return !isComponent && !end.startsWith(RING_PREFIX) && !end.startsWith(EXTERNAL_PREFIX);
}

function unknownExternalProblems(model, graph) {
  const known = new Set((graph.externals ?? []).map((external) => `${EXTERNAL_PREFIX}${external.name}`));
  return model.exceptions
    .filter((entry) => entry.to.startsWith(EXTERNAL_PREFIX) && !known.has(entry.to))
    .map(
      (entry) =>
        `exceptions ${entry.from} -> ${entry.to}: the adapter reports no such external. ` +
        `Run arch model remove-exception ${shellWord(entry.from)} ${shellWord(entry.to)}, or correct the name.`,
    );
}

const REMOVAL_COMMAND = { forbidden: "remove-forbidden-edge", exceptions: "remove-exception" };

function edgeEndProblem(section, entry, end) {
  return (
    `${section} ${entry.from} -> ${entry.to}: "${end}" is not a component, a ring, or the exact path of a module. ` +
    "Ends are matched exactly, never as globs. " +
    `Run arch model ${REMOVAL_COMMAND[section]} ${shellWord(entry.from)} ${shellWord(entry.to)}, ` +
    "then add it again with a component name, ring:<ring>, or the exact path of a module."
  );
}

function unitOfEnd(end) {
  return end.split("#")[0];
}

function edgeEndProblems(model, paths) {
  const known = new Set(paths);
  const entries = [
    ...model.forbidden.map((entry) => ({ section: "forbidden", entry })),
    ...model.exceptions.map((entry) => ({ section: "exceptions", entry })),
  ];
  return entries.flatMap(({ section, entry }) =>
    [entry.from, entry.to]
      .filter((end) => end !== ANY_DESTINATION)
      .filter((end) => isPathEnd(model, end) && !known.has(unitOfEnd(end)))
      .map((end) => edgeEndProblem(section, entry, end)),
  );
}

export function graphProblems(model, graph) {
  const paths = modulePaths(graph);
  const unmatched = unmatchedPairs(model, paths);
  return {
    problems: [
      ...unmatched.filter((pair) => !pair.empty).map(unmatchedPairProblem),
      ...missingPortProblems(model, paths),
      ...overlapProblems(model, paths),
      ...edgeEndProblems(model, paths),
      ...unknownExternalProblems(model, graph),
    ],
    warnings: unmatched.filter((pair) => pair.empty).map(unmatchedPairWarning),
  };
}
