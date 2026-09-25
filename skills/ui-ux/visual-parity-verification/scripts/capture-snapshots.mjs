#!/usr/bin/env node

import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

const DEFAULT_TIMEOUT_MS = 30000;

const SIDE_FLAGS = {
  "--prototype-url": ["prototype", "url"],
  "--prototype-component": ["prototype", "component"],
  "--prototype-root": ["prototype", "root"],
  "--prototype-actions": ["prototype", "actions"],
  "--prototype-storage-state": ["prototype", "storageState"],
  "--real-url": ["real", "url"],
  "--real-root": ["real", "root"],
  "--real-actions": ["real", "actions"],
  "--real-storage-state": ["real", "storageState"],
};
const HEADER_FLAGS = { "--prototype-header": "prototype", "--real-header": "real" };
const VALUE_FLAGS = new Set([
  ...Object.keys(SIDE_FLAGS),
  ...Object.keys(HEADER_FLAGS),
  "--out",
  "--manifest",
  "--viewport",
  "--only-viewports",
  "--timeout",
  "--color-scheme",
  "--wait-for",
]);

const isSelector = (value) => typeof value === "string" && value.length > 0;
const STEP_SHAPES = {
  click: { accepts: isSelector, expects: "a selector string" },
  hover: { accepts: isSelector, expects: "a selector string" },
  waitFor: { accepts: isSelector, expects: "a selector string" },
  press: { accepts: isSelector, expects: "a key name string" },
  fill: {
    accepts: (value) => Array.isArray(value) && value.length === 2 && isSelector(value[0]) && typeof value[1] === "string",
    expects: "[selector, text]",
  },
  wait: { accepts: (value) => Number.isFinite(value) && value >= 0, expects: "a non-negative number of milliseconds" },
};
const STEP_KINDS = Object.keys(STEP_SHAPES);

class CaptureError extends Error {}

class StepFailure extends Error {
  constructor(index, kind, cause) {
    super(firstLine(cause));
    this.index = index;
    this.kind = kind;
  }
}

function usageError(message) {
  process.stderr.write(`usage: ${message}\n`);
  process.exit(2);
}

function firstLine(error) {
  return String(error && error.message ? error.message : error).split("\n")[0];
}

function parseViewport(value, describe) {
  const match = /^(\d+)x(\d+)$/.exec(value);
  if (!match) usageError(`${describe} must be WxH, got "${value}"`);
  return { width: Number(match[1]), height: Number(match[2]), label: value };
}

function parseHeader(value, flag) {
  const separator = value.indexOf(": ");
  if (separator <= 0) usageError(`${flag} must be "Name: value", got "${value}"`);
  return [value.slice(0, separator), value.slice(separator + 2)];
}

function parseTimeout(value) {
  if (!/^\d+$/.test(value) || Number(value) <= 0) {
    usageError(`--timeout must be a positive integer number of milliseconds, got "${value}"`);
  }
  return Number(value);
}

function emptySide(side) {
  return { side, url: null, component: null, root: null, actions: null, storageState: null, headers: {} };
}

function parseArgs(argv) {
  const options = {
    out: null,
    manifest: null,
    onlyViewports: null,
    viewports: [],
    timeout: DEFAULT_TIMEOUT_MS,
    colorScheme: null,
    waitFor: null,
    headed: false,
    prototype: emptySide("prototype"),
    real: emptySide("real"),
  };
  const seenSideFlags = new Set();

  const takeValue = (index, flag) => {
    if (index + 1 >= argv.length) usageError(`${flag} requires a value`);
    return argv[index + 1];
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--headed") {
      options.headed = true;
      continue;
    }
    if (!VALUE_FLAGS.has(arg)) usageError(`unrecognized argument "${arg}"`);
    const value = takeValue(i, arg);
    i += 1;
    if (SIDE_FLAGS[arg]) {
      const [side, field] = SIDE_FLAGS[arg];
      options[side][field] = value;
      seenSideFlags.add(arg);
      continue;
    }
    if (HEADER_FLAGS[arg]) {
      const [name, headerValue] = parseHeader(value, arg);
      options[HEADER_FLAGS[arg]].headers[name] = headerValue;
      seenSideFlags.add(arg);
      continue;
    }
    switch (arg) {
      case "--out":
        options.out = value;
        break;
      case "--manifest":
        options.manifest = value;
        break;
      case "--viewport":
        options.viewports.push(parseViewport(value, "--viewport"));
        break;
      case "--only-viewports":
        options.onlyViewports = new Set(value.split(",").map((entry) => parseViewport(entry, "--only-viewports entry").label));
        break;
      case "--timeout":
        options.timeout = parseTimeout(value);
        break;
      case "--color-scheme":
        if (value !== "light" && value !== "dark") usageError(`--color-scheme must be light or dark, got "${value}"`);
        options.colorScheme = value;
        break;
      case "--wait-for":
        options.waitFor = value;
        break;
      default:
        usageError(`unrecognized argument "${arg}"`);
    }
  }

  validateOptions(options, seenSideFlags);
  return options;
}

