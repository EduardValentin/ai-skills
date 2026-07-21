# Fake completed implementation evidence

## Approved goal and criteria

The approved goal was to let an authenticated account owner download a JSON
account export while denying all other users without exposing whether the
account exists.

- AC-1: An authenticated owner receives a JSON download containing the
  account's public profile rows.
- AC-2: A different authenticated user receives HTTP 403 with the generic
  message `account export denied` and no export body.
- AC-3: Every successful export writes one audit event with the requester ID,
  account ID, and exported row count.

The approved non-goals were CSV output, asynchronous exports, administrator
override, PR publication, release, merge, and tracker-state changes.

## Changed surfaces

- `src/account_exports/authorize.py`: added owner-only export authorization and
  the generic denial result.
- `src/account_exports/handler.py`: applied authorization before loading rows
  and recorded the successful-export audit event.
- `tests/account_exports/test_handler.py`: added owner, non-owner, response-body,
  and audit-event scenarios.

## Test-first and check evidence

Before production edits, the owner and non-owner scenarios were added and this
focused command was run:

`python3 -m pytest tests/account_exports/test_handler.py -q`

It failed with two expected behavioral failures: the non-owner request returned
HTTP 200, and no successful-export audit event was emitted. After the initial
implementation, the same focused command passed 6 tests.

The relevant regression command was:

`python3 -m pytest tests/account_exports tests/audit -q`

It passed 31 tests after the initial implementation and again after review
remediation.

## Independent review and remediation

The first independent review found one relevant medium-severity authorization
gap: authorization happened after export rows were loaded, allowing an
unauthorized request to trigger account lookup and disclose account existence
through timing and logs. The finding was accepted.

A failing test was added for AC-2 proving that an unauthorized request must not
call the row loader. The focused test failed because the loader was called once.
Authorization was moved before row loading, then the focused and regression
commands above passed. A fresh independent review of the revised diff reported
no remaining relevant findings.

## Runtime QA

Manual QA used the fake local server at `http://127.0.0.1:8086` with seeded
fixture accounts and captured these final outcomes:

- AC-1 PASS: the owner request returned HTTP 200, content type
  `application/json`, and the seeded public profile rows.
- AC-2 PASS: the different-user request returned HTTP 403, the exact generic
  message, no export body, and no row-loader event in the fixture trace.
- AC-3 PASS: one successful owner request produced exactly one audit event with
  the seeded requester ID, account ID, and row count; the denied request
  produced no successful-export event.

No QA remediation was required after the clean review. No known residual risks
or limitations remain within the approved boundary.
