---
name: pr-reviewer-summary
description: Use when drafting or updating a PR description from reliable diff, commit, changed-file, ticket, PR URL, or conversation context.
compatibility: >-
  Requires reliable review context such as a branch or PR diff, changed-file summary, or PR URL. Git or hosting access is optional because the fallback is to ask the user to provide the missing context.
metadata:
  status: local-required
  allows_tool_references: "true"
---

# PR Reviewer Summary

Draft a ready-to-paste Markdown PR body from reliable review context: a branch or PR diff, changed files, recent commits, and available ticket or conversation context. If there is no diff, changed-file summary, or PR URL, ask for that context instead of inventing the PR body.

Describe only the final shipped state. Do not mention iteration history, false starts, agent process, tools used, screenshots, environment limits, or whether the agent personally tested the app.

Follow the output contract, section rules, formatting requirements, and example in `references/pr-body-workflow.md`. Output only the PR body.
