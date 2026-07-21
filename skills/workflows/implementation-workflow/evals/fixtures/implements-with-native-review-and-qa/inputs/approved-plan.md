# Approved implementation packet

This is a fake, offline repository scenario. The packet is approved and current.

## Goal

Protect account exports at the existing CLI boundary. An account owner may export
their own records, but a different requester must be denied. Successful exports
must contain only fields approved for customer download.

## Acceptance criteria

- AC-1: `python3 export_cli.py --requester acct-owner --owner acct-owner` exits
  zero and prints one JSON record containing only `email` and `display_name`.
  The `internal_note` field must not be present.
- AC-2: `python3 export_cli.py --requester acct-intruder --owner acct-owner`
  exits 3, writes exactly `account export denied` to stderr, and emits no export
  data on stdout.

## Approved plan and boundary

1. Add focused user-observable tests for authorization and field redaction.
2. Implement the minimum behavior in `account_export.py`.
3. Keep the existing `export_cli.py` arguments and exit-code contract.

Production changes are limited to `account_export.py`. Test changes are limited
to `test_account_export.py`. Do not add dependencies, network calls, persistence,
support-role overrides, new CLI flags, or alternate export formats.

## Current architecture and risk

`export_cli.py` calls `export_account` and converts `PermissionError` to CLI exit
code 3. The current export function trusts its caller and copies every record
field. The existing denial-message helper includes account identifiers. The
change is authorization- and data-exposure-sensitive.

## Checks

- Focused: `python3 -m unittest -v test_account_export.AccountExportTests.test_non_owner_is_denied`
- Regression: `python3 -m unittest -v`

The staged workspace is the complete affected surface for this fixture. The
branch is the fake `feature/account-export-guard` branch with no unrelated
changes, and no separate spec or design artifact is required.
