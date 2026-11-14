#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import {
  apcaLc,
  compositeOver,
  correctiveColor,
  oklchLightness,
  parseColor,
  resolveBackground,
  toHex,
  wcagRatio,
} from "./lib/color.mjs";

const VERSION = "1.0.0";
const BUNDLED_LOOKUP = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "assets", "apca-text-tiers.json");

const HELP = `contrast-audit ${VERSION}: deterministic WCAG 2.x + APCA contrast checks

Usage:
  node contrast-audit.mjs tokens --pair <fg>:<bg>[:<kind>[:<fontSizePx>:<fontWeight>]] ...
  node contrast-audit.mjs tokens --input <pairs.json>
  node contrast-audit.mjs dom --html <path> | --url <url> [--viewports 320,375,1440]

Colors: #RGB, #RRGGBB, #RRGGBBAA, rgb(), hsl(), oklch(), oklab(). Quote pairs in the shell.
Kinds:  text (default, 16px/400 unless given), icon-solid, icon-outline, ui-component,
        input-border, selection, button-boundary, button-pair, discernible
pairs.json: [{ "id", "fg", "bg", "kind", "fontSizePx", "fontWeight", "backdrop"? }]

Options:
  --method wcag|apca|both   contrast models; with both, the stricter bound wins (default both)
  --level aa|aaa            aaa raises every APCA threshold by 15 Lc (default aa)
  --apca-lookup <path|none> APCA text tiers (default: bundled assets/apca-text-tiers.json)
  --allow-inconclusive      inconclusive results do not set exit code 1
  --output <path|->         JSON report destination (default stdout)
  --format json|text        text prints one line per violation
  --verbose                 include passes in the report
  dom: --wait-for <selector>  --ignore <selector> (repeatable)  --icon-fonts <a,b>

Exit: 0 pass, 1 violation or unresolved inconclusive, 2 usage or input error.`;

class UsageError extends Error {}

const NON_TEXT_RULES = {
  "icon-solid": [["CT-WCAG-ICON", "wcag", 3], ["CT-APCA-ICON-SOLID", "apca", 30]],
  "icon-outline": [["CT-WCAG-ICON", "wcag", 3], ["CT-APCA-ICON-FINE", "apca", 45]],
  "ui-component": [["CT-WCAG-UI-COMPONENT", "wcag", 3], ["CT-APCA-NONTEXT-DISCERNIBLE", "apca", 15]],
  "input-border": [["CT-WCAG-INPUT-BORDER", "wcag", 3], ["CT-APCA-NONTEXT-DISCERNIBLE", "apca", 15]],
  "button-boundary": [["CT-WCAG-BUTTON-BOUNDARY", "wcag", 3], ["CT-APCA-NONTEXT-DISCERNIBLE", "apca", 15]],
  "button-pair": [["CT-WCAG-BUTTON-PAIR", "wcag", 3]],
  selection: [["CT-WCAG-SELECTION", "wcag", 4.5]],
  discernible: [["CT-APCA-NONTEXT-DISCERNIBLE", "apca", 15]],
};

function isLargeText(sizePx, weight) {
  return (weight >= 700 && sizePx >= 18.67) || sizePx > 24;
}

function apcaTextTier(lookup, sizePx, weight) {
  const eligible = lookup.filter((row) => row.fontWeight <= weight && row.minFontSizePx <= sizePx);
  return eligible.length ? Math.min(...eligible.map((row) => row.minLc)) : null;
}

function requirementsFor(item, options) {
  const requirements = [];
  if (item.kind === "text") {
    const large = isLargeText(item.fontSizePx, item.fontWeight);
    requirements.push({
      ruleId: large ? "CT-WCAG-TEXT-LARGE" : "CT-WCAG-TEXT-NORMAL",
      metric: "wcag",
      threshold: large ? 3 : 4.5,
    });
    if (options.lookup) {
      const tier = apcaTextTier(options.lookup, item.fontSizePx, item.fontWeight);
      requirements.push({ ruleId: "CT-APCA-TEXT", metric: "apca", threshold: tier, belowSmallestTier: tier === null });
    } else {
      requirements.push({ ruleId: "CT-APCA-TEXT", metric: "apca", skipped: "no-apca-lookup" });
    }
  } else {
    for (const [ruleId, metric, threshold] of NON_TEXT_RULES[item.kind]) requirements.push({ ruleId, metric, threshold });
  }
  const offset = options.level === "aaa" ? 15 : 0;
  return requirements
    .filter((requirement) => options.method === "both" || options.method === requirement.metric)
    .map((requirement) =>
      requirement.metric === "apca" && typeof requirement.threshold === "number"
        ? { ...requirement, threshold: requirement.threshold + offset }
        : requirement,
    );
}

