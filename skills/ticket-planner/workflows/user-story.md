# User Story Workflow

Use when the user wants one implementation-ready story under an existing epic.

## Steps

1. Identify the requested capability and intended user role.
2. Find or confirm the parent epic. If no epic exists, offer to create one first.
3. Read [../references/ticket-quality.md](../references/ticket-quality.md) and, when a prototype exists, [../references/prototype-boundaries.md](../references/prototype-boundaries.md).
4. Deep-dive the relevant PRD sections, prototype routes/states, feature brief, plan, or approved interview brief.
5. Ask only blocking story-level questions:
   - Business rules not documented
   - Scope boundaries
   - Permissions
   - Failure or lifecycle behavior
   - Integration points and dependencies on other stories
6. Draft the ticket using the user story template.
7. Include prototype route/screen/state references instead of duplicating prototype copy or visual details.
8. Verify it is a vertical slice: one user-observable outcome plus all relevant integration points.
9. Refine until the user explicitly approves the exact title, description, parent, and scope.
10. If the user wants to publish the approved story, infer the issue tracker from project docs or ask, then switch to the relevant tracker-specific publishing skill.

## Quality Bar

The story should be testable from public behavior. Acceptance criteria should let QA or an implementation agent verify the result without knowing internal component names.
