const ROUNDING = 100;

function round(value) {
  return value === null ? null : Math.round(value * ROUNDING) / ROUNDING;
}

function crossingModules(units, edges, name) {
  const componentOf = new Map(units.map((unit) => [unit.path, unit.component]));
  const importers = new Set();
  const exporters = new Set();
  for (const edge of edges) {
    const fromComponent = componentOf.get(edge.from) ?? null;
    const toComponent = componentOf.get(edge.to) ?? null;
    if (fromComponent === toComponent || fromComponent === null || toComponent === null) continue;
    if (toComponent === name) importers.add(edge.from);
    if (fromComponent === name) exporters.add(edge.from);
  }
  return { fanIn: importers.size, fanOut: exporters.size };
}

function abstractnessOf(inside) {
  const declaring = inside.filter((unit) => unit.kind !== "barrel");
  if (!declaring.every((unit) => unit.exports)) return null;
  const total = declaring.reduce((sum, unit) => sum + unit.exports.abstract + unit.exports.concrete, 0);
  if (total === 0) return null;
  return declaring.reduce((sum, unit) => sum + unit.exports.abstract, 0) / total;
}

function zoneOf({ instability, abstractness, fanIn }, thresholds) {
  if (instability === null || abstractness === null) return null;
  const inPain =
    instability <= thresholds.painMaxInstability &&
    abstractness <= thresholds.painMaxAbstractness &&
    fanIn >= thresholds.painMinFanIn;
  if (inPain) return "pain";
  const useless =
    abstractness >= thresholds.uselessMinAbstractness && instability >= thresholds.uselessMinInstability;
  return useless ? "uselessness" : null;
}

function metricsOf(units, edges, component, thresholds) {
  const inside = units.filter((unit) => unit.component === component.name);
  const { fanIn, fanOut } = crossingModules(units, edges, component.name);
  const instability = fanIn + fanOut === 0 ? null : fanOut / (fanIn + fanOut);
  const abstractness = abstractnessOf(inside);
  const distance = instability === null || abstractness === null ? null : Math.abs(abstractness + instability - 1);
  const zone = zoneOf({ instability, abstractness, fanIn }, thresholds);
  return {
    name: component.name,
    units: inside.length,
    fanIn,
    fanOut,
    instability: round(instability),
    abstractness: round(abstractness),
    distance: round(distance),
    zone,
  };
}

export function componentMetrics(units, edges, components, thresholds) {
  return components.map((component) => metricsOf(units, edges, component, thresholds));
}

const TOLERANCE = 1e-9;

export function distanceOutliers(components, thresholds) {
  if (components.length < thresholds.distanceMinComponents) return [];
  const measured = components.filter((component) => component.distance !== null && component.distance !== undefined);
  if (measured.length === 0) return [];
  const mean = measured.reduce((sum, component) => sum + component.distance, 0) / measured.length;
  const variance = measured.reduce((sum, component) => sum + (component.distance - mean) ** 2, 0) / measured.length;
  const limit = mean + thresholds.distanceDeviations * Math.sqrt(variance);
  return measured
    .filter((component) => component.distance > limit + TOLERANCE)
    .map((component) => ({ name: component.name, distance: component.distance, mean: round(mean) }));
}
