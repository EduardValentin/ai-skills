import { alternatives } from "../text.mjs";
import { titledRule } from "./rule-titles.mjs";

const COLUMNS = ["Rule", "Target", "Severity", "Status", "Origin", "Evidence", "Corrections"];
const NONE = "None";

function cell(value) {
  return String(value).replaceAll("|", "\\|");
}

function tableRow(cells) {
  return `| ${cells.map(cell).join(" | ")} |`;
}

function ruleCell(rules) {
  return rules.map(titledRule).join("; ");
}

function table(rows) {
  const header = tableRow(COLUMNS);
  const separator = `|${COLUMNS.map(() => "---").join("|")}|`;
  const body = rows.map((row) => {
    const { rules, target, severity, status, origin, evidence, corrections } = row;
    return tableRow([ruleCell(rules), target, severity, status, origin, evidence, alternatives(corrections)]);
  });
  return [header, separator, ...body].join("\n");
}

function incompleteLine(entry) {
  const subject = entry.target ?? entry.check;
  const rules = entry.rules.length > 0 ? ` (${entry.rules.map(titledRule).join("; ")})` : "";
  return `- ${subject}${rules}: ${entry.reason}`;
}

function skippedLine(entry) {
  const place = entry.component ? ` in ${entry.component}` : "";
  return `- ${titledRule(entry.rule)}${place}: ${entry.status} (${entry.reason})`;
}

function section(title, lines) {
  return `## ${title}\n\n${lines.length > 0 ? lines.join("\n") : NONE}`;
}

function notRunLine(entry) {
  return `- ${entry.check} (${entry.rules.map(titledRule).join("; ")}): ${entry.reason}`;
}

export function renderCheckMarkdown({ rows, incomplete, notRun, skipped, covered }) {
  const coveredLine = covered > 0 ? [`Covered by recorded exceptions: ${covered}`] : [];
  return [
    table(rows),
    ...coveredLine,
    section("Incomplete", incomplete.map(incompleteLine)),
    section("Not run", notRun.map(notRunLine)),
    section("Rules not enforced", skipped.map(skippedLine)),
  ].join("\n\n");
}
