#!/usr/bin/env node
// Drives headless Chromium through Playwright to capture parity snapshots
// without the agent ever seeing script text or snapshot bytes.
//
// capture-snapshots.mjs --out <dir> --viewport WxH [--viewport WxH ...]
//   [--prototype-url URL (--prototype-component Name | --prototype-root SELECTOR)]
//   [--real-url URL --real-root SELECTOR-OR-ATTR-VALUE]
//   [--color-scheme light|dark] [--wait-for SELECTOR] [--headed]

import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

function usageError(message) {
  process.stderr.write(`usage: ${message}\n`);
  process.exit(2);
}

function parseArgs(argv) {
  const options = {
    out: null,
    viewports: [],
    prototypeUrl: null,
    prototypeComponent: null,
    prototypeRoot: null,
    realUrl: null,
    realRoot: null,
    colorScheme: null,
    waitFor: null,
    headed: false,
  };

  const takeValue = (index, flag) => {
    if (index + 1 >= argv.length) usageError(`${flag} requires a value`);
    return argv[index + 1];
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    switch (arg) {
      case "--out":
        options.out = takeValue(i, arg);
        i += 1;
        break;
      case "--viewport": {
        const value = takeValue(i, arg);
        i += 1;
        const match = /^(\d+)x(\d+)$/.exec(value);
        if (!match) usageError(`--viewport must be WxH, got "${value}"`);
        options.viewports.push({ width: Number(match[1]), height: Number(match[2]), label: value });
        break;
      }
      case "--prototype-url":
        options.prototypeUrl = takeValue(i, arg);
        i += 1;
        break;
      case "--prototype-component":
        options.prototypeComponent = takeValue(i, arg);
        i += 1;
        break;
      case "--prototype-root":
        options.prototypeRoot = takeValue(i, arg);
        i += 1;
        break;
      case "--real-url":
        options.realUrl = takeValue(i, arg);
        i += 1;
        break;
      case "--real-root":
        options.realRoot = takeValue(i, arg);
        i += 1;
        break;
      case "--color-scheme": {
        const value = takeValue(i, arg);
        i += 1;
        if (value !== "light" && value !== "dark") usageError(`--color-scheme must be light or dark, got "${value}"`);
        options.colorScheme = value;
        break;
      }
      case "--wait-for":
        options.waitFor = takeValue(i, arg);
        i += 1;
        break;
      case "--headed":
        options.headed = true;
        break;
      default:
        usageError(`unrecognized argument "${arg}"`);
    }
  }

  if (!options.out) usageError("--out is required");
  if (options.viewports.length === 0) usageError("at least one --viewport is required");

  const hasPrototype = Boolean(options.prototypeUrl);
  const hasReal = Boolean(options.realUrl);
  if (!hasPrototype && !hasReal) usageError("at least one of --prototype-url or --real-url is required");
  if (hasPrototype && Boolean(options.prototypeComponent) === Boolean(options.prototypeRoot)) {
    usageError("--prototype-url requires exactly one of --prototype-component or --prototype-root");
  }
  if (hasReal && !options.realRoot) usageError("--real-url requires --real-root");

  return options;
}

function resolvePlaywright() {
  const localRequire = createRequire(import.meta.url);
  const attempts = [];

  attempts.push("createRequire(import.meta.url)");
  try {
    return localRequire("playwright");
  } catch {
    // fall through to NODE_PATH entries
  }

  const nodePathEntries = (process.env.NODE_PATH || "").split(path.delimiter).filter(Boolean);
  for (const entry of nodePathEntries) {
    const candidate = path.join(entry, "playwright");
    attempts.push(candidate);
    try {
      return localRequire(candidate);
    } catch {
      // try the next entry
    }
  }

  const cwdCandidate = path.join(process.cwd(), "node_modules", "playwright");
  attempts.push(cwdCandidate);
  try {
    return localRequire(cwdCandidate);
  } catch {
    // exhausted
  }

  process.stderr.write(
    `playwright is not installed: looked in ${attempts.join(", ")}; install it in the project or set NODE_PATH\n`,
  );
  process.exit(2);
  return undefined;
}

