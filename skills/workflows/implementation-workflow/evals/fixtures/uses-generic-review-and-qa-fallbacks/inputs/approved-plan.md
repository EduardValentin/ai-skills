# Approved implementation packet

This fake, offline repository scenario contains an approved implementation that
is ready for checks, independent review, and runtime QA.

## Goal and acceptance criteria

Expose feature flags through the existing CLI without leaking private flags to
operators.

- AC-1: `python3 feature_flags_cli.py --role operator` exits zero and returns
  only the enabled public flag `search-v2`.
- AC-2: `python3 feature_flags_cli.py --role admin` exits zero and returns all
  fixture flag names: `billing-console`, `search-v2`, and `staged-import`.

## Approved implementation and boundary

`feature_flags.py` implements role-aware visibility. `feature_flags_cli.py` is
the runtime entry point, and `test_feature_flags.py` covers the approved
behavior. The implementation is already complete and stayed within these three
files. No dependencies, persistence, network access, new roles, or CLI options
are approved.

## Checks and risk

- Focused: `python3 -m unittest -v test_feature_flags.FeatureFlagTests.test_operator_sees_only_enabled_public_flags`
- Regression: `python3 -m unittest -v`

The risk is authorization-sensitive information exposure at the CLI boundary.
The fake branch is `feature/flag-visibility`, has no unrelated changes, and the
staged workspace is the complete affected surface. Native review and QA agents
are unavailable in this scenario, but the supplied generic dispatch surface
provides separate read-only review and runtime-QA roles.
