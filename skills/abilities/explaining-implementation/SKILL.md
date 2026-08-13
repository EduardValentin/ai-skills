---
name: explaining-implementation
description: >-
  Use when explaining a technical implementation, code review, pull request,
  algorithm, or any existing piece of code to a person, one concept at a time
  from architecture down to functions.
compatibility: >-
  Works standalone from any readable subject — a repository, a diff, a file, or
  a described algorithm. Needs no configuration.
metadata:
  status: experimental
  allows_tool_references: "false"
---

# Explaining Implementation

## Overview

Explain existing work as a paced walk down a bounded hierarchy, one concept per
turn, moving only when the reader says so.

**Core principle:** the reader sets the pace and the depth. A complete report
delivered up front is the failure, however well organized it is.

**Not for:** writing code, planning work, reviewing for defects, or drafting
prose someone else will read.

## Invariants

1. **One concept per turn, then stop.** Never two concepts in one message, never
   a teaser for the next one.
2. **Rung discipline.** No code beyond the current rung's allowance, and no
   descending except through an explicit descent step.
3. **Grounded.** Every concept traces to something actually read. State gaps
   instead of smoothing over them.
4. **Simplifications declared.** Say so whenever an example has been simplified.

## The Ladder

| Rung | Content                                              | Code allowed                                        |
| ---- | ---------------------------------------------------- | --------------------------------------------------- |
| L1   | Architecture, system boundaries, the kernel idea     | High-level pseudocode mirroring the real shape      |
| L2   | Components and files, and the contracts between them | Signatures and interfaces, no bodies                |
| L3   | Data structures, state, control flow                 | Small simplified snippets                           |
| L4   | Function implementations                             | Real code from the subject, quoted with its path and line number |

L4 is the floor. Never go below function implementations.

Skip a rung that holds nothing real rather than padding it: a small pull request
may run L2 then L4.

Above L4, write examples for clarity instead of pasting them. Strip error
handling, generics, and edge cases, and say that you did.

An algorithm or a design maps onto the same ladder: L1 the core idea and its
invariant, L2 the phases, L3 the data structures and control flow, L4 the
implementation.

**Root test:** a concept belongs at the current rung when removing it would make
its siblings meaningless. A concept that only makes sense after another has been
explained is a child; it belongs one rung down.

## The Walk

1. **Scope.** When the request does not identify a single subject — a pull
   request with no identifier, a named flow matching several implementations —
   ask a clarifying question and build nothing until it is answered.
2. **Research.** State in one line what you are about to read, then read in
   silence. Ground concepts in how the subject behaves inside the application;
   the filenames in a diff start the research and never stand in for the
   explanation.
3. **List the roots.** A concise numbered list of root concept titles, with
   nothing attached to them, then stop.
4. **Walk the rung.** One concept per turn, in the shape below.
5. **Descend.** After the last sibling, offer one level down. Group deeper rungs
   by parent and name the parent in the header: `Root 2 → Component 1 of 3`. A
   parent with nothing meaningful beneath it does not appear; never invent a
   child to keep the tree symmetric.
6. **Floor.** When a branch bottoms out at L4, or nothing meaningful remains,
   say so and stop offering to descend.

### One Turn

- Header carrying position and name: `Root 2 of 5 — <name>`
- 150 to 250 words
- At most one code or pseudocode block, calibrated to the rung
- Footer: `[Root 2/5] · continue · more`
- Stop. Say nothing else.

`continue` moves to the next sibling. `more` elaborates the same concept at the
same altitude — motivation, nuance, another example — and never descends.

## Interruptions

Answer an off-script question, then return to the exact position in the walk.
Do not restart, re-list, or drift.

Never offer an out-of-order descent into a single concept. Comply when the
reader explicitly asks for one; a direct instruction outranks this procedure.

## Red Flags

| Thought                                                | Reality                                                                               |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| "This pull request is tiny, I'll explain it in one go" | Small subjects have fewer rungs, not bigger turns.                                     |
| "They'll obviously want the code"                      | Code above its rung is the dump in disguise.                                           |
| "This concept makes no sense without its internals"    | That is the signal it is a parent. Explain the shape; the internals are the next rung. |
| "I'll summarize what's coming"                         | Pre-summarizing is dumping, spread out.                                                |
| "They asked a question, I'll re-explain from the top"  | Answer it and resume in place.                                                         |
