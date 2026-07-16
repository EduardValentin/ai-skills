---
name: github-bot-interaction
description: Use when a task needs GitHub writes or PR/repo interaction under the user's required bot identity, including commits, branch pushes, PR creation or updates, PR comments, reviews, labels, merges, or direct GitHub API mutations. Requires local GitHub App bot credentials.
compatibility: >-
  Requires macOS Keychain access for the ai-skills.gh-bot credential services, Bash, Git, security, curl, openssl, Python 3, xxd, base64, tr, grep, date, GitHub API network access, and an external GitHub tool that honors GH_TOKEN. Fallback for missing configuration, tool support, bot identity, token minting, permissions, or a successful write is no mutation and only a draft or blocker report.
metadata:
  status: config-required
  allows_tool_references: "true"
---

# GitHub Bot Interaction

## Purpose

Use the configured GitHub App bot identity for every GitHub write in personal projects. Never use ambient personal GitHub credentials for writes.

## Required Capabilities

Requires shell execution, `git`, `curl`, `openssl`, `python3`, `xxd`, macOS Keychain access through `security`, and a GitHub CLI or API client that honors `GH_TOKEN`.

## Required Inputs

- repository or worktree path
- intended GitHub action
- branch, PR, issue, or target object
- exact content to write when posting text
- confirmation that the write is intended

If a required input is missing, stop and ask.

Every response that is ready to perform a GitHub write must restate this checklist before the mutation: repository/worktree, target object, intended action, exact approved content when posting text, confirmation that the write is intended, and bot git identity preflight for commit-capable flows. The identity preflight must say bot git name/email come from Keychain and fail closed if they cannot be read.

## Bot Identity

Before committing, set the worktree git author from Keychain:

```bash
BOT_GIT_NAME=$(security find-generic-password -s "ai-skills.gh-bot.git-name" -a "$USER" -w)
BOT_GIT_EMAIL=$(security find-generic-password -s "ai-skills.gh-bot.git-email" -a "$USER" -w)
git -C <worktree> config user.name "$BOT_GIT_NAME"
git -C <worktree> config user.email "$BOT_GIT_EMAIL"
```

If either Keychain read fails, stop. Do not fall back to personal git config.

For any commit-capable flow, state that bot git identity must be read from Keychain and that failure to read it blocks the mutation.

## GitHub Writes

For every GitHub write, run `<skill-root>/scripts/get-bot-gh-token.sh`, retain its stdout only in an ephemeral shell variable, and expose that value as `GH_TOKEN` to exactly one GitHub write command. Never print or persist it.

Use a GitHub CLI or API client that honors `GH_TOKEN` for creating or editing pull requests, posting PR or issue comments, submitting reviews, changing labels, merging, replying to review threads, and POST/PATCH/PUT/DELETE GitHub API mutations.

For `git push`, mint a fresh token, derive the `x-access-token` Basic-auth header in memory, disable credential helpers for that invocation, and scope the header to exactly one HTTPS push. Do not place the token in a URL or persist it in Git configuration.

Read-only GitHub operations may use ambient credentials if needed. Writes may not.

## Fail Closed

If the runtime has no GitHub CLI or API client that honors `GH_TOKEN`, or if token minting, bot git identity, permissions, or the write command fails, stop and report the blocker. Draft intended text in chat instead of posting through personal credentials.

Every GitHub-write response must preserve this fail-closed path explicitly: token minting, permission, bot identity, or write-command failure means no mutation and only a draft/report is returned.
