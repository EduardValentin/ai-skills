# Manage Bitbucket PR Test Log

## 2026-05-14 — RED baseline

Constraint: delegated pressure tests were not run because this session did not have user authorization for delegated agent work.

Local baseline checks:

```bash
test -f skills/manage-bitbucket-pr/SKILL.md
rg -n "manage-bitbucket-pr" skills/ticket-start skills
```

Observed result before implementation:
- No `skills/manage-bitbucket-pr/SKILL.md` existed.
- No `ticket-start` handoff to `manage-bitbucket-pr` existed.

Baseline failure pattern:
- Bitbucket PR API mechanics had no dedicated skill trigger.
- `ticket-start` had no explicit pointer to keep Bitbucket PR management out of its job workflow.

## 2026-05-14 — GREEN local checks

Commands:

```bash
test -f skills/manage-bitbucket-pr/SKILL.md
rg -n "manage-bitbucket-pr" skills/ticket-start/SKILL.md
! rg -n "api\\.bitbucket|/repositories/\\{workspace\\}|pullrequests" skills/ticket-start
! rg -n "Read tool|Write tool|Edit tool|str_replace|ask_user_input|TodoWrite|Agent tool|MCP|spawn|subagent|Subagent" skills/manage-bitbucket-pr/SKILL.md skills/manage-bitbucket-pr/references
```

Observed result after implementation:
- Dedicated `manage-bitbucket-pr` skill exists.
- `ticket-start` describes the Bitbucket PR REST portion without explicit skill invocation.
- The new skill and reference have no obvious agent-specific tool names in their instructions.

## 2026-05-14 — Review feedback: curated endpoints only

Feedback:
- Do not make the agent read full external docs from the reference file.
- Include only the relevant necessary endpoints, such as reading comments, posting comments, and merging PRs.

RED check before fix:

```bash
rg -n "Official references|developer\\.atlassian|List PRs|Update PR metadata|Delete comment|Resolve comment thread|Create task|Approve|Unapprove|Request changes|Withdraw request changes|Diffstat|Patch|Build/status" skills/manage-bitbucket-pr/references/cloud-pullrequests.md
```

Observed failure:
- The reference linked full Atlassian docs.
- The endpoint list included broad operations beyond the curated PR details/comment/merge surface.

GREEN checks after fix:

```bash
! rg -n "Official references|developer\\.atlassian|List PRs|Update PR metadata|Delete comment|Resolve comment thread|Create task|Approve|Unapprove|Request changes|Withdraw request changes|Diffstat|Patch|Build/status" skills/manage-bitbucket-pr/references/cloud-pullrequests.md
rg -n "PR details|Read comments|Post comment|Merge|Merge task status" skills/manage-bitbucket-pr/references/cloud-pullrequests.md
```

Expected result:
- No full-doc links or broad endpoint rows remain.
- The curated endpoint rows remain available locally.

## 2026-05-14 — Review feedback: rely on auto-trigger

Feedback:
- `ticket-start` should not specifically invoke `manage-bitbucket-pr`; it should rely on skill auto-triggering.

RED check before fix:

```bash
rg -n 'use `manage-bitbucket-pr`|manage-bitbucket-pr' skills/ticket-start/SKILL.md
```

Observed failure:
- `ticket-start` explicitly named `manage-bitbucket-pr` in its Ship phase.

GREEN checks after fix:

```bash
! rg -n 'manage-bitbucket-pr' skills/ticket-start/SKILL.md
rg -n 'Bitbucket PR REST work' skills/ticket-start/SKILL.md
```

Expected result:
- `ticket-start` keeps Bitbucket PR REST trigger language without explicitly naming another skill.

## 2026-05-14 — Review feedback: no historical context in skill wording

Feedback:
- `ticket-start` should not say "keep API details out of this skill" or otherwise imply historical migration context.

RED check before fix:

```bash
rg -n "keep .*out of this skill|instead of embedding|endpoint recipes" skills/ticket-start/SKILL.md
```

Observed failure:
- The Ship phase phrased the Bitbucket handoff as removing or excluding prior API details.

GREEN checks after fix:

```bash
! rg -n "keep .*out of this skill|instead of embedding|endpoint recipes" skills/ticket-start/SKILL.md
rg -n "treat that portion as Bitbucket PR REST work" skills/ticket-start/SKILL.md
```

Expected result:
- `ticket-start` uses plain current-state wording for Bitbucket PR REST work.
