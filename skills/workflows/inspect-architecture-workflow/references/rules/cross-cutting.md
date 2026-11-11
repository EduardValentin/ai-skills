# Cross-cutting rules

The rules about value and priority (R1 to R3), and the conventions every other rule group relies
on: when a condition is not raised, which severity a finding carries (always the one in its
condition's table row), and what a correction may propose.
Read this file before any other rule group, and read the vocabulary first if a term is unfamiliar.

## Applying any rule

- Read a rule's `Not a finding when:` line before raising anything under it. Where the rule has
  more than one condition, each clause of that line names the condition it exempts and exempts no
  other.
- A target covered by a recorded exception is not a finding.
- A condition that lacks a fact or a classification it needs is incomplete. It is never reported
  as passing and never guessed.
- A finding takes the base severity in its condition's row. A reviewer never regrades a condition,
  and a check and a reviewer report the same severity for the same condition; only the escalation
  the flow applies can raise it. What relaxes a rule for a project is its status, never a lowered
  severity.
- Speculation never blocks. Only a named upcoming change can raise a finding's weight. When a
  decision in scope would go differently depending on a future feature the reviewer cannot
  confirm, such as a second delivery mechanism, a second store, or another team taking over a
  component, the reviewer returns a question for the user instead of a finding.
- A rule marked as evaluated only for a design or topology decision is skipped when the session's
  scope includes no such decision. An approved topology is verified, never reopened.
- Each finding states its target, its evidence, the consequence for maintenance in one sentence,
  and the smallest correction inside the scope. Anything larger is a wider observation.

## Corrections are held to R8 (Constraints need a named reason)

A correction that adds an interface, layer, or component states what it forbids or which decision
it defers. One that cannot is rewritten smaller, or the finding becomes a wider observation. No
correction proposes a service split, a tier, or another topology change unless the session's scope
includes a design or topology decision, and none asks for restructuring only so the code matches a
pattern.

## Rules

### R1. Deliver behavior and structure together

**Deliver behavior and structure together, and judge structure by the cost of the next change.**
Every design, plan, implementation, or review states both: the behavior delivered, and how the
change keeps or lowers the effort of the next known change. Pattern names, layer counts, and
diagrams are not evidence, and "it works" is the floor. No level of the code is exempt: a
signature, a parameter shape, or a helper's location constrains future change as much as a
module boundary does.

Check questions:
- Does the artifact contain both a behavior statement and a structure statement?
- For the likely next requests in this area, how many units does each touch, and does any require
  reworking something unrelated?

Examples:
- Bad review: "Works as described, approving."
- Good review: "Works as described. The retry policy is duplicated in both callers and the config
  is read inside the loop, so tuning it means three edits."

Not a finding when: the plan or review states, in plain words, how the change keeps or lowers the cost of the likely next requests in the area it touches, even without naming a pattern, a layer count, or a diagram.

### R2. Name a shape mismatch

**Name a shape mismatch instead of forcing the piece in.** When a request does not fit the
current structure, say so, then reshape first or record the debt with its cost. Never hide the
mismatch behind a boolean or mode parameter, a special case keyed on the caller, or a copy with a
twist. A flag that steers control flow through layers is a mismatch; a boolean field in boundary
data that describes state to display is not.

Check questions:
- Did the change add a caller-specific parameter, a special case, or a near-copy?
- Was the mismatch named?

Examples:
- Bad: `regularHours(threshold = 8)` so one caller can pass 9.
- Good: one function per owning actor, or a policy object per actor.

Not a finding when: the boolean is a state field in boundary data that a view maps to an appearance, the requester named the mismatch and its debt is recorded with a cost, or the near-copy serves a different actor and is kept apart on purpose under R11 (Deduplicate only for one owner).

### R3. Importance first, urgency second

Guidance: advisory by default.

**Rank by importance first and urgency second, and schedule structural work against a named
upcoming change.** Structural work is important and rarely urgent, so it outranks work that is
urgent but unimportant; the common error is mistaking urgent and unimportant for urgent and
important. Stakeholders will not ask for structure, so the plan includes it, each item justified
by the named upcoming change whose cost it lowers. Structural work with no named upcoming change
is speculation and is not scheduled. Structural work that has turned urgent is scheduled as
important and urgent, and noted as earlier neglect.

Check questions:
- Is an important item that is not urgent ranked below an urgent one that is not important?
- Does every structural item name the upcoming change it protects?
- What concretely happens if the urgent item ships one iteration later?

Examples:
- Bad: "Client asked for it in the demo, so the refactor waits."
- Good: "Put the payment provider behind a port first; the next provider integration lands as one
  gateway."

Not a finding when: the urgent item has a concrete, stated cost if it ships one iteration later, or the structural item names no upcoming change, in which case it is speculation that stays out of the plan rather than a finding against it.

## Conditions

| Id | Condition | Rule | Decided by | Severity | Defect |
|---|---|---|---|---|---|
| `structure-consequence-unstated` | A plan states the behavior it delivers but not how it keeps or lowers the cost of the next known change. | R1 | judgment | minor | `structure-consequence-unstated` |
| `shape-mismatch-hidden` | A request that does not fit the structure is forced in behind a flag or mode parameter, a special case keyed on the caller, or a near-copy, and the mismatch is not named. | R2 | judgment | major | `shape-mismatch-hidden` |
