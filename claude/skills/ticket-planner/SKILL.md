---
name: ticket-planner
description: "Agile ticket planning for personal projects using Linear. Creates epics and user stories with complete descriptions including overview, acceptance criteria, and technical details. Analyzes the React design reference app (designs/ folder) and PRD.md to generate well-defined, implementation-ready tickets. Invoke with /ticket-planner."
disable-model-invocation: true
---

# Ticket Planner

A structured workflow for planning and creating agile epics and user stories in Linear. The agent reads the project's React design reference app and PRD to generate complete, implementation-ready tickets — then creates them in Linear with proper metadata.

**Supported project types:** Personal projects (Linear). Other project types (e.g., work projects using Jira) may be added in the future.

---

## Prerequisites

Before any ticket planning begins, the agent MUST complete ALL of the following steps in order. Do not skip any step.

### Step 1: Verify Linear MCP Availability

Attempt to use a Linear MCP tool (e.g., list teams or projects). If the tool is not available or returns an authentication error:

1. Inform the user: "The Linear MCP server is not connected. Please restart Claude Code so it picks up the Linear MCP configuration, then authenticate when prompted."
2. Do NOT proceed until Linear tools are confirmed working.

### Step 2: Identify the Linear Project

1. Use the Linear MCP to list existing projects in the user's workspace.
2. Ask the user which project these tickets belong to. Present the list of existing projects for reference.
3. If the user names a project that doesn't exist yet, confirm the preferred name, then create the project in Linear using the MCP.
4. Store the project ID for all subsequent ticket creation in this session.

### Step 3: Ensure the "Epic" Label Exists

1. Use the Linear MCP to check if an "Epic" label exists in the workspace.
2. If it doesn't exist, create it. Use a distinctive icon/color if the Linear MCP supports it.
3. This label is used to distinguish epic issues from normal user story issues.

### Step 4: Read Product Context

Read ALL available context sources to build a comprehensive understanding of the product.

**4a. PRD.md (Product Requirements Document)**

- Look for `PRD.md` at the project root.
- If found, read it in full. This is the source of truth for business logic, user flows, functional requirements, and business rules.
- If not found, note its absence. The design reference app becomes the primary context source.

**4b. React Design Reference App**

- Look for a `designs/` folder in the project root containing a React app.
- Discovery strategy (follow in order):
  1. Check if `<project-root>/designs/` exists and contains a folder with a `package.json` that has React as a dependency. If found, that's the reference app.
  2. If the folder structure isn't obvious, search for `.jsx` and `.tsx` files inside `designs/` recursively. The nearest parent with a `package.json` is the reference app root.
  3. If no `designs/` folder or React files are found, ask the user for the path to their design reference app.

- Once located, spawn a **sub-agent** (using the Agent tool) to analyze the reference app:

  > **Task: Analyze the React reference app and catalog all user flows, features, and business logic**
  >
  > Scan the React reference app at `[reference app path]`. Produce a comprehensive inventory of everything the app does from a *product* perspective.
  >
  > **What to analyze:**
  > - Router configuration: all routes/pages and their hierarchy
  > - Each page component: what it displays, what actions a user can take, what states it has
  > - Forms and inputs: what data is collected, what validation exists, what happens on submit
  > - Navigation flows: how users move between pages, conditional navigation
  > - User types/roles: any role-based UI differences (e.g., coach vs client portals)
  > - Mock data structures: what entities exist, their fields and relationships
  > - Interactive elements: modals, drawers, toggles, filters, scheduling, messaging flows
  > - State management: what global/shared state exists and what it represents in product terms
  > - Notifications, alerts, empty states, error states
  >
  > **Output format:** Return a structured report organized by feature area / user flow. For each flow, describe:
  > - Who the user is (role)
  > - What they can do (actions, inputs, decisions)
  > - What the system does in response (displays, navigates, updates state)
  > - What business rules are implied (constraints, validations, permissions)
  > - What data entities are involved
  >
  > Describe everything in product/business terms. Do NOT include component names, file paths, or implementation details.

- Wait for the sub-agent's report. This analysis, combined with the PRD, forms the full product context for ticket planning.

**If neither PRD.md nor a designs/ folder exists:** Inform the user that there's no product context available and ask them to describe the features manually. Proceed in a purely conversational mode.

