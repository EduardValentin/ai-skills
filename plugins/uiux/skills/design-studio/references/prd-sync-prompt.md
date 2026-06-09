# PRD Sync Prompt

Use after a design-studio change when product behavior may have changed. Replace `<summary>` with what users can now do or what business rule changed.

```markdown
Sync PRD.md with this behavior change:

<summary>

Steps:
1. Read PRD.md.
2. Decide whether the change affects production user stories: capabilities, rules, data model, permissions, flow steps, branching, removal, or replacement.
3. If no, do not edit PRD.md. Return: "No PRD update needed - design-level only."
4. If yes, make the smallest targeted update that preserves the document style.

Include only:
- business rules and constraints
- user flow steps described as actions and outcomes
- data entities, fields, or relationships
- feature areas or behavior changes

Exclude:
- visual details
- widget or layout descriptions
- component names or code structure
- responsive behavior
- animation
- purely visual empty/loading/error treatments

Before saving, confirm every added sentence would still make sense for a different implementation and design system.
```

After sync, tell the user whether `PRD.md` changed and summarize business-level changes only.
