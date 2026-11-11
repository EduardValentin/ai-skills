export function unitsWithoutExports(context, componentNames) {
  return context.graph.units
    .filter((unit) => componentNames.has(unit.component) && unit.kind !== "barrel" && !unit.exports)
    .map((unit) => ({
      target: unit.path,
      reason: `${unit.path} reports no exports although the adapter provides them, so abstractness is unknown. ` +
        "Make the adapter report the exports of every module.",
    }));
}
