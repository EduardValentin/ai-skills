# DEV Execution and Comparison Evidence

## Entry — auto-engaged from Phase 5

Phase 6 auto-engages when the human picks a variant on Phase 5's variant decision surface — see `SKILL.md`'s "Phase progression" table and `references/05-implementation-and-shadow.md` "Variant decision surface". Entry sequence, no user prompt between steps:

1. Promote the human-chosen variant's edits to the Liquibase-owned schema folders (`PROD/`, `YES_SERVICES/`, sibling team folders).
2. Emit `util/<TICKET>/dev_sandbox/shadow_manifest.json` for the chosen variant.
3. Run `generate_metadata_probe.py` and execute the resulting probe against DEV (the metadata probe is read-only data-dictionary queries, so no announce gate; the DDL deploy from step 1 went through its own gate).
4. Run `generate_compare_spec.py` against the manifest + metadata TSV.
5. **Dispatch the parameter-verification subagent** (see "Parameter-verification subagent" below) to probe DEV with each run's inferred arguments. Update `compare_spec.json` with verified values and per-run annotations (`verified_against_dev`, `verified_row_count`, `unverifiable_reason` if applicable). Surface UNVERIFIABLE runs at the top of the next step's review surface.
6. Present `compare_spec.json` (now with verified values) for review per "Compare-spec approval gate" below — wait for the explicit approval token before generating any harness.

Picking the right `evidence_mode` is what tailors Phase 6 to the implemented scenario (regression compare vs new branch vs intentional delta vs perf-only vs compile-contract). That selection is mechanical — `generate_compare_spec.py` infers it from the diff and metadata. The agent's job is to surface the inference for review, not to wait for the user to ask for "manual testing".

Exception: if no variant cleared the plan's threshold, Phase 6 does NOT auto-engage — see `references/04-performance-debugging.md` adjacent-code expansion path.

## Pre-execution announce (mandatory, 5 lines)

Before invoking any SQL on DEV, the agent posts a five-line announce and waits for explicit "go":

```
about to run:  <script path>
alias:         <DB_WORK_DEV_CONNECT>
expected:      <objects compiled / queries run / side-effect tables touched>
evidence_mode: <regression_compare | shadow_expected_result | expected_delta | performance_only | compile_contract_validation>
log:           <spool/log path that the post-execution summary will reference>
```

**Hard rules:**

- If ANY field is unknown, STOP and ask. Do not fabricate. Do not infer `evidence_mode` from filename, directory name, or file contents.
- Re-announce in full once unknowns are resolved. **Never honor "go" against an announce that contains `<unknown>` placeholders.**
- "User asked me to run it" does not waive the announce — the user can say "go" in 2 seconds after the announce.
- "Wallet's set up", "creds are loaded", "the connection works" are auth statements, NOT execution consent.
- The `log` field commits the spool path before execution, so the post-execution summary has a pre-declared evidence anchor.

## Execution

```bash
"$DB_WORK_SKILL_DIR/scripts/run_sqlplus_dev.sh" \
  --connect /@DEVDB_ALIAS \
  --script util/VA-515/dev_sandbox/deploy_shadow.sql
```

See `references/sqlplus-dev-execution.md` for SQLPlus details and `references/01-machine-setup.md` for setup.

## Post-execution summary (mandatory)

After every DEV run:

```
ran:        <script path>
status:     <ok | error>
rows:       <approx rows touched, if applicable>
errors:     <count + first error line, if any>
KPI delta:  <vs baseline if perf run>
log:        <path to spool — must match the path declared in the pre-execution announce>
```

## Comparison evidence (winner only)

After the winner shadow compiles cleanly:

