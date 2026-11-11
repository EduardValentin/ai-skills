import { NOT_PROVIDED } from "./queries/shared.mjs";

function renderValue(value, missing) {
  if (value === null || value === undefined) return missing;
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

function renderTable({ columns, rows, undefinedColumns = [] }) {
  const missing = columns.map((column) => (undefinedColumns.includes(column) ? "undefined" : ""));
  const header = `| ${columns.join(" | ")} |`;
  const separator = `|${columns.map(() => "---").join("|")}|`;
  const body = rows.map((row) => `| ${row.map((value, i) => renderValue(value, missing[i])).join(" | ")} |`);
  return [header, separator, ...body].join("\n");
}

export function renderMarkdown(result) {
  if (result.notProvided) return NOT_PROVIDED;
  if (!result.sections) return renderTable(result);
  return Object.values(result.sections).map(renderTable).join("\n\n");
}

function tableJson({ columns, rows }) {
  return { columns, rows };
}

export function renderJson(result) {
  if (result.notProvided) return JSON.stringify({ notProvided: result.notProvided });
  if (!result.sections) return JSON.stringify(tableJson(result));
  const named = Object.entries(result.sections).map(([name, section]) => [name, tableJson(section)]);
  return JSON.stringify(Object.fromEntries(named));
}
