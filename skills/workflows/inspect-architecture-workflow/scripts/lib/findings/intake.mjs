import { readFileSync } from "node:fs";
import { UsageError } from "../cli/errors.mjs";
import { createContext, rowComponents } from "../checks/context.mjs";
import { escalateRow, highestSeverity } from "../checks/escalate.mjs";
import { JUDGMENTS } from "../checks/registry.mjs";
import { isCoveredByException } from "../checks/exceptions.mjs";
import { statusForRow } from "../checks/status.mjs";
import { DEFAULT_KINDS } from "../model/defaults.mjs";
import { validateShape } from "../model/validate-shape.mjs";
import { evidenceProblems } from "./evidence.mjs";
import { componentOfTarget, isInScope, recognizeTarget } from "./targets.mjs";

const TEXT = { type: "string" };
const SET_BY_JUDGMENT = ["rules", "defect", "severity"];
const LIFT_RULE = 2;

export const JUDGED_SCHEMA = {
  type: "object",
  required: ["findings"],
  additionalProperties: false,
  properties: {
    findings: {
      type: "array",
      items: {
        type: "object",
        required: ["judgment", "target"],
        additionalProperties: false,
        properties: {
          judgment: { type: "string", minLength: 1 },
          target: { type: "string", minLength: 1 },
          consequence: TEXT,
          correction: TEXT,
          evidence: { type: "array", items: TEXT },
          wider: { type: "boolean" },
          origin: { type: "string", enum: ["introduced", "inherited"] },
          liftedBy: { type: "string", minLength: 1 },
        },
      },
    },
    questions: { type: "array", items: { type: "string", minLength: 1 } },
  },
};

function readJudgedFile(file) {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch (error) {
    throw new UsageError(
      `judged findings file ${file} cannot be read as JSON: ${error.message}. ` +
        "Write the reviewer's findings and questions as one JSON object and pass its path with --judged.",
    );
  }
}

export function readJudged(files) {
  return files.map((file) => ({ file, document: readJudgedFile(file) }));
}

export function judgedQuestions(documents) {
  return documents.flatMap(({ document }) => document.questions ?? []);
}

function withoutJudgmentFields(entry) {
  if (entry === null || typeof entry !== "object") return entry;
  return Object.fromEntries(Object.entries(entry).filter(([key]) => !SET_BY_JUDGMENT.includes(key)));
}

function shapeProblems(document) {
  const shapeOnly = Array.isArray(document?.findings)
    ? { ...document, findings: document.findings.map(withoutJudgmentFields) }
    : document;
  return validateShape(shapeOnly, JUDGED_SCHEMA);
}

function blank(text) {
  return typeof text !== "string" || text.trim() === "";
}

function completenessProblems(entry) {
  return [
    ...(entry.evidence?.length > 0 ? [] : ["has no evidence. Add at least one src/file.ts:12 line that shows it."]),
    ...(blank(entry.consequence) ? ["has no consequence. State in one sentence what it costs to maintain."] : []),
    ...(blank(entry.correction) ? ["has no correction. State the smallest change inside the scope."] : []),
  ];
}

function setByJudgmentProblem(entry) {
  const given = SET_BY_JUDGMENT.filter((key) => Object.hasOwn(entry, key));
  if (given.length === 0) return [];
  return [`sets ${given.join(", ")}, which come from the judgment entry. Remove them and name the judgment.`];
}

function escalationRow(recognized, target, judgment) {
  return {
    target,
    defect: judgment.defect,
    severity: judgment.severity,
    units: recognized.units,
    components: recognized.components,
    edge: recognized.edge,
  };
}

function scopeProblems(entry, ctx) {
  const inScope = isInScope(ctx.scope, entry.target);
  if (inScope && entry.wider) {
    return [`is inside the reviewed scope, so it cannot be "wider": true. Remove "wider" and state its origin.`];
  }
  if (!inScope && !entry.wider) {
    return [`is outside the reviewed scope. Mark it "wider": true to report it as a wider observation.`];
  }
  return [];
}

function originProblems(entry, flow) {
  if (flow === "audit") {
    return Object.hasOwn(entry, "origin")
      ? ["sets origin, which an audit does not have. Remove it: an audit has no base to compare with."]
      : [];
  }
  if (entry.origin) return [];
  return [
    'has no origin. State "origin": "introduced" if the change creates the defect, or "inherited" if it leaves ' +
      "a defect that was already there in place.",
  ];
}

function unitFits(unit, targets, model) {
  if (targets.includes(unit.kind)) return true;
  if (targets.includes("test-suite") && unit.kind === "test") return true;
  if (DEFAULT_KINDS[unit.kind]) return false;
  const role = model.kinds[unit.kind]?.role;
  return targets.some((target) => DEFAULT_KINDS[target] && DEFAULT_KINDS[target].role === role);
}

function fitsJudgment(recognized, judgment, ctx) {
  const { targets } = judgment;
  if (targets.includes("plan") && ctx.flow === "plan-review") return true;
  if (recognized.components.length > 0) return targets.includes("component");
  if (recognized.kind === "port" && targets.includes("port")) return true;
  const kindOf = new Map(ctx.graph.units.map((unit) => [unit.path, unit]));
  return recognized.units.some((path) => unitFits(kindOf.get(path), targets, ctx.model));
}

