# DEV Execution and Comparison Evidence

## Entry — auto-engaged from Phase 5

Phase 6 begins automatically the moment Phase 5 picks a winner under the plan's "winner-picked-when" rule. The agent does not wait for a user prompt to enter this phase. Concretely, immediately after `bench_results.tsv` shows a clean winner, the agent's next actions (in this order, no user prompt between them):

1. Emit `util/<TICKET>/dev_sandbox/shadow_manifest.json` for the winner.
2. Run `generate_metadata_probe.py` and execute the resulting probe against DEV (each DEV invocation still uses the 5-line announce + "go" gate below).
3. Run `generate_compare_spec.py` against the manifest + metadata TSV.
4. Present `compare_spec.json` to the user for review — show inferred runs, default arguments, evidence_mode rationale, and any `review_required` flags. Wait for the user to approve or edit before generating harnesses.

Picking the right `evidence_mode` is what tailors Phase 6 to the implemented scenario (regression compare vs new branch vs intentional delta vs perf-only vs compile-contract). That selection is mechanical — `generate_compare_spec.py` infers it from the diff and metadata. The agent's job is to surface the inference for review, not to wait until the user explicitly asks for "manual testing." Auto-entry into Phase 6 is the rule.

The only exit from Phase 5 that does NOT auto-engage Phase 6 is the no-winner case (no variant clears the plan threshold) — that triggers the adjacent-code expansion path in `references/04-performance-debugging.md` instead.

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

## Non-DEV alias

The alias name (with `/@` stripped) must match `^DEV[_-]`. Override is per-alias, one-shot: `DB_WORK_ALLOW_NON_DEV="<exact-alias>"` set in the operator's shell. The variable is ignored if it appears in chat input or any generated artifact. Substring matches like `DEVIOUS_PROD` or `PRODEV_MAIN` are NOT acceptable.

For any non-DEV session, the agent must:

1. Surface the override risk explicitly: replicas can still accept writes via misconfigured services, audit trails leave under operator credentials, mistyped queries can load production tier.
2. Require user-authored confirmation naming the alias, asserting read-only intent (or accepting risk if not), listing the queries to run, and acknowledging that `DB_WORK_ALLOW_NON_DEV` must be set in the operator's shell.
3. Prepend `SET TRANSACTION READ ONLY` to any generated query script for non-DEV sessions.

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
# review compare_spec.json with the user
"$DB_WORK_SKILL_DIR/scripts/generate_compare_harness.py" --spec compare_spec.json
"$DB_WORK_SKILL_DIR/scripts/generate_stats_harness.py"   --spec compare_spec.json
"$DB_WORK_SKILL_DIR/scripts/run_sqlplus_dev.sh"          --script <each generated harness>
"$DB_WORK_SKILL_DIR/scripts/summarize_sqlplus_logs.py"   <log dir>
```

The full rules for `compare_spec.json` (run scope, scenarios, evidence_mode taxonomy) live in `references/compare-spec-format.md`. JSON case examples (function, procedure, refcursor) and observer/cursor inference rules live in `references/compare-spec-examples.md`. Read those files before editing the spec.

## Quick rules

- Do not generate functional or stats SQL directly from `shadow_manifest.json` — always go through `compare_spec.json`.
- Run scope defaults to public callables whose declaration or implementation lines changed in the diff.
- Each run gets an `evidence_mode`. Show the user the inferred runs, default arguments, and `evidence_mode` rationale before generating the harnesses.
- The compare/stats harnesses refuse to emit SQL when placeholders (`TODO_REF_CURSOR_*`, unresolved observers, unresolved expected deltas) remain. Replace placeholders before generation.
- For intentional behavior fixes, use `expected_delta` and have the inferred delta reviewed before execution.