### Step 5: Determine the Scenario

Based on the user's request (from `$ARGUMENTS` or by asking), determine which workflow to follow:

| User Intent | Scenario |
|---|---|
| Create a single epic for a specific feature area | **Scenario A: Single Epic** |
| Plan all epics for the project (big picture first) | **Scenario B: Bulk Epic Planning** |
| Create a user story / ticket under an existing epic | **Scenario C: User Story Creation** |
| Create an epic AND its tickets together | **Scenario D: Epic + Tickets** |

If the intent is unclear from the arguments, ask: "What would you like to do?"
- **(A)** Create a single epic for a feature area
- **(B)** Plan all high-level epics for the project
- **(C)** Create a user story under an existing epic
- **(D)** Create an epic with all its user stories

---

## Linear Modeling Conventions

### Epics

Epics are modeled as **normal Linear issues** with the following distinctions:

- **Label:** Must have the "Epic" label to distinguish them from regular user stories.
- **Description:** Contains a high-level overview of the feature area, its goals, and scope.
- **Sub-issues:** Each user story belonging to this epic is created as a sub-issue of the epic issue.
- **Project:** Always assigned to the project identified in Step 2.

### User Stories (Tickets)

User stories are normal Linear issues created as **sub-issues** of their parent epic. Their description follows the Ticket Template below.

### Metadata

For every issue created, set appropriate metadata:

- **Title:**
  - Epics: descriptive noun phrase (e.g., "Workout Plan Creation", "Client Onboarding Flow")
  - User stories: imperative action describing a capability (e.g., "Create workout plan from template", "Assign exercises to a plan day")
- **Priority:** Set based on the feature's importance and dependencies. If unsure, ask the user.
- **Labels:** "Epic" for epics. Additional labels as appropriate (e.g., feature area tags). If unsure, ask.
- **Estimate:** If the workspace uses estimates, ask the user for their estimation scale and set accordingly.
- **Project:** Always assign to the identified project.
- **Any other field:** If unsure about any metadata field, ask the user before creating the issue.

### Duplicate Detection (Required Before Every Creation)

Before creating ANY issue (epic or user story) in Linear, the agent MUST:

1. Use the Linear MCP to fetch all existing issues in the target project.
2. Compare the proposed epic or story against existing issues by title, scope, and description.
3. If a matching or overlapping issue already exists:
   - Inform the user: "I found an existing issue that may already cover this: **[Issue Title]** ([Issue ID] — [status]). [Brief description of what it covers.]"
   - Ask the user how to proceed: create a new one anyway, skip it, or update the existing one.
4. If no match is found, proceed with creation.

This check applies to every individual epic and every individual user story — not just once per session.

---

## Ticket Template

Every user story description MUST follow this structure:

```
## Overview

[1-3 sentences describing the bigger picture. What feature area does this belong to? Why does
this ticket exist? What user need does it address? An engineer or AI agent reading this should
immediately understand the context without needing to read other tickets.]

## Acceptance Criteria

[Bulleted list of clear, testable criteria. Each criterion is a specific, observable behavior
that must be true for this ticket to be considered done.]

- [ ] [Criterion 1]
- [ ] [Criterion 2]
- ...

## Technical Details

[Key implementation details that an engineer or AI agent needs to build this feature completely.
This section bridges business requirements and implementation.]

- **Data entities and fields:** What data this feature reads, writes, or modifies
- **User flow:** Step-by-step description of what happens (user action → system response)
- **Business rules and validations:** Constraints that must be enforced
- **Edge cases:** Empty states, error states, boundary conditions, concurrent access
- **Integration points:** How this feature interacts with other features or systems
- **Design reference:** Which pages/routes in the design reference app show this feature
- **PRD reference:** Which PRD sections describe the business rules for this feature (if applicable)
```

---

## Scenario A: Single Epic Creation

1. **Identify the feature area.** From the user's request and the product context (PRD + design analysis), determine which feature area the epic covers.

2. **Deep-dive analysis.** Re-read the relevant sections of the PRD and design analysis report. Identify:
   - All user flows in this area
   - All screens/pages involved
   - All interactive elements and their behaviors
   - Business rules and constraints
   - Data entities involved
   - Edge cases (empty states, errors, limits, permissions)

