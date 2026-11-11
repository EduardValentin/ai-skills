import { DEFAULT_KINDS } from "../model/defaults.mjs";

const POLICY = ["entity", "use-case", "port", "boundary-data"];
const BEHAVIOR = ["entity", "use-case", "controller", "presenter", "gateway", "adapter", "ui", "entry-point", "mixed"];
const DEVICE_FACING = ["controller", "presenter", "gateway", "adapter", "ui", "entry-point", "mixed"];
const PRODUCTION = Object.keys(DEFAULT_KINDS).filter((kind) => kind !== "test" && kind !== "barrel");
const ANY_UNIT = Object.keys(DEFAULT_KINDS);

const CROSS_CUTTING = [
  {
    id: "structure-consequence-unstated",
    rules: ["R1"],
    group: "cross-cutting",
    severity: "minor",
    defect: "structure-consequence-unstated",
    targets: ["plan"],
    condition:
      "A plan states the behavior it delivers but not how it keeps or lowers the cost of the next known change.",
  },
  {
    id: "shape-mismatch-hidden",
    rules: ["R2"],
    group: "cross-cutting",
    severity: "major",
    defect: "shape-mismatch-hidden",
    targets: ANY_UNIT,
    condition:
      "A request that does not fit the structure is forced in behind a flag or mode parameter, " +
      "a special case keyed on the caller, or a near-copy, and the mismatch is not named.",
  },
];

const DEPENDENCY_DIRECTION = [
  {
    id: "port-in-shared-bucket",
    rules: ["R5"],
    group: "dependency-direction",
    severity: "blocker",
    defect: "port-on-wrong-side",
    targets: ["port"],
    condition:
      "A port sits in a shared interfaces bucket with no consumer beside it, instead of beside the policy " +
      "that calls it.",
  },
  {
    id: "use-case-names-its-details",
    rules: ["R6"],
    group: "dependency-direction",
    severity: "blocker",
    defect: "policy-depends-on-detail",
    targets: ["use-case"],
    condition:
      "A use case reaches its presenter or its store through their implementations instead of an output boundary " +
      "and a storage port declared in the use-case module.",
  },
  {
    id: "mixed-unit-constructed-outside-root",
    rules: ["R7"],
    group: "dependency-direction",
    severity: "blocker",
    defect: "detail-constructed-outside-root",
    targets: [...BEHAVIOR, "port", "boundary-data"],
    condition:
      "A unit that is not a composition root, config, or test constructs a mixed unit that holds a concrete detail.",
  },
  {
    id: "policy-changes-for-detail-reason",
    rules: ["R4"],
    group: "dependency-direction",
    severity: "blocker",
    defect: "policy-changes-for-detail-reason",
    targets: POLICY,
    condition:
      "A policy unit changed for a device, format, transport, or vendor reason in at least {detailReasonChanges} " +
      "changes within {historyWindow}.",
  },
  {
    id: "abstraction-without-reason",
    rules: ["R8"],
    group: "dependency-direction",
    severity: "minor",
    defect: "unjustified-abstraction",
    targets: ["port", "entity", "use-case", "mixed"],
    condition:
      "An abstraction has a single consumer and a single implementer, and names neither a deferred decision " +
      "nor a ripple it forbids.",
  },
  {
    id: "tests-change-without-behavior-change",
    rules: ["R9"],
    group: "dependency-direction",
    severity: "major",
    defect: "tests-coupled-to-structure",
    targets: ["test-suite"],
    condition: "A change forces edits to tests whose asserted behavior did not change.",
  },
];

