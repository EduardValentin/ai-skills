---
name: design-direction-brainstorming
description: Use whenever a UI or UX task adds or changes a visual part of an application, screen, flow, feature, or product surface, especially when the request does not provide a specific design direction.
---

# Design Direction Brainstorming

## Overview

Align on design direction before changing visual UI. The goal is shared, common understanding: the user and agent agree on audience, intent, constraints, desired reaction, and the design direction before layout or styling decisions are chosen.

## When To Use

Use before implementation whenever the user wants to add or modify a visual part of an application:

- A screen, flow, feature, component, page, layout, style, interaction, or product surface will visually change.
- The user asks to add a new visual surface or element, even if they provide a concrete direction.
- The user asks for broad improvement like "make it better", "more premium", "cleaner", "friendlier", or "less cluttered".
- The request does not specify the desired design direction, audience reaction, visual tone, density, or constraints.
- Several aesthetics, layouts, densities, interaction models, or emotional tones could reasonably fit.
- The change affects first impression, trust, perceived quality, product positioning, or user confidence.

## Direction Alignment

Scale the depth to the request:

- If the user gives a specific design direction, briefly restate the direction, note any meaningful tradeoff or constraint, and proceed unless something important is ambiguous.
- If the user does not give a specific direction, pause for a collaborative interview before implementing.
- If the direction is fuzzy, do not treat the first answer as enough. Keep interviewing, synthesizing, and narrowing until the next design choices are constrained.
- Before enough context is gathered, do not state a current lean, recommend a direction, or choose final styling. Naming possible tradeoff dimensions is fine; picking one side is not.
- The first response to an ambiguous visual request is incomplete unless it also says the answers will be synthesized into two or three distinct directions with tradeoffs and visual language, then narrowed into a shared brief before implementation.

Ask targeted questions that change the design decision:

1. Who is the primary audience and what are they trying to do?
2. What should the surface make them feel or believe?
3. What is the business or product goal?
4. What constraints matter: density, speed, brand, accessibility, content length, device, or parity?
5. What should this avoid feeling like?
6. What existing product surfaces, references, or competitors should it resemble or reject?

Interview adaptively. After each answer, reflect back the current read and ask the next highest-leverage question. If the user says "you decide", treat that as permission to lead the alignment process, not permission to skip it. Name the tradeoff dimensions, gather the minimum context needed, then synthesize options before recommending one unless the direction is already unambiguous.

## Options And Recommendation

After enough context is gathered, propose two or three distinct directions. Each direction should include:

- Core idea.
- Best fit.
- Tradeoff.
- Visual language: hierarchy, density, color rhythm, typography, motion, and shape language.

Then recommend one option and explain why it best fits the audience, goal, constraints, and desired impression. The recommendation should be opinionated, but still invite correction before implementation.

## Shared Understanding Output

End with a compact brief:

```markdown
Shared design direction:
- Audience:
- Goal:
- Desired impression:
- Recommended option:
- Visual language:
- Interaction/motion:
- Accessibility and content constraints:
- Things to avoid:
- Open questions:
```

Do not implement until the brief is confirmed or the remaining open questions are clearly non-blocking. If the user disagrees with the recommendation, keep brainstorming until a common direction emerges.