function fitProblems(entry, judgment, recognized, ctx) {
  if (fitsJudgment(recognized, judgment, ctx)) return [];
  const applies = judgment.targets.map((target) => (target === "plan" ? "plan (plan-review only)" : target));
  return [
    `has the target "${entry.target}", which the judgment "${judgment.id}" does not apply to. ` +
      `It applies to: ${applies.join(", ")}. Pick a target of that kind or another judgment.`,
  ];
}

function liftProblems(entry, ctx) {
  if (!entry.liftedBy || ctx.upcoming.includes(entry.liftedBy)) return [];
  return [
    `lifts for "${entry.liftedBy}", which nobody confirmed. ` +
      "Ask the owner, then pass the answer with --upcoming, or record it in the model.",
  ];
}

function evidenceProblemsOf(entry, ctx) {
  if (!(entry.evidence?.length > 0)) return [];
  return evidenceProblems({ root: ctx.root, flow: ctx.flow, plan: ctx.plan, evidence: entry.evidence });
}

function liftedToBlocker({ severity, lifts }) {
  const lifted = highestSeverity("blocker", severity);
  return { severity: lifted, lifts: lifted === severity ? lifts : [...lifts, LIFT_RULE] };
}

function originOf(entry, flow) {
  return flow === "audit" ? "none" : entry.origin;
}

function buildFinding({ entry, judgment, row, context, flow, graph }) {
  const escalated = escalateRow(row, context);
  const { severity, lifts } = entry.liftedBy ? liftedToBlocker(escalated) : escalated;
  return {
    target: entry.target,
    defect: judgment.defect,
    rules: judgment.rules,
    severity,
    baseSeverity: judgment.severity,
    lifts,
    status: statusForRow(context.model, judgment.rules, rowComponents(row, context)),
    origin: originOf(entry, flow),
    provenance: "judged",
    consequence: entry.consequence.trim(),
    correction: entry.correction.trim(),
    evidence: entry.evidence,
    wider: entry.wider === true,
    ...(entry.liftedBy && { liftedBy: entry.liftedBy }),
    component: componentOfTarget(graph, entry.target),
  };
}

function unknownJudgment(id) {
  return `names the judgment "${id}", which does not exist. Use a judgment id from the rule group files.`;
}

function unknownTarget(target) {
  const kinds = "a unit path, an edge <from> -> <to>, a port <path>#<Symbol>, a component name, or a proposed unit";
  return `has the target "${target}", which the graph does not know. Use ${kinds}.`;
}

function examine(entry, ctx) {
  const early = [...setByJudgmentProblem(entry), ...completenessProblems(entry), ...originProblems(entry, ctx.flow)];
  const judgment = JUDGMENTS.find((candidate) => candidate.id === entry.judgment);
  if (!judgment) return { problems: [...early, unknownJudgment(entry.judgment)] };
  const recognized = recognizeTarget(ctx.graph, entry.target);
  if (!recognized) return { problems: [...early, unknownTarget(entry.target)] };
  const row = escalationRow(recognized, entry.target, judgment);
  const problems = [
    ...early,
    ...fitProblems(entry, judgment, recognized, ctx),
    ...scopeProblems(entry, ctx),
    ...liftProblems(entry, ctx),
    ...evidenceProblemsOf(entry, ctx),
  ];
  return { problems, judgment, row };
}

function labelOf({ entry, index, file }) {
  return `${file}: findings[${index}] (${entry.target ?? entry.judgment ?? "no target"})`;
}

function refuse(problems) {
  throw new UsageError(
    `judged findings were refused and nothing was stored:\n${problems.map((p) => `  ${p}`).join("\n")}\n` +
      "Correct the judged findings file and run arch findings add again.",
  );
}

function entriesOf(documents) {
  return documents.flatMap(({ file, document }) => document.findings.map((entry, index) => ({ entry, index, file })));
}

function documentShapeProblems(documents) {
  return documents.flatMap(({ file, document }) => shapeProblems(document).map((problem) => `${file}: ${problem}`));
}

const DROP_REASONS = { off: "rule off", covered: "covered by an exception" };

function dropReason(judgment, row, context) {
  if (statusForRow(context.model, judgment.rules, rowComponents(row, context)) === "off") return DROP_REASONS.off;
  if (isCoveredByException({ ...row, rules: judgment.rules }, context)) return DROP_REASONS.covered;
  return null;
}

export function judgedFindings({ documents, flow, plan, root, model, graph, scope, upcoming }) {
  const shape = documentShapeProblems(documents);
  if (shape.length > 0) refuse(shape);
  const context = createContext({ graph, model });
  const ctx = { flow, plan, root, graph, model, scope, upcoming, context };
  const located = entriesOf(documents);
  const examined = located.map(({ entry }) => examine(entry, ctx));
  const problems = examined.flatMap((result, position) =>
    result.problems.map((problem) => `${labelOf(located[position])} ${problem}`),
  );
  if (problems.length > 0) refuse(problems);
  const findings = [];
  const dropped = [];
  examined.forEach(({ judgment, row }, position) => {
    const { entry } = located[position];
    const reason = dropReason(judgment, row, context);
    if (reason) dropped.push({ target: entry.target, judgment: judgment.id, reason });
    else findings.push(buildFinding({ entry, judgment, row, context, flow, graph }));
  });
  return { findings, dropped };
}