```bash
"$DB_WORK_SKILL_DIR/scripts/generate_metadata_probe.py"  --manifest util/VA-515/dev_sandbox/shadow_manifest.json
"$DB_WORK_SKILL_DIR/scripts/run_sqlplus_dev.sh"          --script util/VA-515/dev_sandbox/metadata_probe.sql
"$DB_WORK_SKILL_DIR/scripts/generate_compare_spec.py"    --manifest ... --metadata-tsv .../db_metadata.tsv
# HARD GATE — present compare_spec.json to the user and wait for an explicit
# approval token ("approved" / "looks good" / "reviewed") before continuing.
# See "Compare-spec approval gate" below. Harness generation does NOT proceed
# on implicit approval, on a "go" from a separate announce, or on the user's
# original "start the perf testing" instruction.
"$DB_WORK_SKILL_DIR/scripts/generate_compare_harness.py" --spec compare_spec.json
"$DB_WORK_SKILL_DIR/scripts/generate_stats_harness.py"   --spec compare_spec.json
"$DB_WORK_SKILL_DIR/scripts/run_sqlplus_dev.sh"          --script <each generated harness>
"$DB_WORK_SKILL_DIR/scripts/summarize_sqlplus_logs.py"   <log dir>
```

The full rules for `compare_spec.json` (run scope, scenarios, evidence_mode taxonomy) live in `references/compare-spec-format.md`. JSON case examples (function, procedure, refcursor) and observer/cursor inference rules live in `references/compare-spec-examples.md`. Read those files before editing the spec.

## Parameter-verification subagent

Inferred parameter values often hit empty result sets on DEV — wrong ISO/market combination, date window before any data exists, an object id that's been retired. A perf bench or stats harness against zero-row data is meaningless. The agent does NOT skip this verification, does NOT defer it to the user-approval surface ("they can spot bad values"), and does NOT trust mechanical inference.

The verification runs in a subagent so the parent's main context stays lean. The subagent is read-only — it issues `SELECT`s only, no DML, no DDL.

### When to dispatch

- **Phase 5:** after variant subagents return with filled-in `perf.sql` and `bench_spec.json`, BEFORE running `perf-bench.sh`.
- **Phase 6:** after `generate_compare_spec.py` produces the draft `compare_spec.json`, BEFORE presenting the spec to the user for approval.

In both cases the verification is the gate between "inferred parameters" and any user-facing approval surface.

### Subagent prompt template

```
You are verifying performance-testing parameters for ticket <TICKET_ID> — <TITLE>.

You have read-only access to DEV via SQLPlus alias <DB_WORK_DEV_CONNECT>. You may
issue SELECT statements only. Do NOT run any DDL or DML.

Below is a list of cases / runs with their inferred parameter values. For each
run, do the following:

1. Construct a representative SELECT against the underlying tables that the
   target callable would query, using the inferred parameters. (For example,
   if the inferred run is RATE_PKG.GET_FLOWS(iso=>'PJM', market=>'DA',
   start_dt=>sysdate-7, end_dt=>sysdate), the underlying table is RATE_HIST
   filtered by ISO_CD='PJM' and MARKET='DA' and TRADE_DATE between sysdate-7
   and sysdate.) The scope digest at util/<TICKET>/scope_digest.md tells you
   which tables back which callables.

2. Run the SELECT and record the row count.

3. If the row count is 0, propose alternatives close to the inferred shape.
   Examples of "close":
   - keep the ISO/market, widen the date window (last 7 days → last 30 days
     → last 90 days);
   - keep the ISO, change the market (DA → RT, or vice versa);
   - keep the date window, change the ISO to one that has data in this period;
   - drop one filter at a time to isolate which filter is empty.
   Do NOT propose values that contradict the spec's evidence_mode (e.g. don't
   pick a scenario the original handles when the spec is shadow_expected_result
   for a new branch).

4. Return the digest schema specified below. Be terse. No prose beyond the
   schema fields.

Cases / runs to verify:
<paste the inferred runs from compare_spec.json or perf.sql per variant>

Scope digest:
<paste util/<TICKET>/scope_digest.md, or the relevant excerpts>
```

### Required digest schema