function validateOptions(options, seenSideFlags) {
  if (!options.out) usageError("--out is required");
  if (options.manifest) {
    const conflicts = [...seenSideFlags];
    if (options.viewports.length > 0) conflicts.push("--viewport");
    if (conflicts.length > 0) usageError(`--manifest cannot be combined with ${conflicts.join(", ")}`);
    return;
  }
  if (options.onlyViewports) usageError("--only-viewports requires --manifest");
  if (options.viewports.length === 0) usageError("at least one --viewport is required");
  if (!options.prototype.url && !options.real.url) usageError("at least one of --prototype-url or --real-url is required");

  for (const side of [options.prototype, options.real]) {
    const urlFlag = `--${side.side}-url`;
    const orphans = [...seenSideFlags].filter((flag) => flag !== urlFlag && flag.startsWith(`--${side.side}-`));
    if (!side.url && orphans.length > 0) {
      usageError(`${orphans.join(", ")} ${orphans.length > 1 ? "require" : "requires"} ${urlFlag}`);
    }
  }
  if (options.prototype.url && Boolean(options.prototype.component) === Boolean(options.prototype.root)) {
    usageError("--prototype-url requires exactly one of --prototype-component or --prototype-root");
  }
  if (options.real.url && !options.real.root) usageError("--real-url requires --real-root");
}

function loadJson(file, describe) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    return usageError(`${describe} ${file}: ${firstLine(error)}`);
  }
}

function parseStep(step, where) {
  const keys = step && typeof step === "object" && !Array.isArray(step) ? Object.keys(step) : [];
  if (keys.length !== 1) usageError(`${where}: each step is an object with exactly one key (${STEP_KINDS.join(", ")})`);
  const [kind] = keys;
  const shape = STEP_SHAPES[kind];
  if (!shape) usageError(`${where}: unknown step "${kind}" (expected one of ${STEP_KINDS.join(", ")})`);
  if (!shape.accepts(step[kind])) usageError(`${where}: "${kind}" expects ${shape.expects}`);
  return { kind, value: step[kind] };
}

function loadRecipe(file) {
  const steps = loadJson(file, "actions file");
  if (!Array.isArray(steps)) usageError(`actions file ${file} must be a JSON array of steps`);
  return steps.map((step, index) => parseStep(step, `actions file ${file} step ${index}`));
}

function loadRecipes(files) {
  const recipes = new Map([[null, []]]);
  for (const file of files) {
    if (file && !recipes.has(file)) recipes.set(file, loadRecipe(file));
  }
  return recipes;
}

function parseAuth(entry, where) {
  const auth = { storageState: null, headers: {} };
  if (entry === undefined || entry === null) return auth;
  if (typeof entry !== "object" || Array.isArray(entry)) usageError(`${where} must be an object with "storageState" and/or "headers"`);
  if (entry.storageState !== undefined && entry.storageState !== null) {
    if (!isSelector(entry.storageState)) usageError(`${where}.storageState must be a file path`);
    auth.storageState = entry.storageState;
  }
  if (entry.headers !== undefined && entry.headers !== null) {
    const headers = entry.headers;
    const valid = typeof headers === "object" && !Array.isArray(headers) && Object.values(headers).every((value) => typeof value === "string");
    if (!valid) usageError(`${where}.headers must be an object of header name to string value`);
    auth.headers = headers;
  }
  return auth;
}