const measure = (metric, foreground, background) =>
  metric === "wcag" ? wcagRatio(foreground, background) : Math.abs(apcaLc(foreground, background));
const metricName = (metric) => (metric === "wcag" ? "wcag-ratio" : "apca-lc");
const roundFor = (metric, value) => (metric === "wcag" ? Math.round(value * 100) / 100 : Math.round(value * 10) / 10);

function resolvePair(pair) {
  const background = resolveBackground(pair.bg);
  if (background.inconclusive) return background;
  let foreground;
  if (pair.fgLayers) {
    const layered = resolveBackground(pair.fgLayers);
    if (layered.inconclusive) return layered;
    foreground = layered.color;
  } else {
    const color = parseColor(pair.fg);
    foreground = compositeOver(color, background.color, color.a * pair.opacity);
  }
  return { foreground, background: background.color };
}

function evaluateItem(item, options, report, context) {
  const identity = {
    viewport: context.viewport ?? null,
    selector: item.selector ? item.selector + (item.pseudo ?? "") : null,
    tokenId: item.tokenId ?? null,
  };
  const requirements = requirementsFor(item, options);
  const active = requirements.filter((requirement) => !requirement.skipped);
  for (const requirement of requirements.filter((r) => r.skipped)) {
    if (!report.skipped.some((entry) => entry.ruleId === requirement.ruleId)) {
      report.skipped.push({ ruleId: requirement.ruleId, reason: requirement.skipped });
    }
  }

  const resolved = item.pairs.map(resolvePair);
  const reason = item.inconclusiveReason ?? resolved.find((pair) => pair.inconclusive)?.inconclusive;
  if (reason) {
    for (const requirement of active) report.inconclusive.push({ ruleId: requirement.ruleId, ...identity, reason });
    return;
  }

  const best = resolved.reduce((x, y) =>
    wcagRatio(y.foreground, y.background) > wcagRatio(x.foreground, x.background) ? y : x,
  );
  const measurable = active.filter((requirement) => typeof requirement.threshold === "number");
  const pairPasses = (foreground, background) =>
    measurable.every((requirement) => measure(requirement.metric, foreground, background) >= requirement.threshold);
  let correction;

  for (const requirement of active) {
    const value = Math.max(...resolved.map((pair) => measure(requirement.metric, pair.foreground, pair.background)));
    const measured = { metric: metricName(requirement.metric), value: roundFor(requirement.metric, value) };
    if (!requirement.belowSmallestTier && value >= requirement.threshold) {
      report.passes.push({ ruleId: requirement.ruleId, ...identity, measured });
      continue;
    }
    correction ??= measurable.length ? correctiveColor(best.foreground, best.background, pairPasses) : null;
    const corrected = correction && {
      foreground: correction.target === "foreground" ? correction.color : best.foreground,
      background: correction.target === "background" ? correction.color : best.background,
    };
    const violation = {
      ruleId: requirement.ruleId,
      ...identity,
      foreground: toHex(best.foreground),
      background: toHex(best.background),
      measured,
      expected: { metric: measured.metric, operator: ">=", value: requirement.threshold ?? null },
      correctiveTarget: correction?.target ?? null,
      correctiveValue: correction ? toHex(correction.color) : null,
      correctiveLightness: correction ? oklchLightness(correction.color) : null,
      correctiveMeasured: corrected
        ? roundFor(requirement.metric, measure(requirement.metric, corrected.foreground, corrected.background))
        : null,
      correctiveReason: requirement.belowSmallestTier ? "below-smallest-tier" : correction ? null : "unreachable",
    };
    if (item.kind === "text" || item.fontSizePx) {
      Object.assign(violation, {
        textSample: item.textSample ?? null,
        fontSizePx: item.fontSizePx,
        fontWeight: item.fontWeight,
        textClass: isLargeText(item.fontSizePx, item.fontWeight) ? "large" : "normal",
      });
    }
    for (const key of ["side", "adjacent", "pairedSelector"]) if (item[key]) violation[key] = item[key];
    report.violations.push(violation);
  }
}

const KINDS = ["text", ...Object.keys(NON_TEXT_RULES)];

