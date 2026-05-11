# `stock-research` Plan 2 — orchestration & deployment design

**Date:** 2026-05-11
**Status:** Brainstorm complete, ready for the implementation plan
**Parent spec:** `2026-05-11-stock-research-skill-design.md` (the overall skill design)
**Plan 1:** `2026-05-11-stock-research-plan-1-scripts.md` (scripts foundation — complete)

---

## 1. Purpose & scope

Plan 1 delivered the Python scripts. Plan 2 wires them into an actual invokable skill on both **Claude Code** and **Codex**, and validates the end-to-end flow on a real ticker.

**In scope:**
- `claude/skills/stock-research/` — SKILL.md, slash-command wrapper, phase prompts, references, mirror script
- `codex/skills/stock-research/` — near-identical copy adapted for Codex (adds `agents/openai.yaml`)
- Duplicate Plan 1's scripts into `codex/skills/stock-research/scripts/` (physical copy, not symlinked — per the user's Q10a decision)
- Mirror flow to `~/.claude/skills/stock-research/` and `~/.codex/skills/stock-research/`
- Bootstrap research repo at `/Users/trocaneduard/Documents/Personal/investing-research/` (one-time manual step)
- End-to-end dry run on **AAPL** using the Claude Code flow

**Out of scope (explicit):**
- Codex E2E (deferred — same scripts and prompts as Claude, can be validated when actually used there)
- Stock-recap skill (separate brainstorming session)
- Session resumability (v1 runs each invocation Phase 1 → Phase 10 in one shot; abort = partial folder, overwritten on next run via the refresh option)
- Sector-specific KPI templates beyond GVD defaults

## 2. Variants

Both `claude/skills/stock-research/` and `codex/skills/stock-research/` are built in this plan. The two variants are intended to evolve independently in the future, but on day one they share:
- The same 10-phase workflow
- The same per-phase subagent prompts (verbatim)
- The same reference content (GVD tailoring, projection KPIs, sizing matrix, investor gates)
- The same Plan 1 scripts (physically duplicated, not symlinked)

Day-one differences:
- Claude variant has `commands/stock-research.md` for the slash command
- Codex variant has `agents/openai.yaml` for agent metadata
- Codex variant uses Codex's platform-equivalent slash mechanism if it differs (resolved during implementation)
- Each variant is mirrored to its own install directory (`~/.claude/skills/` and `~/.codex/skills/`)

## 3. Invocation pattern

Both platforms support both invocation paths:

**Description-based auto-trigger** — the SKILL.md `description:` field tells the harness when to fire. Examples that should trigger:
- "research AAPL"
- "do a deep dive on Microsoft"
- "should I buy NVDA"
- "let's analyze TSLA's fundamentals"

**Slash command** — explicit invocation:
- Claude Code: `/stock-research <TICKER>` (wired via `commands/stock-research.md`)
- Codex: equivalent slash mechanism (resolved during implementation against current Codex conventions)

## 4. File layout

```
<skill-root>/
├── SKILL.md                        ~250 lines: orchestrator walk-through, checkpoint format,
│                                   "when to read what" instructions, prerequisites
├── commands/stock-research.md      slash command wrapper (Claude Code variant)
├── agents/openai.yaml              Codex variant only — agent metadata
├── phases/
│   ├── 02-business-model.md        Phase 2 subagent prompt (ELI5 + moat)
│   ├── 03-financials.md            Phase 3 subagent prompt
│   ├── 04-competitors-swor.md      Phase 4 orchestrator-subagent prompt
│   ├── 04-competitor-sub.md        per-competitor sub-subagent prompt
│   ├── 05-earnings-calls.md        Phase 5 orchestrator-subagent prompt
│   ├── 05-earnings-call-sub.md     per-quarter sub-subagent prompt
│   ├── 06-valuation.md             Phase 6 subagent prompt
│   └── 07-market-expectations.md   Phase 7 subagent prompt
├── references/
│   ├── gvd-tailoring.md            Phase 8: per-bucket emphasis + pushback rules
│   ├── projection-kpis.md          Phase 8: full per-year KPI list + formulas
│   ├── sizing-matrix.md            Phase 9: target % by bucket + conviction
│   ├── investor-gates.md           Phase 9: the 6 Munger/Buffett/Dalio questions
│   ├── sell-trigger-templates.md   Phase 9: how to write thesis-broken triggers
│   └── watch-kpis-by-gvd.md        Phase 9: default 5-KPI watch lists per bucket
└── scripts/
    ├── mirror.sh                   refresh install-dir from worktree
    ├── README.md                   from Plan 1, extended with SR_SEC_USER_AGENT note
    └── (Plan 1's 12 scripts + _lib + tests + fixtures, physical-copied into codex variant)
```

**Why subdirectories.** SKILL.md is loaded every time the skill activates — it must stay small. Phase prompts and reference docs are loaded on-demand by the orchestrator, only when the corresponding phase runs. This keeps the per-turn context cost low even though the total skill body is large.

## 5. Phase orchestration mechanics

