#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { parseArgs } from "node:util";
import { apcaLc, compositeOver, parseColor, resolveBackground } from "./lib/color.mjs";
import { launchBrowser, toPageUrl } from "./lib/browser.mjs";
import { installPageHelpers } from "./lib/page-helpers.mjs";
import { PAGE_CONSTANTS, auditGeometry, auditTextResize, collectNamedElements } from "./lib/geometry-page.mjs";

const VERSION = "1.0.0";

const DOCUMENT_RULES = [
  "DOC-LANG", "DOC-TITLE", "VIEWPORT-ZOOM", "LANDMARKS", "TABINDEX-VALUE", "TABINDEX-NATIVE", "AUTOFOCUS",
  "MEDIA-MUTE-PRESSED", "MEDIA-VOLUME-RANGE", "CONTROL-NAME", "LABEL-ASSOC", "ARIA-REFS", "IMG-ALT",
];
const VIEWPORT_RULES = [
  "FOCUS-HIDDEN", "TARGET-SIZE", "TARGET-GAP-BUTTON", "TARGET-GAP", "REFLOW-OVERFLOW", "FORM-OPTIONS-VISIBLE",
  "BODY-FONT-SIZE", "LINE-LENGTH", "SPACING-RATIO", "APCA-NONTEXT-15", "APCA-ICON-30", "APCA-TEXT-SIZE", "TEXT-RESIZE-200",
];
const ALL_RULES = [...DOCUMENT_RULES, ...VIEWPORT_RULES];

const HELP = `geometry-audit ${VERSION}: deterministic rendered-DOM geometry and accessibility checks

Usage:
  node geometry-audit.mjs [options] <input>...
  <input>: http(s) URL, .html path, or .txt file listing one URL or path per line

Options:
  --viewports <list>          WIDTH or WIDTHxHEIGHT, comma-separated (default 320,375,1440)
  --mobile-viewports <list>   widths where FORM-OPTIONS-VISIBLE runs (default 320,375)
  --pt-scale <n>              multiplier for the 48px target and 16px/8px gap thresholds (default 1)
  --body-text-selector <css>  body text for LINE-LENGTH and BODY-FONT-SIZE (default "main p")
  --measure-min <n>           minimum average characters per line (default 45)
  --measure-max <n>           maximum average characters per line (default 75)
  --min-body-font <px>        body font-size floor (default 16)
  --apca-table <path>         APCA font table; enables APCA-TEXT-SIZE
  --apca-targets <path>       JSON map of selector -> declared Lc target (15 or 30); data-apca-target also read
  --exclude <css>             subtrees skipped by every geometry check
  --rules <ids> / --skip-rules <ids>
  --wait load|networkidle|<ms>   (default networkidle)
  --out <path>                JSON report destination (default stdout)
  --fail-on-indeterminate     indeterminate results fail the run
  --list-rules                print rule IDs and exit

Rules: ${ALL_RULES.join(", ")}

Notes:
  Inline links inside running text are exempt from target size and gap checks.
  Checkbox and radio targets include their label. Controls revealed on focus (skip links) are measured focused.
  LINE-LENGTH minimum is not enforced when the text already spans 80% of the viewport.
  SPACING-RATIO: the gap under a heading must be smaller than the gap above it, and the largest gap
  inside a section/article/fieldset/li group must not exceed the separation between sibling groups.

Exit: 0 pass, 1 violation, 2 usage or config error, 3 browser or navigation error.`;

class UsageError extends Error {}

const list = (text) => text.split(",").map((part) => part.trim()).filter(Boolean);

function readJson(file, flag) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    throw new UsageError(`${flag} ${file}: ${error.message}`);
  }
}

function parseViewport(text) {
  const [width, height] = text.toLowerCase().split("x").map(Number);
  if (!Number.isInteger(width) || width <= 0 || (height !== undefined && !(height > 0))) {
    throw new UsageError(`invalid viewport "${text}"`);
  }
  return { width, height: height ?? (width < 1024 ? 800 : 900) };
}

