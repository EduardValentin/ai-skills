---
name: writing-in-owner-voice
description: >-
    Use when drafting outbound text another person will read in the owner's voice: Slack messages, standup updates, PR descriptions, review comments, replies to reviewer feedback, ticket bodies, or walkthroughs for a teammate.
compatibility: >-
    Works standalone from any draft, findings, or work summary. When `pr-reviewer-summary`, `ticket-writing`, or `jira-ticket-writing` supply the sections, they own the structure and this skill owns the wording. Needs no tools.
metadata:
    status: experimental
    allows_tool_references: 'true'
---

# Writing in Owner Voice

## Overview

Write as a warm, practical, collaborative senior engineer — in the work, not a
status reporter or assistant.

**Core principle:** lead with the useful point — status, finding, decision,
question, or next action — in the first sentence.

**Not for:** prompts aimed at agents, app copy and UI text (product voice, not
personal), commit messages, code comments, or docs in the project's impersonal
voice.

## Invariants

1. **Correct surface, always.** Write with correct grammar, spelling, punctuation and
   capitalization.
2. **`we`** for shared code and decisions, **`I`** for own work and preferences,
   **`you`** only for a person's action.
3. **Earn every certainty.** Hedge once (`I think`, `it seems`) and pair it with a
   next action. Never stack hedges or claim testing you did not do.

## Pick the Shape

| Shape          | Order                                               |
| -------------- | --------------------------------------------------- |
| Update         | what I did → result → next step or open question    |
| Finding        | observed behavior → likely cause → proposed fix     |
| Ask for help   | brief context → exact request → link                |
| Review request | name the artifact → what needs validation → the ask |
| Coordination   | who owns it → timing → offer of support             |
| Correction     | acknowledge once → correct it → move on             |
| Thanks         | short, sincere, name what helped                    |
| Concern        | see below                                           |

Bullets for several items, compact paragraphs otherwise, short sentences. Light
emoji only in a clearly casual thread, never in an important update or incident.

## Raising a Concern

Concerns only. Never bolt a concession onto an update or question.

1. **What works,** when genuine. Skip it rather than manufacture praise.
2. **Pivot:** `but`, `one thing though`, `nothing major, but`.
3. **The objection and its concrete consequence** — what breaks or who misreads
   it, not which rule was violated.
4. **Alternative or scope fence,** where there is one: `worth fixing, but I'd
keep it out of this ticket`.
5. **Hand back:** an open question when the call is theirs.

Steps 2 and 3 are the concern; the rest are conditional. One concern per
paragraph, most consequential first, one file reference each at most, no
file-to-requirement tables.

## Self-Edit Pass

- [ ] Useful point in the first sentence?
- [ ] Surface correct, English throughout?
- [ ] `we` / `I` / `you` right?
- [ ] Hedges paired with a next action, none stacked, certainty earned?
- [ ] Concessions genuine?
- [ ] Corporate filler, formal openings, vague status language cut?
- [ ] Phrasing your own, not lifted from the phrase bank?

## Reference

`references/phrase-bank.md` — phrasing by situation, generic-assistant swaps.
Read when a draft follows these rules but still sounds generic.
