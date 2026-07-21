"""User-observable contract tests for the Bitbucket Cloud PR helper."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    REPO_ROOT
    / "skills"
    / "integrations"
    / "bitbucket-pr-management"
    / "scripts"
    / "bitbucket-cloud-pr.sh"
)
AUTH_ENV_VARS = (
    "BITBUCKET_TOKEN",
    "BITBUCKET_EMAIL",
    "BITBUCKET_API_TOKEN",
)


def run_script(*arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *arguments],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def fake_curl_environment(
    tmp_path: Path, responses: dict[str, dict[str, object]]
) -> tuple[dict[str, str], Path]:
    fake_curl = tmp_path / "curl"
    fake_curl.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

url = sys.argv[-1]
with open(os.environ["FAKE_CURL_LOG"], "a", encoding="utf-8") as log:
    log.write(f"{url}\\n")

responses = json.loads(os.environ["FAKE_CURL_RESPONSES"])
if url not in responses:
    print(f"unexpected URL: {url}", file=sys.stderr)
    raise SystemExit(22)

json.dump(responses[url], sys.stdout)
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    request_log = tmp_path / "requests.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path}{os.pathsep}{env['PATH']}",
            "BITBUCKET_EMAIL": "developer@example.invalid",
            "BITBUCKET_API_TOKEN": "FAKE_BITBUCKET_API_TOKEN",
            "FAKE_CURL_LOG": str(request_log),
            "FAKE_CURL_RESPONSES": json.dumps(responses),
        }
    )
    env.pop("BITBUCKET_TOKEN", None)
    return env, request_log


def test_help_describes_commands_and_authentication() -> None:
    completed = run_script("--help")

    assert completed.returncode == 0
    assert "Usage:" in completed.stdout
    assert "bitbucket-cloud-pr.sh [--dry-run] pr-details" in completed.stdout
    assert "find-prs-for-branch" in completed.stdout
    assert "update-description" in completed.stdout
    assert "BITBUCKET_TOKEN" in completed.stdout
    assert "OAuth 2 access token" in completed.stdout
    assert "Atlassian account email" in completed.stdout


@pytest.mark.parametrize(
    ("arguments", "expected_output"),
    [
        pytest.param(
            ("pr-details", "acme", "widget", "42"),
            (
                "METHOD=GET",
                "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/"
                "pullrequests/42",
            ),
            id="pr-details",
        ),
        pytest.param(
            ("find-prs-for-branch", "acme", "widget", "feature/auth"),
            (
                "METHOD=GET",
                "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/"
                "pullrequests?q=source.branch.name+%3D+%22feature%2Fauth%22+AND+"
                "state+%3D+%22OPEN%22",
            ),
            id="find-prs-for-branch",
        ),
        pytest.param(
            ("read-comments", "acme", "widget", "42"),
            (
                "METHOD=GET",
                "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/"
                "pullrequests/42/comments",
            ),
            id="read-comments",
        ),
        pytest.param(
            ("post-comment", "acme", "widget", "42", "QA passed on staging"),
            (
                "METHOD=POST",
                "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/"
                "pullrequests/42/comments",
                'BODY={"content":{"raw":"QA passed on staging"}}',
            ),
            id="post-comment",
        ),
        pytest.param(
            (
                "update-description",
                "acme",
                "widget",
                "42",
                "Updated PR description",
            ),
            (
                "METHOD=PUT",
                "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/"
                "pullrequests/42",
                'BODY={"description":"Updated PR description"}',
            ),
            id="update-description",
        ),
        pytest.param(
            ("merge", "acme", "widget", "42"),
            (
                "METHOD=POST",
                "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/"
                "pullrequests/42/merge",
            ),
            id="merge",
        ),
        pytest.param(
            ("merge-status", "acme", "widget", "42", "abc123"),
            (
                "METHOD=GET",
                "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/"
                "pullrequests/42/merge/task-status/abc123",
            ),
            id="merge-status",
        ),
    ],
)
def test_dry_run_reports_request_without_calling_bitbucket(
    arguments: tuple[str, ...], expected_output: tuple[str, ...]
) -> None:
    completed = run_script("--dry-run", *arguments)

    assert completed.returncode == 0
    for expected in expected_output:
        assert expected in completed.stdout


def test_dry_run_does_not_expose_token_values() -> None:
    env = os.environ.copy()
    env["BITBUCKET_TOKEN"] = "FAKE_BITBUCKET_TOKEN"

    completed = run_script(
        "--dry-run", "pr-details", "acme", "widget", "42", env=env
    )

    assert completed.returncode == 0
    assert "FAKE_BITBUCKET_TOKEN" not in completed.stdout
    assert "FAKE_BITBUCKET_TOKEN" not in completed.stderr


def test_read_comments_combines_validated_pages_without_exposing_credentials(
    tmp_path: Path,
) -> None:
    first_url = (
        "https://api.bitbucket.org/2.0/repositories/acme/widget/"
        "pullrequests/42/comments"
    )
    second_url = f"{first_url}?page=2"
    env, request_log = fake_curl_environment(
        tmp_path,
        {
            first_url: {
                "size": 2,
                "page": 1,
                "pagelen": 1,
                "next": second_url,
                "values": [{"id": 101, "content": {"raw": "First"}}],
            },
            second_url: {
                "size": 2,
                "page": 2,
                "pagelen": 1,
                "previous": first_url,
                "values": [{"id": 102, "content": {"raw": "Second"}}],
            },
        },
    )

    completed = run_script("read-comments", "acme", "widget", "42", env=env)

    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    assert [comment["id"] for comment in result["values"]] == [101, 102]
    assert "next" not in result
    assert request_log.read_text(encoding="utf-8").splitlines() == [
        first_url,
        second_url,
    ]
    assert "FAKE_BITBUCKET_API_TOKEN" not in completed.stdout
    assert "FAKE_BITBUCKET_API_TOKEN" not in completed.stderr


@pytest.mark.parametrize(
    "next_url",
    [
        pytest.param(
            "https://credentials.example/2.0/repositories/acme/widget/"
            "pullrequests/42/comments?page=2",
            id="foreign-host",
        ),
        pytest.param(
            "https://api.bitbucket.org/2.0/repositories/acme/other/"
            "pullrequests/42/comments?page=2",
            id="different-comments-collection",
        ),
    ],
)
def test_read_comments_rejects_mismatched_next_url_before_requesting_it(
    tmp_path: Path, next_url: str
) -> None:
    first_url = (
        "https://api.bitbucket.org/2.0/repositories/acme/widget/"
        "pullrequests/42/comments"
    )
    env, request_log = fake_curl_environment(
        tmp_path,
        {
            first_url: {
                "size": 2,
                "page": 1,
                "pagelen": 1,
                "next": next_url,
                "values": [{"id": 101}],
            }
        },
    )

    completed = run_script("read-comments", "acme", "widget", "42", env=env)

    assert completed.returncode != 0
    assert "Refusing untrusted comments pagination URL" in completed.stderr
    assert request_log.read_text(encoding="utf-8").splitlines() == [first_url]
    assert "FAKE_BITBUCKET_API_TOKEN" not in completed.stdout
    assert "FAKE_BITBUCKET_API_TOKEN" not in completed.stderr


def test_non_dry_run_requires_explicit_authentication() -> None:
    env = os.environ.copy()
    for variable in AUTH_ENV_VARS:
        env.pop(variable, None)

    completed = run_script("pr-details", "acme", "widget", "42", env=env)

    assert completed.returncode != 0
    assert (
        "Set BITBUCKET_TOKEN or BITBUCKET_EMAIL + BITBUCKET_API_TOKEN"
        in completed.stderr
    )