function parseManifestRow(row, index, file) {
  const where = `manifest ${file} row ${index}`;
  for (const key of ["id", "protoRoute", "realRoute", "realRoot", "shareProto"]) {
    if (!isSelector(row[key])) usageError(`${where}: "${key}" must be a non-empty string`);
  }
  if (Boolean(row.protoComponent) === Boolean(row.protoRoot)) {
    usageError(`${where} (${row.id}): exactly one of "protoComponent" or "protoRoot" is required`);
  }
  if (!Array.isArray(row.viewports)) usageError(`${where} (${row.id}): "viewports" must be an array of WxH strings`);
  for (const key of ["protoActions", "realActions"]) {
    if (row[key] !== undefined && row[key] !== null && !isSelector(row[key])) usageError(`${where} (${row.id}): "${key}" must be a file path or null`);
  }
  return {
    id: row.id,
    protoRoute: row.protoRoute,
    realRoute: row.realRoute,
    protoComponent: row.protoComponent || null,
    protoRoot: row.protoRoot || null,
    realRoot: row.realRoot,
    viewports: row.viewports.map((value) => parseViewport(value, `${where} (${row.id}) viewport`)),
    protoActions: row.protoActions || null,
    realActions: row.realActions || null,
    shareProto: row.shareProto,
  };
}

function loadManifest(file) {
  const data = loadJson(file, "manifest");
  if (!data || typeof data !== "object" || !Array.isArray(data.rows)) usageError(`manifest ${file}: "rows" must be an array`);
  for (const key of ["prototypeUrl", "realUrl"]) {
    if (!isSelector(data[key])) usageError(`manifest ${file}: "${key}" must be a non-empty string`);
  }
  const rows = data.rows.map((row, index) => parseManifestRow(row, index, file));
  const ids = new Set();
  for (const row of rows) {
    if (ids.has(row.id)) usageError(`manifest ${file}: duplicate row id "${row.id}"`);
    ids.add(row.id);
  }
  for (const row of rows) {
    if (!ids.has(row.shareProto)) usageError(`manifest ${file} row ${row.id}: shareProto "${row.shareProto}" names no row`);
  }
  return {
    prototypeUrl: data.prototypeUrl,
    realUrl: data.realUrl,
    prototype: parseAuth(data.prototype, `manifest ${file}: "prototype"`),
    real: parseAuth(data.real, `manifest ${file}: "real"`),
    rows,
  };
}

function tryRequire(localRequire, spec) {
  try {
    return localRequire(spec);
  } catch (error) {
    if (error.code === "MODULE_NOT_FOUND") return null;
    throw error;
  }
}

function resolvePlaywright() {
  const localRequire = createRequire(import.meta.url);
  const attempts = ["createRequire(import.meta.url)"];

  const direct = tryRequire(localRequire, "playwright");
  if (direct) return direct;

  const nodePathEntries = (process.env.NODE_PATH || "").split(path.delimiter).filter(Boolean);
  for (const entry of nodePathEntries) {
    const candidate = path.join(entry, "playwright");
    attempts.push(candidate);
    const resolved = tryRequire(localRequire, candidate);
    if (resolved) return resolved;
  }

  const cwdCandidate = path.join(process.cwd(), "node_modules", "playwright");
  attempts.push(cwdCandidate);
  const resolved = tryRequire(localRequire, cwdCandidate);
  if (resolved) return resolved;

  process.stderr.write(
    `playwright is not installed: looked in ${attempts.join(", ")}; install it in the project or set NODE_PATH\n`,
  );
  return process.exit(2);
}

function countNodes(node) {
  let total = 1;
  for (const child of node.children || []) total += countNodes(child);
  return total;
}

function countDirectChildren(node) {
  let total = 0;
  for (const child of node.children || []) total += child.wrapper ? countDirectChildren(child) : 1;
  return total;
}

class ContextPool {
  constructor(browser, colorScheme) {
    this.browser = browser;
    this.colorScheme = colorScheme;
    this.contexts = new Map();
  }

  async acquire(viewport, auth) {
    const key = JSON.stringify([viewport.label, auth.storageState || "", this.colorScheme || "", auth.headers]);
    if (this.contexts.has(key)) return this.contexts.get(key);
    const contextOptions = { viewport: { width: viewport.width, height: viewport.height } };
    if (this.colorScheme) contextOptions.colorScheme = this.colorScheme;
    if (auth.storageState) contextOptions.storageState = auth.storageState;
    const context = await this.browser.newContext(contextOptions);
    if (Object.keys(auth.headers).length > 0) await context.setExtraHTTPHeaders(auth.headers);
    this.contexts.set(key, context);
    return context;
  }

