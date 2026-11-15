---
name: distilling-sources
description: Use when the user wants to distill, condense, or boil down a set of web pages, articles, documentation pages, or local text files on any topic into a small set of size-limited files, such as rulesets, guidelines, checklists, or reference notes for coding agents or people.
compatibility: >-
  Requires Python 3.9 or newer for the bundled scripts and a harness that can dispatch subagents
  on a small and a strong model tier. When subagent dispatch is unavailable, run each map and
  reduce prompt yourself, one at a time, and tell the user the run will be slower.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Distilling Sources

## Overview

Turn many sources into a few short files in five steps: interview, fetch, map, bucket, reduce.
The user controls the result through a **profile**, which you build with them by interview and
save as `profile.json` in the output folder. The steps never change; only the profile does.

You are the coordinator. Hold only paths and counts. Never read raw pages, chunks, fragments, or
buckets into your own context; the scripts and subagents do that.

## Files

| File | Purpose |
|---|---|
| `scripts/fetch_chunk.py` | Downloads or reads each source, cleans it, and splits it into chunks |
| `scripts/bucket.py` | Groups extracted items into one bucket file per target |
| `scripts/audit.py` | Measures each output file against its size limit |
| `assets/map-prompt.md` | Prompt for the subagents that extract items from one chunk |
| `assets/reduce-prompt.md` | Prompt for the subagents that write one output file |
| `assets/example-profile.json` | A complete profile to copy the shape from |

Everything a run creates lives in the output folder: `profile.json`, the output files, and a
`.staging` folder with the chunks, fragments, and buckets.

## Step 1: Interview

If the output folder already has a `profile.json`, show a short summary and ask whether to
reuse it, change it, or add sources. Otherwise ask the questions below.

Ask one question per message, in this order. Each message has three parts:

1. The question.
2. How the answer shapes the distillation, in two or three sentences drawn from the note below
   and worded for this user's topic. Questions without a note skip this part.
3. A proposed answer the user can accept or change, once earlier answers make one possible.

Save each answer to `profile.json` before asking the next question, so the user never edits the
file by hand.

**1. What is the result for, and who or what will read it?** (`goal`)
The goal is given to every subagent, so it decides what counts as relevant and how the output
is worded. A specific reader and moment of use gives tighter results than a topic name.

**2. Which folder should hold the result?** (location of `profile.json`)

**3. Which sources? URLs or local text files.** (`sources`)

**4. What kind of content should be kept?** (`keep`)
This is the filter applied to every chunk. A narrow answer yields few, precise items. A broad
answer yields many, and the size limits then force most of them out when the files are written.

**5. What should be thrown away?** (`discard`)
Anything not discarded competes for space in the output. Name the noise these sources are
likely to carry, such as anecdotes, history, or advice tied to one product.

**6. When two sources disagree, which one wins?** (`conflicts`)
This rule settles every clash when items are merged. Common choices are the stricter value,
the most recent source, one named source, or keeping both and noting the disagreement.

**7. Which output files do you want?** (`targets`)
Each file is one target, and every extracted item goes to exactly one of them. A few broad
targets give general files; many narrow ones give focused files that may come out thin. Split
by when each file will be read. Propose a set drawn from the goal.

**8. For each target in turn: what belongs in it, how long may it be, and what should it look
like?** (`route`, `cap_tokens`, `format`)
The route is the sentence subagents use to sort items, so a vague route misfiles them. A low
size limit keeps only the strongest items; no limit keeps everything. The format sets the
shape, such as bullets, decision rules, or a specification.

**9. Which targets are foundations that the others must not repeat?** (`pass`)
Foundations are written first, and the other files are told what they cover and leave it out.
Pick the files that are always loaded or checked automatically. With no foundations, every
file is written independently and some content may repeat. Save `pass` 1 for foundations and 2
for the rest.

**10. Do you want to review the results after fetching, after bucketing, both, or neither?**
(`checkpoints`)

Each target also needs a short uppercase `name` and an `output` file name; choose them yourself
and show them. Use `null` for `cap_tokens` when a file has no size limit. When every answer is
saved, show the profile as a short table and ask for a go-ahead before step 2.

## Step 2: Fetch

Run `python3 -I scripts/fetch_chunk.py <output folder>/profile.json`.

It prints one line per source and the path of the list of chunks that still need mapping.
A `FAILED` line starting with `blocked` or `empty` means the site refused the request or needs
a browser: leave that source out, and never try mirrors, archives, or other ways around the
block. A line starting with `error` is a server or network failure: run the command once more
at the end of step 3, since it skips every source it already has.

At the `after_fetch` checkpoint, show the per-source chunk counts and failures, then wait.

## Step 3: Map

Fill `assets/map-prompt.md` once from the profile. Write `{targets}` as one line per target,
`- NAME: route`. Dispatch one subagent on the small model tier per chunk in the to-map list, in
parallel, each with the identical filled prompt followed by two lines:

```
Chunk file: <chunk path>
Output file: <fragments folder>/<same file name as the chunk>
```

## Step 4: Bucket

Run `python3 -I scripts/bucket.py <output folder>/profile.json`.

It prints the item count and bucket path per target. An `UNMAPPED` line names a chunk whose
subagent wrote nothing: map it again, then rerun the command.

At the `after_bucket` checkpoint, show the counts per target, then wait. A target with almost no
items is worth pointing out: the user may want to drop it or reword its route.

## Step 5: Reduce

Fill `assets/reduce-prompt.md` once per target and dispatch one subagent on the strong model
tier for each, followed by the bucket path and the output path. Skip targets with an empty
bucket and say so in the report.

1. Dispatch all pass 1 targets in parallel with `{already_covered}` set to `Nothing yet.`
2. Join the `COVERED:` lines they return, then dispatch all pass 2 targets in parallel with
   that text as `{already_covered}`.

Write `{size}` as `At most N tokens, about 4 x N characters.` or, without a cap, `No limit.`

Then run `python3 -I scripts/audit.py <output folder>/profile.json`. For each file marked
`OVER`, dispatch one strong-tier subagent to shorten that file until it fits, at most twice.
A target you skipped for an empty bucket shows as `MISSING`; that is expected.

## Report

End with a table of output file, item count, characters, estimated tokens, and cap, taken from
the audit output. Below it, state:

- that token counts are estimates of characters divided by four;
- every source that failed and why, asking for an alternative URL or a saved copy;
- any target skipped for an empty bucket and any file still over its cap.

Keep `.staging` until the user says to delete it. With it in place, adding a source later only
means adding it to the profile and repeating steps 2 to 5; only the new chunks are mapped.

## Rules

- Never ask the user to download, convert, or edit files; ask only the interview questions and
  for replacements of failed sources.
- Never change the profile after the go-ahead without asking.
- Never present a result as complete when a source failed; name the gap first.
