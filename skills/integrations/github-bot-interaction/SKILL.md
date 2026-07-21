---
name: github-bot-interaction
description: Use when a task requires commits or GitHub mutations under the user's configured GitHub App bot identity, including branch pushes, pull request creation or updates, comments, reviews, labels, merges, or direct API writes.
compatibility: >-
  Uses GH_BOT_APP_ID, GH_BOT_INSTALLATION_ID, GH_BOT_PRIVATE_KEY_PATH, GH_BOT_GIT_NAME, GH_BOT_GIT_EMAIL, and optional GH_BOT_KEYCHAIN_ACCOUNT. Non-empty values override ai-skills.gh-bot Keychain fallbacks; the key path points to a PEM file. Requires Bash, Git, curl, openssl, Python 3, date, grep, and GitHub API access; Keychain fallback adds macOS security and xxd. Token config, tooling, permission, minting, or write failure blocks remote mutation; missing git identity blocks only commit flows.
metadata:
  status: config-required
  allows_tool_references: "true"
---

# GitHub Bot Interaction

## Purpose

Use the configured GitHub App for remote GitHub mutations and the configured bot author identity for commits. Never use ambient personal GitHub credentials for remote writes.

## Required Capabilities

Requires shell execution, `git`, `curl`, `openssl`, `python3`, `date`, `grep`, and a GitHub CLI or API client that honors `GH_TOKEN`. Keychain fallback additionally requires macOS `security` and `xxd`.

## Configuration

Explicit non-empty environment inputs take precedence: `GH_BOT_APP_ID`, `GH_BOT_INSTALLATION_ID`, and `GH_BOT_PRIVATE_KEY_PATH` configure token minting; `GH_BOT_GIT_NAME` and `GH_BOT_GIT_EMAIL` configure commit identity. `GH_BOT_PRIVATE_KEY_PATH` must point to the GitHub App PEM file; never place private-key contents in an environment variable, command, skill file, log, or commit.

Each unset value falls back to its existing `ai-skills.gh-bot.{app-id,installation-id,private-key,git-name,git-email}` Keychain service. `GH_BOT_KEYCHAIN_ACCOUNT` selects the fallback account; otherwise `$USER` is used. An unreadable explicit key path or missing token fallback blocks remote writes. Missing git name or email blocks only flows that create commits. Neither failure permits personal credentials.

## Required Inputs

- repository or worktree path
- intended GitHub action
- branch, PR, issue, or target object
- approved mutation parameters, including the commit message or exact posted text when applicable
- confirmation that the write is intended

If a required input is missing, stop and ask.

Before writing, restate the supplied repository or worktree, target, action, approved parameters, and confirmation. Restate exact approved text only for text-posting actions. Include bot git identity preflight only for commit-capable flows. Do not ask again for inputs already supplied.

## Bot Identity

Before creating a commit, resolve each identity field independently from explicit configuration, then its Keychain fallback, and set the worktree author:

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

A local-only commit requires bot author identity but no GitHub token. Mint a token only when the flow reaches a remote mutation.

## Remote GitHub Writes

For every remote GitHub mutation, run `<skill-root>/scripts/get-bot-gh-token.sh`, retain its stdout only in an ephemeral shell variable, and expose that value as `GH_TOKEN` to exactly one GitHub write command. Never print or persist it.

Use a GitHub CLI or API client that honors `GH_TOKEN` for creating or editing pull requests, posting PR or issue comments, submitting reviews, changing labels, merging, replying to review threads, and POST/PATCH/PUT/DELETE GitHub API mutations.

For `git push`, mint a fresh token immediately before the remote operation, derive the `x-access-token` Basic-auth header in memory, disable credential helpers for that invocation, and scope the header to exactly one HTTPS push. Do not place the token in a URL or persist it in Git configuration.

Read-only GitHub operations may use ambient credentials if needed. Writes may not.

## Fail Closed

If the runtime has no GitHub CLI or API client that honors `GH_TOKEN`, or if token minting, permissions, or the remote write fails, stop and report the blocker. Bot git identity failure blocks commit-capable flows but does not block an API-only mutation whose token preflight succeeds.

For a blocked text-posting action, return the exact approved text as an unposted draft. For other blocked mutations, report the approved parameters. Never fall back to personal credentials.
