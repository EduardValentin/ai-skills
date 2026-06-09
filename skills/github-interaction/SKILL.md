---
name: github-interaction
description: Use when a task needs GitHub writes or PR/repo interaction under the user's required bot identity, including commits, branch pushes, PR creation or updates, PR comments, reviews, labels, merges, or direct GitHub API mutations. Requires local GitHub App bot credentials.
---

# GitHub Interaction

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

## Bot Identity

Before committing, set the worktree git author from Keychain:

```bash
BOT_GIT_NAME=$(security find-generic-password -s "ai-skills.gh-bot.git-name" -a "$USER" -w)
BOT_GIT_EMAIL=$(security find-generic-password -s "ai-skills.gh-bot.git-email" -a "$USER" -w)
git -C <worktree> config user.name "$BOT_GIT_NAME"
git -C <worktree> config user.email "$BOT_GIT_EMAIL"
```

If either Keychain read fails, stop. Do not fall back to personal git config.

## GitHub Writes

For every GitHub write, mint a fresh token and scope it to one write command:

```bash
GH_TOKEN=$(<skill-root>/scripts/get-bot-gh-token.sh) <run the GitHub write command>
```

Use a GitHub CLI or API client that honors `GH_TOKEN` for creating or editing pull requests, posting PR or issue comments, submitting reviews, changing labels, merging, replying to review threads, and POST/PATCH/PUT/DELETE GitHub API mutations.

For `git push`, use a fresh token as the HTTPS credential:

```bash
GH_TOKEN=$(<skill-root>/scripts/get-bot-gh-token.sh)
BASIC_AUTH=$(printf 'x-access-token:%s' "$GH_TOKEN" | base64 | tr -d '\n')
git -c credential.helper= \
  -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $BASIC_AUTH" \
  push origin <branch>
```

Read-only GitHub operations may use ambient credentials if needed. Writes may not.

## Fail Closed

If token minting, bot git identity, permissions, or the write command fails, stop and report the blocker. Draft intended text in chat instead of posting through personal credentials.
