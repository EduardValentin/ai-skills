# No Internal Browser — Fallback Path

Visual validation is not optional. Without it, design work is flying blind. Follow this in order.

## 1. Check for an existing browser-automation MCP

Look in `.claude/settings.json`, `.claude/settings.local.json`, or `~/.claude/settings.json` for an MCP server that provides browser automation — `playwright`, `puppeteer`, `browserbase`, `browser-use`, or similar. If found, confirm it works with a test screenshot before proceeding.

## 2. Fall back to user-provided screenshots

If no MCP is available:

**a. Start the dev server** so the user can access the app in their own browser.

**b. Request initial screenshots:**

> "I don't have an internal browser or browser automation in this environment, so I can't take screenshots myself. Before I start, I need to understand the current state of the app visually.
>
> Please open the app and send me screenshots of:
> - The page(s) or area(s) where the design work will happen
> - Any related pages that share layout or visual patterns with the target area
> - The overall navigation/layout so I can understand the app's visual language
>
> Once I've reviewed them, I'll proceed with your request."

**c. Wait.** Do not start any design implementation until screenshots have been received.

**d. Confirm understanding.** After reviewing, describe back what you observe — layout, visual patterns, color usage, typography, spacing, component styles, overall aesthetic. Confirm with the user before proceeding.

**e. Validation also requires screenshots.** After implementing changes, ask the user for new screenshots at the relevant viewport widths (every breakpoint boundary, plus 320px and 1920px). Same review process applies — do not consider the task done until you've seen the result.

## 3. Suggest setting up an MCP for next time

After the session, mention to the user (once, not repeatedly):

> "Tip: For a faster workflow where I can take screenshots automatically, you can configure a browser-automation MCP server.
>
> **Option A — Playwright MCP (recommended):**
> ```json
> // ~/.claude/settings.json or <project-root>/.claude/settings.json
> {
>   "mcpServers": {
>     "playwright": {
>       "command": "npx",
>       "args": ["@anthropic-ai/mcp-playwright"]
>     }
>   }
> }
> ```
>
> **Option B —** any other browser-automation MCP (Puppeteer, Browserbase, etc.) that can navigate to URLs and take screenshots."

## Hard rule

Do not proceed with design work until visual context is available — internal browser, browser-automation MCP, or user-provided screenshots. No exceptions.
