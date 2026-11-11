export const RULE_TITLES = {
  R1: "Deliver behavior and structure together",
  R2: "Name a shape mismatch",
  R3: "Importance first, urgency second",
  R4: "Dependencies point toward policy",
  R5: "The consumer owns the port",
  R6: "Use cases own their boundaries",
  R7: "Lower-level components are plugins",
  R8: "Constraints need a named reason",
  R9: "Trace change impact along dependencies",
  R10: "One actor per module",
  R11: "Deduplicate only for one owner",
  R12: "Add behavior by adding code",
  R13: "Substitutable implementations, narrow interfaces",
  R14: "Hide data behind behavior",
  R15: "Decompose into independently understood units",
  R16: "Default to immutable values",
  R17: "Critical rules live in entities",
  R18: "Use cases hold application rules",
  R19: "Cross boundaries with plain data",
  R20: "Split humble from testable units",
  R21: "Presenter finishes every decision",
  R22: "Reach storage through a gateway",
  R23: "Defer unforced decisions",
  R24: "No tiers without a reason",
  R25: "Boundaries at axes of change",
  R26: "Demonstrate the model without I/O",
  R27: "One component, one published surface",
  R28: "Name your cohesion position",
  R29: "Let the component map emerge",
  R30: "No dependency cycles",
  R31: "Depend toward stability",
  R32: "Use metrics as a screen",
  R33: "Release components bottom-up",
  R34: "Tests are the outermost component",
  R35: "Test through a testing API",
  R36: "Organize tests by behavior",
  R37: "Tests falsify, they do not prove",
  R38: "Enforce boundaries with the build",
  R39: "Make forbidden edges uncompilable",
  R40: "Organize a monolith by domain",
  R41: "Verify the real dependency graph",
};

export function ruleNumber(rule) {
  return Number(rule.slice(1));
}

export function titledRule(rule) {
  return `${rule} ${RULE_TITLES[rule] ?? ""}`.trimEnd();
}
