import { readFileSync } from "node:fs";

export const LEDGER_PATH = ".architecture/ledger.md";
export const MODES = ["audit", "change-review", "plan-review"];

const TEMPLATE_URL = new URL("../../assets/ledger/ledger.md", import.meta.url);
const SEVERITIES = ["minor", "major", "blocker"];
const OPEN_VERDICTS = new Set(["SHOULD_CHANGE", "ACCEPTED", "UNDERSPECIFIED"]);
const INCOMING_VERDICTS = new Set(["OK", "SHOULD_CHANGE", "UNDERSPECIFIED"]);
const ESCALATION_RULES = [1, 2, 3, 4];
const DIRECTION_LENGTH = 3;
const DASH = "\u2014";

const TABLES = {
  runs: { section: "Run log", columns: { Run: "run", Date: "date", Commit: "commit", Mode: "mode", Scope: "scope", Verdict: "verdict", Blocker: "blocker", Major: "major", Minor: "minor", OK: "ok" } },
  changes: { section: "Changes", columns: { Change: "change", Description: "description", Resolves: "resolves" } },
  findings: { section: "Findings", columns: { ID: "id", Workflow: "workflow", Target: "target", Rule: "rule", Origin: "origin", Verdict: "verdict", Severity: "severity", Evidence: "evidence", Change: "change", Protects: "protects", Run: "run" } },
  acceptances: { section: "Acceptances", columns: { Finding: "finding", "One-off or standing": "kind", Reason: "reason", "Accepted by": "by", Date: "date", "Promoted to": "promoted" } },
  pending: { section: "Pending record updates", columns: { Finding: "finding", File: "file", Row: "row", Operation: "operation" } },
  map: { section: "Improvement map", columns: { Order: "order", Change: "change", Severity: "severity", Rows: "rows", Protects: "protects" } },
};

const INCOMING_COLUMNS = { Workflow: "workflow", Target: "target", Rule: "rule", Origin: "origin", Verdict: "verdict", Severity: "severity", Evidence: "evidence", Change: "change", Escalation: "escalation", Protects: "protects" };

function splitRow(line) {
  const body = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  const cells = [];
  let cell = "";
  for (let i = 0; i < body.length; i += 1) {
    if (body[i] === "\\" && body[i + 1] === "|") { cell += "|"; i += 1; continue; }
    if (body[i] === "|") { cells.push(cell.trim()); cell = ""; continue; }
    cell += body[i];
  }
  cells.push(cell.trim());
  return cells;
}

function escapeCell(value) {
  return String(value ?? "").replace(/\s*\n\s*/g, " ").replace(/\|/g, "\\|");
}

function isSeparator(line) { return /^\|(\s*:?-+:?\s*\|)+\s*$/.test(line.trim()); }
function isTableLine(line) { return line.trim().startsWith("|"); }

function rowObject(headers, cells, columns) {
  const row = Object.fromEntries(Object.values(columns).map((key) => [key, ""]));
  headers.forEach((header, i) => { if (columns[header]) row[columns[header]] = cells[i] ?? ""; });
  return row;
}

function readTable(lines, start, columns) {
  const headers = splitRow(lines[start]);
  let end = start + 1;
  if (end < lines.length && isSeparator(lines[end])) end += 1;
  const rows = [];
  while (end < lines.length && isTableLine(lines[end])) { rows.push(rowObject(headers, splitRow(lines[end]), columns)); end += 1; }
  return { rows, end };
}

function renderTable(columns, rows) {
  const headers = Object.keys(columns);
  const header = `| ${headers.join(" | ")} |`;
  const separator = `|${headers.map(() => "---").join("|")}|`;
  const body = rows.map((row) => `| ${Object.values(columns).map((key) => escapeCell(row[key])).join(" | ")} |`);
  return [header, separator, ...body];
}

function tableKeyOf(section) {
  return Object.keys(TABLES).find((key) => TABLES[key].section === section);
}

