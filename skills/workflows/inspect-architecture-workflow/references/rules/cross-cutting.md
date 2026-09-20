# Cross-cutting: value and priority

**R1. Deliver behavior and structure together, and judge structure by the cost of the next
change.** Behavior is what the change makes the system do; structure is what the change does to
the cost of the next change. Every design, plan, implementation, or review states both: the
behavior delivered and how it keeps or lowers the effort of the next known change. Pattern
names, layer counts, and diagrams are not evidence; "it works" is the floor. No level of the
code is exempt: a signature, a parameter shape, or a helper's location constrains future change
as much as a module boundary.
- Check: does the artifact contain both a behavior statement and a structure statement? For the one to three likely next requests here, how many units does each touch, and does any require reworking something unrelated?
- Bad review: "Works as described, approving."
- Good review: "Works as described. The retry policy is duplicated in both callers and the config is read inside the loop, so tuning it means three edits."

**R2. Name a shape mismatch instead of forcing the piece in.** When a request does not fit the
current structure, say so, then reshape first or record the debt with its cost. Never hide the
mismatch behind a boolean or mode parameter, a special case keyed on the caller, or a copy with
a twist. A boolean field in boundary data that describes state to display is not a mismatch; a
flag steering control flow through layers is.
- Check: did the change add a caller-specific parameter, a special case, or a near-copy? Was it named?
- Bad: `regularHours(threshold = 8)` so one caller can pass 9.
- Good: one function per owning actor, or a policy object per actor.

**R3. Importance first, urgency second; schedule structural work against a named upcoming
change.** Urgent work has a concrete cost if it ships later; important work changes the cost of
every later change. Structural work is important and rarely urgent, so it outranks
urgent-but-unimportant feature work; the common error is mistaking urgent-and-unimportant for
urgent-and-important. Stakeholders will not ask for structure, so the plan includes it, each
item justified by a known upcoming request whose cost it lowers. Structural work with no named
upcoming change is speculation and is not scheduled. Structural work turned urgent is scheduled as
important-and-urgent and noted as earlier neglect.
- Check: is an important-not-urgent item ranked below an urgent-not-important one? Does every structural item name the request it protects? What concretely happens if the urgent item ships one iteration later?
- Bad: "Client asked for it in the demo, so the refactor waits."
- Good: "Invert the payment gateway first; the next provider integration lands as one adapter."