3. **Ask clarifying questions.** Act as a professional product manager. Before creating the epic, ask the user targeted questions that:
   - Fill gaps in the PRD or design reference
   - Surface edge cases the user may not have considered
   - Clarify ambiguous business rules
   - Confirm assumptions about user flow branching
   - Address permissions and role-based behavior
   - Probe error handling and failure scenarios

   Present all questions in a single organized batch, grouped by topic. Do NOT drip-feed questions one at a time.

4. **Present the epic.** After clarifications, present the proposed epic:
   - Epic title
   - Epic description (overview of the feature area, goals, scope)
   - List of user stories that would fall under this epic (titles only, to show scope)
   - Proposed metadata (priority, labels)

5. **Preview and refine.** Present the full epic draft to the user and enter a refinement loop:
   - The user may approve as-is, or request changes to the title, description, scope, or metadata.
   - Apply requested changes and present the updated draft.
   - Repeat until the user explicitly approves.
   - Do NOT create anything in Linear until the user says the draft is final.

6. **Check for duplicates.** Run the Duplicate Detection check (see Linear Modeling Conventions). If a matching epic exists, inform the user and ask how to proceed before creating anything.

7. **Create in Linear.** Only after explicit approval and duplicate check, use the Linear MCP to:
   - Create the epic issue with the "Epic" label, description, and metadata
   - Assign it to the project
   - Report the created issue URL to the user

8. **Offer next steps.** Ask: "Want me to create the user stories for this epic now?"

---

## Scenario B: Bulk Epic Planning

1. **Comprehensive product analysis.** Using the full product context (PRD + design analysis), identify ALL major feature areas that would each constitute an epic. Think holistically:
   - Core product flows (the main things users do)
   - Supporting features (settings, profiles, preferences)
   - Onboarding/setup flows
   - Management and admin features
   - Cross-cutting concerns (notifications, search, navigation)

2. **Present the epic roadmap.** List all proposed epics with:
   - Epic title
   - 1-2 sentence scope description
   - Rough complexity indicator (small / medium / large)
   - Suggested priority order

3. **Get approval.** The user may:
   - Approve the list as-is
   - Add, remove, rename, merge, or split epics
   - Reorder priorities

   Iterate until the user approves the final list.

4. **Detail each epic.** Go through each approved epic one at a time:

   a. Present a detailed analysis of the epic's scope based on the PRD and design reference.

   b. Ask clarifying questions specific to this epic (same PM behavior as Scenario A, Step 3). Focus on aspects unique to this epic — do not repeat questions already answered during earlier epics.

   c. After the user answers, present the final epic title, description, and list of user stories it would contain (titles only).

   d. Enter a refinement loop: present the draft, let the user request changes, update, and repeat until explicitly approved.

   e. Do NOT move to the next epic until the current one is finalized.

5. **Check for duplicates and create in Linear.** After each epic is individually approved, run the Duplicate Detection check. If no conflict, create it in Linear:
   - Create the epic issue with the "Epic" label, description, and metadata
   - Assign it to the project
   - Report the created issue URL

6. **Summary.** After all epics are created, present a summary of all epic URLs.

7. **Offer next steps.** Ask: "All epics are created. Want to dive into any of them and create its user stories?"

---

## Scenario C: User Story Creation

1. **Identify the story.** From the user's request, determine what user story / feature they want to create a ticket for.

2. **Find the parent epic.**
   - Use the Linear MCP to fetch all issues with the "Epic" label in the current project.
   - Based on the story's topic, infer which epic it belongs to.
   - If confident (strong match), confirm with the user: "This seems to belong under the '[Epic Name]' epic. Correct?"
   - If unsure (multiple possible matches or no clear match), present the list of epics and ask: "Which epic should this story go under?"
   - If no epics exist yet, inform the user and offer to create one first (switch to Scenario A or D).

3. **Deep-dive analysis.** Read the relevant PRD sections and design reference analysis for this specific feature. Identify:
   - The exact user flow step by step
   - All UI states (default, loading, empty, error, success)
   - Business rules and validations
   - Data entities and fields involved
   - Interactions with other features