const REASONS_TO_CHANGE = [
  {
    id: "unit-serves-several-actors",
    rules: ["R10"],
    group: "reasons-to-change",
    severity: "major",
    defect: "several-actors-in-one-unit",
    targets: BEHAVIOR,
    condition: "A unit serves more than one actor and holds behavior for each of them.",
  },
  {
    id: "helper-shared-across-actors",
    rules: ["R11"],
    group: "reasons-to-change",
    severity: "major",
    defect: "helper-shared-across-actors",
    targets: BEHAVIOR,
    condition: "A behavior-bearing unit is imported by units that serve different actors.",
  },
  {
    id: "consumer-uses-few-interface-members",
    rules: ["R13"],
    group: "reasons-to-change",
    severity: "major",
    defect: "interface-wider-than-consumer",
    targets: [...BEHAVIOR, "port"],
    condition: "A consumer uses less than {interfaceUseShare} of the members of the interface it depends on.",
  },
  {
    id: "variant-added-by-conditional",
    rules: ["R12"],
    group: "reasons-to-change",
    severity: "major",
    defect: "variant-added-by-conditional",
    targets: BEHAVIOR,
    condition: "A variant is added through a conditional ladder over kinds inside a stable unit.",
  },
  {
    id: "subtype-never-substituted",
    rules: ["R12"],
    group: "reasons-to-change",
    severity: "major",
    defect: "subtype-never-substituted",
    targets: BEHAVIOR,
    condition: "A subtype is never used where its supertype is expected.",
  },
  {
    id: "mutable-internals-exposed",
    rules: ["R14"],
    group: "reasons-to-change",
    severity: "major",
    defect: "mutable-internals-exposed",
    targets: BEHAVIOR,
    condition: "A behavior-bearing unit exposes mutable internal data to outside code.",
  },
  {
    id: "function-not-understood-alone",
    rules: ["R15"],
    group: "reasons-to-change",
    severity: "minor",
    defect: "function-not-understood-alone",
    targets: BEHAVIOR,
    condition:
      "A function's path is decided by flag-driven loops, exceptions used as control flow, or non-local state.",
  },
  {
    id: "shared-state-mutated-outside-edges",
    rules: ["R16"],
    group: "reasons-to-change",
    severity: "major",
    defect: "shared-state-mutated-outside-edges",
    targets: BEHAVIOR,
    condition: "Shared state is mutated outside the units named as the mutating ones.",
  },
];

const BUSINESS_RULE_PLACEMENT = [
  {
    id: "entity-carries-framework-traits",
    rules: ["R17"],
    group: "business-rule-placement",
    severity: "blocker",
    defect: "policy-depends-on-detail",
    targets: ["entity"],
    condition: "An entity carries framework annotations, a framework base class, or serialization methods.",
  },
  {
    id: "entity-holds-system-concerns",
    rules: ["R17"],
    group: "business-rule-placement",
    severity: "minor",
    defect: "entity-holds-system-concerns",
    targets: ["entity"],
    condition: "An entity has fields no rule function reads, or functions only the system needs.",
  },
  {
    id: "critical-rule-in-use-case",
    rules: ["R18"],
    group: "business-rule-placement",
    severity: "blocker",
    defect: "critical-rule-outside-entity",
    targets: ["use-case"],
    condition: "A use case contains business arithmetic or a decision a clerk would make without the system.",
  },
  {
    id: "entity-hook-for-use-case",
    rules: ["R18"],
    group: "business-rule-placement",
    severity: "blocker",
    defect: "entity-depends-outward",
    targets: ["entity"],
    condition: "An entity exposes a hook or callback that exists for a use case.",
  },
  {
    id: "boundary-data-carries-detail-shape",
    rules: ["R19"],
    group: "business-rule-placement",
    severity: "blocker",
    defect: "boundary-data-not-plain",
    targets: ["boundary-data"],
    condition:
      "A request or response model extends a framework type, wraps a row or envelope, carries channel fields, " +
      "or has an entity-typed field.",
  },
  {
    id: "entity-crosses-use-case-boundary",
    rules: ["R19"],
    group: "business-rule-placement",
    severity: "blocker",
    defect: "entity-crosses-boundary",
    targets: ["use-case", "port"],
    condition: "A use case accepts or returns an entity across its input or output boundary.",
  },
  {
    id: "adapter-branches-on-shape",
    rules: ["R19"],
    group: "business-rule-placement",
    severity: "blocker",
    defect: "adapter-branches-on-shape",
    targets: ["adapter", "presenter", "controller", "gateway", "mixed"],
    condition: "An adapter or presenter branches on which shape of data it received.",
  },
  {
    id: "business-rules-outside-policy",
    rules: ["R17", "R18"],
    group: "business-rule-placement",
    severity: "blocker",
    defect: "business-rules-outside-policy",
    targets: ["component", ...DEVICE_FACING],
    condition:
      "The code has business rules but no unit is classified entity or use case, so the rules live in adapters " +
      "or framework glue.",
  },
];

