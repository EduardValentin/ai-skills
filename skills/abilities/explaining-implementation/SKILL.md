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

Explain existing work as a paced walk through a bounded hierarchy, one concept
per turn, one root at a time from its top rung down to its floor, each turn
picking up the thread of the last, moving only when the reader says so.

**Core principle:** the reader sets the pace and the depth. A complete report
delivered up front is the failure, however well organized it is.

**Not for:** writing code, planning work, reviewing for defects, or drafting
prose someone else will read.

## Invariants

1. **One concept per turn, then stop.** Never two concepts in one message, never
   a teaser for the next one.
2. **Rung discipline.** No code beyond the current rung's allowance. Descend
   only when the reader moves, one step at a time, into a child of the concept
   just explained.
3. **Grounded.** Every concept traces to something actually read. State gaps
   instead of smoothing over them.
4. **Simplifications declared.** Say so whenever an example has been simplified.
5. **Every named file is a link the reader can open locally.** Whenever a turn
   names a file, cite it as a markdown link whose target is a path in the
   reader's own checkout, relative to the repository root, and append a line
   number when the concept sits at one exact place. Never substitute a hosted or
   remote view of the code. When the subject is not present in a local checkout,
   say so plainly instead of linking somewhere the reader cannot inspect.

## The Ladder

| Rung | Content                                              | Code allowed                                        |
| ---- | ---------------------------------------------------- | --------------------------------------------------- |
| L1   | Architecture, system boundaries, the kernel idea     | High-level pseudocode mirroring the real shape      |
| L2   | Components and files, and the contracts between them | Signatures and interfaces, no bodies                |
| L3   | Data structures, state, control flow                 | Small simplified snippets                           |
| L4   | Function implementations                             | Real code from the subject, quoted with a link to its exact location |

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
4. **Walk.** One concept per turn, in walk order, in the shape below. Move only
   when the reader moves.
5. **End.** After the last concept of the last root, say the walk is complete
   and stop.

### Walk Order

Depth first. A concept is followed by its own children, rung by rung to the
bottom of its branch, before its next sibling; a root's whole branch is finished
before the next root begins. Each step down is one rung, or the next rung that
holds something real. A concept with nothing meaningful beneath it is a leaf;
never invent a child to keep the tree symmetric.

Two roots, where the second component of the first root holds nothing real at
L3:

```
Root 1 of 2
Root 1 → Component 1 of 2
Root 1 → Component 1 → Mechanism 1 of 1
Root 1 → Component 1 → Mechanism 1 → Function 1 of 2
Root 1 → Component 1 → Mechanism 1 → Function 2 of 2
Root 1 → Component 2 of 2
Root 1 → Component 2 → Function 1 of 1
Root 2 of 2
```

### One Turn

- Header carrying position and name: `Root 1 → Component 2 of 2 — <name>`. One
  segment per rung walked, named `Root`, `Component`, `Mechanism`, and
  `Function` for L1 to L4; only the last segment carries its count.
- Thread, before the body: one or two sentences placing the concept in the walk
  so far. Say what the concept above needed that this one supplies; for a root,
  the concept above is the subject itself. After a sibling, say what this one
  adds or does differently. After a climb, close the branch just left in a
  clause before placing the new concept. Continuity looks back, never ahead.
- 150 to 250 words
- At most one code or pseudocode block, calibrated to the rung
- Footer: `[Root 1 → Component 2/2] · continue · more · skip`, without `skip`
  at a leaf
- Stop. Say nothing else.

### Moves

`continue` moves to the next concept in walk order: the first child of the
concept just explained, or at a leaf its next sibling, climbing to the nearest
ancestor with a next sibling when it has none. `skip` leaves the children of the
concept just explained unvisited and moves to its next sibling, climbing the
same way. `more` elaborates the same concept at the same altitude — motivation,
nuance, another example — and never descends.

## Interruptions

Answer an off-script question, then return to the exact position in the walk.
Do not restart, re-list, or drift.

Never offer a jump out of walk order. Comply when the reader explicitly asks for
one; a direct instruction outranks this procedure.

## Red Flags

| Thought                                                | Reality                                                                               |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| "This pull request is tiny, I'll explain it in one go" | Small subjects have fewer rungs, not bigger turns.                                     |
| "They'll obviously want the code"                      | Code above its rung is the dump in disguise.                                           |
| "This concept makes no sense without its internals"    | That is the signal it is a parent. Explain the shape; the internals are the next rung. |
| "I'll cover this rung for every root before going deeper" | Each root visited between a concept and its children is a context switch. Finish the branch first. |
| "This branch is routine, I'll move on to the next root" | Depth is the reader's call. `skip` is theirs, not yours.                             |
| "This child is small, I'll fold it into the parent's turn" | A turn holds one rung. A child too small for its own turn is not a child; it is part of the parent's shape. |
| "The header already shows where we are"               | The header is a coordinate, not a connection. Open with the thread.                   |
| "I'll summarize what's coming"                         | Pre-summarizing is dumping, spread out.                                                |
| "They asked a question, I'll re-explain from the top"  | Answer it and resume in place.                                                         |
| "Naming the file is enough, they can find it"          | An unlinked file name hands the reader a search. Link it.                              |
| "A hosted link shows the same code and renders nicely" | It is not the reader's checkout. Link the local path.                                  |