4. **Ask clarifying questions.** Focus specifically on:
   - Details the PRD mentions vaguely or omits for this feature
   - Edge cases visible in the design but not documented
   - Business decisions that affect acceptance criteria
   - Scope boundaries — what's in vs. out for this specific story

   Present all questions in a single organized batch.

5. **Present the ticket.** Show the full ticket following the Ticket Template:
   - Title
   - Full description (overview, acceptance criteria, technical details)
   - Proposed metadata (priority, labels, estimate)
   - Parent epic confirmation

6. **Preview and refine.** Present the full ticket draft to the user and enter a refinement loop:
   - The user may approve as-is, or request changes to the title, description, acceptance criteria, technical details, or metadata.
   - Apply requested changes and present the updated draft.
   - Repeat until the user explicitly approves.
   - Do NOT create anything in Linear until the user confirms the draft is final.

7. **Check for duplicates.** Run the Duplicate Detection check (see Linear Modeling Conventions). If a matching story exists under the same epic, inform the user and ask how to proceed.

8. **Create in Linear.** Only after explicit approval and duplicate check, use the Linear MCP to:
   - Create the issue as a sub-issue of the parent epic
   - Set all metadata
   - Assign to the project
   - Report the created issue URL to the user

9. **Offer next steps.** Ask: "Want to create another story under this epic, or a different one?"

---

## Scenario D: Epic + Tickets (Combined)

This combines Scenario A and multiple rounds of Scenario C into a single flow.

1. **Follow Scenario A Steps 1-6** to identify, clarify, and create the epic in Linear.

2. **Plan the stories.** Based on the product context and clarifications gathered during epic creation, propose a list of user stories:
   - Story titles
   - Brief scope description for each
   - Suggested order (by dependency or implementation priority)

3. **Get approval on the story list.** The user may add, remove, reorder, merge, or split stories. Iterate until approved.

4. **Detail each story.** For each approved story:

   a. Draft the full ticket following the Ticket Template.

   b. Ask clarifying questions specific to this story. Since epic-level clarifications are already done, focus on story-level details:
      - Exact acceptance criteria and their edge cases
      - Interactions with other stories in this epic
      - Business rules not yet covered at the epic level

   c. Present the full ticket draft and enter a refinement loop: the user may request changes to any part of the ticket. Apply changes, re-present, and repeat until the user explicitly approves.

   d. Run the Duplicate Detection check. If a matching story exists, inform the user and ask how to proceed.

   e. Only after approval and duplicate check, create the issue in Linear as a sub-issue of the epic. Report the URL.

5. **Summary.** After all stories are created, present a final summary:
   - Epic title and URL
   - All created stories with their URLs
   - Any open questions or future considerations noted during the process

---

## Product Manager Behavior

Throughout ALL scenarios, the agent MUST behave as a professional product manager. This is not optional — it is a core part of the skill.

### Asking Smart Questions

Questions must NOT be generic checklists. They must be **specific to the feature at hand** and demonstrate that the agent has thoroughly read and understood the PRD and design reference. Good questions:

- Surface **contradictions** between the PRD and design reference (e.g., "The PRD says clients can only see published plans, but the design shows a 'Draft' tab in the client view. Which is correct?")
- Identify **missing flows** (e.g., "The design shows a delete button on exercises, but the PRD doesn't specify what happens to exercise history when a plan is deleted")
- Probe **business edge cases** (e.g., "What happens if a coach assigns an exercise that's already in the plan for that day?")
- Clarify **role-based behavior** (e.g., "Can clients view workout plans still in draft, or only published ones?")
- Ask about **limits and constraints** (e.g., "Is there a maximum number of exercises per day? Per plan?")
- Consider **state transitions** (e.g., "Can a completed plan be reactivated? Under what conditions?")
- Think about **data lifecycle** (e.g., "When a template is updated, do existing plans created from it inherit the changes?")
- Probe **error scenarios** (e.g., "What should happen if the coach loses connectivity while editing a plan?")

### Ensuring Completeness

Before finalizing any ticket, mentally walk through the entire user flow and verify:

- **Happy path** is fully defined
- **Error states** are considered (network failure, validation errors, permission denied)
- **Empty states** are addressed (first-time user, no data yet)
- **Loading states** are mentioned where relevant
- **Boundary conditions** are covered (max/min values, character limits, pagination)
- **Cross-feature impact** is noted (how this feature affects or is affected by others)
- **Permissions** are explicit (who can see this, who can edit, who can delete)

### PRD Sync After Clarifications

When the user answers clarifying questions and their answers introduce new details that are **not already documented** in the PRD, the agent MUST update `PRD.md` with those details — but ONLY if the new information is about:

- Business rules or constraints
- Domain concepts or data models
- User flows or flow branching
- Permissions or role-based behavior
- State transitions or lifecycle rules
- Edge cases with business implications

**Do NOT update the PRD with:**
- Implementation or technology details
- Styling, layout, or visual decisions
- UI interaction patterns (dropdown vs. modal, etc.)
- Component or code architecture

**How to execute:**

1. After the user answers clarifying questions, review each answer and identify any new business-level details not already in the PRD.
2. If new details exist and a `PRD.md` is present, spawn a **background sub-agent** (using the Agent tool) with instructions:

   > **Task: Update PRD.md with new business details from ticket planning clarifications**
   >
   > The user provided the following clarifications during ticket planning:
   > [Include the relevant Q&A pairs — only the ones that contain new business-level information]
   >
   > Read `PRD.md` in full. Find the relevant section(s) and add the new details. Follow these rules:
   > - Only add business rules, domain concepts, user flows, permissions, state transitions, or edge cases with business implications.
   > - Do NOT add implementation details, styling, UI patterns, or component architecture.
   > - Preserve the existing writing style, structure, and level of detail.
   > - Keep additions concise — one sentence per rule, one bullet per flow step.
   > - Self-check: for each line added, ask "Would this make sense in a PRD for a completely different tech stack and design system?" If no, remove it.

3. The sub-agent runs in the background so it does not block ticket creation.
4. Once it completes, briefly inform the user that the PRD was updated and summarize what was added.

If no `PRD.md` exists, skip this step entirely.

### What NOT to Do

- Do NOT create tickets with vague acceptance criteria like "the feature works correctly"
- Do NOT skip clarifying questions to save time — incomplete tickets cost more later
- Do NOT assume business rules that aren't explicitly stated in the PRD or design — ask
- Do NOT create tickets that duplicate functionality already covered by existing tickets in Linear
- Do NOT include specific UI framework implementation details (e.g., "use a `<Dialog>` component") — describe the behavior, not the widget
- Do NOT rush through multiple stories without pausing for user input on each one

---

## Definition of Done

A ticket planning session is complete when:

- [ ] All product context has been read and analyzed (PRD + design reference app)
- [ ] The correct Linear project is identified or created
- [ ] The "Epic" label exists in the workspace
- [ ] Clarifying questions have been asked and answered for every epic and story
- [ ] Every epic has the "Epic" label and a clear scope description
- [ ] Every user story follows the Ticket Template (overview, acceptance criteria, technical details)
- [ ] Every issue has appropriate metadata (priority, labels, project, estimate if applicable)
- [ ] User stories are linked as sub-issues of their parent epic
- [ ] All issues are created in Linear via the MCP
- [ ] The user has explicitly approved every epic and story before creation
- [ ] Issue URLs have been reported to the user
- [ ] If the user's clarification answers introduced new business-level details, `PRD.md` has been updated accordingly

---

## Important Reminders

- **Always read before you write.** The PRD and design reference app must be fully analyzed before any ticket is drafted.
- **When in doubt, ask.** It is always better to ask a clarifying question than to make an assumption that leads to an incomplete or incorrect ticket.
- **Preview before creating.** Always show the full draft of an epic or ticket and enter a refinement loop with the user. Never create anything in Linear until the user explicitly confirms the draft is final.
- **One approval at a time.** Never batch-create multiple tickets without individual user approval for each one.
- **The user has the final say.** If the user disagrees with a proposed ticket structure, priority, or scope — adjust. Do not argue for the "correct" agile way.
- **Keep context across the session.** If the user already answered a question during an earlier epic, do not ask it again. Build on prior answers.
- **Linear is the system of record.** Every epic and story discussed must end up as a created issue in Linear. Do not leave approved tickets uncreated.