const HUMBLE_OBJECTS = [
  {
    id: "device-unit-holds-logic",
    rules: ["R20"],
    group: "humble-objects",
    severity: "major",
    defect: "humble-unit-holds-logic",
    targets: DEVICE_FACING,
    condition:
      "A unit talks to a device and also holds conditionals, calculations, formatting, or lookups, " +
      "with no testable counterpart.",
  },
  {
    id: "handler-holds-business-logic",
    rules: ["R20"],
    group: "humble-objects",
    severity: "major",
    defect: "humble-unit-holds-logic",
    targets: ["controller", "adapter", "gateway", "entry-point", "mixed"],
    condition: "A handler or sender validates business rules, branches on domain state, or formats for display.",
  },
  {
    id: "view-makes-decisions",
    rules: ["R21"],
    group: "humble-objects",
    severity: "major",
    defect: "view-makes-decisions",
    targets: ["ui", "mixed"],
    condition: "A view makes a decision beyond mapping a flag or enumeration to its appearance.",
  },
  {
    id: "view-model-not-formatted",
    rules: ["R21"],
    group: "humble-objects",
    severity: "major",
    defect: "view-model-not-formatted",
    targets: ["presenter", "boundary-data", "ui", "mixed"],
    condition: "A view model holds a date, a money type, an unformatted number, a domain object, or a method.",
  },
  {
    id: "storage-port-exposes-queries",
    rules: ["R22"],
    group: "humble-objects",
    severity: "blocker",
    defect: "storage-port-exposes-queries",
    targets: ["port", "gateway"],
    condition: "A storage port exposes a raw query, a generic find by specification, or a query builder.",
  },
  {
    id: "query-inside-policy",
    rules: ["R22"],
    group: "humble-objects",
    severity: "blocker",
    defect: "policy-depends-on-detail",
    targets: ["use-case", "entity", "mixed"],
    condition: "A query string, query builder, session, or ORM type appears inside a use case or entity.",
  },
  {
    id: "orm-class-as-domain-model",
    rules: ["R22"],
    group: "humble-objects",
    severity: "blocker",
    defect: "policy-depends-on-detail",
    targets: ["entity", "gateway", "mixed"],
    condition: "An ORM-annotated class is used as the domain model.",
  },
  {
    id: "port-named-for-detail",
    rules: ["R22"],
    group: "humble-objects",
    severity: "minor",
    defect: "port-named-for-detail",
    targets: ["port"],
    condition: "A port the domain owns carries a storage, transport, or vendor word in its name.",
  },
];

const DEFERRAL_AND_BOUNDARIES = [
  {
    id: "detail-reached-without-port",
    rules: ["R23"],
    group: "deferral-and-boundaries",
    severity: "major",
    defect: "policy-depends-on-detail",
    targets: [...POLICY, "mixed"],
    condition: "A framework, store, or vendor is reached with no port between it and the policy.",
  },
  {
    id: "port-without-test-double",
    rules: ["R23"],
    group: "deferral-and-boundaries",
    severity: "major",
    defect: "rules-need-real-detail",
    targets: ["port", "test-suite"],
    condition: "A port has no in-memory or stub implementation while the rule tests need the real detail.",
  },
  {
    id: "tiers-without-reason",
    rules: ["R24"],
    group: "deferral-and-boundaries",
    severity: "major",
    defect: "tiers-without-reason",
    targets: ["component", "plan"],
    condition:
      "More than one deployable or a service catalog exists with no recorded team or deployment reason, " +
      "and the simplest change edits more than one of them.",
  },
  {
    id: "boundary-defers-nothing",
    rules: ["R25"],
    group: "deferral-and-boundaries",
    severity: "minor",
    defect: "unjustified-abstraction",
    targets: ["port", "component"],
    condition: "A boundary defers no decision and the code on both sides of it changes together for the same reason.",
  },
  {
    id: "unit-mixes-change-cadences",
    rules: ["R25"],
    group: "deferral-and-boundaries",
    severity: "major",
    defect: "missing-boundary",
    targets: BEHAVIOR,
    condition: "A unit changes for unrelated reasons at unrelated cadences, so an internal boundary is missing.",
  },
  {
    id: "rules-need-io",
    rules: ["R26"],
    group: "deferral-and-boundaries",
    severity: "major",
    defect: "rules-need-real-detail",
    targets: ["use-case", "entity", "test-suite"],
    condition: "The business rules cannot be exercised without a UI, a store, or a server in the process.",
  },
  {
    id: "plan-sequences-io-first",
    rules: ["R26"],
    group: "deferral-and-boundaries",
    severity: "major",
    defect: "plan-sequences-io-first",
    targets: ["plan"],
    condition: "The plan or brief sequences framework, schema, or screen work before the rules.",
  },
];

