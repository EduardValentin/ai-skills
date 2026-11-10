import { COMPONENTS_AND_STABILITY_CHECKS } from "./components-and-stability.mjs";
import { DEPENDENCY_DIRECTION_CHECKS } from "./dependency-direction.mjs";

export { RULE_TITLES } from "./rule-titles.mjs";

export const CHECKS = [...DEPENDENCY_DIRECTION_CHECKS, ...COMPONENTS_AND_STABILITY_CHECKS];
