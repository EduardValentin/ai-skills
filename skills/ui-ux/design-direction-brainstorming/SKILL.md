---
name: design-direction-brainstorming
description: Use when a UI or UX task adds or changes a visual part of an application, screen, flow, feature, or product surface and needs its audience, intent, constraints, or visual language aligned before implementation, especially when the request lacks a specific design direction.
metadata:
  status: experimental
  allows_tool_references: "false"
---

# Design Direction Brainstorming

## Overview

Align audience, intent, constraints, desired reaction, and visual language before changing visual UI. Scale the alignment to uncertainty: preserve a specific supplied direction, and collaboratively narrow an ambiguous one.

## When To Use

Use before implementation whenever the user wants to add or modify a visual part of an application:

- A screen, flow, feature, component, page, layout, style, interaction, or product surface will visually change.
- The user asks to add a new visual surface or element, even if they provide a concrete direction.
- The user asks for broad improvement like "make it better", "more premium", "cleaner", "friendlier", or "less cluttered".
- The request does not specify the desired design direction, audience reaction, visual tone, density, or constraints.
- Several aesthetics, layouts, densities, interaction models, or emotional tones could reasonably fit.
- The change affects first impression, trust, perceived quality, product positioning, or user confidence.

Do not use this skill when the request changes only copy, semantics, data, or nonvisual behavior while explicitly preserving the existing appearance and layout.

## Choose Alignment Depth

### Specific Direction

A supplied direction is specific enough when it meaningfully constrains the intended impression, hierarchy or density, product context, and important limits or references.

The user's supplied direction already confirms that baseline. Briefly reflect it, identify a meaningful tradeoff or constraint, and proceed toward implementation in the same turn. Ask only about an ambiguity or conflict that could materially change the result. Do not require a full interview, option synthesis, complete shared brief, or separate confirmation turn.

### Ambiguous Direction

An ambiguous direction includes broad requests such as "premium," "cleaner," or "friendlier," even when the user says "you decide." Begin an adaptive interview before choosing styling or implementing:

1. Explain that the answers will be synthesized into two or three distinct directions with tradeoffs and visual language, then narrowed into a shared brief before implementation.
2. Ask the highest-leverage question that changes the design decision.
3. Reflect the current read after each answer and continue narrowing until the next design choices are constrained.

Before enough context is gathered, name relevant tradeoff dimensions but do not state a current lean, recommend a direction, choose final styling, or implement. Permission to "use your judgment" means lead the alignment process; it does not remove the need for shared understanding.

## Decision-Shaping Questions

Ask only questions that change the direction:

1. Who is the primary audience and what are they trying to do?
2. What should the surface make them feel or believe?
3. What is the business or product goal?
4. What constraints matter: density, speed, brand, accessibility, content length, device, or parity?
5. What should this avoid feeling like?
6. What existing product surfaces, references, or competitors should it resemble or reject?

## Options And Recommendation

After enough context is gathered, propose two or three distinct directions. Each direction should include:

- Core idea.
- Best fit.
- Tradeoff.
- Visual language: hierarchy, density, color rhythm, typography, motion, and shape language.

Then recommend one option and explain why it best fits the audience, goal, constraints, and desired impression. Be opinionated, invite correction or confirmation, and do not implement in the same response.

## Shared Understanding Output

Produce the full brief only after enough context exists to synthesize and recommend. During early interview turns, reflect the current read without inventing undecided fields.

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

For the ambiguous path, do not implement until the user confirms the brief or explicitly delegates the final selection after seeing the recommendation. If the user disagrees, keep brainstorming until a common direction emerges. For the specific path, the compact alignment check is sufficient because the original request already confirmed the baseline.