function countNodes(node) {
  let total = 1;
  for (const child of node.children || []) total += countNodes(child);
  return total;
}

function sidesFrom(options) {
  const sides = [];
  if (options.prototypeUrl) {
    sides.push({
      side: "prototype",
      url: options.prototypeUrl,
      component: options.prototypeComponent,
      root: options.prototypeRoot,
    });
  }
  if (options.realUrl) {
    sides.push({ side: "real", url: options.realUrl, root: options.realRoot });
  }
  return sides;
}

async function resolvePrototypeRoot(page, config, viewport, rootFinderPath) {
  await page.addScriptTag({ path: rootFinderPath });
  const found = await page.evaluate((names) => globalThis.parityFindReactRoots(names), [config.component]);
  if (found.error) {
    return { error: `${config.side} ${viewport.label}: ${found.error}` };
  }
  const roots = (found.roots && found.roots[config.component]) || [];
  if (roots.length === 0) {
    return { error: `${config.side} ${viewport.label}: no roots found for component "${config.component}"` };
  }
  if (roots.length > 1) {
    const selectors = roots.map((entry) => entry.selector).join(", ");
    return {
      error: `${config.side} ${viewport.label}: ${roots.length} roots found for component "${config.component}": ${selectors}`,
    };
  }
  return { selector: roots[0].selector };
}

async function captureOne(browser, config, viewport, options, rootFinderPath, snapshotScriptPath, outDir) {
  const contextOptions = { viewport: { width: viewport.width, height: viewport.height } };
  if (options.colorScheme) contextOptions.colorScheme = options.colorScheme;
  const context = await browser.newContext(contextOptions);
  try {
    const page = await context.newPage();
    await page.goto(config.url, { waitUntil: "load" });
    if (options.waitFor) await page.waitForSelector(options.waitFor);

    let resolvedRoot = config.root;
    if (config.component) {
      const resolution = await resolvePrototypeRoot(page, config, viewport, rootFinderPath);
      if (resolution.error) return { ok: false, error: resolution.error };
      resolvedRoot = resolution.selector;
    }

    await page.addScriptTag({ path: snapshotScriptPath });
    const snapshot = await page.evaluate((root) => globalThis.paritySnapshot(root), resolvedRoot);
    if (snapshot && snapshot.error) {
      return { ok: false, error: `${config.side} ${viewport.label}: ${snapshot.error} for root "${resolvedRoot}"` };
    }

    const filePath = path.join(outDir, `${config.side}-${viewport.label}.json`);
    fs.writeFileSync(filePath, JSON.stringify(snapshot));
    const nodeCount = countNodes(snapshot.root);
    const { tag, role, name, geometry } = snapshot.root;
    const line = `${config.side} ${viewport.label} ${nodeCount} nodes root=${tag} ${role} "${name}" ${geometry.width}x${geometry.height} -> ${filePath}`;
    return { ok: true, line };
  } finally {
    await context.close();
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const playwright = resolvePlaywright();
  fs.mkdirSync(options.out, { recursive: true });

  const here = path.dirname(fileURLToPath(import.meta.url));
  const rootFinderPath = path.join(here, "find-react-roots.browser.js");
  const snapshotScriptPath = path.join(here, "snapshot-subtree.browser.js");
  const sides = sidesFrom(options);

  const browser = await playwright.chromium.launch({ headless: !options.headed });
  let hadFailure = false;
  try {
    for (const viewport of options.viewports) {
      for (const config of sides) {
        try {
          const result = await captureOne(browser, config, viewport, options, rootFinderPath, snapshotScriptPath, options.out);
          if (result.ok) {
            console.log(result.line);
          } else {
            hadFailure = true;
            console.error(result.error);
          }
        } catch (error) {
          hadFailure = true;
          console.error(`${config.side} ${viewport.label}: ${error.message}`);
        }
      }
    }
  } finally {
    await browser.close();
  }
  process.exit(hadFailure ? 1 : 0);
}

main();