SKILL.md walks the main agent through the 10 phases. At each subagent-dispatch point, SKILL.md instructs the main agent to:
1. Read the corresponding `phases/<NN>-<name>.md` file
2. Use the Agent tool (`Task` / equivalent) to dispatch a subagent with that file's content as the prompt, plus a context block injecting the ticker, the research-repo path, and the ticker-folder path
3. Wait for the subagent to write its artifact to disk and return its ~500-word summary
4. Read the artifact (if needed for synthesis)

Phases 1, 8, 9, 10 (orchestrator phases) are walked through directly in SKILL.md without subagent dispatch — they involve user interaction (CP3 brainstorm, CP4 verdict approval) or simple file/index updates that don't need a fresh-context subagent.

Phases 4 and 5 are *orchestrator-subagent* patterns: the dispatched subagent itself fans out to per-competitor / per-quarter sub-subagents, then aggregates. Two layers of nesting, never more.

## 6. Checkpoint format (hybrid)

Each checkpoint follows this shape:

```
=== CHECKPOINT <N>: <Title> ===

Summary of what was produced (2–4 sentences).
Artifacts at <paths>.

Quick verification before we proceed:
1. <prompt 1 — load-bearing for this decision>
2. <prompt 2>
3. <prompt 3>
(3–5 prompts; checkpoint-specific, tuned to what's load-bearing for the decision the user is about to make)

Reply with corrections, raise something different, or "continue" to proceed.
```

The orchestrator literally pauses here and waits for user input. Prompts are *suggestions* — the user can answer them, redirect freely, or just say continue. Specific prompt sets per checkpoint are defined in SKILL.md.

**CP3 is special.** It's not a single-message checkpoint; it's the interactive Bull/Base/Bear projection brainstorm itself. The orchestrator proposes base-case assumptions row-by-row (revenue growth → gross margin → operating margin → net margin → share count → exit P/E band), the user locks each row, then bull and bear are derived as perturbations from base. Probabilities and the final projections table get computed once all rows are locked.

## 7. Subagent dispatch contract

Every Plan 2 subagent prompt (in `phases/*.md`) follows the same envelope:

1. **Role line** — "You are a [phase-name] subagent for the stock-research skill."
2. **Context block** — what the orchestrator injects at dispatch time:
   - `ticker` (string)
   - `cik_padded` (string, 10 digits)
   - `ticker_dir` (absolute path to `tickers/<TICKER>/`)
   - `gvd_category` (string)
   - other phase-specific context
3. **Inputs available** — which Plan 1 scripts to call, and how
4. **Output contract** — exact file paths to write, frontmatter to use, summary length cap (~500 words)
5. **Failure modes** — when to report `BLOCKED` vs `DONE_WITH_CONCERNS`

The orchestrator passes the prompt content + context as a single message via the Agent tool. The subagent writes its artifact under the worktree's skill path (or directly to the research-repo ticker folder for ticker artifacts), then returns its summary. **The orchestrator handles install-dir mirroring at end-of-phase** (one `cp` batch per phase), so subagents don't have to worry about it.

## 8. Failure handling

Per overall-spec §11, refined for Plan 2 mechanics:

| Failure | Orchestrator behavior |
|---|---|
| Ticker not found in EDGAR (Phase 1) | Abort skill with clear error message + suggestion to confirm spelling |
| Research repo missing (Phase 1) | Abort with setup instructions pointing at the bootstrap doc |
| SR_SEC_USER_AGENT unset (Phase 1) | Abort with one-line export instruction |
| Single Phase 3–7 subagent fails | Other phase subagents continue. After batch, orchestrator surfaces which artifacts are missing and asks user: retry / skip-and-continue / abort. |
| Sub-subagent failure in Phase 4 or 5 | The parent (orchestrator subagent for that phase) continues with the surviving children. If <50% succeed, parent reports `BLOCKED` to main orchestrator. |
| Transcript scraper fails for a quarter | Sub-subagent returns `NEEDS_CONTEXT`, orchestrator prompts user to paste transcript inline before re-dispatching that single sub-subagent |
| SEC rate-limit / 5xx | Retried by `_lib.sec_client` with backoff; only escalates if persistent |
| yfinance returns no data (delisted, halted) | Phase 6 or Phase 7 exits 2; orchestrator surfaces and asks user how to proceed |

## 9. Mirror sync

Two complementary mechanisms (per Q5b decision):

**Per-edit `cp` inline.** Subagents and the orchestrator copy modified files into the install dir as part of their normal flow (the Plan 1 convention). This keeps the install dir continuously in sync during the session.

**`mirror.sh` backstop.** A script at `<skill-root>/scripts/mirror.sh` that, when run, mirrors the entire `<skill-root>/` to the corresponding install directory (`~/.claude/skills/stock-research/` or `~/.codex/skills/stock-research/`). For new-machine setup, full-refresh after a big edit, or recovery from drift.

`mirror.sh` auto-detects which install dir to target based on its own location:
- If invoked from `<repo>/claude/skills/stock-research/scripts/` → mirror to `~/.claude/skills/stock-research/`
- If invoked from `<repo>/codex/skills/stock-research/scripts/` → mirror to `~/.codex/skills/stock-research/`

