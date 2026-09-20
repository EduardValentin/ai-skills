import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const scripts = resolve(here, "../../../../skills/ui-ux/visual-parity-verification/scripts");
const require = createRequire(import.meta.url);

let JSDOM;
try {
  ({ JSDOM } = require("jsdom"));
} catch (error) {
  console.log(JSON.stringify({ skipped: "jsdom unavailable" }));
  process.exit(0);
}

const html = readFileSync(resolve(here, "fixture.html"), "utf8");
const dom = new JSDOM(html, { url: "http://localhost:5173/orders", pretendToBeVisual: true, runScripts: "dangerously" });
const { window } = dom;

window.Element.prototype.getBoundingClientRect = function getBoundingClientRect() {
  const raw = this.getAttribute("data-test-rect");
  const [x, y, width, height] = raw ? raw.split(",").map(Number) : [0, 0, 100, 20];
  return { x, y, left: x, top: y, width, height, right: x + width, bottom: y + height };
};

for (const file of ["snapshot-subtree.browser.js", "find-react-roots.browser.js"]) {
  window.eval(readFileSync(resolve(scripts, file), "utf8"));
}

const checks = {};
const details = {};

const snapshot = window.paritySnapshot("OrderSummary");
details.snapshotError = snapshot.error || null;
checks.resolvesRootByAttribute = !snapshot.error && snapshot.rootSelector === "OrderSummary";
checks.rootSummaryHasRegionRole = snapshot.rootSummary && snapshot.rootSummary.role === "region" && snapshot.rootSummary.name === "Order summary";

const paths = [];
const byPath = new Map();
(function walk(node) {
  paths.push(node.path);
  byPath.set(node.path, node);
  node.children.forEach(walk);
})(snapshot.root);
details.paths = paths;

checks.pathsUseNthOfType = paths.includes("section > div:nth-of-type(1) > p:nth-of-type(2)");
checks.skipsHiddenAndScript = !paths.some((path) => path.includes("div:nth-of-type(2)")) && !paths.some((path) => path.includes("script"));
checks.hookIsRecorded = byPath.get("section > div:nth-of-type(1) > p:nth-of-type(1) > span:nth-of-type(1)")?.hook === "subtotal";
checks.ownTextExcludesChildren = byPath.get("section > div:nth-of-type(1) > p:nth-of-type(1)")?.ownText === "Subtotal";
checks.headingRoleAndName = byPath.get("section > h2:nth-of-type(1)")?.role === "heading" && byPath.get("section > h2:nth-of-type(1)")?.name === "Order summary";
checks.buttonIsFocusableWithName = byPath.get("section > button:nth-of-type(1)")?.focusable === true && byPath.get("section > button:nth-of-type(1)")?.name === "Place order";
checks.imgNameFromAlt = byPath.get("section > img:nth-of-type(1)")?.name === "Brand";
checks.inputNameFromLabel = byPath.get("section > label:nth-of-type(1) > input:nth-of-type(1)")?.name === "Coupon";
checks.relativeGeometryFromRoot = byPath.get("section > h2:nth-of-type(1)")?.geometry.x === 16 && byPath.get("section > h2:nth-of-type(1)")?.geometry.y === 16;
checks.wrapperFlagOnPlainDiv = byPath.get("section > div:nth-of-type(1)")?.wrapper === true;
checks.rootStyleHasEveryKey = Object.keys(snapshot.root.style).length === 68;
checks.childStyleIsDelta = (() => {
  const h2Style = byPath.get("section > h2:nth-of-type(1)").style;
  return Object.keys(h2Style).length < 68 && Object.prototype.hasOwnProperty.call(h2Style, "fontSize");
})();

checks.buttonNameFromContent = byPath.get("section > button:nth-of-type(1)")?.nameFrom === "content";
checks.imgNameFromAuthor = byPath.get("section > img:nth-of-type(1)")?.nameFrom === "author";
checks.wrapperNameFromEmpty = byPath.get("section > div:nth-of-type(1)")?.nameFrom === "";
checks.unparseableBackgroundIsNotWrapper = byPath.get("section > div:nth-of-type(3)")?.wrapper === false;

checks.rootNotFound = window.paritySnapshot("Missing").error === "root-not-found";
checks.rootAmbiguous = window.paritySnapshot("Duplicate").error === "root-ambiguous" && window.paritySnapshot("Duplicate").count === 2;
checks.cssSelectorAlsoWorks = window.paritySnapshot("#app > section:nth-of-type(1)").rootSelector === "#app > section:nth-of-type(1)";

checks.noFibersIsAnError = window.parityFindReactRoots(["OrderSummary"]).error === "no-react-fibers";

function OrderSummary() {}
function LineItem() {}
const orderSummaryFiber = { type: OrderSummary, return: { type: "div", return: null } };
const section = window.document.querySelector("[data-parity-root='OrderSummary']");
section.__reactFiber$abc = { type: "section", return: orderSummaryFiber };
for (const paragraph of section.querySelectorAll("p")) {
  paragraph.__reactFiber$abc = { type: "p", return: { type: LineItem, return: { type: "div", return: orderSummaryFiber } } };
}
const roots = window.parityFindReactRoots(["OrderSummary", "LineItem", "Unmounted"]);
details.roots = roots;
checks.findsOutermostRootPerComponent = roots.roots.OrderSummary.length === 1 && roots.roots.OrderSummary[0].selector === "body > div:nth-of-type(1) > section:nth-of-type(1)";
checks.findsEveryInstance = roots.roots.LineItem.length === 2;
checks.unmountedIsEmptyList = Array.isArray(roots.roots.Unmounted) && roots.roots.Unmounted.length === 0;
checks.rootSummaryFromFinder = roots.roots.OrderSummary[0].summary.name === "Order summary" && roots.roots.OrderSummary[0].summary.width === 640;

const encodedFallback = await window.paritySnapshot("OrderSummary", { encoding: "gzip-base64" });
checks.encodingOptionFallsBackWithoutCompressionStream = Boolean(encodedFallback) && typeof encodedFallback === "object" && "root" in encodedFallback;

console.log(JSON.stringify({ checks, details }));