function parseSegments(text) {
  const lines = text.split("\n");
  const layout = [];
  const tables = {};
  let section = null;
  for (let i = 0; i < lines.length;) {
    const heading = lines[i].match(/^## (.+)$/);
    if (heading) section = heading[1].trim();
    const key = tableKeyOf(section);
    if (key && !tables[key] && isTableLine(lines[i])) {
      const { rows, end } = readTable(lines, i, TABLES[key].columns);
      tables[key] = rows;
      layout.push({ table: key });
      i = end;
      continue;
    }
    layout.push(lines[i]);
    i += 1;
  }
  return { layout, tables };
}

function templateSection(key) {
  const { layout } = parseSegments(readFileSync(TEMPLATE_URL, "utf8"));
  const start = layout.indexOf(`## ${TABLES[key].section}`);
  const next = layout.findIndex((segment, i) => i > start && typeof segment === "string" && segment.startsWith("## "));
  const section = layout.slice(start, next === -1 ? layout.length : next);
  while (section.at(-1) === "") section.pop();
  return section;
}

export function templateText() {
  return readFileSync(TEMPLATE_URL, "utf8");
}

export function parseLedger(text) {
  const { layout, tables } = parseSegments(text);
  for (const key of Object.keys(TABLES)) {
    if (tables[key]) continue;
    const trailing = layout.at(-1) === "" ? layout.pop() : null;
    layout.push("", ...templateSection(key));
    if (trailing !== null) layout.push(trailing);
    tables[key] = [];
  }
  return { ...tables, layout };
}

export function writeLedger(ledger) {
  return ledger.layout.flatMap((segment) => (typeof segment === "string" ? [segment] : renderTable(TABLES[segment.table].columns, ledger[segment.table]))).join("\n");
}

export function parseRows(text) {
  const lines = text.split("\n");
  const rows = [];
  for (let i = 0; i < lines.length;) {
    if (!isTableLine(lines[i]) || !splitRow(lines[i]).includes("Target")) { i += 1; continue; }
    const table = readTable(lines, i, INCOMING_COLUMNS);
    rows.push(...table.rows);
    i = table.end;
  }
  return rows;
}

function today() { return new Date().toISOString().slice(0, 10); }
function findingKey(row) { return `${row.target}\u0000${row.rule}`; }
const SEVERITY_CELL = /^\s*(blocker|major|minor)\b(?:\s*\(base (blocker|major|minor)\))?/i;
const MARK = /\s*\[rule (\d+)\]/g;
const BASE_IMPLIED_RULES = new Set(["1", "3"]);

function severityOf(row) { return String(row.severity).match(SEVERITY_CELL)?.[1]?.toLowerCase() ?? null; }
function baseSeverityOf(row) { return String(row.severity).match(SEVERITY_CELL)?.[2]?.toLowerCase() ?? null; }
function severityCell(severity, base) { return base && base !== severity ? `${severity} (base ${base})` : severity ?? ""; }
function marksOf(evidence) { return [...String(evidence).matchAll(MARK)].map((m) => m[1]); }
function withoutMarks(evidence) { return String(evidence).replace(MARK, "").trim(); }
function withMarks(evidence, marks) {
  const sorted = [...new Set(marks)].sort((a, b) => Number(a) - Number(b));
  return [withoutMarks(evidence), ...sorted.map((rule) => `[rule ${rule}]`)].filter(Boolean).join(" ");
}
function severityRank(severity) { return SEVERITIES.indexOf(severity); }
function liftedBy(row, rule) { return marksOf(row.evidence).includes(String(rule)); }

function impliedBase(severity, marks) {
  const onlyAtLeastMajor = marks.length > 0 && marks.every((rule) => BASE_IMPLIED_RULES.has(rule));
  return severity === "major" && onlyAtLeastMajor ? "minor" : null;
}

function incomingSeverity(row, marks) {
  const severity = severityOf(row);
  if (!severity) return String(row.severity ?? "").trim().toLowerCase();
  return severityCell(severity, baseSeverityOf(row) ?? impliedBase(severity, marks));
}

function normalizeIncoming(row, mode) {
  const verdict = String(row.verdict).trim().toUpperCase();
  if (!INCOMING_VERDICTS.has(verdict)) throw new Error(`row ${row.target} ${row.rule}: verdict must be OK, SHOULD_CHANGE, or UNDERSPECIFIED, got "${row.verdict}"`);
  const origin = row.origin || (mode === "change-review" ? "" : "introduced");
  if (verdict !== "OK" && !["introduced", "left"].includes(origin)) throw new Error(`row ${row.target} ${row.rule}: Origin must be introduced or left in a change review`);
  const marks = [...marksOf(row.evidence), ...(String(row.escalation ?? "").match(/\d+/g) ?? [])];
  return {
    workflow: row.workflow, target: row.target, rule: row.rule, origin, verdict,
    severity: incomingSeverity(row, marks), evidence: withMarks(row.evidence, marks),
    change: row.change, protects: row.protects ?? "",
  };
}

function mergeDuplicates(kept, row) {
  const higher = severityRank(severityOf(row)) > severityRank(severityOf(kept)) ? row : kept;
  const fuller = withoutMarks(row.evidence).length > withoutMarks(kept.evidence).length ? row : kept;
  return { ...fuller, severity: higher.severity, evidence: withMarks(fuller.evidence, [...marksOf(kept.evidence), ...marksOf(row.evidence)]) };
}

function dedupe(rows) {
  const byKey = new Map();
  for (const row of rows) {
    const kept = byKey.get(findingKey(row));
    byKey.set(findingKey(row), kept ? mergeDuplicates(kept, row) : row);
  }
  return [...byKey.values()];
}

function stripSymbol(part) {
  if (part.startsWith("external:") || !part.includes(":")) return part;
  return part.slice(0, part.lastIndexOf(":"));
}

function targetMatcher(listed, exact = []) {
  const everything = listed.includes("*");
  const names = new Set(listed);
  const exactNames = new Set(exact);
  return (target) => {
    if (everything || exactNames.has(target) || names.has(target)) return true;
    return target.split(" -> ").some((part) => names.has(part) || names.has(stripSymbol(part)));
  };
}

function nextNumber(values, pattern) {
  return values.reduce((max, value) => Math.max(max, Number(String(value).match(pattern)?.[1] ?? 0)), 0) + 1;
}

function resolved(finding, run, commit, note) {
  const suffix = note ? `resolved at ${commit}: ${note}` : `resolved at ${commit}`;
  return { ...finding, verdict: "RESOLVED", evidence: [finding.evidence, suffix].filter(Boolean).join("; "), run };
}

function settleAbsent(finding, { run, commit, skipped, isRemoved, isEvaluated }) {
  if (!OPEN_VERDICTS.has(finding.verdict)) return finding;
  if (isRemoved(finding.target)) return resolved(finding, run, commit, "target removed");
  if (skipped.has(finding.workflow)) return finding;
  if (isEvaluated(finding.target)) return resolved(finding, run, commit, null);
  return finding;
}

function settleMatched(existing, row, run, commit) {
  if (row.verdict === "OK" && existing.verdict === "RESOLVED") return existing;
  if (row.verdict === "OK" && OPEN_VERDICTS.has(existing.verdict)) return resolved({ ...existing, evidence: row.evidence || existing.evidence }, run, commit, null);
  const verdict = existing.verdict === "ACCEPTED" && row.verdict === "SHOULD_CHANGE" ? "ACCEPTED" : row.verdict;
  return { ...existing, ...row, verdict, protects: row.protects || existing.protects, run };
}

function runLogRow(ledger, base) {
  const result = runVerdict(ledger, base.run);
  return { ...base, verdict: result.verdict, blocker: String(result.counts.blocker), major: String(result.counts.major), minor: String(result.counts.minor), ok: String(result.ok) };
}

export function addRun(ledger, { mode, scope, commit, rows, skippedWorkflows = [], evaluatedTargets = [], removedTargets = [], date = today() }) {
  const run = String(nextNumber(ledger.runs.map((r) => r.run), /^(\d+)$/));
  const incoming = dedupe(rows.map((row) => normalizeIncoming(row, mode)));
  const incomingByKey = new Map(incoming.map((row) => [findingKey(row), row]));
  const context = {
    run, commit, skipped: new Set(skippedWorkflows),
    isRemoved: targetMatcher(removedTargets),
    isEvaluated: targetMatcher(evaluatedTargets, incoming.map((row) => row.target)),
  };
  const findings = ledger.findings.map((finding) => {
    const row = incomingByKey.get(findingKey(finding));
    if (!row) return settleAbsent(finding, context);
    incomingByKey.delete(findingKey(finding));
    return settleMatched(finding, row, run, commit);
  });
  let nextId = nextNumber(ledger.findings.map((f) => f.id), /^F(\d+)$/);
  for (const row of incomingByKey.values()) { findings.push({ id: `F${nextId}`, ...row, run }); nextId += 1; }
  const skippedNote = skippedWorkflows.length > 0 ? `; skipped ${skippedWorkflows.join(", ")}` : "";
  const updated = { ...ledger, findings };
  const logRow = runLogRow(updated, { run, date, commit, mode, scope: `${scope}${skippedNote}` });
  return { ...updated, runs: [...ledger.runs, logRow] };
}

export function refreshRunLog(ledger, run) {
  return { ...ledger, runs: ledger.runs.map((row) => (row.run === run ? runLogRow(ledger, row) : row)) };
}

function emptyCounts() { return Object.fromEntries(SEVERITIES.map((s) => [s, 0])); }

function scopeOf(runRow) { return String(runRow.scope).replace(/; skipped .*$/, ""); }

function sameScopeRuns(ledger, run) {
  const current = ledger.runs.find((r) => r.run === run);
  if (!current) return new Set([run]);
  return new Set(ledger.runs.filter((r) => r.mode === current.mode && scopeOf(r) === scopeOf(current)).map((r) => r.run));
}

export function runVerdict(ledger, run) {
  const scopeRuns = sameScopeRuns(ledger, run);
  const isOpen = (f) => f.verdict === "SHOULD_CHANGE";
  const rows = ledger.findings.filter((f) => f.run === run || (isOpen(f) && scopeRuns.has(f.run)));
  const open = rows.filter(isOpen);
  const counts = emptyCounts();
  const preExisting = emptyCounts();
  let blocking = false;
  for (const row of open) {
    const severity = severityOf(row);
    if (!severity) continue;
    const counted = row.origin !== "left" || liftedBy(row, 2);
    (counted ? counts : preExisting)[severity] += 1;
    if (counted && severityRank(severity) >= severityRank("major")) blocking = true;
  }
  const lifted = rows.filter((f) => f.verdict === "SHOULD_CHANGE" || f.verdict === "ACCEPTED");
  const escalation = Object.fromEntries(ESCALATION_RULES.map((rule) => [rule, lifted.filter((f) => liftedBy(f, rule)).length]));
  return {
    verdict: blocking ? "SHOULD_CHANGE" : "OK",
    counts, preExisting, escalation,
    carried: ledger.findings.filter((f) => isOpen(f) && !scopeRuns.has(f.run)).length,
    ok: rows.filter((f) => f.verdict === "OK").length,
    underspecified: rows.filter((f) => f.verdict === "UNDERSPECIFIED").length,
    changes: ledger.changes.length,
  };
}

function changeName(index) {
  let name = "";
  for (let n = index + 1; n > 0; n = Math.floor((n - 1) / 26)) name = String.fromCharCode(65 + ((n - 1) % 26)) + name;
  return `CH-${name}`;
}

function protectsOf(rows) {
  const names = rows.flatMap((row) => String(row.protects).split(",").map((s) => s.trim()).filter(Boolean));
  return [...new Set(names)].join(", ");
}

export function buildMap(ledger) {
  const descriptions = new Map(ledger.changes.map((c) => [c.change, c.description]));
  const findings = ledger.findings.map((f) => ({ ...f, change: descriptions.get(f.change) ?? f.change }));
  const clusters = new Map();
  for (const finding of findings) {
    if (finding.verdict !== "SHOULD_CHANGE" || !finding.change) continue;
    if (!clusters.has(finding.change)) clusters.set(finding.change, []);
    clusters.get(finding.change).push(finding);
  }
  const ordered = [...clusters.entries()]
    .map(([description, rows]) => ({ description, rows, severity: rows.map(severityOf).reduce((top, s) => (severityRank(s) > severityRank(top) ? s : top), null) }))
    .sort((a, b) => severityRank(b.severity) - severityRank(a.severity) || b.rows.length - a.rows.length || a.description.localeCompare(b.description))
    .map((cluster, i) => ({ ...cluster, name: changeName(i) }));
  const nameOf = new Map(ordered.map((cluster) => [cluster.description, cluster.name]));
  return {
    ...ledger,
    findings: findings.map((f) => (f.verdict === "SHOULD_CHANGE" && nameOf.has(f.change) ? { ...f, change: nameOf.get(f.change) } : f)),
    changes: ordered.map((c) => ({ change: c.name, description: c.description, resolves: c.rows.map((r) => r.id).join(", ") })),
    map: ordered.map((c, i) => ({ order: String(i + 1), change: c.name, severity: c.severity ?? "", rows: String(c.rows.length), protects: protectsOf(c.rows) })),
  };
}

export function directionLines(ledger) {
  return ledger.map.slice(0, DIRECTION_LENGTH).map((entry) => {
    const change = ledger.changes.find((c) => c.change === entry.change);
    const rules = [...new Set(ledger.findings.filter((f) => f.change === entry.change && f.verdict === "SHOULD_CHANGE").map((f) => f.rule))].join(", ");
    return `${entry.order}. ${entry.change} ${DASH} ${rules} ${DASH} ${change?.description ?? ""} ${DASH} protects ${entry.protects || "none"}`;
  });
}

export function contractLines(ledger, run, agents) {
  const result = runVerdict(ledger, run);
  const { counts, preExisting, escalation } = result;
  const direction = directionLines(ledger);
  return [
    `Verdict: ${result.verdict} ${DASH} ${counts.blocker} blocker, ${counts.major} major, ${counts.minor} minor open; ${result.ok} targets OK; ${result.changes} changes named`,
    `Pre-existing: ${preExisting.blocker} blocker, ${preExisting.major} major, ${preExisting.minor} minor (not blocking)`,
    `Carried: ${result.carried} open from earlier scopes (not blocking)`,
    `Escalation: ${escalation[1]} rows lifted by rule 1, ${escalation[2]} by rule 2, ${escalation[3]} by rule 3, ${escalation[4]} by rule 4`,
    "Direction:",
    ...(direction.length > 0 ? direction : ["none"]),
    `Agents: ${agents}`,
  ];
}

function quoted(text) { return `"${String(text).replace(/(["\\$`])/g, "\\$1")}"`; }

