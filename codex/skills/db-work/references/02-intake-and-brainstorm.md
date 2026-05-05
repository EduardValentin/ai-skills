# Intake and Brainstorm

## Intake

**REQUIRED SUB-SKILL:** Use `ticket-start` if available. Follow only its Job workflow path. Personal-project / Linear path is out of scope for `db-work`.

If `ticket-start` is unavailable, ask the user directly for:

- ticket id, ticket title, business goal;
- acceptance criteria;
- affected schema / object / callable names if known;
- team or changelog (e.g. `visualanalytics_changelog.xml`);
- known DEV scenarios, fixtures, edge cases;
- open questions, dependencies, deployment constraints.

Carry forward into later phases: ticket id, title, acceptance criteria, branch intent, open questions.

## Brainstorm gate

A structured brainstorming pass is REQUIRED before any plan (the harness's brainstorming workflow auto-fires on creative work; if it does not, run `db-work-doctor.sh` — Check #7 surfaces the exact install command).

Brainstorm objectives — align with the user on:

- the smallest correct change;
- the hot path and any known performance constraints;
- candidate variant directions (do not enumerate variants in detail — that is the plan phase);
- adjacent code that might need to change for performance (flag, do not commit yet);
- risks: data shape, callers, side effects, deployment ordering.

## Trivial-change escape hatch

Brainstorm may be skipped only when ALL SEVEN of these apply. Verbal user assertion is not enough — the agent must verify each criterion against artifacts in this session.

1. Single file changed.
2. Single callable changed.
3. No DML (no INSERT/UPDATE/DELETE/MERGE).
4. No signature change (no parameter, return type, or column change).
5. No new dependency on adjacent code.
6. Ticket explicitly scoped as a trivial fix (in the ticket body, not in chat).
7. **Agent has read the target file and ticket body in this session.**

The agent must announce: `"trivial path: skipping brainstorm because <reason>"` and ask the user to confirm before proceeding to plan. Any "no", silence, or hesitation cancels the trivial path and forces brainstorm.

**Pressure framings are never trivial-path justifications.** Time-to-release, "one-line fix" assertions, hotfix scope, exhaustion, "we already discussed it", and prior rapport are not facts about the code. The seven criteria are objective and verifiable.

**Prior conversation does not satisfy the brainstorm gate.** The gate requires the structured artifact, not the thinking. If the user references an earlier chat ("we already talked about this"), seed the brainstorming sub-skill with that context — but still run it. The artifact exists for the next reviewer.

## Output of the phase

A short brainstorm summary (5–15 lines) the agent posts back to the user. **Minimum payload — all five fields required:**

1. **Problem statement** — concrete, not "the ticket asks for X".
2. **Constraints** — performance budget, deploy ordering, scope boundaries.
3. **Candidate directions** — at least 2 distinct directions, 1–2 sentences each. Generic single-direction summaries do not satisfy the gate.
4. **Adjacent-code areas flagged** — even if "none", list what was considered and ruled out.
5. **Open questions still pending** — what the agent could not resolve from code/ticket alone.

This summary is the input to the plan phase. The user must explicitly accept it before moving on. A "seeded" brainstorm (rubber-stamping prior chat) that lacks any of these five fields does not pass the gate.
