---
name: design-studio
description: "Design iteration workflow for React reference apps. Use when the user mentions: 'UI/UX', 'design work', 'update the UI', 'work on the UI', 'design session', 'iterate on the design', 'extend the design', 'build the UI', 'design a feature', 'work on the prototype', or wants to make visual/layout/styling changes to a React reference app. This skill handles all design work on a React + Tailwind reference app that serves as a style guide for a real production codebase. Only the React reference app is modified - never the production code."
---

# Design Studio

A structured workflow for iterating on UI/UX design within a React + Tailwind reference app. This skill ensures every design change is tasteful, accessible, responsive, token-driven, and visually validated through an internal browser preview.

---

## Prerequisites

Before any design work begins, the agent MUST complete ALL of the following steps in order. Do not skip any step.

### Step 0: Prepare the Design Studio Environment

Run the bundled preparation script before manually inspecting or launching the React reference app:

```bash
<skill-dir>/scripts/prepare-design-studio.sh --project-root <absolute-project-or-worktree-root>
```

If the React reference app path is already known, pass it explicitly:

```bash
<skill-dir>/scripts/prepare-design-studio.sh --project-root <absolute-project-or-worktree-root> --app-root <absolute-design-app-root>
```

This script is the deterministic setup path. It:

- Locates the React reference app under `designs/` when `--app-root` is not provided.
- Reads the project Node version from `.node-version`, `.nvmrc`, or `.tool-versions` at the project/worktree root.
- Uses `nvm` when available to install/use the declared Node version before dependency work.
- Detects the package manager from the design app first (`packageManager`, `pnpm-lock.yaml`, `package-lock.json`, `yarn.lock`), then falls back to the project root package-manager signals, then npm.
- Installs dependencies only for the React reference app. In a Claude worktree, dependency install is always required. Outside a worktree, install only happens when `node_modules/` is missing unless `--force-install` is passed.
- Writes or updates `.claude/launch.json` with a `design-reference` configuration that starts the app with the detected package manager, uses the declared Node version through `nvm` when available, exposes the design app and project `node_modules/.bin` paths, and pins the Vite preview port when the dev script uses Vite.

Do not hand-create `.claude/launch.json` or manually install design-app dependencies unless the script fails. If it fails, fix the underlying setup issue or ask the user before falling back to manual steps.

### Step 1: Locate the React Reference App

Look for a `designs/` folder in the project root containing the React reference app.

**Expected path pattern:** `<project-root>/designs/<app-name>/`

**Discovery strategy (follow in order):**

1. Check if `<project-root>/designs/` exists and contains a folder with a `package.json` that has React as a dependency. If found, that's the reference app.
2. If the folder structure isn't obvious, search for `.jsx` and `.tsx` files inside the `designs/` directory recursively. The directory containing these files (or their nearest parent with a `package.json`) is the reference app root.
3. If no `designs/` folder exists, or no JSX/TSX files are found inside it, THEN ask the user: "I can't find the React reference app. I searched for JSX/TSX files inside the `designs/` folder but found nothing. What's the path to your design reference app?"
4. Do NOT proceed until the reference app path is confirmed and validated (must contain a `package.json` with React).

### Step 2: Read and Load Project Context

Read ALL of the following files. If a file doesn't exist, note it and handle as described.

**Required reads (every session):**

1. **`DESIGN.md`** (project root) - The design system philosophy, color palette, typography, shapes, textures, interactions.
   - If missing: Ask the user for the design direction, then CREATE `DESIGN.md` at the project root with the agreed-upon design system documentation before proceeding.

2. **`brand-voice.md`** (project root) - Brand voice, tone, and copy guidelines.
   - If missing: Inform the user that no brand voice guide exists. Ask if they want to create one or proceed without it. If proceeding without, use clear, direct, human-sounding copy as default.