function listed(text) { return text.split(",").map((id) => id.trim()).filter(Boolean); }

function touchedComponents(finding) {
  return listed(String(finding.evidence).match(/touches (.+?) and the model records no cohesion groups/)?.[1] ?? "");
}

const R27_EVIDENCE = /^(\S+) shares no recorded group with (.+?); groups holding \S+: (.+)$/;

function spreadEvidence(finding) {
  const match = String(finding.evidence).match(R27_EVIDENCE);
  if (!match) return { partners: [], holding: [] };
  const holding = match[3].trim() === "none" ? [] : listed(match[3]);
  return { partners: listed(match[2]), holding };
}

function naturalSorted(ids) { return [...new Set(ids)].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })); }

const GROUP_PARAGRAPH = `Then write the group's paragraph under "Cohesion groups" in decisions.md.`;

function newGroupPromotion(members, absorbs) {
  return {
    promoted: "model/boundaries.json group <name>; decisions.md Cohesion groups",
    instruction: `arch model add-group <name> components=${naturalSorted(members).join(",")} absorbs=${quoted(absorbs)}\n${GROUP_PARAGRAPH}`,
  };
}

function spreadPromotion(finding, { reason, groups }) {
  const { partners, holding } = spreadEvidence(finding);
  if (holding.length === 0) return newGroupPromotion([finding.target, ...partners], "<to be stated>");
  const commands = holding.map((name) => {
    const current = (groups ?? []).find((g) => g.name === name);
    const members = naturalSorted([...(current?.components ?? [finding.target]), ...partners]);
    return `arch model add-group ${name} components=${members.join(",")} absorbs=${quoted(current?.absorbs || reason)}`;
  });
  const noun = holding.length === 1 ? "group" : "groups";
  return {
    promoted: `model/boundaries.json ${noun} ${holding.join(", ")}; decisions.md Cohesion groups`,
    instruction: `${commands.join("\n")}\n${GROUP_PARAGRAPH}`,
  };
}

