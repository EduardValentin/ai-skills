# Visual-Output Capture — Capability Ladder

Visual validation is not optional. Without it, design work is flying blind. Pick the highest rung on this ladder that your environment supports, and degrade gracefully when a rung isn't available.

## Rung 1 — Native screenshot capability

If your agent exposes a built-in capability for navigating to a URL and capturing a screenshot of the running app, use it. This is the fastest path and produces deterministic output. Confirm it works with a single test capture before relying on it for validation.

## Rung 2 — Browser automation via shell

If no native capability is available, check whether a browser-automation tool is installed and reachable from a shell:

- **Playwright** — `npx playwright --version` (or check for a project-local install).
- **Puppeteer** — `npx puppeteer --version` or a project-local Node script.
- **Headless Chromium / `chromedriver`** — system browsers can be driven from a one-off script.
- **A hosted browser-automation service** — if the project already authenticates against one (Browserbase, Browserless, etc.), use the existing configuration; do not introduce a new dependency.

The skill does not prescribe a specific tool. The agent's job is to detect what's installed (or what the project already uses), invoke it from the shell, and read the resulting screenshot file from disk.

A minimal Playwright script — adapt the viewport list to the canonical breakpoint set (the project's Tailwind breakpoint boundaries, plus 320px and 1920px):

```js
// scripts/screenshot.js
const { chromium } = require('playwright');
const fs = require('fs');

const url = process.argv[2];
const outDir = process.argv[3] || 'screenshots';
const viewports = [
  { name: 'mobile-320', width: 320, height: 720 },
  { name: 'desktop-1920', width: 1920, height: 1080 },
  // add breakpoint boundaries from the project's Tailwind theme
];

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  for (const v of viewports) {
    const ctx = await browser.newContext({ viewport: { width: v.width, height: v.height } });
    const page = await ctx.newPage();
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.screenshot({ path: `${outDir}/${v.name}.png`, fullPage: true });
    await ctx.close();
  }
  await browser.close();
})();
```

Invoke from the shell once the dev server is running. Place the script under the skill's `scripts/` directory or the project's working directory — wherever the agent can write and execute it.

## Rung 3 — User-provided screenshots

If no automation rung is reachable:

1. **Start the dev server** so the user can access the app in their own browser.

2. **Request initial screenshots:**

   > "I don't have visual-output capture in this environment, so I can't take screenshots myself. Before I start, I need to understand the current state of the app visually.
   >
   > Please open the app and send me screenshots of:
   > - The page(s) or area(s) where the design work will happen.
   > - Any related pages that share layout or visual patterns with the target area.
   > - The overall navigation/layout so I can understand the app's visual language.
   >
   > Once I've reviewed them, I'll proceed with your request."

3. **Wait.** Do not start any design implementation until screenshots have been received.

4. **Confirm understanding.** After reviewing, describe back what you observe — layout, visual patterns, color usage, typography, spacing, component styles, overall aesthetic. Confirm with the user before proceeding.

5. **Validation also requires screenshots.** After implementing changes, ask the user for fresh screenshots at the canonical breakpoint set (every breakpoint boundary, plus 320px and 1920px). Same review process applies — do not consider the task done until you've seen the result.

## Suggesting an upgrade

After the session, mention to the user once — not repeatedly — that installing a browser-automation tool (Playwright is a common default; the project may have its own preference) makes the next round faster, because the agent can drive screenshots from the shell without involving them. If their agent has a native screenshot capability that just needs enabling, point at the relevant docs. Do not insist; user-provided screenshots are a valid permanent rung.

## Hard rule

Do not proceed with design work until visual context is available — native capture, browser automation, or user-provided screenshots. No exceptions.