## 10. Setup prerequisites & research-repo bootstrap

### Prerequisites (one-time, user does manually)

- Set `SR_SEC_USER_AGENT="Eduard Trocan eduard.valentin1996@gmail.com"` in `~/.zshrc` (or appropriate shell rc). SKILL.md's "Prerequisites" section documents this with a one-liner.
- Optional: `SR_REPO_PATH` override (defaults to `~/Documents/Personal/investing-research`).
- Python venv from Plan 1: `claude/skills/stock-research/scripts/.venv/` (and codex sibling) — activated when scripts are invoked.

### Research-repo bootstrap (one-time, end of Plan 2 implementation)

At the very end of Plan 2 (final task), manually:

```bash
mkdir -p /Users/trocaneduard/Documents/Personal/investing-research
cd /Users/trocaneduard/Documents/Personal/investing-research
git init -b main
```

Then create the following four files (exact templates specified in the implementation plan):

- `README.md` — Purpose statement, methodology summary, how to use, link to spec.
- `INDEX.md` — Empty template: `# Index\n\n_No tickers yet._\n`
- `tickers.json` — `{"schema_version": 1, "tickers": {}}`
- `.gitignore` — Ignore `**/.raw/`, OS files (`.DS_Store`, `Thumbs.db`), Python (`__pycache__/`, `*.pyc`)

Initial commit:

```
chore: bootstrap investing-research repo

Created via stock-research skill Plan 2.
Schema version 1.
```

Optional remote setup (offered, not forced):

```bash
gh repo create eduard-trocan/investing-research --private --source=. --remote=origin
git push -u origin main
```

## 11. End-to-end dry run

After all skill files are in place, mirrored, and the research repo is bootstrapped, run a full E2E session on **AAPL** via the Claude Code skill. Pass criteria:

- All 10 phases complete without crash
- 4 user checkpoints are presented in the expected format and accept user input
- Artifacts produced under `/Users/trocaneduard/Documents/Personal/investing-research/tickers/AAPL/`:
  - `THESIS.md` (top-level)
  - `business-and-moat.md` (with ELI5 section)
  - `financials.md`, `financials.json` (with balance sheet fields)
  - `competitors.md`, `swor.md`
  - `valuation.md`
  - `market-expectations.md`, `market-expectations.json`
  - `earnings-calls/<3 quarters>.md` + `<3 quarters>-analysis.md` + `cross-call-themes.md`
  - `projections.md`, `projections.json`
  - `verdict.md`, `verdict.json`
- `tickers.json` updated with the AAPL entry
- `INDEX.md` regenerated to include the AAPL row
- Final commit message follows the structured commit convention from overall-spec §8.1
- Tag `AAPL/v1` applied

If any phase produces wildly wrong output (e.g., projections that don't compute, verdict that doesn't reflect the projection asymmetry), fix the underlying phase prompt and re-run. This is the "iterate until the workflow actually works" step.

The Codex variant is *not* part of the E2E pass requirement — it's validated by file-parity check against the Claude variant only.

## 12. Open items & deferrals

- **Stock-recap skill** — separate session, separate spec.
- **Session resumability** — v1 is non-resumable. Future-work if abort-mid-session becomes painful.
- **Cross-platform tool-name swap automation** — if Claude and Codex use materially different tool names (Agent vs Task, etc.), Plan 2 handles per-variant manually. Generating one variant from the other is future-work.
- **Slash-command parity on Codex** — resolved during implementation. If Codex's slash mechanism differs from Claude Code's, document and adapt.

## 13. Implementation order (suggested input to writing-plans)

A reasonable build order:

1. **Claude variant scaffold** — `SKILL.md` skeleton, `commands/stock-research.md`, empty `phases/` and `references/` subdirs, `scripts/mirror.sh`.
2. **Reference docs** — write the 6 `references/*.md` files (they're data tables / question lists; minimal logic).
3. **Phase prompts** — write the 8 `phases/*.md` files (one per dispatchable subagent), each conforming to the §7 dispatch contract.
4. **SKILL.md body** — fill in the orchestrator walk-through that references the phase and reference files.
5. **Claude install-dir mirror** — copy everything to `~/.claude/skills/stock-research/`.
6. **Codex variant** — duplicate the Claude tree into `codex/skills/stock-research/`, create `agents/openai.yaml`, adjust the slash-command file if Codex uses a different mechanism (resolve at implementation time against current Codex conventions), and copy Plan 1's scripts (`scripts/_lib/`, all 12 top-level scripts, `tests/`, `pytest.ini`, `requirements.txt`, `README.md`) into `codex/skills/stock-research/scripts/`.
7. **Codex install-dir mirror** — copy to `~/.codex/skills/stock-research/`.
8. **Research-repo bootstrap** — one-time manual step per §10.
9. **End-to-end dry run on AAPL** — validate against §11 pass criteria; iterate on phase prompts until correct.

End of design.
