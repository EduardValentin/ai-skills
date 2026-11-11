import { existsSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

const CODE_EVIDENCE = /^(.+):(\d+)$/;
const PLAN_EVIDENCE = /^([^#]+)#(.+)$/;
const HEADING = /^#{1,6}\s+(.*?)\s*#*\s*$/;

function readFileInside(root, file) {
  const absolute = path.resolve(root, file);
  const relative = path.relative(root, absolute);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return null;
  if (!existsSync(absolute) || !statSync(absolute).isFile()) return null;
  return readFileSync(absolute, "utf8");
}

function lineCount(text) {
  const lines = text.split("\n");
  return lines.at(-1) === "" ? lines.length - 1 : lines.length;
}

function codeEvidenceProblem(root, entry) {
  const match = CODE_EVIDENCE.exec(entry);
  if (!match) return `evidence "${entry}" is not path:line. Cite it as src/file.ts:12.`;
  const [, file, lineText] = match;
  const line = Number(lineText);
  const text = readFileInside(root, file);
  if (text === null) {
    return `evidence "${entry}": ${file} does not exist in the reviewed tree. Cite a file that exists.`;
  }
  const lines = lineCount(text);
  if (line < 1 || line > lines) {
    return `evidence "${entry}": line ${line} is outside ${file}, which has ${lines} lines. Cite a line that exists.`;
  }
  return null;
}

function headingsOf(text) {
  return text.split("\n").map((line) => HEADING.exec(line)?.[1].toLowerCase()).filter(Boolean);
}

function planEvidenceProblem(root, plan, entry) {
  const match = PLAN_EVIDENCE.exec(entry);
  if (!match || path.normalize(match[1]) !== path.normalize(plan)) {
    return `evidence "${entry}" is not a plan section. In plan-review cite ${plan}#<heading>.`;
  }
  const text = readFileInside(root, plan);
  if (text === null) return `evidence "${entry}": the plan ${plan} does not exist. Pass the plan path with --plan.`;
  if (headingsOf(text).includes(match[2].trim().toLowerCase())) return null;
  return `evidence "${entry}": ${plan} has no heading "${match[2]}". Cite a heading that exists in the plan.`;
}

export function evidenceProblems({ root, flow, plan, evidence }) {
  const check = flow === "plan-review"
    ? (entry) => planEvidenceProblem(root, plan, entry)
    : (entry) => codeEvidenceProblem(root, entry);
  return evidence.map(check).filter(Boolean);
}