function tokenItem(entry, index) {
  const tokenId = entry.id ?? `pair[${index}]`;
  const kind = entry.kind ?? "text";
  if (!KINDS.includes(kind)) throw new UsageError(`${tokenId}: unknown kind "${kind}"`);
  if (entry.fg === undefined || entry.bg === undefined) throw new UsageError(`${tokenId}: fg and bg are required`);
  let background;
  try {
    background = parseColor(entry.bg);
    parseColor(entry.fg);
    if (entry.backdrop) parseColor(entry.backdrop);
  } catch (error) {
    throw new UsageError(`${tokenId}: ${error.message}`);
  }
  if (background.a < 1 && !entry.backdrop) throw new UsageError(`${tokenId}: translucent bg needs an opaque backdrop`);
  const bg = [{ color: entry.bg, image: false }, ...(entry.backdrop ? [{ color: entry.backdrop, image: false }] : [])];
  const item = { kind, tokenId, pairs: [{ fg: entry.fg, opacity: 1, bg }] };
  if (kind === "text") {
    item.fontSizePx = Number(entry.fontSizePx ?? 16);
    item.fontWeight = Number(entry.fontWeight ?? 400);
    if (Number.isNaN(item.fontSizePx) || Number.isNaN(item.fontWeight)) {
      throw new UsageError(`${tokenId}: fontSizePx and fontWeight must be numbers`);
    }
  }
  return item;
}

function splitPair(text) {
  const fields = [];
  let depth = 0;
  let current = "";
  for (const character of text) {
    if (character === "(") depth += 1;
    if (character === ")") depth -= 1;
    if (character === ":" && depth === 0) {
      fields.push(current);
      current = "";
    } else {
      current += character;
    }
  }
  fields.push(current);
  if (fields.length < 2) throw new UsageError(`--pair needs <fg>:<bg>, got "${text}"`);
  const [fg, bg, kind, fontSizePx, fontWeight] = fields.map((field) => field.trim());
  return { fg, bg, kind: kind || undefined, fontSizePx, fontWeight };
}

function readJson(file, label) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    throw new UsageError(`${label} ${file}: ${error.message}`);
  }
}

function loadLookup(setting) {
  if (setting === "none") return null;
  const file = setting ?? BUNDLED_LOOKUP;
  if (!setting && !fs.existsSync(file)) return null;
  const data = readJson(file, "--apca-lookup");
  const rows = Array.isArray(data) ? data : data.tiers;
  const valid =
    Array.isArray(rows) &&
    rows.every((row) => ["minFontSizePx", "fontWeight", "minLc"].every((key) => typeof row[key] === "number"));
  if (!valid) throw new UsageError(`--apca-lookup ${file}: expected rows of { minFontSizePx, fontWeight, minLc }`);
  return rows;
}

async function auditDom(values, options, report) {
  const { launchBrowser, toPageUrl } = await import("./lib/browser.mjs");
  const { installPageHelpers } = await import("./lib/page-helpers.mjs");
  const { collectContrastItems } = await import("./lib/contrast-page.mjs");
  let url;
  try {
    url = toPageUrl(values.url ?? values.html);
  } catch (error) {
    throw new UsageError(error.message);
  }
  report.target = values.url ?? values.html;
  report.viewports = (values.viewports ?? "320,375,1440").split(",").map(Number);
  if (report.viewports.some((width) => !Number.isInteger(width) || width <= 0)) {
    throw new UsageError("--viewports takes comma-separated pixel widths");
  }
  report.ignored = values.ignore ?? [];
  const pageConfig = {
    ignore: report.ignored,
    iconFonts: (values["icon-fonts"] ?? "").split(",").map((font) => font.trim().toLowerCase()).filter(Boolean),
  };
  const browser = await launchBrowser().catch((error) => {
    throw new UsageError(error.message);
  });
  try {
    const page = await browser.newPage();
    for (const viewport of report.viewports) {
      await page.setViewport(viewport, 1000);
      await page.navigate(url).catch((error) => {
        throw new UsageError(error.message);
      });
      if (values["wait-for"]) {
        const found = await page.evaluate(async (selector) => {
          for (let attempt = 0; attempt < 100 && !document.querySelector(selector); attempt += 1) {
            await new Promise((resolve) => setTimeout(resolve, 100));
          }
          return Boolean(document.querySelector(selector));
        }, values["wait-for"]);
        if (!found) throw new UsageError(`--wait-for ${values["wait-for"]} never appeared`);
      }
      await page.evaluate(installPageHelpers);
      const { items, excluded } = await page.evaluate(collectContrastItems, pageConfig);
      for (const [reason, count] of Object.entries(excluded)) report.excluded[reason] = Math.max(report.excluded[reason], count);
      for (const item of items) evaluateItem(item, options, report, { viewport });
    }
  } finally {
    await browser.close();
  }
}

