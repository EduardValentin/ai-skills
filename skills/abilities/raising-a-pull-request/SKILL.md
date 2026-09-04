---
name: raising-a-pull-request
description: Use when opening a pull request, deciding whether a pull request is ready for review or merge, executing an explicitly approved merge, or responding to a CI failure before or after merge.
compatibility: >-
  Requires source-control and CI read access through connectors, a CLI, or an API, and an approved write identity for an explicitly requested merge. Missing read access makes readiness unverified rather than assumed; missing write access blocks the merge.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Raising a Pull Request

## Purpose

Hard rules for the last mile of a change: opening the PR, calling it ready,
merging it, and handling CI after merge. Workflows that own tickets apply these
rules; this skill does not own ticket state, review, QA, or PR copy.

## Rules

- Read PR, CI, mergeability, review, and ticket state from the provider before
  asking the user to transcribe any of it. Prefer the live read over a prior
  report or the user's recollection.
- Green CI is not mergeability. The provider must positively report the PR
  mergeable and conflict-free; an unknown, still-calculating, or unavailable
  result is a blocker.
- Required approvals, code owners, and required checks come from the
  repository's rulesets or branch protection. When they cannot be read,
  readiness is unverified, not assumed.
- Any CI failure is fixed and rerun to green before the final report is
  presented. A report that lists a red check as a follow-up is not a readiness
  report.
- Evidence goes stale. A readiness verdict from an earlier step is not current
  evidence; before any merge, every gate is re-read in the same step.
- Readiness is never merge authorization. Merge only after the user explicitly
  approves it.
- After a merge, watch the merge commit's checks until they finish. A
  post-merge failure is fixed in a follow-up PR against the target branch that
  names the failing job and the affected commit; never push to the merged
  branch, and never call an observed failure a monitoring problem.

## Report

State, in one line each: PR and lifecycle state, provider mergeability, gate
policy source, CI status, review blockers, and the action taken or blocked.
