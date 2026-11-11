export const DEFAULT_RINGS = ["entities", "use-cases", "adapters", "frameworks"];

export const ROLES = ["policy", "detail", "wiring", "neutral"];

export const DEFAULT_KINDS = {
  entity: { role: "policy", ring: "entities" },
  "use-case": { role: "policy", ring: "use-cases" },
  port: { role: "policy", ring: "entities" },
  "boundary-data": { role: "policy", ring: "use-cases" },
  controller: { role: "detail", ring: "adapters" },
  presenter: { role: "detail", ring: "adapters" },
  gateway: { role: "detail", ring: "adapters" },
  adapter: { role: "detail", ring: "adapters" },
  "entry-point": { role: "detail", ring: "frameworks" },
  ui: { role: "detail", ring: "frameworks" },
  "composition-root": { role: "wiring", ring: "frameworks" },
  test: { role: "wiring", ring: "adapters" },
  config: { role: "wiring", ring: "frameworks" },
  barrel: { role: "neutral", ring: null },
  mixed: { role: "neutral", ring: null },
};

export const DEFAULT_THRESHOLDS = {
  interfaceUseShare: 0.5,
  componentUseShare: 0.25,
  detailReasonChanges: 2,
  historyWindow: "6 months",
  escalationFanIn: 3,
  painMaxInstability: 0.2,
  painMaxAbstractness: 0.2,
  painMinFanIn: 3,
  uselessMinAbstractness: 0.8,
  uselessMinInstability: 0.8,
  distanceDeviations: 1,
  distanceJump: 0.1,
  distanceMinComponents: 8,
  planFixRounds: 2,
};

export const THRESHOLD_DESCRIPTIONS = {
  interfaceUseShare: "Share of an interface's members a consumer must use for the interface to fit that consumer.",
  componentUseShare: "Share of a component's exports a consumer must use for the dependency to count as real use.",
  detailReasonChanges: "Count of recent changes for a detail reason that marks a unit as changing for that reason.",
  historyWindow: "How far back change history reaches, written as a date expression such as 6 months.",
  escalationFanIn: "Count of dependents that makes a unit widely depended on, which escalates findings about it.",
  painMaxInstability: "Highest instability of a unit that still sits in the zone of pain.",
  painMaxAbstractness: "Highest abstractness of a unit that still sits in the zone of pain.",
  painMinFanIn: "Count of dependents a stable, concrete unit needs before it is reported in the zone of pain.",
  uselessMinAbstractness: "Lowest abstractness of a unit that sits in the zone of uselessness.",
  uselessMinInstability: "Lowest instability of a unit that sits in the zone of uselessness.",
  distanceDeviations: "Standard deviations above the mean distance to the main sequence that mark an outlier.",
  distanceJump: "Increase in a component's distance to the main sequence between base and head that is reported.",
  distanceMinComponents: "Fewest components for which distance from the balanced line is compared across the graph.",
  planFixRounds: "Rounds of plan fixes before the remaining findings go to the user.",
};

export const RULE_COUNT = 41;

export const RULE_STATUSES = ["enforced", "advisory", "off"];

const ADVISORY_IN_BOTH = ["R3", "R15", "R23", "R24", "R26", "R29", "R33", "R37"];
const ADVISORY_IN_LEGACY = ["R6", "R19", "R21", "R22"];

function statusesFor(advisoryRules) {
  const statuses = {};
  for (let number = 1; number <= RULE_COUNT; number += 1) {
    const id = `R${number}`;
    statuses[id] = advisoryRules.includes(id) ? "advisory" : "enforced";
  }
  return statuses;
}

export const DEFAULT_STATUSES = {
  greenfield: statusesFor(ADVISORY_IN_BOTH),
  legacy: statusesFor([...ADVISORY_IN_BOTH, ...ADVISORY_IN_LEGACY]),
};

export const ANY_DESTINATION = "*";
