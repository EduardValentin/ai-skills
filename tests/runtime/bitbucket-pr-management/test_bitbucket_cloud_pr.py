"""User-observable contract tests for the Bitbucket Cloud PR helper."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

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
SKILL_ROOT = SCRIPT.parents[1]
AUTH_ENV_VARS = (
    "BITBUCKET_TOKEN",
    "BITBUCKET_EMAIL",
    "BITBUCKET_API_TOKEN",
)


def run_script(
    *arguments: str,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    script: Path = SCRIPT,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *arguments],
        cwd=REPO_ROOT,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


def fake_http_environment(
    tmp_path: Path,
    responses: dict[str, dict[str, object]],
    *,
    request_error: str = "",
    redirects: dict[str, str] | None = None,
) -> tuple[dict[str, str], Path, Path]:
    response_specs = {
        url: {"status": 200, "reason": "OK", "body": body}
        for url, body in responses.items()
    }
    for source, target in (redirects or {}).items():
        response_specs[source] = {
            "status": 302,
            "reason": "Found",
            "headers": {"Location": target},
            "body": {},
        }
    sitecustomize = tmp_path / "sitecustomize.py"
    sitecustomize.write_text(
        """import os
from pathlib import Path

Path(os.environ["FAKE_SITECUSTOMIZE_MARKER"]).write_text(
    "loaded", encoding="utf-8"
)
""",
        encoding="utf-8",
    )

    python_dispatcher = tmp_path / "python-dispatcher.py"
    python_dispatcher.write_text(
        """import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit


arguments = sys.argv[1:]
if arguments[:3] == ["-I", "-B", "-S"]:
    helper_arguments = arguments[3:]
elif arguments[:2] == ["-I", "-S"]:
    helper_arguments = arguments[2:]
else:
    helper_arguments = arguments
is_http_request = (
    len(helper_arguments) >= 5
    and helper_arguments[0].endswith("bitbucket-cloud-api.py")
    and helper_arguments[1] == "request"
)
if not is_http_request:
    real_python = os.environ["FAKE_REAL_PYTHON"]
    os.execv(real_python, [real_python, *arguments])

