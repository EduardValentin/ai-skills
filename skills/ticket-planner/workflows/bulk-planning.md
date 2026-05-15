# Bulk Epic Planning Workflow

Use when the user wants all major epics for a project.

## Steps

1. Read the available product context broadly.
2. Identify major product capabilities:
   - Core user flows
   - Onboarding and setup
   - Management/admin areas
   - Settings and preferences
   - Search, notifications, and navigation
   - Cross-cutting data or permission concerns
3. Present an epic roadmap with:
   - Epic title
   - 1-2 sentence scope
   - Complexity: small, medium, or large
   - Suggested priority order
   - Prototype/PRD source areas
4. Let the user add, remove, rename, merge, split, or reorder epics.
5. After the roadmap is approved, detail one epic at a time using [single-epic.md](single-epic.md).
6. Do not create or move to the next epic until the current epic is approved.
7. Summarize approved epic drafts and ask which epic should receive vertical-slice stories next.
8. If the user wants to publish the approved roadmap, infer the issue tracker from project docs or ask, then switch to the relevant tracker-specific publishing skill.

## Quality Bar

Prefer fewer coherent epics over one epic per screen. Use the prototype to ensure coverage, not to define the hierarchy by UI navigation alone.