const COMPONENTS_AND_STABILITY = [
  {
    id: "zone-of-pain-changing",
    rules: ["R31", "R32"],
    group: "components-and-stability",
    severity: "major",
    defect: "zone-of-pain",
    targets: ["component"],
    condition:
      "In an audit, a component in the zone of pain which at least {painMinChanges} commits touched within " +
      "{historyWindow}, where no change under review touches it for the check to decide.",
  },
  {
    id: "abstractions-without-implementor",
    rules: ["R31", "R32"],
    group: "components-and-stability",
    severity: "minor",
    defect: "unused-abstraction",
    targets: ["component", "port"],
    condition:
      "A component has abstract types with no implementor, or outside consumers that use none of its abstract types.",
  },
  {
    id: "change-history-spans-groups",
    rules: ["R27"],
    group: "components-and-stability",
    severity: "major",
    defect: "change-spans-groups",
    targets: ["component"],
    condition:
      "In an audit, changes within {historyWindow} touched this component together with a component " +
      "it shares no recorded cohesion group with.",
  },
  {
    id: "change-history-without-groups",
    rules: ["R28"],
    group: "components-and-stability",
    severity: "minor",
    defect: "no-cohesion-groups",
    targets: ["component"],
    condition:
      "In an audit, the model records no cohesion groups and changes within {historyWindow} " +
      "touched more than one component together.",
  },
  {
    id: "thin-use-of-unpublished-component",
    rules: ["R27"],
    group: "components-and-stability",
    severity: "minor",
    defect: "thin-component-use",
    targets: ["component"],
    condition:
      "A consumer uses less than {componentUseShare} of what a component with no declared published surface exports.",
  },
  {
    id: "cohesion-position-unstated",
    rules: ["R28"],
    group: "components-and-stability",
    severity: "minor",
    defect: "cohesion-position-unstated",
    targets: ["component"],
    condition:
      "A component's cohesion position and its cost are not stated, and its boundaries were not revisited " +
      "while its change patterns shifted.",
  },
  {
    id: "unversioned-dependency-across-releases",
    rules: ["R33"],
    group: "components-and-stability",
    severity: "major",
    defect: "unversioned-dependency-across-releases",
    targets: ["component"],
    condition: "A component is consumed by path with no version although it and its consumer release separately.",
  },
  {
    id: "component-map-fixed-upfront",
    rules: ["R29"],
    group: "components-and-stability",
    severity: "minor",
    defect: "component-map-fixed-upfront",
    targets: ["plan"],
    condition: "A greenfield plan fixes the full component map before code exists.",
  },
];

const TESTS = [
  {
    id: "test-power-behind-flag",
    rules: ["R34"],
    group: "tests",
    severity: "blocker",
    defect: "production-depends-on-test",
    targets: PRODUCTION,
    condition: "Production code holds a test-only power behind a runtime flag or an environment check.",
  },
  {
    id: "test-code-in-production-deployable",
    rules: ["R34"],
    group: "tests",
    severity: "blocker",
    defect: "production-depends-on-test",
    targets: ["entry-point", "composition-root", "config", "test-suite"],
    condition: "Test-only routes or fixtures are included in the production deployable.",
  },
  {
    id: "security-bypass-untested",
    rules: ["R34"],
    group: "tests",
    severity: "blocker",
    defect: "security-bypass-untested",
    targets: ["test-suite"],
    condition: "Tests use a security bypass and no separate tests cover authorization.",
  },
  {
    id: "rule-tested-through-volatile-surface",
    rules: ["R35"],
    group: "tests",
    severity: "blocker",
    defect: "rule-tested-through-volatile-surface",
    targets: ["test-suite"],
    condition: "A business-rule assertion is reached through a screen, navigation, login, or vendor path.",
  },
  {
    id: "no-testing-api",
    rules: ["R35"],
    group: "tests",
    severity: "blocker",
    defect: "no-testing-api",
    targets: ["test-suite", "use-case"],
    condition: "Business rules exist and tests have no testing API or direct use-case boundary to reach them.",
  },
  {
    id: "tests-mirror-production",
    rules: ["R36"],
    group: "tests",
    severity: "major",
    defect: "tests-coupled-to-structure",
    targets: ["test-suite"],
    condition:
      "The test tree mirrors the production tree class for class, and internal refactors within {historyWindow} " +
      "changed tests.",
  },
  {
    id: "tests-falsify-nothing",
    rules: ["R37"],
    group: "tests",
    severity: "minor",
    defect: "tests-falsify-nothing",
    targets: ["test-suite"],
    condition:
      "Tests assert nothing a specific defect would falsify, or a report claims correctness because the tests pass.",
  },
  {
    id: "plan-names-no-falsifying-tests",
    rules: ["R37"],
    group: "tests",
    severity: "minor",
    defect: "tests-falsify-nothing",
    targets: ["plan"],
    condition: "The plan does not name, per behavior, the defect its test would catch and the surface it runs through.",
  },
];