  async closeAll() {
    for (const context of this.contexts.values()) await context.close();
    this.contexts.clear();
  }
}

async function runStep(page, step, timeout) {
  const { kind, value } = step;
  if (kind === "click") return page.click(value, { timeout });
  if (kind === "hover") return page.hover(value, { timeout });
  if (kind === "press") return page.keyboard.press(value);
  if (kind === "fill") return page.fill(value[0], value[1], { timeout });
  if (kind === "wait") return page.waitForTimeout(value);
  return page.waitForSelector(value, { timeout });
}

async function runRecipe(page, steps, timeout) {
  for (const [index, step] of steps.entries()) {
    try {
      await runStep(page, step, timeout);
    } catch (error) {
      throw new StepFailure(index, step.kind, error);
    }
  }
  await page.mouse.move(0, 0);
  await page.waitForLoadState("networkidle", { timeout });
}

async function resolvePrototypeRoot(page, job, rootFinderPath) {
  await page.addScriptTag({ path: rootFinderPath });
  const found = await page.evaluate((names) => globalThis.parityFindReactRoots(names), [job.component]);
  if (found.error) throw new CaptureError(found.error);
  const roots = (found.roots && found.roots[job.component]) || [];
  if (roots.length === 0) throw new CaptureError(`no roots found for component "${job.component}"`);
  if (roots.length > 1) {
    const selectors = roots.map((entry) => entry.selector).join(", ");
    throw new CaptureError(`${roots.length} roots found for component "${job.component}": ${selectors}`);
  }
  return roots[0].selector;
}

function writeSnapshot(filePath, snapshot) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.rmSync(filePath, { force: true });
  fs.writeFileSync(filePath, JSON.stringify(snapshot));
}

function summaryOf(snapshot) {
  const { tag, role, name, geometry } = snapshot.root;
  const nodes = `${countNodes(snapshot.root)} nodes children=${countDirectChildren(snapshot.root)}`;
  return `${nodes} root=${tag} ${role} "${name}" ${geometry.width}x${geometry.height}`;
}

function summaryLine(job, summary, sharedFrom = null) {
  const shared = sharedFrom ? ` (shared from ${sharedFrom})` : "";
  return `${job.side} ${job.viewport.label} ${summary}${shared} -> ${job.filePath}`;
}

function describeFailure(job, error) {
  const prefix = `${job.side} ${job.viewport.label}`;
  const line = error instanceof StepFailure
    ? `${prefix} step ${error.index} ${error.kind}: ${error.message}`
    : `${prefix}: ${firstLine(error)}`;
  return job.rowId ? `${line} (row ${job.rowId})` : line;
}

async function captureOne(job, runtime) {
  const { options, rootFinderPath, snapshotScriptPath } = runtime;
  const context = await runtime.pool.acquire(job.viewport, job.auth);
  const page = await context.newPage();
  try {
    await page.goto(job.url, { waitUntil: "load", timeout: options.timeout });
    if (options.waitFor) await page.waitForSelector(options.waitFor, { timeout: options.timeout });
    await runRecipe(page, job.steps, options.timeout);

    const resolvedRoot = job.component ? await resolvePrototypeRoot(page, job, rootFinderPath) : job.root;
    await page.addScriptTag({ path: snapshotScriptPath });
    const snapshot = await page.evaluate((root) => globalThis.paritySnapshot(root), resolvedRoot);
    if (snapshot && snapshot.error) throw new CaptureError(`${snapshot.error} for root "${resolvedRoot}"`);

    writeSnapshot(job.filePath, snapshot);
    return summaryOf(snapshot);
  } finally {
    await page.close();
  }
}

async function runCapture(job, runtime) {
  try {
    const summary = await captureOne(job, runtime);
    console.log(summaryLine(job, summary));
    return summary;
  } catch (error) {
    runtime.failed = true;
    console.error(describeFailure(job, error));
    return null;
  }
}

function sideJob(side, viewport, runtime) {
  return {
    side: side.side,
    rowId: null,
    viewport,
    url: side.url,
    component: side.component,
    root: side.root,
    steps: runtime.recipes.get(side.actions),
    auth: { storageState: side.storageState, headers: side.headers },
    filePath: path.join(runtime.options.out, `${side.side}-${viewport.label}.json`),
  };
}

