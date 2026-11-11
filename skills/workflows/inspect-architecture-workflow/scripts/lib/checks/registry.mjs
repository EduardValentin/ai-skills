import { BUSINESS_RULE_PLACEMENT_CHECKS } from "./business-rule-placement.mjs";
import { COMPONENTS_AND_STABILITY_CHECKS } from "./components-and-stability.mjs";
import { DEFERRAL_AND_BOUNDARIES_CHECKS } from "./deferral-and-boundaries.mjs";
import { DEPENDENCY_DIRECTION_CHECKS } from "./dependency-direction.mjs";
import { ENFORCEMENT_AND_ORGANIZATION_CHECKS } from "./enforcement-and-organization.mjs";
import { HUMBLE_OBJECTS_CHECKS } from "./humble-objects.mjs";
import { REASONS_TO_CHANGE_CHECKS } from "./reasons-to-change.mjs";
import { TESTS_CHECKS } from "./tests.mjs";

export { JUDGMENTS } from "./judgments.mjs";
export { RULE_TITLES } from "./rule-titles.mjs";

export const CHECKS = [
  ...DEPENDENCY_DIRECTION_CHECKS,
  ...REASONS_TO_CHANGE_CHECKS,
  ...BUSINESS_RULE_PLACEMENT_CHECKS,
  ...HUMBLE_OBJECTS_CHECKS,
  ...DEFERRAL_AND_BOUNDARIES_CHECKS,
  ...COMPONENTS_AND_STABILITY_CHECKS,
  ...TESTS_CHECKS,
  ...ENFORCEMENT_AND_ORGANIZATION_CHECKS,
];
