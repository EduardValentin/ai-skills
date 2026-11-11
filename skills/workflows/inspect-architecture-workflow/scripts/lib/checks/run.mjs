import { createContext, rowComponents } from "./context.mjs";
import { escalateRow, highestSeverity } from "./escalate.mjs";
import { isCoveredByException } from "./exceptions.mjs";
import { createOriginResolver } from "./origin.mjs";
import { CHECKS } from "./registry.mjs";
import { ruleNumber } from "./rule-titles.mjs";
import { isOffForEveryComponent, skippedRules, statusForRow } from "./status.mjs";
import { naturalOrder } from "./targets.mjs";

const CLASSIFICATION_CHECK = "classification";
const NEEDS_BASE = "needs --base";

function union(lists) {
  return [...new Set(lists.flat())];
}

function mergeGroup(rows) {
  const [first] = rows;
  return {
    ...first,
    check: union(rows.map((row) => [row.check])).join(", "),
    rules: union(rows.map((row) => row.rules)).sort((a, b) => ruleNumber(a) - ruleNumber(b)),
    severity: rows.map((row) => row.severity).reduce(highestSeverity),
    origin: rows.some((row) => row.origin === "introduced") ? "introduced" : first.origin,
    evidence: union(rows.map((row) => [row.evidence])).join("; "),
    units: union(rows.map((row) => row.units)),
    components: union(rows.map((row) => row.components)),
  };
}

export function mergeRows(rows) {
  const groups = new Map();
  for (const row of rows) {
    const key = JSON.stringify([row.target, row.defect]);
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  return [...groups.values()].map(mergeGroup);
}

function inScope(row, touched) {
  if (!touched || (row.units.length === 0 && row.components.length === 0)) return true;
  const units = new Set(touched.units);
  const components = new Set(touched.components);
  return row.units.some((path) => units.has(path)) || row.components.some((name) => components.has(name));
}

function notRunEntry(check, reason) {
  return { check: check.id, rules: check.rules, reason };
}

function missingFactEntry(check, missing) {
  return {
    check: check.id,
    rules: check.rules,
    target: null,
    reason:
      `the adapter document does not provide ${missing.join(", ")}, so ${check.id} could not be decided. ` +
      `Make the adapter provide it, or set ${check.rules.join(", ")} to advisory or off with arch model set-rule.`,
  };
}

function undecidedEntries(check, context) {
  return (check.undecided?.(context) ?? []).map((entry) => ({ check: check.id, rules: check.rules, ...entry }));
}

function runCheck(check, context) {
  if (check.needsBase && !context.touched) {
    return { rows: [], incomplete: [], notRun: [notRunEntry(check, NEEDS_BASE)] };
  }
  if (check.applies?.(context) === false) return { rows: [], incomplete: [], notRun: [] };
  const reason = check.notRunReason?.(context);
  if (reason) return { rows: [], incomplete: [], notRun: [notRunEntry(check, reason)] };
  const missing = check.facts.filter((fact) => !context.graph.capabilities?.[fact]);
  if (missing.length > 0) return { rows: [], incomplete: [missingFactEntry(check, missing)], notRun: [] };
  const rows = check.run(context).map((raw) => ({
    ...raw,
    check: check.id,
    defect: raw.defect ?? check.defect,
    rules: check.rules,
    severity: check.severity,
    consequence: check.consequence(raw),
  }));
  return { rows, incomplete: undecidedEntries(check, context), notRun: [] };
}

function unclassifiedEntries(graph, touched) {
  return (touched ? touched.uncovered : graph.uncovered).map((path) => ({
    check: CLASSIFICATION_CHECK,
    rules: [],
    target: path,
    reason:
      `${path} has no component or no kind, so no check could judge it. ` +
      "Add its component or classify it with arch model classify.",
  }));
}

function finalRow(row, context) {
  const { severity, lifts } = escalateRow(row, context);
  return {
    check: row.check,
    target: row.target,
    defect: row.defect,
    rules: row.rules,
    severity,
    baseSeverity: row.severity,
    lifts,
    status: statusForRow(context.model, row.rules, rowComponents(row, context)),
    origin: row.origin,
    evidence: row.evidence,
    consequence: row.consequence,
    correction: row.correction,
  };
}

function byRuleThenTarget(a, b) {
  return ruleNumber(a.rules[0]) - ruleNumber(b.rules[0]) || naturalOrder(a.target, b.target);
}

function baseRowsOf(checks, { baseGraph, model, touched, history }) {
  if (!baseGraph) return [];
  const context = createContext({ graph: baseGraph, model, touched, history });
  return checks.flatMap((check) => runCheck(check, context).rows);
}

export function runChecks({ graph, model, baseGraph = null, touched = null, history = null }) {
  const context = createContext({ graph, model, baseGraph, touched, history });
  const active = CHECKS.filter((check) => !isOffForEveryComponent(model, check.rules));
  const results = active.map((check) => runCheck(check, context));
  const originOf = createOriginResolver({ graph, baseGraph, baseRows: baseRowsOf(active, context), touched });
  const inChange = results.flatMap((result) => result.rows).filter((row) => inScope(row, touched));
  const decided = mergeRows(inChange.map((row) => ({ ...row, origin: originOf(row) }))).filter(
    (row) => statusForRow(model, row.rules, rowComponents(row, context)) !== "off",
  );
  const uncovered = decided.filter((row) => !isCoveredByException(row, context));
  return {
    rows: uncovered.map((row) => finalRow(row, context)).sort(byRuleThenTarget),
    incomplete: [...results.flatMap((result) => result.incomplete), ...unclassifiedEntries(graph, touched)],
    notRun: results.flatMap((result) => result.notRun),
    skipped: skippedRules(model),
    covered: decided.length - uncovered.length,
  };
}
