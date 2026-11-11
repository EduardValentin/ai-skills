import { compileGlob, matchesAny } from "../glob.mjs";
import { relativeToComponent } from "./classify.mjs";

const RING_PREFIX = "ring:";

function modulePaths(graph) {
  return graph.units.map((unit) => unit.path);
}

function unmatchedPairProblems(model, paths) {
  return model.components.flatMap((component) => {
    const relatives = paths
      .filter((path) => matchesAny(path, component.paths))
      .map((path) => relativeToComponent(component, path));
    return component.classify
      .filter((pair) => !relatives.some((relative) => compileGlob(pair.pattern).test(relative)))
      .map(
        (pair) =>
          `component "${component.name}": classification pattern "${pair.pattern}" matches no module. ` +
          `Remove it with arch model unclassify ${component.name} "${pair.pattern}" or correct the pattern.`,
      );
  });
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
        `Run arch model remove-exception ${entry.from} ${entry.to}, or correct the name.`,
    );
}

const REMOVAL_COMMAND = { forbidden: "remove-forbidden-edge", exceptions: "remove-exception" };

function edgeEndProblem(section, entry, end) {
  return (
    `${section} ${entry.from} -> ${entry.to}: "${end}" is not a component, a ring, or a path matching a module. ` +
    `Run arch model ${REMOVAL_COMMAND[section]} ${entry.from} ${entry.to}, ` +
    "then add it again with a component name, ring:<ring>, or an existing path."
  );
}

function edgeEndProblems(model, paths) {
  const entries = [
    ...model.forbidden.map((entry) => ({ section: "forbidden", entry })),
    ...model.exceptions.map((entry) => ({ section: "exceptions", entry })),
  ];
  return entries.flatMap(({ section, entry }) =>
    [entry.from, entry.to]
      .filter((end) => isPathEnd(model, end) && !paths.some((path) => compileGlob(end).test(path)))
      .map((end) => edgeEndProblem(section, entry, end)),
  );
}

export function graphProblems(model, graph) {
  const paths = modulePaths(graph);
  return [
    ...unmatchedPairProblems(model, paths),
    ...missingPortProblems(model, paths),
    ...overlapProblems(model, paths),
    ...edgeEndProblems(model, paths),
    ...unknownExternalProblems(model, graph),
  ];
}