function finish(report, values) {
  const blocking = report.violations.length + (values["allow-inconclusive"] ? 0 : report.inconclusive.length);
  report.summary = {
    evaluated: report.passes.length + report.violations.length + report.inconclusive.length,
    passed: report.passes.length,
    violations: report.violations.length,
    inconclusive: report.inconclusive.length,
    skipped: report.skipped.length,
    result: blocking === 0 ? "pass" : "fail",
  };
  if (!values.verbose) delete report.passes;
  const { summary, ...rest } = report;
  const ordered = JSON.stringify({ ...headerOf(rest), summary, ...bodyOf(rest) }, null, 2);
  const output = values.output ?? "-";
  if (output !== "-") fs.writeFileSync(output, `${ordered}\n`);
  if (values.format === "text") {
    for (const v of report.violations) {
      const fix = v.correctiveValue ? ` -> set ${v.correctiveTarget} ${v.correctiveValue}` : ` (${v.correctiveReason})`;
      console.log(
        `${v.ruleId} ${v.selector ?? v.tokenId}${v.viewport ? ` @${v.viewport}` : ""}: ${v.foreground} on ${v.background} ` +
          `${v.measured.metric} ${v.measured.value} < ${v.expected.value}${fix}`,
      );
    }
    for (const entry of report.inconclusive) console.log(`INCONCLUSIVE ${entry.ruleId} ${entry.selector}: ${entry.reason}`);
    console.log(`${summary.result}: ${summary.violations} violations, ${summary.inconclusive} inconclusive`);
  } else if (output === "-") {
    console.log(ordered);
  }
  return blocking === 0 ? 0 : 1;
}

const HEADER_KEYS = ["tool", "version", "mode", "target", "method", "level", "apcaLookup", "viewports"];
const headerOf = (report) => Object.fromEntries(HEADER_KEYS.filter((key) => key in report).map((key) => [key, report[key]]));
const bodyOf = (report) => Object.fromEntries(Object.entries(report).filter(([key]) => !HEADER_KEYS.includes(key)));

async function main() {
  const [mode, ...rest] = process.argv.slice(2);
  if (!mode || mode === "--help" || mode === "-h" || rest.includes("--help")) {
    console.log(HELP);
    return 0;
  }
  if (mode !== "tokens" && mode !== "dom") throw new UsageError(`unknown mode "${mode}"; use tokens or dom`);
  let values;
  try {
    ({ values } = parseArgs({
      args: rest,
      options: {
        input: { type: "string" },
        pair: { type: "string", multiple: true },
        url: { type: "string" },
        html: { type: "string" },
        viewports: { type: "string" },
        "wait-for": { type: "string" },
        ignore: { type: "string", multiple: true },
        "icon-fonts": { type: "string" },
        method: { type: "string", default: "both" },
        level: { type: "string", default: "aa" },
        "apca-lookup": { type: "string" },
        "allow-inconclusive": { type: "boolean", default: false },
        output: { type: "string" },
        format: { type: "string", default: "json" },
        verbose: { type: "boolean", default: false },
      },
    }));
  } catch (error) {
    throw new UsageError(error.message);
  }
  if (!["wcag", "apca", "both"].includes(values.method)) throw new UsageError("--method is wcag, apca or both");
  if (!["aa", "aaa"].includes(values.level)) throw new UsageError("--level is aa or aaa");
  if (!["json", "text"].includes(values.format)) throw new UsageError("--format is json or text");

  const options = { method: values.method, level: values.level, lookup: loadLookup(values["apca-lookup"]) };
  const report = {
    tool: "contrast-audit",
    version: VERSION,
    mode,
    target: null,
    method: values.method,
    level: values.level,
    apcaLookup: options.lookup ? (values["apca-lookup"] ?? "bundled") : null,
    violations: [],
    inconclusive: [],
    skipped: [],
    excluded: { hidden: 0, disabled: 0, "aria-hidden": 0, "ignored-selector": 0 },
    passes: [],
  };

  if (mode === "tokens") {
    const entries = [...(values.input ? readJson(values.input, "--input") : []), ...(values.pair ?? []).map(splitPair)];
    if (!Array.isArray(entries) || entries.length === 0) throw new UsageError("tokens mode needs --input or --pair");
    report.target = values.input ?? "inline";
    delete report.excluded;
    entries.map(tokenItem).forEach((item) => evaluateItem(item, options, report, {}));
  } else {
    if (!values.url === !values.html) throw new UsageError("dom mode needs exactly one of --url or --html");
    await auditDom(values, options, report);
  }
  return finish(report, values);
}

main().then(
  (code) => {
    process.exitCode = code;
  },
  (error) => {
    console.error(JSON.stringify({ tool: "contrast-audit", error: error.message }));
    process.exitCode = 2;
  },
);
