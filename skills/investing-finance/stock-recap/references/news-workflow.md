# Stock Recap News Workflow

## News mode Phase 1.5: Event capture

(Phase 1 ran already in shared form; News mode adds an event-capture step before any fetch.)

### Step 1.5.1 — Capture the event (free-form)

Ask the user, in plain Markdown:

> What's the event? Be specific — date, what was announced, where it was disclosed (8-K, press release, news article, transcript, etc.).

Capture the answer verbatim into a session variable `event_description`.

Also ask:

> What date did the event take place? (YYYY-MM-DD)

Capture as `event_date`.

### Step 1.5.2 — Classify the event (agent + user)

The agent proposes a classification from this fixed list:

- `M&A` — acquisition, divestiture, merger.
- `leadership` — CEO / CFO / Chair change, board resignation.
- `regulatory` — ruling, fine, antitrust action, new compliance regime.
- `guidance-restated` — pre-announcement, profit warning, reaffirmation.
- `customer-or-supply-chain` — major customer loss / win / supplier disruption.
- `litigation` — verdict, settlement, class-action.
- `other` — anything else.

Use native interactive-input — 7 options (one per class). The user confirms or picks a different class.

Capture as `event_class`.

## News mode Phase 2: Optional context fetch

The agent proposes which refreshes are warranted based on `event_class`. Defaults:

| event_class | Default proposed fetches |
|---|---|
| M&A | `latest-8K`, `target-financials` (if target US-listed and known) |
| leadership | (none — usually no fetch needed) |
| regulatory | `latest-8K`, `risk-factors-diff` (latest 10-K vs prior) |
| guidance-restated | `latest-8K`, `prices+consensus` |
| customer-or-supply-chain | `latest-8K`, `competitor-pull` (if a peer is named in the event) |
| litigation | `latest-8K`, `risk-factors-diff` |
| other | (none — agent asks the user what to fetch) |

Surface the proposed fetches via native interactive-input — multi-select with one option per proposed fetch, plus "Skip all fetches" as an alternative. The user can pick a subset.

For each selected fetch, dispatch one sub-agent in parallel using `references/phases/news/02-context-fetch-sub.md`. Wait for all to return.

On any `BLOCKED` status: surface via native interactive-input — 2 options: **Continue without that data** / **Retry**.

## News mode Phase 3: Impact analysis (interactive)

This phase runs in the main agent. It does NOT fan out.

**Read these references before starting:**
- `references/sell-trigger-evaluation.md` — for sub-step 3.4.
- `references/auto-recommend-rules.md` — for the recommendation evaluation.

For each affected thesis layer, walk the user through what changes:

### Step 3.1 — Business model / moat

Does this event widen, narrow, or leave the moat unchanged? One paragraph. Cite specific evidence from Phase 2's fetched data (or, if no fetch, from the saved `business-and-moat.md`).

### Step 3.2 — Financials

Which line items are affected over the next 4 quarters? Direction (up / down) and rough magnitude (small / material / transformative). One bullet per affected line.

### Step 3.3 — Projection levers

For each of bull / base / bear, propose deltas on the affected yearly KPI rows. Use free-form dialogue:

> Phase 3 of the news analysis: I think this event shifts the **base case** Y2 revenue from $X.XB to $Y.YB (a -<delta>% impact) because <reason>. Bull case Y2 revenue: from $A.AB to $B.BB. Bear case Y2 revenue: from $C.CB to $D.DB (worst-affected scenario). What do you think?

The user accepts / disputes / proposes alternates. Capture agreed shifts.

### Step 3.4 — Sell triggers — re-evaluate only the affected ones

Identify the subset of triggers across all three categories in `verdict.json.sell_triggers` (`materially_overvalued`, `thesis_broken`, `better_opportunity`) that this event plausibly affects (the agent proposes; the user confirms with a quick "yes / I'd add this one too" exchange). Apply `references/sell-trigger-evaluation.md` to each of those. The unaffected triggers stay marked "not re-evaluated this session."

## News mode Checkpoint 1 — Impact review

**Before rendering:** assemble §3.1–§3.4 plus the auto-recommend evaluation from `references/auto-recommend-rules.md` (rules 1, 2, 4, 6 apply in news mode; rules 3 and 5 are quarterly-mode specific and skipped).

Format (rendered Markdown):

```markdown
## Checkpoint 1 — News impact review

### Event

> <event_description from Phase 1.5>

Class: **<event_class>** | Date: <event_date>

### Business model / moat impact

<§3.1, one paragraph.>

### Financials impact

<§3.2, bullet list of affected line items.>

### Projection levers shifted

<§3.3, table of bull/base/bear yearly KPI changes.>

### Sell triggers re-evaluated

<§3.4, list of affected triggers with new state + justification. Note explicitly which triggers were NOT re-evaluated this session.>

---

### Auto-recommend evaluation

<Same as Quarterly Checkpoint 2's auto-recommend block — apply rules 1, 2, 4, 6 only. If any fires, recommend Phase 4 update. Otherwise, no automatic update.>
```

Use native interactive-input — same 2 options as Quarterly Checkpoint 2 (depending on the recommendation): **Enter Phase 4 to update** vs **Continue without updating**, OR **Continue without updating** vs **Update anyway**.

If continue → jump to Phase 5 (commit & index).
If enter Phase 4 → proceed.

## News mode Phase 4: Update thesis (optional)

Identical to Quarterly Phase 6 — same three sub-modes (surgical / reclassification / pivot-to-restart), same `update-flow.md` workflow, same diff-before-write Checkpoint 2.

## News mode Checkpoint 2 — Diff before write

Identical to Quarterly Checkpoint 3 — same diff rendering, same Apply / Revise further options, same write-on-Apply logic.

## News mode Phase 5: Commit & index

Identical to Quarterly Phase 7 with two differences:

1. The recap doc is named `<ticker_dir>/recaps/recap-<YYYY-MM-DD>-news.md` (mode = `news` in frontmatter).
2. The commit trailer has `session: news-recap` and `trigger: 8-K-<event_date>` if Phase 2 fetched an 8-K, otherwise `trigger: news` or `trigger: catalyst-event` depending on what the event was.

The body of the recap doc uses this local News mode section contract:

```yaml
---
ticker: <TICKER>
artifact: recap
mode: news
session: news-recap
session_date: <YYYY-MM-DD>
window_start: <event_date>
window_end: <event_date>
event_summary: "<short version of event_description>"
event_class: <event_class>
periods_processed: []
thesis_version_before: <vN>
thesis_version_after: <vN | vN+1>
schema_version: 1
---

# <TICKER> — News recap, <YYYY-MM-DD>

## Event

<event_description verbatim.>

Class: **<event_class>** | Date: <event_date> | Disclosure: <8-K | press release | etc.>

## Affected thesis layers

### Business model / moat
<§3.1>

### Financials
<§3.2>

### Projection levers
<§3.3>

## Affected sell triggers

<§3.4 — only the re-evaluated ones, with state + justification. Explicit note that unaffected triggers remain in the state from the last quarterly recap.>

## Thesis update applied

<Same shape as Quarterly Phase 7 step 7.1.>

## Next review trigger

<today + 90 days, or earlier if user specified.>
```