function groupPromotion(finding, options) {
  if (finding.rule.includes("R27")) return spreadPromotion(finding, options);
  return newGroupPromotion(touchedComponents(finding), options.reason);
}

function exceptionPromotion(finding, { by, reason, date, componentOf }) {
  const [from, to] = finding.target.split(" -> ").map((end) => componentOf?.get(end) ?? end);
  return {
    promoted: `decisions.md intended exception ${from} -> ${to}`,
    instruction: `Add to "Intended exceptions" in decisions.md, stated at component or ring level:\n| ${from} -> ${to} | ${reason} | <risk accepted> | ${by} | ${date} |`,
  };
}

function standingPromotion(finding, options) {
  if (/\bR2[78]\b/.test(finding.rule)) return groupPromotion(finding, options);
  if (finding.target.split(" -> ").length === 2) return exceptionPromotion(finding, options);
  return {
    promoted: "decisions.md",
    instruction: `Record a deferred decision or cohesion position in decisions.md covering ${finding.target} (${finding.rule}), stated at component or boundary level.`,
  };
}

export function accept(ledger, id, { kind, by, reason, date = today(), componentOf = null, groups = [] }) {
  const finding = ledger.findings.find((f) => f.id === id);
  if (!finding) throw new Error(`no finding ${id}`);
  if (finding.verdict !== "SHOULD_CHANGE" && finding.verdict !== "ACCEPTED") throw new Error(`${id} is ${finding.verdict}; only a SHOULD_CHANGE finding can be accepted`);
  const promotion = kind === "standing" ? standingPromotion(finding, { by, reason, date, componentOf, groups }) : null;
  const acceptance = { finding: id, kind, reason, by, date, promoted: promotion?.promoted ?? "none" };
  const index = ledger.acceptances.findIndex((a) => a.finding === id);
  const acceptances = index === -1 ? [...ledger.acceptances, acceptance] : ledger.acceptances.map((a, i) => (i === index ? acceptance : a));
  return {
    ledger: {
      ...ledger,
      findings: ledger.findings.map((f) => (f.id === id ? { ...f, verdict: "ACCEPTED" } : f)),
      acceptances,
    },
    suggestion: promotion?.instruction ?? null,
  };
}

export function lastRun(ledger) {
  return ledger.runs.at(-1) ?? null;
}

export function renderRunLogRow(row) {
  return renderTable(TABLES.runs.columns, [row]).at(-1);
}