3. **Tailwind theme/config** - Read the Tailwind configuration to understand ALL existing semantic tokens, colors, fonts, spacing, breakpoints.
   - For Tailwind v4: Look for `@theme` blocks in CSS files (typically `src/styles/theme.css` or similar).
   - For Tailwind v3: Read `tailwind.config.ts` or `tailwind.config.js`.
   - Map out every available semantic token. This is your styling vocabulary - you CANNOT use anything outside of it without explicit approval.

4. **Component inventory** - Scan the `components/` directory structure to understand:
   - What UI primitives exist (buttons, cards, inputs, modals, etc.)
   - What custom components exist (page-specific or feature-specific)
   - What patterns are used (CVA variants, cn() utility, data-slot attributes, etc.)

5. **Existing pages and routes** - Read the router config and page components to understand the current app structure.

6. **`package.json`** - Understand the exact dependency versions (React, Tailwind, Radix, animation libraries, etc.).

7. **`PRD.md`** (project root) - The product requirements document: business rules, user flows, functional requirements, and feature definitions. This is the source of truth for production user stories.
   - If present: Read it in full. This context helps you understand the product intent behind design requests and ensures Phase 6 (PRD Sync) can update it accurately after functional changes.
   - If missing: Handle in Step 3 below (PRD Generation).

### Step 3: PRD Generation (if missing)

If no `PRD.md` was found at the project root, offer the user the option to generate one:

> "I noticed there's no `PRD.md` in this project. The PRD serves as the source of truth for business rules, user flows, and functional requirements — it's what production user stories get created from. Want me to generate one by analyzing the current state of the reference app?"

**If the user declines:** Note that PRD sync (Phase 6) will be skipped for all design changes in this session, and proceed to the next step.

**If the user accepts:** Generate the PRD using sub-agents to keep the main agent's context clean. Execute the following:

1. **Spawn a code analysis sub-agent** with instructions:

   > **Task: Analyze the React reference app and catalog all user flows, features, and business logic**
   >
   > Scan the React reference app at `[reference app path]`. Your goal is to produce a comprehensive inventory of everything the app does from a *product* perspective (not a code perspective).
   >
   > **What to analyze:**
   > - Router configuration: all routes/pages and their hierarchy
   > - Each page component: what it displays, what actions a user can take, what states it has
   > - Forms and inputs: what data is collected, what validation exists, what happens on submit
   > - Navigation flows: how users move between pages, conditional navigation, protected routes
   > - User types/roles: any role-based UI differences (e.g., coach vs client portals)
   > - Mock data structures: what entities exist (users, plans, exercises, messages, etc.), their fields and relationships
   > - Interactive elements: modals, drawers, toggles, filters, scheduling actions, messaging flows
   > - State management: what global/shared state exists and what it represents in product terms
   > - Notifications, alerts, empty states, error states
   >
   > **Output format:** Return a structured report organized by feature area / user flow. For each flow, describe:
   > - Who the user is (visitor, client, coach)
   > - What they can do (actions, inputs, decisions)
   > - What the system does in response (displays, navigates, updates state)
   > - What business rules are implied (constraints, validations, permissions)
   > - What data entities are involved
   >
   > Do NOT include React component names, file paths, or implementation details in your output. Describe everything in product/business terms.

2. **Take screenshots of the main pages** using the browser preview or browser automation MCP. Navigate through the primary routes and capture each page. These screenshots give visual context for understanding the app's structure, layout, and feature set.

