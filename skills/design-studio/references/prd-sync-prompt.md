# PRD Sync Prompt

Use this template for PRD sync. Prefer delegating the PRD read/check to a context-isolated worker/subagent when the current environment supports that; run inline only when delegation is unavailable. Replace the `[summary]` placeholder with a clear, business-level description of what changed (what the user can now DO, not how it looks).

---

> **Task: Sync PRD.md with a design change — business flows only**
>
> A design change was just made to the React reference app. Your job is to determine whether `PRD.md` at the project root needs updating, and if so, update ONLY business-level functional requirements. The design reference app is the source of truth for the design; the PRD is the source of truth for business logic and functional requirements.
>
> **Context about what changed:**
> [summary — clear, business-level: new user flows, modified flows, new business rules, new data entities. Focus on what a user can now DO, not on how it looks.]
>
> **Instructions:**
>
> 1. Read `PRD.md` in full.
>
> 2. Determine if a PRD update is actually needed. Ask: *"Does this change introduce or alter a business user flow that would result in new or changed user stories for production?"* If no — if the change is purely visual, structural, or about how something looks rather than what it does — DO NOT modify the PRD. Return: **"No PRD update needed — the change is design-level only."**
>
> 3. If an update IS needed, identify which sections are affected and make targeted edits. Strict content rules:
>
>    **DO include:**
>    - New or modified business rules and constraints
>    - New or modified user flow steps (described as actions and outcomes, not UI interactions)
>    - New data entities, fields, or relationships that production would need to model
>    - New feature areas (add a new section following the document's existing structure)
>
>    **DO NOT include — hard exclusions:**
>    - Visual details: colors, badges, icons, illustrations, layout descriptions, card styles, typography choices
>    - Interaction patterns: "calendar grid", "dropdown", "modal", "bottom sheet", "sidebar collapse", "drag and drop" — describe the capability ("client selects a date"), not the widget
>    - Component or code architecture: shared components, component names, variants, file structure
>    - Responsive behavior: how the UI adapts to screen sizes
>    - Animation or transition descriptions
>    - Empty/loading state visual treatments (unless the *behavior* is a business requirement)
>    - Any detail that only makes sense because you've seen the specific UI implementation
>
> 4. Preserve the existing writing style, structure, and level of detail in the PRD. Match the surrounding tone and granularity.
>
> 5. Do NOT remove or weaken existing requirements unless the design change explicitly replaces prior functionality.
>
> 6. Keep additions concise. A new business rule is one sentence. A new flow step is one bullet point. Don't over-document.
>
> 7. **Self-check before saving:** Re-read every line you added or changed. For each, ask: *"Would this sentence make sense in a PRD for a product built with a completely different tech stack and design system?"* If no, remove it.

---

After the sync completes, briefly inform the user whether the PRD was updated and, if so, summarize the business-level changes only (no visual details).