function expandInputs(inputs) {
  return inputs.flatMap((input) => {
    if (!input.toLowerCase().endsWith(".txt")) return [input];
    if (!fs.existsSync(input)) throw new UsageError(`input not found: ${input}`);
    const base = path.dirname(input);
    return fs
      .readFileSync(input, "utf8")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => (/^https?:\/\//i.test(line) ? line : path.resolve(base, line)));
  });
}

const WEIGHT_KEYS = ["100", "200", "300", "400", "500", "600", "700", "800", "900"];

function loadApcaTable(file) {
  const table = readJson(file, "--apca-table");
  const valid =
    Array.isArray(table.tiers) &&
    table.tiers.every(
      (tier) => typeof tier.lc === "number" && WEIGHT_KEYS.every((key) => key in (tier.minFontPxByWeight ?? {})),
    );
  if (!valid) throw new UsageError(`--apca-table ${file}: every tier needs lc and minFontPxByWeight for weights 100..900`);
  return { source: table.source ?? file, tiers: [...table.tiers].sort((x, y) => y.lc - x.lc) };
}

function resolveLc(item) {
  const background = resolveBackground(item.bg);
  if (background.inconclusive) return null;
  const color = parseColor(item.fg);
  return Math.abs(apcaLc(compositeOver(color, background.color, color.a * item.opacity), background.color));
}

function judgeApcaItem(item, table) {
  const base = { ruleId: item.ruleId, selector: item.selector };
  const lc = resolveLc(item);
  if (lc === null) {
    return { ...base, status: "indeterminate", measured: null, expected: "measurable", reason: "complex-background" };
  }
  const measuredLc = Math.round(lc * 10) / 10;
  if (item.ruleId !== "APCA-TEXT-SIZE") {
    const expected = `Lc >= ${item.target}, >= ${item.minDimension} px`;
    if (lc < item.target) {
      return { ...base, status: "fail", measured: { lc: measuredLc }, expected, corrective: { lc: item.target } };
    }
    if (item.dimension < item.minDimension) {
      const measured = { smallestSolidDimensionPx: item.dimension };
      return { ...base, status: "fail", measured, expected, corrective: { minDimensionPx: item.minDimension } };
    }
    return null;
  }

  const measured = { lc: measuredLc, fontSizePx: item.fontSizePx, fontWeight: item.fontWeight };
  const tier = table.tiers.find((candidate) => candidate.lc <= lc);
  if (!tier) {
    const lowest = table.tiers[table.tiers.length - 1].lc;
    return { ...base, status: "fail", measured, expected: `Lc >= ${lowest}`, corrective: { lc: lowest } };
  }
  const weightKey = WEIGHT_KEYS.filter((key) => Number(key) <= item.fontWeight).pop() ?? "100";
  const minimum = tier.minFontPxByWeight[weightKey];
  const allowedWeights = WEIGHT_KEYS.filter((key) => tier.minFontPxByWeight[key] !== null);
  if (minimum === null) {
    return { ...base, status: "fail", measured, expected: `weight >= ${allowedWeights[0]}`, corrective: { fontWeight: Number(allowedWeights[0]) } };
  }
  if (item.fontSizePx >= minimum) return null;
  const heavier = allowedWeights.find((key) => Number(key) > item.fontWeight && tier.minFontPxByWeight[key] <= item.fontSizePx);
  const corrective = heavier ? { fontWeight: Number(heavier) } : { fontSizePx: minimum };
  return { ...base, status: "fail", measured, expected: `font-size >= ${minimum}px at Lc ${tier.lc}, weight ${weightKey}`, corrective };
}

async function auditInput(page, input, settings) {
  const url = toPageUrl(input);
  const results = [];
  const ran = new Set();
  let title = null;
  let excluded = [];

  for (const [index, viewport] of settings.viewports.entries()) {
    const label = `${viewport.width}x${viewport.height}`;
    await page.setViewport(viewport.width, viewport.height);
    await page.navigate(url, settings.wait);
    await page.evaluate(installPageHelpers);
    const namedCount = await page.evaluate(collectNamedElements, PAGE_CONSTANTS);
    const names = [];
    for (let position = 0; position < namedCount; position += 1) {
      names.push(await page.accessibleName(`window.__uxAudit.named[${position}]`));
    }

    const outcome = await page.evaluate(auditGeometry, {
      constants: PAGE_CONSTANTS,
      rules: settings.rules,
      documentChecks: index === 0,
      isMobileViewport: settings.mobileViewports.includes(viewport.width),
      names,
      ptScale: settings.ptScale,
      bodyTextSelector: settings.bodyTextSelector,
      measureMin: settings.measureMin,
      measureMax: settings.measureMax,
      minBodyFontPx: settings.minBodyFontPx,
      exclude: settings.exclude,
      apcaTargets: settings.apcaTargets,
    });
    title ??= outcome.title;
    excluded = outcome.excluded;
    outcome.ran.forEach((ruleId) => ran.add(ruleId));
    const judged = outcome.apca.map((item) => judgeApcaItem(item, settings.apcaTable)).filter(Boolean);
    const isDocumentRule = (result) => DOCUMENT_RULES.includes(result.ruleId);
    for (const result of [...outcome.results, ...judged]) {
      results.push({ ...result, viewport: isDocumentRule(result) ? null : label });
    }

    if (settings.rules.includes("TEXT-RESIZE-200")) {
      ran.add("TEXT-RESIZE-200");
      for (const result of await page.evaluate(auditTextResize)) results.push({ ...result, viewport: label });
    }
  }

  const ordered = results.map(({ ruleId, status, viewport, selector, ...rest }) => ({ ruleId, status, viewport, selector, ...rest }));
  return { input, title, excluded, results: ordered, ran };
}

function flagDuplicateTitles(pages) {
  const byTitle = new Map();
  for (const page of pages) {
    if (page.title) byTitle.set(page.title, [...(byTitle.get(page.title) ?? []), page]);
  }
  for (const sharing of byTitle.values()) {
    if (sharing.length < 2) continue;
    for (const page of sharing) {
      if (!page.ran.has("DOC-TITLE")) continue;
      page.results.push({
        ruleId: "DOC-TITLE", status: "fail", viewport: null, selector: "head > title",
        measured: { duplicateInputs: sharing.map((other) => other.input) }, expected: "unique, non-empty title", corrective: "add unique <title>",
      });
    }
  }
}

function parseSettings(argv) {
  let parsed;
  try {
    parsed = parseArgs({
      args: argv,
      allowPositionals: true,
      options: {
        viewports: { type: "string", default: "320,375,1440" },
        "mobile-viewports": { type: "string", default: "320,375" },
        "pt-scale": { type: "string", default: "1" },
        "apca-table": { type: "string" },
        "apca-targets": { type: "string" },
        "body-text-selector": { type: "string", default: "main p" },
        "measure-min": { type: "string", default: "45" },
        "measure-max": { type: "string", default: "75" },
        "min-body-font": { type: "string", default: "16" },
        exclude: { type: "string" },
        rules: { type: "string" },
        "skip-rules": { type: "string" },
        wait: { type: "string", default: "networkidle" },
        out: { type: "string" },
        "fail-on-indeterminate": { type: "boolean", default: false },
        "list-rules": { type: "boolean", default: false },
        help: { type: "boolean", short: "h", default: false },
      },
    });
  } catch (error) {
    throw new UsageError(error.message);
  }
  const { values, positionals } = parsed;
  if (values.help) return { help: true };
  if (values["list-rules"]) return { listRules: true };
  if (positionals.length === 0) throw new UsageError("no input given; pass a URL or an .html path");

  const number = (flag) => {
    const value = Number(values[flag]);
    if (!(value > 0)) throw new UsageError(`--${flag} must be a positive number`);
    return value;
  };
  const viewports = list(values.viewports).map(parseViewport);
  const mobileViewports = list(values["mobile-viewports"]).map(Number).filter((width) => viewports.some((v) => v.width === width));
  const requested = values.rules ? list(values.rules) : ALL_RULES;
  const skipped = values["skip-rules"] ? list(values["skip-rules"]) : [];
  const unknown = [...requested, ...skipped].filter((ruleId) => !ALL_RULES.includes(ruleId));
  if (unknown.length) throw new UsageError(`unknown rule: ${unknown.join(", ")}`);
  if (values.rules && requested.includes("APCA-TEXT-SIZE") && !values["apca-table"]) {
    throw new UsageError("APCA-TEXT-SIZE needs --apca-table");
  }
  const apcaTable = values["apca-table"] ? loadApcaTable(values["apca-table"]) : null;
  const rules = requested.filter((ruleId) => !skipped.includes(ruleId) && (ruleId !== "APCA-TEXT-SIZE" || apcaTable));
  const wait = /^\d+$/.test(values.wait) ? Number(values.wait) : values.wait;
  if (typeof wait === "string" && !["load", "networkidle"].includes(wait)) throw new UsageError("--wait is load, networkidle or milliseconds");
  const inputs = expandInputs(positionals);
  inputs.forEach((input) => {
    try {
      toPageUrl(input);
    } catch (error) {
      throw new UsageError(error.message);
    }
  });

  return {
    inputs,
    viewports,
    mobileViewports,
    rules,
    wait,
    apcaTable,
    apcaTargets: values["apca-targets"] ? readJson(values["apca-targets"], "--apca-targets") : {},
    ptScale: number("pt-scale"),
    measureMin: number("measure-min"),
    measureMax: number("measure-max"),
    minBodyFontPx: number("min-body-font"),
    bodyTextSelector: values["body-text-selector"],
    exclude: values.exclude ?? null,
    out: values.out ?? null,
    failOnIndeterminate: values["fail-on-indeterminate"],
  };
}

function emit(report, out) {
  const text = JSON.stringify(report, null, 2);
  if (out) fs.writeFileSync(out, `${text}\n`);
  else console.log(text);
}

async function main() {
  const settings = parseSettings(process.argv.slice(2));
  if (settings.help) {
    console.log(HELP);
    return 0;
  }
  if (settings.listRules) {
    console.log(ALL_RULES.join("\n"));
    return 0;
  }

  const browser = await launchBrowser();
  let pages;
  try {
    const page = await browser.newPage();
    pages = [];
    for (const input of settings.inputs) pages.push(await auditInput(page, input, settings));
  } finally {
    await browser.close();
  }
  flagDuplicateTitles(pages);

  const all = pages.flatMap((page) => page.results);
  const violations = all.filter((result) => result.status === "fail");
  const indeterminate = all.filter((result) => result.status === "indeterminate");
  const byRule = {};
  for (const result of violations) byRule[result.ruleId] = (byRule[result.ruleId] ?? 0) + 1;
  const exitCode = violations.length || (settings.failOnIndeterminate && indeterminate.length) ? 1 : 0;

  emit(
    {
      tool: "geometry-auditor",
      version: VERSION,
      config: {
        viewports: settings.viewports.map((viewport) => `${viewport.width}x${viewport.height}`),
        mobileViewports: settings.mobileViewports,
        ptScale: settings.ptScale,
        measure: { min: settings.measureMin, max: settings.measureMax },
        minBodyFontPx: settings.minBodyFontPx,
        apcaTableSource: settings.apcaTable?.source ?? null,
        rules: settings.rules,
        browser: browser.product,
      },
      summary: { passed: exitCode === 0, violations: violations.length, indeterminate: indeterminate.length, byRule, exitCode },
      pages: pages.map(({ ran, ...page }) => ({
        ...page,
        passedRules: [...ran].filter((ruleId) => !page.results.some((result) => result.ruleId === ruleId && result.status === "fail")),
      })),
    },
    settings.out,
  );
  return exitCode;
}

main().then(
  (code) => {
    process.exitCode = code;
  },
  (error) => {
    const exitCode = error instanceof UsageError ? 2 : 3;
    console.error(JSON.stringify({ tool: "geometry-auditor", error: error.message, exitCode }));
    process.exitCode = exitCode;
  },
);