async function runSides(runtime) {
  const { options } = runtime;
  for (const viewport of options.viewports) {
    for (const side of [options.prototype, options.real]) {
      if (side.url) await runCapture(sideJob(side, viewport, runtime), runtime);
    }
  }
}

function rowFilePath(rowId, side, viewport, outDir) {
  return path.join(outDir, rowId, `${side}-${viewport.label}.json`);
}

function prototypeJob(manifest, row, viewport, runtime) {
  return {
    side: "prototype",
    rowId: row.id,
    viewport,
    url: new URL(row.protoRoute, manifest.prototypeUrl).href,
    component: row.protoComponent,
    root: row.protoRoot,
    steps: runtime.recipes.get(row.protoActions),
    auth: manifest.prototype,
    filePath: rowFilePath(row.id, "prototype", viewport, runtime.options.out),
  };
}

function realJob(manifest, row, viewport, runtime) {
  return {
    side: "real",
    rowId: row.id,
    viewport,
    url: new URL(row.realRoute, manifest.realUrl).href,
    component: null,
    root: row.realRoot,
    steps: runtime.recipes.get(row.realActions),
    auth: manifest.real,
    filePath: rowFilePath(row.id, "real", viewport, runtime.options.out),
  };
}

function linkOrCopy(from, to) {
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.rmSync(to, { force: true });
  try {
    fs.linkSync(from, to);
  } catch {
    fs.copyFileSync(from, to);
  }
}

function sharePrototype(row, source, viewport, summary, runtime) {
  const outDir = runtime.options.out;
  const target = { side: "prototype", viewport, filePath: rowFilePath(row.id, "prototype", viewport, outDir) };
  if (!summary) {
    runtime.failed = true;
    console.error(`prototype ${viewport.label}: shared prototype from ${source.id} was not captured (row ${row.id})`);
    return;
  }
  linkOrCopy(rowFilePath(source.id, "prototype", viewport, outDir), target.filePath);
  console.log(summaryLine(target, summary, source.id));
}

async function runManifest(manifest, runtime) {
  const rowsById = new Map(manifest.rows.map((row) => [row.id, row]));
  const prototypeSummaries = new Map();
  const ensurePrototype = async (source, viewport) => {
    const key = `${source.id} ${viewport.label}`;
    if (!prototypeSummaries.has(key)) {
      prototypeSummaries.set(key, await runCapture(prototypeJob(manifest, source, viewport, runtime), runtime));
    }
    return prototypeSummaries.get(key);
  };

  const { onlyViewports } = runtime.options;
  for (const row of manifest.rows) {
    const viewports = onlyViewports ? row.viewports.filter((viewport) => onlyViewports.has(viewport.label)) : row.viewports;
    if (viewports.length === 0) {
      console.error(`skip ${row.id}: no viewports`);
      continue;
    }
    const source = rowsById.get(row.shareProto);
    for (const viewport of viewports) {
      const summary = await ensurePrototype(source, viewport);
      if (source !== row) sharePrototype(row, source, viewport, summary, runtime);
      await runCapture(realJob(manifest, row, viewport, runtime), runtime);
    }
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const manifest = options.manifest ? loadManifest(options.manifest) : null;
  const actionFiles = manifest
    ? manifest.rows.flatMap((row) => [row.protoActions, row.realActions])
    : [options.prototype.actions, options.real.actions];
  const recipes = loadRecipes(actionFiles);
  const playwright = resolvePlaywright();
  fs.mkdirSync(options.out, { recursive: true });

  const here = path.dirname(fileURLToPath(import.meta.url));
  const browser = await playwright.chromium.launch({ headless: !options.headed });
  const runtime = {
    options,
    recipes,
    pool: new ContextPool(browser, options.colorScheme),
    rootFinderPath: path.join(here, "find-react-roots.browser.js"),
    snapshotScriptPath: path.join(here, "snapshot-subtree.browser.js"),
    failed: false,
  };
  try {
    if (manifest) await runManifest(manifest, runtime);
    else await runSides(runtime);
  } finally {
    await runtime.pool.closeAll();
    await browser.close();
  }
  process.exit(runtime.failed ? 1 : 0);
}

main().catch((error) => {
  console.error(firstLine(error));
  process.exit(1);
});
