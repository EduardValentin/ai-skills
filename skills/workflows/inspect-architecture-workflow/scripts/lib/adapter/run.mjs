import { spawn } from "node:child_process";
import { ToolingError } from "../cli/errors.mjs";
import { readAdapterDocument } from "./document.mjs";

const REQUEST_VERSION = 1;
const STDERR_LINES_SHOWN = 5;

function buildRequest(model) {
  return {
    version: REQUEST_VERSION,
    frameworks: model.frameworks,
    ports: model.ports.map(({ path, symbol }) => ({ path, symbol })),
  };
}

function lastLines(text, count) {
  return text.trimEnd().split("\n").slice(-count).join("\n");
}

function failureMessage(command, status, stderr) {
  const shown = lastLines(stderr, STDERR_LINES_SHOWN);
  return (
    `The adapter command \`${command}\` failed with status ${status}.\n` +
    `${shown ? `Last lines of its standard error:\n${shown}\n` : ""}` +
    "Run the command by hand from the project root to see the full output, then fix it or the model's adapter."
  );
}

function execute(command, request, treeRoot, sourceRoot) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, {
      shell: true,
      cwd: treeRoot,
      env: { ...process.env, ARCH_SOURCE_ROOT: sourceRoot },
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.stdin.on("error", () => {});
    child.on("error", reject);
    child.on("close", (status) => resolve({ status, stdout, stderr }));
    child.stdin.end(JSON.stringify(request));
  });
}

export async function runAdapter(model, treeRoot, sourceRoot) {
  const command = model.adapter;
  if (!command) {
    throw new ToolingError(
      "The model names no adapter command. " +
        "Set \"adapter\" in the model to the command that prints the adapter document.",
    );
  }
  const { status, stdout, stderr } = await execute(command, buildRequest(model), treeRoot, sourceRoot);
  if (status !== 0) throw new ToolingError(failureMessage(command, status, stderr));
  return readAdapterDocument(stdout, command);
}
