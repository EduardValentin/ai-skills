---
name: github-bot-interaction
description: Use when a task needs GitHub writes or PR/repo interaction under the user's required bot identity, including commits, branch pushes, PR creation or updates, PR comments, reviews, labels, merges, or direct GitHub API mutations. Requires local GitHub App bot credentials.
compatibility: >-
  Supports GH_BOT_APP_ID, GH_BOT_INSTALLATION_ID, GH_BOT_PRIVATE_KEY_PATH, GH_BOT_GIT_NAME, GH_BOT_GIT_EMAIL, and optional GH_BOT_KEYCHAIN_ACCOUNT. Explicit values override ai-skills.gh-bot Keychain fallbacks; GH_BOT_PRIVATE_KEY_PATH names the PEM file, never literal key material. Requires Bash/Git/curl/openssl/Python 3 and GitHub API; fallback also needs security/xxd. Missing config, identity, tooling, permissions, minting, or writes fail closed to a draft/blocker with no mutation.
metadata:
  status: config-required
  allows_tool_references: "true"
---

# GitHub Bot Interaction

## Purpose

Use the configured GitHub App bot identity for every GitHub write in personal projects. Never use ambient personal GitHub credentials for writes.

## Required Capabilities

Requires shell execution, `git`, `curl`, `openssl`, `python3`, and a GitHub CLI or API client that honors `GH_TOKEN`. Keychain fallback additionally requires macOS `security` and `xxd`.

## Configuration

Explicit non-empty environment inputs take precedence: `GH_BOT_APP_ID`, `GH_BOT_INSTALLATION_ID`, and `GH_BOT_PRIVATE_KEY_PATH` configure token minting; `GH_BOT_GIT_NAME` and `GH_BOT_GIT_EMAIL` configure commit identity. `GH_BOT_PRIVATE_KEY_PATH` must point to the GitHub App PEM file; never place private-key contents in an environment variable, command, skill file, log, or commit.

Each unset value falls back to its existing `ai-skills.gh-bot.{app-id,installation-id,private-key,git-name,git-email}` Keychain service. `GH_BOT_KEYCHAIN_ACCOUNT` selects the fallback account; otherwise `$USER` is used. An explicit but unreadable key path or a missing fallback blocks the write rather than switching to personal credentials.

## Required Inputs

- repository or worktree path
- intended GitHub action
- branch, PR, issue, or target object
- exact content to write when posting text
- confirmation that the write is intended

If a required input is missing, stop and ask.

Every response ready to write must restate repository/worktree, target object, action, approved text, confirmation, and bot identity preflight for commit-capable flows. Identity comes from the explicit environment surface first and Keychain only for missing values; unresolved identity blocks the mutation.

## Bot Identity

Before committing, resolve each identity field independently from explicit configuration, then its Keychain fallback, and set the worktree author:

```bash
BOT_ACCOUNT="${GH_BOT_KEYCHAIN_ACCOUNT:-${USER:-}}"
BOT_GIT_NAME="${GH_BOT_GIT_NAME:-}"
BOT_GIT_EMAIL="${GH_BOT_GIT_EMAIL:-}"
[[ -n "$BOT_GIT_NAME" ]] || BOT_GIT_NAME=$(security find-generic-password -s "ai-skills.gh-bot.git-name" -a "$BOT_ACCOUNT" -w)
[[ -n "$BOT_GIT_EMAIL" ]] || BOT_GIT_EMAIL=$(security find-generic-password -s "ai-skills.gh-bot.git-email" -a "$BOT_ACCOUNT" -w)
[[ -n "$BOT_GIT_NAME" && -n "$BOT_GIT_EMAIL" ]] || exit 1
git -C <worktree> config user.name "$BOT_GIT_NAME"
git -C <worktree> config user.email "$BOT_GIT_EMAIL"
```

If either field cannot be resolved, stop. Never fall back to personal git config.

## GitHub Writes

For every GitHub write, run `<skill-root>/scripts/get-bot-gh-token.sh`, retain its stdout only in an ephemeral shell variable, and expose that value as `GH_TOKEN` to exactly one GitHub write command. Never print or persist it.

Use a GitHub CLI or API client that honors `GH_TOKEN` for creating or editing pull requests, posting PR or issue comments, submitting reviews, changing labels, merging, replying to review threads, and POST/PATCH/PUT/DELETE GitHub API mutations.

For `git push`, mint a fresh token, derive the `x-access-token` Basic-auth header in memory, disable credential helpers for that invocation, and scope the header to exactly one HTTPS push. Do not place the token in a URL or persist it in Git configuration.

Read-only GitHub operations may use ambient credentials if needed. Writes may not.

## Fail Closed

If the runtime has no GitHub CLI or API client that honors `GH_TOKEN`, or if token minting, bot git identity, permissions, or the write command fails, stop and report the blocker. Draft intended text in chat instead of posting through personal credentials.

Every GitHub-write response must preserve this fail-closed path explicitly: token minting, permission, bot identity, or write-command failure means no mutation and only a draft/report is returned.