helper_path = helper_arguments[0]
spec = importlib.util.spec_from_file_location("bitbucket_cloud_api_under_test", helper_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class _FakeResponse:
    def __init__(self, response_spec):
        self.status = response_spec.get("status", 200)
        self.reason = response_spec.get("reason", "OK")
        body = response_spec.get("body", {})
        if isinstance(body, str):
            self._body = body.encode("utf-8")
        else:
            self._body = json.dumps(body, ensure_ascii=False).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def close(self):
        return None


class _FakeHTTPSConnection:
    def __init__(self, host, port=None, timeout=None, **_kwargs):
        if os.environ.get("FAKE_REQUIRE_PROXY_AWARE") == "1":
            raise AssertionError("direct HTTPS transport bypassed HTTPS_PROXY")
        self.host = host
        self.port = port
        self.timeout = timeout
        self._response = None

    def request(self, method, target, body=None, headers=None, **_kwargs):
        request_error = os.environ.get("FAKE_BITBUCKET_REQUEST_ERROR", "")
        if request_error:
            raise module.http.client.BadStatusLine(request_error)
        authority = self.host
        if self.port not in (None, 443):
            authority = f"{authority}:{self.port}"
        url = f"https://{authority}{target}"
        responses = json.loads(os.environ["FAKE_HTTP_RESPONSES"])
        if url not in responses:
            raise AssertionError(f"unexpected URL: {url}")
        rendered_body = body.decode("utf-8") if isinstance(body, bytes) else body or ""
        record = {
            "host": self.host,
            "port": self.port,
            "timeout": self.timeout,
            "method": method,
            "target": target,
            "headers": dict(headers or {}),
            "body": rendered_body,
        }
        with open(os.environ["FAKE_HTTP_LOG"], "a", encoding="utf-8") as log:
            log.write(json.dumps(record, ensure_ascii=False) + "\\n")
        self._response = _FakeResponse(responses[url])

    def getresponse(self):
        return self._response

    def close(self):
        return None


def _open_request(request, timeout, redirect_handlers):
    request_error = os.environ.get("FAKE_BITBUCKET_REQUEST_ERROR", "")
    if request_error:
        raise module.http.client.BadStatusLine(request_error)
    proxy = os.environ.get("HTTPS_PROXY", "")
    if os.environ.get("FAKE_REQUIRE_PROXY_AWARE") == "1" and not proxy:
        raise AssertionError("HTTPS_PROXY was not available to proxy-aware transport")
    url = request.full_url.replace(
        "https://api.bitbucket.org:443/",
        "https://api.bitbucket.org/",
        1,
    )
    responses = json.loads(os.environ["FAKE_HTTP_RESPONSES"])
    if url not in responses:
        raise AssertionError(f"unexpected URL: {url}")
    response_spec = responses[url]
    parsed = urlsplit(request.full_url)
    body = request.data.decode("utf-8") if request.data else ""
    record = {
        "host": parsed.hostname,
        "port": parsed.port or (443 if parsed.scheme == "https" else 80),
        "timeout": timeout,
        "method": request.get_method(),
        "target": parsed.path + (f"?{parsed.query}" if parsed.query else ""),
        "headers": dict(request.header_items()),
        "body": body,
        "proxy": proxy,
    }
    with open(os.environ["FAKE_HTTP_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps(record, ensure_ascii=False) + "\\n")
    status = response_spec.get("status", 200)
    if status in {301, 302, 303, 307, 308}:
        location = response_spec.get("headers", {}).get("Location", "")
        for handler in redirect_handlers:
            if isinstance(handler, urllib.request.HTTPRedirectHandler):
                redirected = handler.redirect_request(
                    request,
                    _FakeResponse(response_spec),
                    status,
                    response_spec.get("reason", "Redirect"),
                    response_spec.get("headers", {}),
                    location,
                )
                if redirected is None:
                    raise urllib.error.HTTPError(
                        request.full_url,
                        status,
                        "redirect rejected",
                        response_spec.get("headers", {}),
                        None,
                    )
                return _open_request(redirected, timeout, ())
        redirected = urllib.request.Request(
            location,
            headers=dict(request.header_items()),
            method="GET",
        )
        return _open_request(redirected, timeout, ())
    return _FakeResponse(response_spec)


def _fake_urlopen(request, timeout=None):
    return _open_request(request, timeout, ())


class _FakeOpener:
    def __init__(self, handlers):
        self.handlers = handlers

    def open(self, request, timeout=None):
        return _open_request(request, timeout, self.handlers)


def _fake_build_opener(*handlers):
    return _FakeOpener(handlers)


module.http.client.HTTPSConnection = _FakeHTTPSConnection
urllib.request.urlopen = _fake_urlopen
urllib.request.build_opener = _fake_build_opener
sys.argv = [helper_path, *helper_arguments[1:]]
try:
    module.main()
except module.HelperError as error:
    print(f"Error: {error}", file=sys.stderr)
    raise SystemExit(1)
""",
        encoding="utf-8",
    )

    fake_python = tmp_path / "python3"
    fake_python.write_text(
        """#!/bin/sh
{
  printf 'python3\\0'
  printf '%s\\0' "$@"
} >> "$FAKE_PROCESS_ARGV_LOG"
if [ "${1-}" = "-I" ] && [ "${2-}" = "-S" ]; then
  exec "$FAKE_REAL_PYTHON" -I -S "$FAKE_PYTHON_DISPATCHER" "$@"
fi
if [ "${1-}" = "-I" ] && [ "${2-}" = "-B" ] && [ "${3-}" = "-S" ]; then
  exec "$FAKE_REAL_PYTHON" -I -B -S "$FAKE_PYTHON_DISPATCHER" "$@"
fi
exec "$FAKE_REAL_PYTHON" "$FAKE_PYTHON_DISPATCHER" "$@"
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    fake_curl = tmp_path / "curl"
    fake_curl.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

url = sys.argv[-1]
with open(os.environ["FAKE_PROCESS_ARGV_LOG"], "ab") as log:
    log.write(b"curl\\0")
    for argument in sys.argv[1:]:
        log.write(argument.encode("utf-8") + b"\\0")

responses = json.loads(os.environ["FAKE_HTTP_RESPONSES"])
if url not in responses:
    print(f"unexpected URL: {url}", file=sys.stderr)
    raise SystemExit(22)

arguments = sys.argv[1:]
headers = {}
for index, argument in enumerate(arguments):
    if argument == "--header":
        name, value = arguments[index + 1].split(":", 1)
        headers[name] = value.lstrip()
    elif argument == "--oauth2-bearer":
        headers["Authorization"] = f"Bearer {arguments[index + 1]}"
    elif argument == "--user":
        headers["X-Fake-Basic-Credentials"] = arguments[index + 1]

body = ""
if "--data" in arguments:
    body = arguments[arguments.index("--data") + 1]
record = {
    "host": "api.bitbucket.org",
    "port": None,
    "timeout": None,
    "method": arguments[arguments.index("--request") + 1],
    "target": url.removeprefix("https://api.bitbucket.org"),
    "headers": headers,
    "body": body,
}
with open(os.environ["FAKE_HTTP_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(record, ensure_ascii=False) + "\\n")

spec = responses[url]
body = spec.get("body", {})
if isinstance(body, str):
    sys.stdout.write(body)
else:
    json.dump(body, sys.stdout, ensure_ascii=False)
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    request_log = tmp_path / "requests.log"
    process_argv_log = tmp_path / "process-argv.log"
    sitecustomize_marker = tmp_path / "sitecustomize-loaded"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path}{os.pathsep}{env['PATH']}",
            "PYTHONPATH": f"{tmp_path}{os.pathsep}{env.get('PYTHONPATH', '')}",
            "BITBUCKET_EMAIL": "developer@example.invalid",
            "BITBUCKET_API_TOKEN": "FAKE_BITBUCKET_API_TOKEN",
            "FAKE_HTTP_LOG": str(request_log),
            "FAKE_HTTP_RESPONSES": json.dumps(response_specs, ensure_ascii=False),
            "FAKE_BITBUCKET_REQUEST_ERROR": request_error,
            "FAKE_PROCESS_ARGV_LOG": str(process_argv_log),
            "FAKE_PYTHON_DISPATCHER": str(python_dispatcher),
            "FAKE_REAL_PYTHON": sys.executable,
            "FAKE_SITECUSTOMIZE_MARKER": str(sitecustomize_marker),
        }
    )
    env.pop("BITBUCKET_TOKEN", None)
    return env, request_log, process_argv_log


def read_http_requests(request_log: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in request_log.read_text(encoding="utf-8").splitlines()
    ]


def skill_source_manifest(skill_root: Path) -> dict[str, tuple[object, ...]]:
    manifest: dict[str, tuple[object, ...]] = {}
    for entry in sorted(skill_root.rglob("*")):
        relative_path = entry.relative_to(skill_root).as_posix()
        metadata = entry.lstat()
        mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISREG(metadata.st_mode):
            digest = hashlib.sha256(entry.read_bytes()).hexdigest()
            manifest[relative_path] = ("file", mode, digest)
        elif stat.S_ISDIR(metadata.st_mode):
            manifest[relative_path] = ("directory", mode)
        elif stat.S_ISLNK(metadata.st_mode):
            manifest[relative_path] = ("symlink", mode, os.readlink(entry))
        else:
            manifest[relative_path] = ("special", mode)
    return manifest


def test_help_describes_commands_and_authentication() -> None:
    completed = run_script("--help")

    assert completed.returncode == 0
    assert "Usage:" in completed.stdout
    assert "bitbucket-cloud-pr.sh [--dry-run] pr-details" in completed.stdout
    assert "find-prs-for-branch" in completed.stdout
    assert "update-comment" in completed.stdout
    assert "update-description" in completed.stdout
    assert completed.stdout.count("# text from stdin") == 3
    assert "BITBUCKET_TOKEN" in completed.stdout
    assert "OAuth 2 access token" in completed.stdout
    assert "Atlassian account email" in completed.stdout


@pytest.mark.parametrize(
    ("arguments", "input_text", "expected_output"),
    [
        pytest.param(
            ("pr-details", "acme", "widget", "42"),
            None,
            (
                "METHOD=GET",
                "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/"
                "pullrequests/42",
            ),
            id="pr-details",
        ),
        pytest.param(
            ("find-prs-for-branch", "acme", "widget", "feature/auth"),
            None,
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
            None,
            (
                "METHOD=GET",
                "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/"
                "pullrequests/42/comments",
            ),
            id="read-comments",
        ),
        pytest.param(
            ("post-comment", "acme", "widget", "42"),
            "QA passed on staging",
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
            ),
            "Updated PR description",
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
            None,
            (
                "METHOD=POST",
                "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/"
                "pullrequests/42/merge",
            ),
            id="merge",
        ),
        pytest.param(
            ("merge-status", "acme", "widget", "42", "task-7"),
            None,
            (
                "METHOD=GET",
                "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/"
                "pullrequests/42/merge/task-status/task-7",
            ),
            id="merge-status",
        ),
    ],
)
def test_dry_run_reports_request_without_calling_bitbucket(
    arguments: tuple[str, ...],
    input_text: str | None,
    expected_output: tuple[str, ...],
) -> None:
    completed = run_script("--dry-run", *arguments, input_text=input_text)

    assert completed.returncode == 0
    for expected in expected_output:
        assert expected in completed.stdout


def test_dry_run_posts_inline_comment_with_repository_relative_anchor() -> None:
    completed = run_script(
        "--dry-run",
        "post-comment",
        "acme",
        "widget",
        "42",
        "src/widget.py",
        "17",
        input_text="Please handle the empty state",
    )

    assert completed.returncode == 0
    assert "METHOD=POST" in completed.stdout
    assert (
        "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/"
        "pullrequests/42/comments"
    ) in completed.stdout
    _, separator, raw_body = completed.stdout.partition("BODY=")
    assert separator == "BODY="
    assert json.loads(raw_body) == {
        "content": {"raw": "Please handle the empty state"},
        "inline": {"path": "src/widget.py", "to": 17},
    }


def test_dry_run_updates_existing_comment_body() -> None:
    completed = run_script(
        "--dry-run",
        "update-comment",
        "acme",
        "widget",
        "42",
        "101",
        input_text="Updated review comment",
    )

    assert completed.returncode == 0
    assert "METHOD=PUT" in completed.stdout
    assert (
        "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/"
        "pullrequests/42/comments/101"
    ) in completed.stdout
    _, separator, raw_body = completed.stdout.partition("BODY=")
    assert separator == "BODY="
    assert json.loads(raw_body) == {
        "content": {"raw": "Updated review comment"}
    }


@pytest.mark.parametrize(
    ("file_path", "line", "expected_error"),
    [
        pytest.param(
            "/src/widget.py",
            "17",
            "repository-relative",
            id="absolute-path",
        ),
        pytest.param(
            "src/widget.py\nother.py",
            "17",
            "control characters",
            id="path-control",
        ),
        pytest.param(
            "src/widget.py",
            "0",
            "positive decimal integer",
            id="zero-line",
        ),
    ],
)
def test_inline_comment_rejects_invalid_anchor(
    file_path: str,
    line: str,
    expected_error: str,
) -> None:
    completed = run_script(
        "--dry-run",
        "post-comment",
        "acme",
        "widget",
        "42",
        file_path,
        line,
        input_text="Review comment",
    )

    assert completed.returncode != 0
    assert expected_error in completed.stderr
    assert "BODY=" not in completed.stdout


def test_update_comment_rejects_invalid_comment_id() -> None:
    completed = run_script(
        "--dry-run",
        "update-comment",
        "acme",
        "widget",
        "42",
        "0",
        input_text="Updated review comment",
    )

    assert completed.returncode != 0
    assert "positive decimal integer" in completed.stderr
    assert "BODY=" not in completed.stdout


def test_dry_run_does_not_expose_token_values() -> None:
    env = os.environ.copy()
    env["BITBUCKET_TOKEN"] = "FAKE_BITBUCKET_TOKEN"

    completed = run_script(
        "--dry-run", "pr-details", "acme", "widget", "42", env=env
    )

    assert completed.returncode == 0
    assert "FAKE_BITBUCKET_TOKEN" not in completed.stdout
    assert "FAKE_BITBUCKET_TOKEN" not in completed.stderr


def test_helper_ignores_untrusted_python_startup_hooks(tmp_path: Path) -> None:
    env, _, process_argv_log = fake_http_environment(tmp_path, {})
    marker = Path(env["FAKE_SITECUSTOMIZE_MARKER"])

    completed = run_script(
        "--dry-run", "pr-details", "acme", "widget", "42", env=env
    )

    assert completed.returncode == 0
    assert not marker.exists()
    process_argv = process_argv_log.read_bytes()
    assert b"-I\0-B\0-S\0" in process_argv


def test_authenticated_request_honors_runner_https_proxy(tmp_path: Path) -> None:
    url = (
        "https://api.bitbucket.org/2.0/repositories/acme/widget/"
        "pullrequests/42"
    )
    env, request_log, _ = fake_http_environment(tmp_path, {url: {"id": 42}})
    env["HTTPS_PROXY"] = "http://127.0.0.1:1080"
    env["FAKE_REQUIRE_PROXY_AWARE"] = "1"

    completed = run_script("pr-details", "acme", "widget", "42", env=env)

    assert completed.returncode == 0
    assert read_http_requests(request_log)[0]["proxy"] == env["HTTPS_PROXY"]


def test_authenticated_inline_comment_posts_anchor_and_stdin_body(
    tmp_path: Path,
) -> None:
    url = (
        "https://api.bitbucket.org/2.0/repositories/acme/widget/"
        "pullrequests/42/comments"
    )
    env, request_log, _ = fake_http_environment(tmp_path, {url: {"id": 101}})

    completed = run_script(
        "post-comment",
        "acme",
        "widget",
        "42",
        "src/widget.py",
        "17",
        env=env,
        input_text="Please handle the empty state",
    )

    assert completed.returncode == 0
    request = read_http_requests(request_log)[0]
    assert request["method"] == "POST"
    assert request["target"].endswith("/pullrequests/42/comments")
    assert json.loads(str(request["body"])) == {
        "content": {"raw": "Please handle the empty state"},
        "inline": {"path": "src/widget.py", "to": 17},
    }


def test_authenticated_comment_update_targets_comment_and_uses_stdin_body(
    tmp_path: Path,
) -> None:
    url = (
        "https://api.bitbucket.org/2.0/repositories/acme/widget/"
        "pullrequests/42/comments/101"
    )
    env, request_log, _ = fake_http_environment(tmp_path, {url: {"id": 101}})

    completed = run_script(
        "update-comment",
        "acme",
        "widget",
        "42",
        "101",
        env=env,
        input_text="Updated review comment",
    )

    assert completed.returncode == 0
    request = read_http_requests(request_log)[0]
    assert request["method"] == "PUT"
    assert request["target"].endswith("/pullrequests/42/comments/101")
    assert json.loads(str(request["body"])) == {
        "content": {"raw": "Updated review comment"}
    }


@pytest.mark.parametrize(
    "redirect_target",
    [
        pytest.param(
            "https://credentials.example.invalid/stolen",
            id="cross-origin",
        ),
        pytest.param(
            "http://api.bitbucket.org/2.0/repositories/acme/widget/"
            "pullrequests/42",
            id="https-downgrade",
        ),
    ],
)
def test_authenticated_request_rejects_redirect_without_forwarding_credentials(
    tmp_path: Path,
    redirect_target: str,
) -> None:
    initial_url = (
        "https://api.bitbucket.org/2.0/repositories/acme/widget/"
        "pullrequests/42"
    )
    env, request_log, _ = fake_http_environment(
        tmp_path,
        {redirect_target: {"id": "redirected"}},
        redirects={initial_url: redirect_target},
    )

    completed = run_script("pr-details", "acme", "widget", "42", env=env)

    assert completed.returncode != 0
    requests = read_http_requests(request_log)
    assert len(requests) == 1
    assert requests[0]["host"] == "api.bitbucket.org"
    assert "FAKE_BITBUCKET_API_TOKEN" not in completed.stdout
    assert "FAKE_BITBUCKET_API_TOKEN" not in completed.stderr


@pytest.mark.parametrize(
    ("task_id", "encoded_task_id"),
    [
        pytest.param(
            "task 7+zăpadă;v=1",
            "task%207%2Bz%C4%83pad%C4%83%3Bv%3D1",
            id="utf8-and-reserved-characters",
        ),
        pytest.param("a" * 255, "a" * 255, id="maximum-utf8-byte-length"),
    ],
)
def test_dry_run_encodes_bounded_opaque_task_identifier_as_one_segment(
    task_id: str, encoded_task_id: str
) -> None:
    completed = run_script(
        "--dry-run", "merge-status", "acme", "widget", "42", task_id
    )

    assert completed.returncode == 0
    assert completed.stdout.endswith(f"/merge/task-status/{encoded_task_id}\n")


@pytest.mark.parametrize(
    ("command", "body_key"),
    [
        pytest.param("post-comment", "content", id="comment"),
        pytest.param("update-description", "description", id="description"),
    ],
)
def test_dry_run_json_body_preserves_controls_and_unicode(
    command: str, body_key: str
) -> None:
    text = "Review\bpage\fcontrol:\x01; Unicode: zăpadă 雪"

    completed = run_script(
        "--dry-run", command, "acme", "widget", "42", input_text=text
    )

    assert completed.returncode == 0
    _, separator, raw_body = completed.stdout.partition("BODY=")
    assert separator == "BODY="
    raw_body = raw_body.removesuffix("\n")
    parsed_body = json.loads(raw_body)
    if body_key == "content":
        assert parsed_body == {"content": {"raw": text}}
    else:
        assert parsed_body == {"description": text}
    assert "\\b" in raw_body
    assert "\\f" in raw_body
    assert "\\u0001" in raw_body


def test_dry_run_query_uses_utf8_percent_encoding() -> None:
    branch_name = 'feature/naïve 雪 "quoted"'
    query = (
        'source.branch.name = "feature/naïve 雪 \\"quoted\\"" '
        'AND state = "OPEN"'
    )
    expected_url = (
        "https://api.bitbucket.org/2.0/repositories/acme/widget/pullrequests?"
        + urlencode({"q": query})
    )

    completed = run_script(
        "--dry-run",
        "find-prs-for-branch",
        "acme",
        "widget",
        branch_name,
    )

    assert completed.returncode == 0
    assert f"URL={expected_url}\n" in completed.stdout


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        pytest.param("pr-details", (".", "widget", "42"), id="workspace-dot"),
        pytest.param("pr-details", ("..", "widget", "42"), id="workspace-dot-dot"),
        pytest.param(
            "pr-details", ("acme/redirect", "widget", "42"), id="workspace-slash"
        ),
        pytest.param(
            "pr-details", ("acme%2Fredirect", "widget", "42"), id="encoded-slash"
        ),
        pytest.param(
            "pr-details", ("acme%252Fredirect", "widget", "42"), id="double-encoded-slash"
        ),
        pytest.param(
            "pr-details", ("acme", "widget\\redirect", "42"), id="repo-backslash"
        ),
        pytest.param(
            "pr-details", ("acme", "widget?admin=true", "42"), id="repo-query"
        ),
        pytest.param(
            "pr-details", ("acme", "widget#fragment", "42"), id="repo-fragment"
        ),
        pytest.param("pr-details", ("acmé", "widget", "42"), id="unicode-workspace"),
        pytest.param("pr-details", ("acme", "wídget", "42"), id="unicode-repo"),
        pytest.param("pr-details", ("ACME", "widget", "42"), id="uppercase-workspace"),
        pytest.param("pr-details", ("acme", "-widget", "42"), id="leading-repo-hyphen"),
        pytest.param("pr-details", ("acme", "widget-", "42"), id="trailing-repo-hyphen"),
        pytest.param("pr-details", ("acme", "wid--get", "42"), id="repeated-repo-hyphen"),
        pytest.param("pr-details", ("acme", "w" * 63, "42"), id="long-repo"),
        pytest.param("pr-details", ("acme", "widget", "0"), id="zero-pr-id"),
        pytest.param("pr-details", ("acme", "widget", "-1"), id="negative-pr-id"),
        pytest.param("pr-details", ("acme", "widget", "1/merge"), id="path-pr-id"),
        pytest.param(
            "merge-status", ("acme", "widget", "42", ""), id="empty-task-id"
        ),
        pytest.param(
            "merge-status", ("acme", "widget", "42", "."), id="task-dot-segment"
        ),
        pytest.param(
            "merge-status", ("acme", "widget", "42", ".."), id="task-dot-dot-segment"
        ),
        pytest.param(
            "merge-status", ("acme", "widget", "42", "task/7"), id="task-slash"
        ),
        pytest.param(
            "merge-status", ("acme", "widget", "42", "task\\7"), id="task-backslash"
        ),
        pytest.param(
            "merge-status", ("acme", "widget", "42", "task?7"), id="task-query"
        ),
        pytest.param(
            "merge-status", ("acme", "widget", "42", "task#7"), id="task-fragment"
        ),
        pytest.param(
            "merge-status", ("acme", "widget", "42", "task:7"), id="task-colon"
        ),
        pytest.param(
            "merge-status", ("acme", "widget", "42", "task@7"), id="task-at-sign"
        ),
        pytest.param(
            "merge-status", ("acme", "widget", "42", "task%2F7"), id="encoded-task-slash"
        ),
        pytest.param(
            "merge-status",
            ("acme", "widget", "42", "task%252F7"),
            id="double-encoded-task-slash",
        ),
        pytest.param(
            "merge-status", ("acme", "widget", "42", "%2E%2E"), id="encoded-task-dot-segment"
        ),
        pytest.param(
            "merge-status", ("acme", "widget", "42", "task\n7"), id="task-control"
        ),
        pytest.param(
            "merge-status", ("acme", "widget", "42", "task\x7f7"), id="task-delete-control"
        ),
        pytest.param(
            "merge-status", ("acme", "widget", "42", "a" * 256), id="overlong-task-id"
        ),
    ],
)
def test_dry_run_rejects_noncanonical_path_identifiers(
    command: str, arguments: tuple[str, ...]
) -> None:
    completed = run_script("--dry-run", command, *arguments)

    assert completed.returncode != 0
    assert "Error:" in completed.stderr


