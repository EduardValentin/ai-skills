# PRD Generation (only when PRD.md is missing)

If no `PRD.md` exists at the project root, offer to generate one:

> "I noticed there's no `PRD.md` in this project. The PRD is the source of truth for business rules, user flows, and functional requirements — it's what production user stories get created from. Want me to generate one by analyzing the current state of the reference app?"

If the user **declines**, note that PRD sync (Phase 6) will be skipped for the rest of the session, and proceed.

If the user **accepts**, follow the steps below. Use sub-agents for both code analysis and PRD writing so the main agent's context stays clean.

## Step 1 — Spawn a code analysis sub-agent

Dispatch a sub-agent (Agent tool) with this prompt:

> **Task: Analyze the React reference app and catalog all user flows, features, and business logic**
>
> Scan the React reference app at `[reference app path]`. Produce a comprehensive inventory of everything the app does from a *product* perspective (not a code perspective).
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
> **Output format:** A structured report organized by feature area / user flow. For each flow, describe:
> - Who the user is (visitor, client, coach, etc.)
> - What they can do (actions, inputs, decisions)
> - What the system does in response (displays, navigates, updates state)
> - What business rules are implied (constraints, validations, permissions)
> - What data entities are involved
>
> Do NOT include React component names, file paths, or implementation details. Describe everything in product/business terms.

## Step 2 — Capture screenshots of the main pages

Use the internal browser (or browser automation MCP) to navigate the primary routes and screenshot each page. These give visual context for understanding the app's structure, layout, and feature set.

If neither is available, ask the user for screenshots — see `browser-fallback.md`.

## Step 3 — Spawn a PRD writing sub-agent

Once the analysis report and screenshots are ready, dispatch a second sub-agent with this prompt:

> **Task: Write a PRD.md based on the app analysis**
>
> You are writing a Product Requirements Document for a product whose reference app has already been built. The PRD must serve as the **source of truth for creating production user stories** — it defines what the product does, its business rules, user flows, and functional requirements.
>
> **Inputs:**
> - App analysis report: [paste the code analysis sub-agent's output]
> - Screenshot observations: [describe what each screenshot shows — pages, layouts, key UI elements, user flows visible]
>
> **Writing guidelines:**
> - Structure: Product Summary, Product Goals, Non-Goals, Core User Types, Feature Areas (with sub-sections per feature), Business Rules, plus any other sections that emerge from the analysis.
> - For each feature area, describe: what it does, who uses it, the user flow step by step, business rules and constraints, data involved, and edge cases / states (empty, error, loading).
> - Clear, direct language. Audience: product managers, designers, developers who will create user stories from this document.
> - Do NOT include implementation details, component names, or tech stack references. Describe *what* the product does, not *how* it's built.
> - Do NOT invent features that aren't evidenced in the analysis or screenshots. Only document what actually exists.
> - If something is ambiguous (a button exists but its behavior is unclear), mark it `[TBD]` so the user can clarify later.
>
> Write the full PRD content. It will be saved as `PRD.md` at the project root.

## Step 4 — Save and hand off

Save the sub-agent's output as `PRD.md` at the project root. Briefly summarize for the user what was documented and invite them to flag anything that needs correction. Then proceed with the design task.
