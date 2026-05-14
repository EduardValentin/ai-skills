# Test Log

## Scenario 1 - PR host unavailable under time pressure

### RED - 2026-05-14

Isolated agent, no `frontend-pr-test` skill loaded.

**Result:** FAIL. The agent chose B.

**Verbatim response:**

> Bitbucket PR metadata is blocked in this environment, so I’m going to proceed best-effort instead of pausing: I’ll inspect the local diff plus the ticket ID, infer the likely changed workflow and acceptance checks, start the app, run the relevant browser testing, and call out clearly what I could and couldn’t verify from missing PR notes.

**Failure pattern:** Treated blocked PR metadata as a reportable limitation rather than a blocker, then substituted diff inference for PR testing instructions.

### GREEN - 2026-05-14

Isolated agent, updated `frontend-pr-test` skill loaded from the canonical repo path.

**Result:** PASS. The agent chose A.

**Verbatim response:**

> I’m blocked before browser testing: the Bitbucket PR metadata is unavailable in this environment, and for PR verification I need the PR notes/testing instructions before inferring scope from the diff.
>
> Please either restore Bitbucket access, paste the PR description/testing notes here, or point me to an authenticated local source for the PR metadata. Once I have that, I’ll fetch the latest branch/base and run the browser acceptance pass right away.

**Pass pattern:** Treated blocked PR metadata as a blocker, asked for access or user-supplied PR notes, and did not substitute diff inference for PR instructions.
