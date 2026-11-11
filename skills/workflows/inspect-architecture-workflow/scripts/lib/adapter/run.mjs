import { spawn } from "node:child_process";
import { ToolingError } from "../cli/errors.mjs";
import { readAdapterDocument } from "./document.mjs";

const REQUEST_VERSION = 1;
const STDERR_LINES_SHOWN = 5;
const DEFAULT_TIMEOUT_SECONDS = 600;
const TIMEOUT_VARIABLE = "ARCH_ADAPTER_TIMEOUT_SECONDS";

function timeoutSeconds() {
  const raw = process.env[TIMEOUT_VARIABLE];
  if (raw === undefined || raw === "") return DEFAULT_TIMEOUT_SECONDS;
  const seconds = Number(raw);
  if (!(seconds > 0)) {
    throw new ToolingError(`${TIMEOUT_VARIABLE} is "${raw}". Set it to a positive number of seconds or unset it.`);
  }
  return seconds;
}

function timeoutMessage(command, seconds) {
  return (
    `The adapter command \`${command}\` did not finish within ${seconds} seconds and was stopped. ` +
    `Raise the limit by setting ${TIMEOUT_VARIABLE} to a larger number of seconds, ` +
    "or run the command by hand from the project root to find out why it is slow."
  );
}

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

function execute(command, request, treeRoot, sourceRoot, seconds) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, {
      shell: true,
      detached: true,
      cwd: treeRoot,
      env: { ...process.env, ARCH_SOURCE_ROOT: sourceRoot },
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      process.kill(-child.pid, "SIGKILL");
    }, seconds * 1000);
    child.stdin.on("error", () => {});
    child.on("error", (error) => { clearTimeout(timer); reject(error); });
    child.on("close", (status) => {
      clearTimeout(timer);
      resolve({ status, stdout, stderr, timedOut });
    });
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
  const seconds = timeoutSeconds();
  const request = buildRequest(model);
  const { status, stdout, stderr, timedOut } = await execute(command, request, treeRoot, sourceRoot, seconds);
  if (timedOut) throw new ToolingError(timeoutMessage(command, seconds));
  if (status !== 0) throw new ToolingError(failureMessage(command, status, stderr));
  return readAdapterDocument(stdout, command);
}
