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

## Scope research (subagent-only)

The policy — "PL/SQL scope reads happen in a subagent, never in the parent" — is the iron rule in `SKILL.md`. This section covers the *mechanics*: when to dispatch, the subagent prompt, the digest schema, and what the parent does with what comes back.

**Why this is gated:** PL/SQL packages routinely run 1000+ lines; pulling several into the main window has been observed to consume the bulk of a 250K-token session before the plan is even drafted. The subagent isolates that cost in a disposable context and returns a digest the parent can hold cheaply.

**Rationalizations that fail the rule:**
- "just look at the file";
- "it's only one package";
- "the subagent is overkill for this one";
- "the user explicitly named the file so I should look at it";
- "the file isn't that big";
- "I'll just skim it";
- "I'll fall back to direct reads since the first digest was incomplete" — re-dispatch the subagent with a corrective prompt instead.

### When to dispatch

Immediately after the Intake fields are populated, BEFORE the brainstorm gate runs. Brainstorm and plan-writing operate on the digest, not on raw source.

### Subagent prompt template

The parent passes ticket metadata and asks for a digest. The subagent is **not** told it is a test or that it is part of db-work — it is given a research task with an explicit output schema:

```
You are researching the database scope for ticket <TICKET_ID> — <TITLE>.

Acceptance criteria:
<paste from intake>

Named in-scope objects (from ticket / user):
<list of schemas, packages, callables, views, tables>

Repo roots to inspect:
- <PROD/...>
- <YES_SERVICES/...>
- <other team folders as relevant>

Read whatever PL/SQL, views, or changelogs are needed to answer the questions below. Do NOT propose fixes, variants, or design — research only. Return a digest in the schema specified. Cite every claim with file:line ranges so the parent can re-read specific spans if needed.
```

### Required digest schema

The subagent MUST return all sections. Missing sections force a re-dispatch.

```markdown
# Scope Digest — <TICKET>

## In-scope callables
For each callable named in the ticket OR found to contain changed/affected logic:

- **Name:** <SCHEMA.PACKAGE.CALLABLE>
- **Signature (verbatim):** <full param list with modes + return type, copy-paste from source>
- **Source location:** <file>:<line_start>-<line_end>
- **Purpose (1 sentence):** ...
- **Hot-path notes:** loops / joins / subqueries that look expensive, with file:line ranges. NO SQL bodies — line ranges only.
- **Side effects:** DML target tables, autonomous transactions, sequence reads. Names only.
- **Dependent objects:** types, sequences, views, packages referenced. Names + file:line where each is defined if findable.

## Public callers
For each in-scope callable, list public packages/procedures/functions/views/jobs that invoke it:

- <CALLER>: <file>:<line_start>-<line_end> — <one-line note on how it's used>

If a caller is itself a private helper, recurse one level until a public entry point is reached.

## Open questions
Things the subagent could not resolve from code alone (missing fixtures, ambiguous business intent, untraced callers, cross-schema synonyms it could not follow).

## Citation index
A flat list the parent can scan to re-read specific spans:

- <file>:<line_start>-<line_end> — <what's there>
```

### Parent rules after the digest returns

- The parent agent reads the digest into its main context. The digest replaces the raw source for design purposes.
- If brainstorm or plan-writing genuinely needs more detail than the digest provides, the parent re-reads ONLY the specific line ranges cited in the citation index — never whole files.
- If the digest is structurally incomplete (missing schema sections, no citations, paraphrased signatures instead of verbatim), the parent re-dispatches the subagent with a corrective prompt. The parent does NOT fall back to reading the source itself.
- Multiple subagent passes are cheaper than one polluted main context. Re-dispatch freely.
- The digest is committed under `util/<TICKET>/scope_digest.md` so later phases (and the handoff report) can reference it.

### Out of scope for this subagent

The scope-research subagent does NOT:
- propose variants;
- write any part of the plan;
- make design decisions;
- run anything against DEV;
- read more than the in-scope objects + their callers + their direct dependents (no whole-package speculative reads).

If the subagent volunteers a fix or a variant idea, the parent ignores it. Design happens in the brainstorm/plan phases, with the user, on the digest.

## Brainstorm gate

A structured brainstorming pass is REQUIRED before any plan — use `superpowers:brainstorming`. If it's not available, run `db-work-doctor.sh` (Check #7) for the install command.

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
