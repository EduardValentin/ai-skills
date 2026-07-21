---
name: pr-reviewer-summary
description: Use when drafting or updating a PR description from an accessible diff or reliable changed-file summary, optionally with commit, ticket, PR URL, or conversation context, or when that minimum review evidence is missing.
compatibility: >-
  Requires an accessible branch or PR diff or a reliable changed-file summary. Git and hosting access are optional; when they are unavailable or a PR URL cannot be opened, ask for pasted review evidence.
metadata:
  status: local-required
  allows_tool_references: "true"
---

# PR Reviewer Summary

Draft a ready-to-paste Markdown PR body from reliable review evidence.

## Evidence

- Require an accessible branch or PR diff or a reliable changed-file summary as the minimum evidence. A PR URL counts only when it can be opened to obtain that evidence.
- Use recent commits, ticket details, and conversation context as optional enrichment. They do not replace the minimum evidence.
- If the minimum evidence is unavailable, ask concisely for a pasted diff, changed-file summary, or accessible PR URL. This request is the only exception to the PR-body-only output rule.
- Include automated commands only when supplied by the user or directly supported by inspected repository scripts, configuration, or tests. Otherwise write `Not specified.`
- Build manual verification only from reliable setup, public entry points, reviewer actions, and observable outcomes. When those are unavailable, write `Not specified.` under Manual Verification instead of inventing steps.

Describe only the final shipped state. Do not mention iteration history, false starts, agent process, tools used, screenshots, agent execution or tooling limits, or whether the agent personally tested the app. When reliable review context names a mocked external boundary and gives a rationale, include that specific rationale without generalizing it into an agent or tooling limitation.

Follow the output contract, section rules, formatting requirements, and example in `references/pr-body-workflow.md`. When the minimum evidence exists, output only the PR body.
