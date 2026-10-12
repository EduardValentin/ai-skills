import { access } from "node:fs/promises";
import path from "node:path";
import { createTypescriptAdapter } from "./typescript.mjs";

const SUPPORTED = ["typescript"];

async function exists(file) { try { await access(file); return true; } catch { return false; } }

export async function selectAdapter(model, root) {
  const tooling = model.components.tooling ?? {};
  let language = tooling.language;
  if (!language && (await exists(path.join(root, "package.json")))) language = "typescript";
  if (language === "typescript") return createTypescriptAdapter({ root, tooling });
  throw new Error(`no adapter for language: ${language ?? "unknown"}; supported: ${SUPPORTED.join(", ")}`);
}