def test_read_comments_combines_validated_pages_without_exposing_credentials(
    tmp_path: Path,
) -> None:
    first_url = (
        "https://api.bitbucket.org/2.0/repositories/acme/widget/"
        "pullrequests/42/comments"
    )
    second_url = f"{first_url}?page=2"
    env, request_log, _ = fake_http_environment(
        tmp_path,
        {
            first_url: {
                "size": 2,
                "page": 1,
                "pagelen": 1,
                "next": second_url,
                "values": [{"id": 101, "content": {"raw": "Primul: zăpadă"}}],
            },
            second_url: {
                "size": 2,
                "page": 2,
                "pagelen": 1,
                "previous": first_url,
                "values": [{"id": 102, "content": {"raw": "Al doilea: 雪"}}],
            },
        },
    )
    env["PYTHONIOENCODING"] = "ascii"

    completed = run_script("read-comments", "acme", "widget", "42", env=env)

    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    assert [comment["id"] for comment in result["values"]] == [101, 102]
    assert [comment["content"]["raw"] for comment in result["values"]] == [
        "Primul: zăpadă",
        "Al doilea: 雪",
    ]
    assert "next" not in result
    assert [request["target"] for request in read_http_requests(request_log)] == [
        "/2.0/repositories/acme/widget/pullrequests/42/comments",
        "/2.0/repositories/acme/widget/pullrequests/42/comments?page=2",
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
        pytest.param(
            "http://api.bitbucket.org/2.0/repositories/acme/widget/"
            "pullrequests/42/comments?page=2",
            id="http-scheme",
        ),
        pytest.param(
            "https://api.bitbucket.org:444/2.0/repositories/acme/widget/"
            "pullrequests/42/comments?page=2",
            id="nondefault-port",
        ),
        pytest.param(
            "https://api.bitbucket.org@credentials.example/2.0/repositories/"
            "acme/widget/pullrequests/42/comments?page=2",
            id="userinfo-host-confusion",
        ),
        pytest.param(
            "https://api.bitbucket.org/2.0/repositories/acme/other/../widget/"
            "pullrequests/42/comments?page=2",
            id="dot-segment",
        ),
        pytest.param(
            "https://api.bitbucket.org/2.0/repositories/acme%2Fwidget/"
            "pullrequests/42/comments?page=2",
            id="encoded-path-delimiter",
        ),
        pytest.param(
            "https://api.bitbucket.org/2.0/repositories/acme/widget/"
            "pullrequests/42/comments?page=2#fragment",
            id="fragment",
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
    env, request_log, _ = fake_http_environment(
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
    assert [request["target"] for request in read_http_requests(request_log)] == [
        "/2.0/repositories/acme/widget/pullrequests/42/comments"
    ]
    assert "FAKE_BITBUCKET_API_TOKEN" not in completed.stdout
    assert "FAKE_BITBUCKET_API_TOKEN" not in completed.stderr


def test_read_comments_accepts_explicit_default_https_port(tmp_path: Path) -> None:
    first_url = (
        "https://api.bitbucket.org/2.0/repositories/acme/widget/"
        "pullrequests/42/comments"
    )
    second_network_url = f"{first_url}?page=2"
    second_response_url = second_network_url.replace(
        "api.bitbucket.org", "api.bitbucket.org:443"
    )
    env, request_log, _ = fake_http_environment(
        tmp_path,
        {
            first_url: {
                "size": 2,
                "next": second_response_url,
                "values": [{"id": 101}],
            },
            second_network_url: {
                "size": 2,
                "values": [{"id": 102}],
            },
        },
    )

    completed = run_script("read-comments", "acme", "widget", "42", env=env)

    assert completed.returncode == 0
    assert [comment["id"] for comment in json.loads(completed.stdout)["values"]] == [
        101,
        102,
    ]
    assert len(read_http_requests(request_log)) == 2


def test_malicious_path_is_rejected_before_authenticated_request(
    tmp_path: Path,
) -> None:
    env, request_log, _ = fake_http_environment(tmp_path, {})

    completed = run_script(
        "pr-details", "acme%2Fcredentials.example", "widget", "42", env=env
    )

    assert completed.returncode != 0
    assert "Error:" in completed.stderr
    assert not request_log.exists()
    assert "FAKE_BITBUCKET_API_TOKEN" not in completed.stdout
    assert "FAKE_BITBUCKET_API_TOKEN" not in completed.stderr


@pytest.mark.parametrize("source_kind", ["canonical", "installed"])
def test_repeated_dispatcher_requests_preserve_skill_source_manifest(
    tmp_path: Path, source_kind: str
) -> None:
    if source_kind == "canonical":
        skill_root = SKILL_ROOT
    else:
        skill_root = tmp_path / "installed" / "bitbucket-pr-management"
        shutil.copytree(
            SKILL_ROOT,
            skill_root,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    script = skill_root / "scripts" / "bitbucket-cloud-pr.sh"
    url = (
        "https://api.bitbucket.org/2.0/repositories/acme/widget/"
        "pullrequests/42"
    )
    env, request_log, _ = fake_http_environment(tmp_path, {url: {"id": 42}})
    original_manifest = skill_source_manifest(skill_root)
    assert not any(
        path.endswith(".pyc") or "__pycache__" in Path(path).parts
        for path in original_manifest
    )

    for _ in range(2):
        completed = run_script(
            "pr-details", "acme", "widget", "42", env=env, script=script
        )
        assert completed.returncode == 0

    assert len(read_http_requests(request_log)) == 2
    assert skill_source_manifest(skill_root) == original_manifest


@pytest.mark.parametrize(
    ("command", "url_suffix", "expected_method", "body_shape"),
    [
        pytest.param(
            "post-comment", "/comments", "POST", "comment", id="comment"
        ),
        pytest.param(
            "update-description", "", "PUT", "description", id="description"
        ),
    ],
)
def test_authenticated_request_keeps_credentials_and_body_out_of_process_argv(
    tmp_path: Path,
    command: str,
    url_suffix: str,
    expected_method: str,
    body_shape: str,
) -> None:
    url = (
        "https://api.bitbucket.org/2.0/repositories/acme/widget/"
        f"pullrequests/42{url_suffix}"
    )
    env, request_log, process_argv_log = fake_http_environment(
        tmp_path, {url: {"id": 101}}
    )
    mutation_text = "PROCESS_ARGV_SENTINEL_ß\b\f\x01"

    completed = run_script(
        command,
        "acme",
        "widget",
        "42",
        env=env,
        input_text=mutation_text,
    )

    assert completed.returncode == 0
    assert mutation_text not in completed.args
    requests = read_http_requests(request_log)
    assert len(requests) == 1
    assert requests[0]["host"] == "api.bitbucket.org"
    assert requests[0]["port"] == 443
    assert requests[0]["method"] == expected_method
    if body_shape == "comment":
        expected_body = {"content": {"raw": mutation_text}}
    else:
        expected_body = {"description": mutation_text}
    assert json.loads(str(requests[0]["body"])) == expected_body
    process_argv = process_argv_log.read_bytes()
    for sensitive_value in (
        "developer@example.invalid",
        "FAKE_BITBUCKET_API_TOKEN",
        mutation_text,
        json.dumps(expected_body, ensure_ascii=False, separators=(",", ":")),
    ):
        assert sensitive_value.encode("utf-8") not in process_argv
    assert "FAKE_BITBUCKET_API_TOKEN" not in completed.stdout
    assert "FAKE_BITBUCKET_API_TOKEN" not in completed.stderr


@pytest.mark.parametrize("command", ["post-comment", "update-description"])
def test_mutation_commands_reject_positional_body(command: str) -> None:
    completed = run_script(
        "--dry-run",
        command,
        "acme",
        "widget",
        "42",
        "body-must-not-be-an-argument",
        input_text="stdin body",
    )

    assert completed.returncode == 2
    assert "body-must-not-be-an-argument" not in completed.stdout
    assert "body-must-not-be-an-argument" not in completed.stderr


def test_oauth_request_keeps_access_token_out_of_child_argv(tmp_path: Path) -> None:
    url = (
        "https://api.bitbucket.org/2.0/repositories/acme/widget/"
        "pullrequests/42"
    )
    env, request_log, process_argv_log = fake_http_environment(
        tmp_path, {url: {"id": 42}}
    )
    oauth_token = "FAKE_BITBUCKET_OAUTH_PROCESS_ARGV_SENTINEL"
    env["BITBUCKET_TOKEN"] = oauth_token
    env.pop("BITBUCKET_EMAIL", None)
    env.pop("BITBUCKET_API_TOKEN", None)

    completed = run_script("pr-details", "acme", "widget", "42", env=env)

    assert completed.returncode == 0
    request = read_http_requests(request_log)[0]
    assert request["headers"]["Authorization"] == f"Bearer {oauth_token}"
    assert oauth_token.encode("ascii") not in process_argv_log.read_bytes()
    assert oauth_token not in completed.stdout
    assert oauth_token not in completed.stderr


def test_oauth_token_with_header_controls_fails_without_exposure(
    tmp_path: Path,
) -> None:
    url = (
        "https://api.bitbucket.org/2.0/repositories/acme/widget/"
        "pullrequests/42"
    )
    env, request_log, _ = fake_http_environment(tmp_path, {url: {"id": 42}})
    invalid_token = "FAKE_OAUTH_HEADER\r\nINJECTED_HEADER"
    env["BITBUCKET_TOKEN"] = invalid_token
    env.pop("BITBUCKET_EMAIL", None)
    env.pop("BITBUCKET_API_TOKEN", None)

    completed = run_script("pr-details", "acme", "widget", "42", env=env)

    assert completed.returncode != 0
    assert not request_log.exists()
    assert invalid_token not in completed.stdout
    assert invalid_token not in completed.stderr
    assert "INJECTED_HEADER" not in completed.stderr


def test_http_protocol_exception_does_not_echo_response_data(tmp_path: Path) -> None:
    url = (
        "https://api.bitbucket.org/2.0/repositories/acme/widget/"
        "pullrequests/42"
    )
    response_sentinel = "FAKE_UNTRUSTED_BITBUCKET_STATUS_LINE"
    env, _, _ = fake_http_environment(
        tmp_path,
        {url: {"id": 42}},
        request_error=response_sentinel,
    )

    completed = run_script("pr-details", "acme", "widget", "42", env=env)

    assert completed.returncode != 0
    assert "Bitbucket API request failed" in completed.stderr
    assert response_sentinel not in completed.stdout
    assert response_sentinel not in completed.stderr


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