const ENFORCEMENT_AND_ORGANIZATION = [
  {
    id: "concrete-published-beside-interface",
    rules: ["R38"],
    group: "enforcement-and-organization",
    severity: "major",
    defect: "published-without-consumer",
    targets: ["component", "adapter", "gateway"],
    condition: "A component publishes a concrete implementation although outside code consumes only its interface.",
  },
  {
    id: "unconsumed-export-of-unpublished-component",
    rules: ["R38"],
    group: "enforcement-and-organization",
    severity: "major",
    defect: "published-without-consumer",
    targets: ["component"],
    condition: "A component with no declared published surface exports a symbol that no unit outside it consumes.",
  },
  {
    id: "forbidden-edge-unenforced",
    rules: ["R39"],
    group: "enforcement-and-organization",
    severity: "major",
    defect: "forbidden-edge-unenforced",
    targets: ["component"],
    condition: "A recorded forbidden edge is absent from the code, but nothing in the build would stop it.",
  },
  {
    id: "edge-skips-ring",
    rules: ["R39"],
    group: "enforcement-and-organization",
    severity: "major",
    defect: "edge-skips-ring",
    targets: [...BEHAVIOR, "port", "boundary-data"],
    condition:
      "A unit depends on a unit more than one ring inward with no recorded exception, " +
      "and the skip is not a detail implementing or translating to policy types.",
  },
  {
    id: "structure-named-by-technology",
    rules: ["R40"],
    group: "enforcement-and-organization",
    severity: "major",
    defect: "structure-named-by-technology",
    targets: ["component", "use-case"],
    condition:
      "The top-level structure is named by technology, such as web, service, or data, " +
      "so a use case's code is spread across those technical folders.",
  },
  {
    id: "delivery-inside-domain-component",
    rules: ["R40"],
    group: "enforcement-and-organization",
    severity: "major",
    defect: "delivery-inside-domain-component",
    targets: ["controller", "presenter", "ui", "entry-point", "gateway", "component"],
    condition:
      "A delivery-mechanism class sits inside a domain component, or persistence is reachable from delivery code.",
  },
  {
    id: "edge-outside-intended-graph",
    rules: ["R41"],
    group: "enforcement-and-organization",
    severity: "major",
    defect: "edge-outside-intended-graph",
    targets: ["component"],
    condition: "An edge present in the code is absent from the intended component graph.",
  },
  {
    id: "shared-shape-without-owner",
    rules: ["R41"],
    group: "enforcement-and-organization",
    severity: "major",
    defect: "shared-shape-without-owner",
    targets: ["component", "gateway", "boundary-data"],
    condition: "Components share a table, document, or wire shape that no component owns.",
  },
];

export const JUDGMENTS = [
  ...CROSS_CUTTING,
  ...DEPENDENCY_DIRECTION,
  ...REASONS_TO_CHANGE,
  ...BUSINESS_RULE_PLACEMENT,
  ...HUMBLE_OBJECTS,
  ...DEFERRAL_AND_BOUNDARIES,
  ...COMPONENTS_AND_STABILITY,
  ...TESTS,
  ...ENFORCEMENT_AND_ORGANIZATION,
];
