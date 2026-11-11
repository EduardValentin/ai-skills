import { touchesBarrel } from "./context.mjs";
import { describedPair, unitEdgeRow } from "./rows.mjs";
import { edgePairs } from "./targets.mjs";

const GROUP = "tests";
const TEST_KIND = "test";

function productionImportsTest(context) {
  return edgePairs(context.graph)
    .filter((pair) => !touchesBarrel(context, pair.from, pair.to))
    .filter((pair) => {
      const fromKind = context.unitOf(pair.from)?.kind;
      return fromKind && fromKind !== TEST_KIND && context.unitOf(pair.to)?.kind === TEST_KIND;
    })
    .map((pair) =>
      unitEdgeRow({
        ...pair,
        evidence: `production unit depends on a test unit: ${describedPair(context, pair)}`,
        correction:
          `Move what ${pair.from} needs from ${pair.to} into production code, ` +
          "or into a test-only module that nothing ships",
      }),
    );
}

export const TESTS_CHECKS = [
  {
    id: "production-imports-test",
    rules: ["R34"],
    group: GROUP,
    defect: "production-depends-on-test",
    severity: "blocker",
    facts: [],
    needsBase: false,
    run: productionImportsTest,
    consequence: ({ edge }) =>
      `Shipped code depends on ${edge.to}, so a change to the tests can break production and the test code ships.`,
  },
];