3. **Spawn a PRD writing sub-agent** once the code analysis and screenshots are ready, with instructions:

   > **Task: Write a PRD.md based on the app analysis**
   >
   > You are writing a Product Requirements Document for a product whose reference app has already been built. The PRD must serve as the **source of truth for creating production user stories** — it defines what the product does, its business rules, user flows, and functional requirements.
   >
   > **Inputs:**
   > - App analysis report: [paste the code analysis sub-agent's output]
   > - Screenshot observations: [describe what each screenshot shows — pages, layouts, key UI elements, user flows visible]
   >
   > **Writing guidelines:**
   > - Structure the PRD with clear sections: Product Summary, Product Goals, Non-Goals, Core User Types, Feature Areas (with sub-sections per feature), Business Rules, and any other sections that naturally emerge from the analysis.
   > - For each feature area, describe: what it does, who uses it, the user flow step-by-step, business rules and constraints, data involved, and edge cases / states (empty, error, loading).
   > - Write in clear, direct language. The audience is product managers, designers, and developers who will create user stories from this document.
   > - Do NOT include implementation details, component names, or tech stack references. Describe *what* the product does, not *how* it's built.
   > - Do NOT invent features or requirements that aren't evidenced in the analysis or screenshots. Only document what actually exists.
   > - If something is ambiguous from the analysis (e.g., a button exists but its behavior is unclear), note it with a `[TBD]` marker so the user can clarify later.
   >
   > Write the full PRD content. It will be saved as `PRD.md` at the project root.

4. Save the sub-agent's output as `PRD.md` at the project root.
5. Inform the user that the PRD has been generated and give a brief summary of what was documented. Invite them to review it and flag anything that needs correction.

After PRD generation (or if the user declined), proceed to the next step.

### Step 4: Start the Dev Server and Preview

Start the React dev server and open an internal browser preview to inspect the current state of the app.

1. Confirm Step 0 created or updated `.claude/launch.json` with a `design-reference` entry. It should follow this shape:
   ```json
   {
     "version": "0.0.1",
     "configurations": [
       {
         "name": "design-reference",
         "runtimeExecutable": "/bin/zsh",
         "runtimeArgs": ["-lc", "<node/package-manager setup> && <package-manager> run dev"],
         "port": 5173,
         "cwd": "<absolute-path-to-react-reference-app>"
       }
     ]
   }
   ```
   The command must come from the preparation script so the package manager, Node version, and binary paths stay consistent across local checkouts and Claude worktrees.

2. Start the preview server using `preview_start`.
3. Take a screenshot of the current app state.
4. Navigate through the main pages/routes and take screenshots to build a mental model of the current design, vibe, and aesthetic.

This visual preload is CRITICAL. The agent must understand the existing look and feel before making any changes.

**If internal browser capabilities are not available (e.g. Claude Code CLI):**

The agent MUST have a way to visually validate its work. Without visual validation, design work is flying blind. Follow these steps:

1. **Check if a browser automation MCP is already configured:**
   - Look in `.claude/settings.json`, `.claude/settings.local.json`, or `~/.claude/settings.json` for an existing MCP server that provides browser automation (e.g. `playwright`, `puppeteer`, `browserbase`, `browser-use`, etc.).
   - If found, confirm it works by attempting to take a screenshot of a test page.

2. **If no browser automation MCP is found, fall back to user-provided screenshots:**

   If the agent does not have internal browsing capabilities AND no browser automation MCP is configured, the agent MUST ask the user to provide screenshots before any design work begins. Follow this process:

   a. **Start the dev server** so the user can access the app in their own browser.

   b. **Request screenshots from the user:**

      > "I don't have access to an internal browser or browser automation in this environment, so I can't take screenshots myself. Before I can start designing, I need to understand the current state of the app visually.
      >
      > Please open the app in your browser and send me screenshots of the following:
      > - The page(s) or area(s) where the design work will happen
      > - Any related pages that share layout or visual patterns with the target area
      > - The overall navigation/layout so I can understand the app's visual language
      >
      > Once I've reviewed the screenshots and understand the current design, I'll proceed with your request."

   c. **Wait for the user to provide the screenshots.** Do NOT proceed with any design implementation until screenshots have been received and reviewed.

   d. **Review and confirm understanding.** After receiving the screenshots, describe back to the user what you observe — the layout, visual patterns, color usage, typography, spacing, component styles, and overall aesthetic. Confirm with the user that your understanding is accurate before proceeding to design work.

   e. **During validation (Phase 4), request screenshots again.** After implementing changes, ask the user to provide new screenshots of the modified areas at relevant viewport widths so you can visually validate the result. The same review process applies — you must see the result before considering the task complete.

   f. **Inform the user about browser automation for a smoother workflow:**

      > "Tip: For a faster design workflow where I can take screenshots automatically, you can set up a browser automation MCP server:
      >
      > **Option A: Playwright MCP (recommended)**
      > ```json
      > // Add to ~/.claude/settings.json or <project-root>/.claude/settings.json
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
      > **Option B: Any other browser automation MCP** (Puppeteer, Browserbase, etc.) that can navigate to URLs and take screenshots."

3. **Do NOT proceed with design work until visual context is available** — either through internal browser capabilities, a browser automation MCP, or user-provided screenshots. The agent must understand the current design before making any changes.

---

## Design Rules

These rules are NON-NEGOTIABLE. Every design action must comply with ALL of them.

### Rule 1: Semantic Tokens Only

- **NEVER** use ad-hoc hex codes, rgb values, or arbitrary Tailwind values for colors, spacing, or typography.
- Every style MUST reference an existing semantic token from the Tailwind theme config.
- If no token exists for what you need:
  1. STOP.
  2. Ask the user: "I need a token for [describe the purpose]. What should we name it? My suggestion: `--[proposed-name]`"
  3. Wait for user approval on the token name.
  4. Add the token to the theme configuration.
  5. Update `DESIGN.md` to document the new token.
  6. THEN use it in your component.

### Rule 2: Design System Consistency

- **NEVER** invent new visual patterns, colors, fonts, or component styles that aren't already established in the design system.
- Every new UI element must look like it belongs with the existing app.
- Match the existing aesthetic: refer to `DESIGN.md` for the vibe, patterns, and principles.
- If the user explicitly asks to extend the design system (new colors, fonts, components), THEN and only then may you be creative - but the additions must harmonize with the existing system.
- When extending the design system, always update `DESIGN.md` to reflect the additions.

### Rule 3: Accessibility

- All design work MUST follow WCAG 2.1 AA guidelines at minimum.
- Ensure sufficient color contrast ratios (4.5:1 for normal text, 3:1 for large text).
- All interactive elements must be keyboard accessible.
- Use semantic HTML elements (nav, main, section, article, button, etc.).
- Provide appropriate ARIA labels where semantic HTML is insufficient.
- Focus states must be visible and clear.
- Motion/animations must respect `prefers-reduced-motion`.

### Rule 4: Responsive Design

- Every design MUST be responsive across all defined breakpoints.
- Check the Tailwind config for defined breakpoints. If none are custom-defined (using Tailwind defaults):
  - Ask the user: "No custom breakpoints are defined. Should we use Tailwind's defaults (sm:640px, md:768px, lg:1024px, xl:1280px, 2xl:1536px) or define custom ones?"
  - Wait for confirmation before proceeding.
- Test responsiveness at all breakpoints during validation.
- Nothing should clip, overflow, or break at any viewport size.

### Rule 5: Component-First Architecture

- **Prefer building reusable components** over creating ad-hoc inline UI.
- If a UI pattern appears (or could appear) more than once, extract it into a component.
- If a change might affect an existing component:
  1. STOP.
  2. Ask the user: "This change could affect the [ComponentName] component. Should I: (A) Extend the existing component with a new variant/prop, or (B) Create a new separate component?"
  3. Wait for the user's decision.
- Components must be composable with clean prop APIs.
- No business logic or page-specific decisions inside reusable components.

### Rule 6: Brand Voice for Copy

- All UI copy (CTAs, headings, labels, descriptions, empty states, error messages) MUST follow `brand-voice.md` guidelines.
- If no `brand-voice.md` exists, use clear, direct, human-sounding language. Avoid corporate jargon, buzzwords, and generic AI-sounding text.
- When writing copy, read the brand voice guide and match its tone exactly.

### Rule 7: Purposeful Animation

- Animations should enhance UX, never hinder it.
- Use the animation library already in the project (check `package.json` for `motion`, `framer-motion`, `tw-animate-css`, etc.).
- Keep transitions smooth and purposeful: 200-300ms for micro-interactions, up to 500ms for page transitions.
- Respect `prefers-reduced-motion` by disabling or reducing animations.
- No gratuitous animations. Every animation must serve a purpose: guide attention, provide feedback, or smooth transitions.

### Rule 8: React Router Navigation Only

- **NEVER** use `window.location.href`, `window.location.assign()`, `window.location.replace()`, or any other direct browser navigation API. These cause a full page reload and destroy all in-memory app state (including Dev Toggle settings and React context).
- **NEVER** use raw `<a>` tags for in-app navigation. Raw anchors also trigger full page reloads and lose app state.
- **ALWAYS** use React Router navigation for any link or redirect within the app: `<Link>` component, `useNavigate()` hook, or `<Navigate>` component.
- The only acceptable use of `<a>` is for links that navigate **away from the app entirely** (e.g., external websites, social media). In that case, always include `target="_blank"` and `rel="noopener noreferrer"`.

### Rule 9: Clean Code

- Even though the primary concern is design, the React code must remain clean and composable.
- Prefer composition over inheritance.
- Use TypeScript types for all component props.
- Keep components focused and single-responsibility.
- Extract repeated patterns into utilities or shared components.
- Follow the existing code conventions found in the reference app (CVA patterns, cn() utility, data-slot attributes, etc.).

### Rule 10: Scope Discipline

- Only build UI/UX for the feature being designed RIGHT NOW.
- Do not add unrelated UI elements, pages, or features.
- Backend integrations should be mocked (static data, setTimeout for async simulation, local state).
- If a feature needs data, create realistic mock data that demonstrates the UI properly.

### Rule 11: Latest Best Practices

- Always apply current UI/UX best practices for layout, interaction patterns, and visual design.
- Use the latest recommended patterns for the tech stack in the reference app (React patterns, Tailwind utilities, Radix UI composition, etc.).
- When unsure about a UI/UX pattern, prefer established patterns from reputable design systems (Material Design principles, Apple HIG concepts, Nielsen Norman Group guidelines).

### Rule 12: No Ad-Hoc Spacing or Sizing on Reusable Components

- **NEVER** apply ad-hoc padding, margin, gap, width, height, or other spacing/sizing overrides directly to reusable components (e.g. via className props, wrapper divs with spacing, or inline styles).
- Reusable components must control their own internal spacing and sizing through **variants**, not through external ad-hoc classes.
- When a component needs to render at a different size or with different spacing:
  1. **Check if the component already has a variant system** (e.g. CVA `size` variant, `variant` prop, etc.).
     - If YES: **Extend the existing variant system** by adding a new variant value that covers the needed size/spacing. Ensure the new variant is responsive-aware (uses breakpoint-appropriate values).
     - If NO: **Create a variant system** for the component. At minimum, define `size` variants (e.g. `sm`, `md`, `lg`) that properly accommodate all defined breakpoints.
  2. Variants must use semantic spacing tokens from the theme — never arbitrary values.
  3. Each size variant must be tested at all breakpoints to ensure responsiveness is maintained.
  4. Update `DESIGN.md` to document the new or extended variant.
- **The only acceptable external spacing** on a reusable component is layout-level spacing applied by a parent container (e.g. `gap` on a flex/grid parent, or margin on a layout wrapper). This spacing controls the relationship *between* components, not the component's own dimensions.
- If the user requests an ad-hoc spacing/sizing tweak on a reusable component, STOP and explain: "Instead of adding ad-hoc spacing, I'll extend this component's variant system so the sizing is reusable and responsive across all breakpoints."

---

## Design Workflow

For each design task, follow this workflow:

### Phase 1: Understand the Request

1. Clarify what feature or UI change is being requested.
2. Determine if this is:
   - **Extending an existing feature** (e.g., making a button functional, adding a modal flow)
   - **Building a new feature from scratch** (e.g., creating a Blog section)
   - **Refining existing UI** (e.g., adjusting spacing, improving a layout)
3. Identify which pages, components, and tokens will be affected.
4. If the scope is unclear, ask clarifying questions before writing any code.

### Phase 2: Plan the Design

1. Describe to the user what you plan to build/change and how it fits with the existing design.
2. List which components will be created, modified, or reused.
3. Identify any new tokens that might be needed.
4. If building something new, describe the responsive behavior at each breakpoint.
5. Get user approval before writing code.

### Phase 3: Implement

1. Write the code following all Design Rules above.
2. Build incrementally - implement one component or section at a time.
3. After each significant change, preview the result in the internal browser.
4. If something doesn't look right, fix it before moving on.

### Phase 4: Visual Validation (Self-Review)

After implementation, the agent MUST perform a thorough visual validation:

1. **Screenshot the result** at desktop viewport.
2. **Check responsive behavior at breakpoint boundaries:**
   - For EACH defined breakpoint (e.g. sm:640px, md:768px, lg:1024px, xl:1280px, 2xl:1536px or custom), screenshot at TWO widths:
     - **Just BEFORE the breakpoint** (e.g. 639px, 767px, 1023px) — the last pixel before the breakpoint fires.
     - **Just AFTER the breakpoint** (e.g. 640px, 768px, 1024px) — the first pixel where the breakpoint is active.
   - This catches layout jumps, content clipping, and misalignment that only appear at the transition between breakpoints.
   - Also screenshot at the smallest supported width (e.g. 320px) and a wide desktop width (e.g. 1920px).
   - At EVERY viewport width, verify:
     - **No clipping:** Text, images, and interactive elements are fully visible — nothing is cut off or hidden behind other elements.
     - **No overflow:** Content does not extend beyond its container or cause unwanted horizontal scrolling.
     - **Proper alignment:** Elements are correctly aligned (centered content stays centered, grid items stay in their tracks, flex items wrap gracefully).
     - **No layout collapse:** Containers maintain sensible dimensions — no 0-height sections, no overlapping elements, no crushed whitespace.
     - **Readable typography:** Text remains legible and appropriately sized at every viewport width.
   - If ANY issue is found at any viewport width, fix it before proceeding.
3. **Compare against existing design:**
   - Does it match the vibe and aesthetic of the rest of the app?
   - Are the same tokens, patterns, and visual language used?
4. **Accessibility check:**
   - Inspect color contrast on key text elements.
   - Verify interactive elements are focusable.
5. **Cross-reference with DESIGN.md:**
   - Does the implementation follow the documented design principles?

If ANY validation check fails, fix the issue before presenting to the user.

### Phase 5: Update Documentation

After the design is validated:

1. If new tokens were added to the theme, update `DESIGN.md` with the new tokens and their purpose.
2. If new components were created, document them in `DESIGN.md` under a Components section.
3. If the design system was extended (new colors, fonts, patterns), update `DESIGN.md` to reflect these additions.
4. Keep `DESIGN.md` as the single source of truth for the design system.

### Phase 6: PRD Sync

After all design and documentation work is complete, check if a `PRD.md` file exists at the project root. If it does not (and the user declined generation during Prerequisites Step 3), skip this phase.

#### Source of Truth

The **design reference app is the source of truth for the design** — it defines what the product looks like, how interactions feel, and what components exist. The **PRD is the source of truth for business logic** — it defines what the product does, its business rules, user flows, functional requirements, and data models. The PRD exists so that production user stories can be created from it without needing to reverse-engineer behavior from the reference app.

The PRD should only be updated when the design change alters or introduces business-level functionality. Most design sessions will NOT require a PRD update.

#### When to trigger

Update the PRD ONLY when the design change introduces or modifies a **business user flow** — meaning a change that would result in new or altered user stories for production. Examples:

- A new page or feature area that represents a new product capability (e.g., adding a check-in scheduling flow)
- A change to an existing user flow's steps, states, or branching logic (e.g., adding an approval step that didn't exist before)
- New business rules or constraints implied by the UI (e.g., "a client can only have one pending request at a time")
- New data entities or fields that production would need to store (e.g., adding a "goal type" to the plan model)
- Removal or replacement of an existing flow (e.g., replacing a single-step save with a draft/publish workflow)

#### When NOT to trigger

Do NOT update the PRD for changes that are purely about design, presentation, or implementation:

- Any visual/cosmetic change: colors, spacing, typography, layout adjustments, responsive fixes, animation tweaks, token additions
- UI polish: icon changes, hover states, focus ring styling, shadow adjustments, border radius changes
- Component architecture decisions: extracting a shared component, adding variants, refactoring how something is built
- Information hierarchy changes that don't alter what data is shown (e.g., moving a field from a sidebar to a card)
- Empty states, loading skeletons, or error state styling — unless these represent new *behavioral* requirements (e.g., "the system must show X when the list is empty" is worth capturing only if the specific behavior matters for production)

**When in doubt, don't update.** A missing PRD line can be added later. A PRD cluttered with visual or technical details actively harms the quality of user stories written from it.

#### What belongs in the PRD vs. what does NOT

The PRD must describe the product in **functional, business-level language** that translates cleanly into user stories and acceptance criteria. It must read as if no reference app exists.

**Belongs in the PRD (functional / business-level):**
- "Clients can request an ad-hoc check-in with the coach" ✓
- "The coach can approve or decline check-in requests" ✓
- "A client may have at most one pending check-in request at a time" ✓
- "Plan templates default to 4 weeks with 1 deload week" ✓
- "Completed plans must be distinguishable from active plans" ✓

**Does NOT belong in the PRD (visual / implementation details):**
- "Active plans show a green badge on the card" ✗ — this is a visual decision owned by the design
- "The check-in picker uses a calendar grid with hourly time slots from 9–4" ✗ — interaction pattern detail; the PRD should say "client selects a date and time" and leave the how to design
- "A shared PlanBuilder component is used for both template and client contexts" ✗ — implementation architecture
- "Cards use `rounded-xl` with `shadow-soft`" ✗ — styling
- "The sidebar collapses into a bottom sheet on mobile" ✗ — responsive behavior owned by design
- "Empty state shows an illustration with a CTA button" ✗ — visual treatment
- "Status badges use `bg-emerald-50 text-emerald-700`" ✗ — token/color detail

**Rule of thumb:** If a sentence would still make sense in a PRD for a product built with a completely different tech stack and design system, it belongs. If it only makes sense because you've seen the reference app's specific UI, it doesn't.

#### How to execute

Spawn a **background sub-agent** (using the Agent tool) with the following instructions:

> **Task: Sync PRD.md with a design change — business flows only**
>
> A design change was just made to the React reference app. Your job is to determine whether `PRD.md` at the project root needs updating, and if so, update ONLY the business-level functional requirements. The design reference app is the source of truth for the design; the PRD is the source of truth for business logic and functional requirements.
>
> **Context about what changed:**
> [Include a clear summary of the design change: what new user flows or business capabilities were added/modified. Focus on what a user can now DO, not on how it looks.]
>
> **Instructions:**
>
> 1. Read `PRD.md` in full.
>
> 2. Determine if a PRD update is actually needed. Ask yourself: "Does this change introduce or alter a business user flow that would result in new or changed user stories for production?" If the answer is no — if the change is purely visual, structural, or about how something looks rather than what it does — then DO NOT modify the PRD. Instead, return a message saying "No PRD update needed — the change is design-level only."
>
> 3. If an update IS needed, identify which sections are affected and make targeted edits. Follow these content rules strictly:
>
>    **DO include:**
>    - New or modified business rules and constraints
>    - New or modified user flow steps (described as actions and outcomes, not UI interactions)
>    - New data entities, fields, or relationships that production would need to model
>    - New feature areas (add a new section following the document's existing structure)
>
>    **DO NOT include — these are hard exclusions:**
>    - Visual details: colors, badges, icons, illustrations, layout descriptions, card styles, typography choices
>    - Interaction patterns: "calendar grid", "dropdown", "modal", "bottom sheet", "sidebar collapse", "drag and drop" — describe the capability ("client selects a date"), not the widget
>    - Component or code architecture: shared components, component names, variants, file structure
>    - Responsive behavior: how the UI adapts to screen sizes
>    - Animation or transition descriptions
>    - Empty state or loading state visual treatments (unless the *behavior* is a business requirement)
>    - Any detail that only makes sense because you've seen the specific UI implementation
>
> 4. Preserve the existing writing style, structure, and level of detail in the PRD. Match the tone and granularity of the surrounding content.
>
> 5. Do NOT remove or weaken existing requirements unless the design change explicitly replaces prior functionality.
>
> 6. Keep additions concise. A new business rule is one sentence. A new flow step is one bullet point. Do not over-document.
>
> 7. **Self-check before saving:** Re-read every line you added or changed. For each line, ask: "Would this sentence make sense in a PRD for a product built with a completely different tech stack and design system?" If no, remove it.

The sub-agent runs in the background so it does not block the main design workflow. Once it completes, briefly inform the user whether the PRD was updated and, if so, summarize only the business-level changes (not visual details).

### Phase 7: Session Wrap-Up and PR Creation

When the user signals that the design session is ending, the agent MUST treat that as an instruction to prepare and create a pull request for the current React reference app work.

#### End-of-session triggers

Treat phrases such as the following as explicit PR creation requests:

- "let's end this session"
- "let's create the PR"
- Any clearly equivalent instruction to wrap up the current design session and open a PR

#### What the PR must include

Before creating the PR:

1. Ensure the branch includes **all React reference app changes from this session**.
2. Ensure any `PRD.md` additions or edits produced by Phase 6 are also included in the same PR.
3. If `PRD.md` did not need an update, note that in the PR description instead of forcing a PRD change.
4. Do NOT omit relevant design-app changes or leave PRD sync changes unstaged if they belong to the session.

#### PR description requirements

The PR description must be concise and cover:

- What was changed in the React reference app
- Any `PRD.md` additions or updates made during the session (or a short note that no PRD update was needed)

Keep the description brief and practical. The goal is a clean handoff that shows both the design app work and the product-requirements updates that came out of the session.

---

## Definition of Done

A design task is complete ONLY when ALL of the following are true:

- [ ] The new feature/change is implemented and renders correctly
- [ ] The design is tasteful and creative, matching the existing app aesthetic
- [ ] The design perfectly matches the existing design system (tokens, patterns, components)
- [ ] The design is accessible according to WCAG 2.1 AA guidelines
- [ ] The design is responsive at all defined breakpoints with no clipping or overflow
- [ ] Only semantic tokens are used (no ad-hoc hex codes or arbitrary values)
- [ ] All copy follows brand-voice.md guidelines
- [ ] Components are reusable and composable where applicable
- [ ] The code is clean, typed, and follows existing conventions
- [ ] The agent has visually validated the result through the internal browser preview, browser automation MCP, or user-provided screenshots
- [ ] `DESIGN.md` is up to date with any design system changes
- [ ] If `PRD.md` exists and the change introduced or modified a business user flow, a sub-agent has been spawned to sync the PRD (business rules and functional requirements only — no visual or implementation details)
- [ ] Only the React reference app was modified (no production code changes, except `PRD.md` updates)
- [ ] If the user ends the session or asks to create the PR, a PR is created that includes the React reference app changes and any `PRD.md` additions from the session

---

## Important Reminders

- **This skill is for design work only.** The production codebase is synced separately.
- **Only the React reference app should be modified.** Never touch files outside the `designs/` folder (except `DESIGN.md`, `brand-voice.md`, and `PRD.md` at the project root).
- **Session end means PR time.** If the user says something like "let's end this session" or "let's create the PR", treat that as an explicit instruction to create a PR for the current design-session work.
- **When in doubt, ask.** It's better to confirm with the user than to guess and introduce inconsistencies.
- **The internal browser preview (or browser automation MCP) is your eyes.** Use it frequently to validate your work, not just at the end. If neither is available, request screenshots from the user to understand the current design before starting, and request new screenshots after implementation to validate the result.
- **Mock everything.** Backend APIs, data fetching, authentication - all should be mocked with realistic data within the React app.