```markdown
# Parameter Verification — <TICKET>

## case <name>

### run <name>

- **Inferred values:** <verbatim inferred values>
- **Probe SQL:** <verbatim SELECT executed against DEV>
- **Original row count:** <integer> <PASS|FAIL>
- **Shadow row count (if shadow exists at probe time):** <integer> <PASS|FAIL|N/A>
- **Verification verdict:** <PASS — inferred values produce > 0 rows> | <FAIL — recommend alternative below> | <UNVERIFIABLE — see notes>
- **Recommended values (if changed):** <verbatim values with the same parameter shape as inferred>
- **Reason for change:** <one sentence>
- **Alternatives probed (if recommended != inferred):**
    - <values> → <row count>
    - <values> → <row count>

## case <next> ...

## Cases that could not be verified

- <case>: <reason — e.g. "no underlying table found for callable X", "scope digest does not name a backing table">

## Notes

<any structural observations the parent should consider — e.g. "case 3 is
shadow_expected_result for a brand-new branch; original is expected to be
empty — verified shadow rows only">
```

### Pass / fail bar by `evidence_mode`

The verification verdict depends on the run's `evidence_mode`:

| evidence_mode | Pass requires |
|---------------|---------------|
| `regression_compare` | Original > 0 rows AND shadow > 0 rows (or shadow is the same shape and would also be > 0). |
| `shadow_expected_result` | Shadow > 0 rows (the new branch / new callable produces output). Original is expected to be empty for this run. |
| `expected_delta` | Original > 0 rows (the change-from baseline must exist) AND shadow > 0 rows (the changed behaviour must be observable). |
| `performance_only` | Either original or shadow > 0 rows — perf is the question, the side that runs must hit data. |
| `compile_contract_validation` | Verification does not apply — these runs prove compile/signature compatibility, no row-count meaning. Mark `N/A`. |

### Parent rules after the subagent returns

- For every run marked PASS: keep inferred values, annotate the artifact (`perf.sql` for Phase 5, `compare_spec.json` for Phase 6) with `verified_against_dev: true` and `verified_row_count: <n>`.
- For every run marked FAIL with a recommended replacement: update the artifact's parameter values to the recommended values, annotate with `verified_against_dev: true`, `verified_row_count: <n>`, and `original_inferred_values: <…>` for audit.
- For every run marked UNVERIFIABLE: mark the run `verified_against_dev: false` AND `unverifiable_reason: "<…>"`, and surface it explicitly at the top of the user-approval surface so the user can decide to skip the run, change the `evidence_mode`, or load fixtures.
- The parent does NOT silently fix UNVERIFIABLE cases. They go to the user as red-flagged items.
- If the subagent's digest is structurally incomplete (missing schema fields, paraphrased values instead of verbatim), the parent re-dispatches with a corrective prompt — does NOT fall back to running the probes itself.

### Out of scope for this subagent

- Proposing fixes to the spec's `evidence_mode`.
- Running anything against the original or shadow callable directly (verification probes the underlying tables, not the callable — keeps probes cheap and avoids needing the shadow to be compiled).
- DML or DDL of any kind.
- Touching `util/<TICKET>/` directory contents.

If the subagent volunteers a recommendation outside its scope (e.g. "you should change `evidence_mode` from `regression_compare` to `expected_delta`"), the parent surfaces the observation to the user as a separate question — but does NOT act on it without user input.

## Compare-spec approval gate (mandatory)

After `generate_compare_spec.py` produces `util/<TICKET>/dev_sandbox/compare_spec.json` AND the parameter-verification subagent has updated it with verified values, the agent posts a review surface to the user and waits for an explicit affirmative approval token before generating any harness. This gate has the same shape as the Phase 7 walkthrough gate.

### What the agent posts

For each case in the spec, the agent shows verbatim (not paraphrased):

