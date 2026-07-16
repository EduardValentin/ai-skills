"""Human-readable validation issue reporting."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from collections.abc import Iterable


@dataclass(frozen=True)
class ValidationIssue:
    scope: str
    message: str
    severity: str = "error"


def print_grouped_issues(issues: Iterable[ValidationIssue]) -> None:
    """Print issues grouped by their scope for terminal users."""
    grouped: dict[str, list[ValidationIssue]] = defaultdict(list)
    for issue in issues:
        grouped[issue.scope].append(issue)

    for scope in sorted(grouped):
        print(f"{scope}:")
        for issue in grouped[scope]:
            print(f"  {issue.severity}: {issue.message}")
