# DEV Execution and Comparison Evidence

## Entry — auto-engaged from Phase 5

Phase 6 auto-engages when Phase 5 picks a winner — see `SKILL.md`'s "Phase progression" table. Entry sequence, no user prompt between steps:

1. Emit `util/<TICKET>/dev_sandbox/shadow_manifest.json` for the winner.
2. Run `generate_metadata_probe.py` and execute the resulting probe against DEV (each DEV invocation still uses the 5-line announce + "go" gate below).
3. Run `generate_compare_spec.py` against the manifest + metadata TSV.
4. Present `compare_spec.json` for review per "Compare-spec approval gate" below — wait for the explicit approval token before generating any harness.

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

## Compare-spec approval gate (mandatory)

After `generate_compare_spec.py` produces `util/<TICKET>/dev_sandbox/compare_spec.json`, the agent posts a review surface to the user and waits for an explicit affirmative approval token before generating any harness. This gate has the same shape as the Phase 7 walkthrough gate.

### What the agent posts

For each case in the spec, the agent shows verbatim (not paraphrased):

- The callable name and signature.
- Each `run`'s arguments (default values, scenario dimensions like ISO/market/window).
- The `evidence_mode` per run AND the rationale (why `regression_compare` vs `shadow_expected_result` vs `expected_delta` vs `performance_only` vs `compile_contract_validation`).
- Every `review_required: true` field.
- Every `'TODO'`-valued field.
- Every `baseline_review_required` run.
- Every observer-inference, cursor-materialization, or expected-delta SQL block the spec contains — fully, not as a "see file" reference.
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

## Quick rules

- Do not generate functional or stats SQL directly from `shadow_manifest.json` — always go through `compare_spec.json`.
- Run scope defaults to public callables whose declaration or implementation lines changed in the diff.
- Each run gets an `evidence_mode`. Show the user the inferred runs, default arguments, and `evidence_mode` rationale before generating the harnesses — see the approval gate above.
- The compare/stats harnesses refuse to emit SQL when placeholders (`TODO_REF_CURSOR_*`, unresolved observers, unresolved expected deltas) remain. Replace placeholders before generation.
- For intentional behavior fixes, use `expected_delta` and have the inferred delta reviewed before execution.