- The callable name and signature.
- Each `run`'s arguments (verified values + the row count they produced + a flag if the verification subagent changed them).
- The `evidence_mode` per run AND the rationale (why `regression_compare` vs `shadow_expected_result` vs `expected_delta` vs `performance_only` vs `compile_contract_validation`).
- Every `review_required: true` field.
- Every `'TODO'`-valued field.
- Every `baseline_review_required` run.
- Every observer-inference, cursor-materialization, or expected-delta SQL block the spec contains — fully, not as a "see file" reference.
- **Verification status banner at the top:** `<N> runs verified (>0 rows)`, `<M> runs verification-changed (inferred values returned 0; subagent proposed replacements)`, `<K> runs UNVERIFIABLE (reason listed below)`. UNVERIFIABLE runs are red-flagged so the user can decide before approving.
- The list of public callables in scope and the diff lines that placed them there.

If any of those fields contain placeholders (`TODO_REF_CURSOR_*`, `"needs_agent_inference"`, unresolved expected deltas), the agent flags them at the top of the review surface — placeholders MUST be resolved (by user input or by the agent reading specific cited spans of the source) before the user is asked to approve.

### Approval token

Approval requires the user to type one of: `"approved"`, `"looks good"`, `"reviewed"` — explicit and affirmative. Anything else (silence, "k", emoji-only ack, "ok run it", a question, a request to change a value) keeps the gate open. The agent answers follow-ups and revises the spec inline; the gate stays open until the explicit token arrives.

The approval token is **per-artifact**. None of the following carry over to the spec:

- Plan approval (Phase 4).
- Brainstorm approval (Phase 3).
- "Go" on a DEV announce (any phase).
- "Yes" to a clarifying question.
- The user's original "start the perf testing" / "let's run the comparison" instruction.

Each is approval for what it names, not for the spec. The user has to look at the spec and say "approved".

### What the gate prevents

Harness generation (`generate_compare_harness.py`, `generate_stats_harness.py`) is the action the gate blocks. Until the explicit approval token arrives, the agent does NOT:

- run `generate_compare_harness.py`;
- run `generate_stats_harness.py`;
- run any harness against DEV;
- mutate `compare_spec.json` after the user has been shown a version (only further user-driven edits modify it after presentation).

Rationalizations that fail the gate are listed in `SKILL.md`'s iron rule — they apply here verbatim.

## Harness execution (post-spec-approval)

The full gate rule is in `SKILL.md`'s pre-execution-announce iron rule. Short version for Phase 6:

- `compare_harness.sql` and `stats_harness.sql` are generated from the approved `compare_spec.json`. Their mutations (observer inserts into helper tables, the observer's `cleanup_sql: "rollback;"`, any expected_delta materialization the spec authorizes) are pre-approved by the spec approval and run WITHOUT a per-action 5-line announce.
- The agent posts a one-line "running <harness>" before each invocation and a one-line "done <harness>: <rows / errors / log file>" after, so progress is auditable.
- Read-only diagnostic queries the agent runs mid-Phase-6 (data sanity checks, row counts, plan inspection) run without a gate — they are SELECTs.
- Any mutation outside what the spec authorizes — extra DML, helper-table cleanup the spec didn't wire, ad-hoc `DELETE` of orphan rows, schema changes, GRANTs — re-gates with a full announce + "go". Same with mutations against a different ticket's scope, or against a fresh session that hasn't loaded this spec.

If the user types `"stop"`, `"wait"`, `"pause"`, or paraphrase mid-Phase-6, the agent halts before the next action and re-gates everything that follows with full announces.

## Quick rules

- Do not generate functional or stats SQL directly from `shadow_manifest.json` — always go through `compare_spec.json`.
- Run scope defaults to public callables whose declaration or implementation lines changed in the diff.
- Each run gets an `evidence_mode`. Show the user the inferred runs, default arguments, and `evidence_mode` rationale before generating the harnesses — see the approval gate above.
- The compare/stats harnesses refuse to emit SQL when placeholders (`TODO_REF_CURSOR_*`, unresolved observers, unresolved expected deltas) remain. Replace placeholders before generation.
- For intentional behavior fixes, use `expected_delta` and have the inferred delta reviewed before execution.
