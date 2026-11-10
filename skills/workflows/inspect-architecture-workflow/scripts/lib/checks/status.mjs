import { ruleNumber } from "./rule-titles.mjs";

const STRICTNESS = { off: 0, advisory: 1, enforced: 2 };

export function statusForRule(model, rule, component) {
  const specific = component ? model.rules[`${rule}@${component}`] : undefined;
  return specific?.status ?? model.rules[rule]?.status ?? "enforced";
}

function strictest(statuses) {
  return statuses.reduce((best, status) => (STRICTNESS[status] > STRICTNESS[best] ? status : best), "off");
}

export function statusForRow(model, rules, components) {
  const owners = components.length > 0 ? components : [null];
  const perRule = rules.map((rule) => strictest(owners.map((owner) => statusForRule(model, rule, owner))));
  return strictest(perRule);
}

export function isOffForProject(model, rules) {
  return rules.every((rule) => statusForRule(model, rule, null) === "off");
}

export function concernsEnforcedRule(model, rules) {
  return rules.length === 0 || rules.some((rule) => statusForRule(model, rule, null) === "enforced");
}

export function skippedRules(model) {
  return Object.entries(model.rules)
    .filter(([, entry]) => entry.status !== "enforced")
    .map(([key, entry]) => ({
      rule: key.split("@")[0],
      status: entry.status,
      reason: entry.reason,
      component: entry.component ?? null,
    }))
    .sort((a, b) => ruleNumber(a.rule) - ruleNumber(b.rule) || (a.component ?? "").localeCompare(b.component ?? ""));
}
