"""Security and behavior tests for GitHub App token minting."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    REPO_ROOT
    / "skills"
    / "integrations"
    / "github-bot-interaction"
    / "scripts"
    / "get-bot-gh-token.sh"
)


def run_script(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def fake_http_environment(
    tmp_path: Path,
    *,
    response_body: dict[str, object],
    response_status: int = 201,
    response_reason: str = "Created",
    request_error: str = "",
    redirect_location: str = "",
) -> tuple[dict[str, str], Path, Path]:
    private_key = tmp_path / "github-app.pem"
    pem_begin = "-----BE" + "GIN RSA PRIVATE KEY-----"
    pem_end = "-----E" + "ND RSA PRIVATE KEY-----"
    private_key.write_text(
        f"{pem_begin}\nFAKE_KEY_MATERIAL\n{pem_end}\n",
        encoding="utf-8",
    )

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
        """import http.client
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit


arguments = sys.argv[1:]
command_arguments = arguments[2:] if arguments[:2] == ["-I", "-S"] else arguments
is_http_exchange = (
    len(command_arguments) == 2
    and command_arguments[0] == "-c"
    and "GH_BOT_HTTP_INSTALLATION_ID" in command_arguments[1]
)
if not is_http_exchange:
    real_python = os.environ["FAKE_REAL_PYTHON"]
    os.execv(real_python, [real_python, *arguments])


class _FakeResponse:
    def __init__(self, status, reason, body):
        self.status = status
        self.reason = reason
        self._body = body

    def read(self):
        return self._body.encode("utf-8")

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

    def request(self, method, target, body=None, headers=None, **_kwargs):
        request_error = os.environ.get("FAKE_GITHUB_REQUEST_ERROR", "")
        if request_error:
            raise http.client.BadStatusLine(request_error)
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
        with open(os.environ["FAKE_GITHUB_HTTP_LOG"], "a", encoding="utf-8") as log:
            log.write(json.dumps(record) + "\\n")

    def getresponse(self):
        return _FakeResponse(
            int(os.environ["FAKE_GITHUB_RESPONSE_STATUS"]),
            os.environ["FAKE_GITHUB_RESPONSE_REASON"],
            os.environ["FAKE_GITHUB_RESPONSE_BODY"],
        )

    def close(self):
        return None


def _open_request(request, timeout, redirect_handlers):
    request_error = os.environ.get("FAKE_GITHUB_REQUEST_ERROR", "")
    if request_error:
        raise http.client.BadStatusLine(request_error)
    proxy = os.environ.get("HTTPS_PROXY", "")
    if os.environ.get("FAKE_REQUIRE_PROXY_AWARE") == "1" and not proxy:
        raise AssertionError("HTTPS_PROXY was not available to proxy-aware transport")
    parsed = urlsplit(request.full_url)
    headers = {name.title(): value for name, value in request.header_items()}
    body = request.data.decode("utf-8") if request.data else ""
    record = {
        "host": parsed.hostname,
        "port": parsed.port or (443 if parsed.scheme == "https" else 80),
        "timeout": timeout,
        "method": request.get_method(),
        "target": parsed.path + (f"?{parsed.query}" if parsed.query else ""),
        "headers": headers,
        "body": body,
        "proxy": proxy,
    }
    with open(os.environ["FAKE_GITHUB_HTTP_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps(record) + "\\n")
    redirect_location = os.environ.get("FAKE_GITHUB_REDIRECT_LOCATION", "")
    status = int(os.environ["FAKE_GITHUB_RESPONSE_STATUS"])
    reason = os.environ["FAKE_GITHUB_RESPONSE_REASON"]
    response_body = os.environ["FAKE_GITHUB_RESPONSE_BODY"]
    if redirect_location and request.full_url.startswith("https://api.github.com/"):
        for handler in redirect_handlers:
            if isinstance(handler, urllib.request.HTTPRedirectHandler):
                redirected = handler.redirect_request(
                    request,
                    _FakeResponse(status, reason, response_body),
                    status,
                    reason,
                    {"Location": redirect_location},
                    redirect_location,
                )
                if redirected is None:
                    raise urllib.error.HTTPError(
                        request.full_url,
                        status,
                        "redirect rejected",
                        {"Location": redirect_location},
                        None,
                    )
                return _open_request(redirected, timeout, ())
        redirected = urllib.request.Request(
            redirect_location,
            headers=dict(request.header_items()),
            method="GET",
        )
        return _open_request(redirected, timeout, ())
    if redirect_location:
        status = 201
        reason = "Created"
        response_body = os.environ["FAKE_GITHUB_REDIRECT_BODY"]
    return _FakeResponse(status, reason, response_body)


def _fake_urlopen(request, timeout=None):
    return _open_request(request, timeout, ())


class _FakeOpener:
    def __init__(self, handlers):
        self.handlers = handlers

    def open(self, request, timeout=None):
        return _open_request(request, timeout, self.handlers)


def _fake_build_opener(*handlers):
    return _FakeOpener(handlers)


http.client.HTTPSConnection = _FakeHTTPSConnection
urllib.request.urlopen = _fake_urlopen
urllib.request.build_opener = _fake_build_opener
code = compile(command_arguments[1], "<github-token-http-helper>", "exec")
exec(code, {"__name__": "__main__"})
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
exec "$FAKE_REAL_PYTHON" "$FAKE_PYTHON_DISPATCHER" "$@"
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    fake_openssl = tmp_path / "openssl"
    fake_openssl.write_text(
        """#!/bin/sh
{
  printf 'openssl\\0'
  printf '%s\\0' "$@"
} >> "$FAKE_PROCESS_ARGV_LOG"
/bin/cat >/dev/null
printf 'fake-signature'
""",
        encoding="utf-8",
    )
    fake_openssl.chmod(0o755)

    fake_curl = tmp_path / "curl"
    fake_curl.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ["FAKE_PROCESS_ARGV_LOG"], "ab") as log:
    log.write(b"curl\\0")
    for argument in sys.argv[1:]:
        log.write(argument.encode("utf-8") + b"\\0")

arguments = sys.argv[1:]
headers = {}
for index, argument in enumerate(arguments):
    if argument == "-H":
        name, value = arguments[index + 1].split(":", 1)
        headers[name] = value.lstrip()
record = {
    "host": "api.github.com",
    "port": None,
    "timeout": None,
    "method": "POST",
    "target": arguments[-1].removeprefix("https://api.github.com"),
    "headers": headers,
    "body": "",
}
with open(os.environ["FAKE_GITHUB_HTTP_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(record) + "\\n")

sys.stdout.write(os.environ["FAKE_GITHUB_RESPONSE_BODY"])
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
            "GH_BOT_APP_ID": "12345",
            "GH_BOT_INSTALLATION_ID": "67890",
            "GH_BOT_PRIVATE_KEY_PATH": str(private_key),
            "FAKE_GITHUB_RESPONSE_BODY": json.dumps(response_body),
            "FAKE_GITHUB_RESPONSE_STATUS": str(response_status),
            "FAKE_GITHUB_RESPONSE_REASON": response_reason,
            "FAKE_GITHUB_REQUEST_ERROR": request_error,
            "FAKE_GITHUB_REDIRECT_LOCATION": redirect_location,
            "FAKE_GITHUB_REDIRECT_BODY": json.dumps(
                {"token": "FAKE_REDIRECTED_GITHUB_TOKEN"}
            ),
            "FAKE_GITHUB_HTTP_LOG": str(request_log),
            "FAKE_PROCESS_ARGV_LOG": str(process_argv_log),
            "FAKE_PYTHON_DISPATCHER": str(python_dispatcher),
            "FAKE_REAL_PYTHON": sys.executable,
            "FAKE_SITECUSTOMIZE_MARKER": str(sitecustomize_marker),
        }
    )
    return env, request_log, process_argv_log


def decode_jwt_payload(jwt: str) -> dict[str, object]:
    encoded_payload = jwt.split(".")[1]
    padding = "=" * (-len(encoded_payload) % 4)
    return json.loads(base64.urlsafe_b64decode(encoded_payload + padding))


def test_token_exchange_keeps_jwt_out_of_spawned_process_arguments(
    tmp_path: Path,
) -> None:
    token = "FAKE_GITHUB_INSTALLATION_TOKEN"
    env, request_log, process_argv_log = fake_http_environment(
        tmp_path, response_body={"token": token}
    )

    completed = run_script(env)

    assert completed.returncode == 0
    assert completed.stdout == f"{token}\n"
    request = json.loads(request_log.read_text(encoding="utf-8"))
    assert request["host"] == "api.github.com"
    assert request["port"] == 443
    assert request["method"] == "POST"
    assert request["target"] == "/app/installations/67890/access_tokens"
    assert request["headers"]["User-Agent"] == "ai-skills-github-app-token-helper/1"
    jwt = request["headers"]["Authorization"].removeprefix("Bearer ")
    assert len(jwt.split(".")) == 3
    payload = decode_jwt_payload(jwt)
    assert payload["iss"] == "12345"
    assert payload["exp"] - payload["iat"] == 540

    process_argv = process_argv_log.read_bytes()
    assert b"-I\0-S\0" in process_argv
    assert jwt.encode("ascii") not in process_argv
    assert b"curl\0" not in process_argv
    assert not Path(env["FAKE_SITECUSTOMIZE_MARKER"]).exists()
    assert jwt not in completed.stdout
    assert jwt not in completed.stderr


def test_token_exchange_honors_runner_https_proxy(tmp_path: Path) -> None:
    env, request_log, _ = fake_http_environment(
        tmp_path,
        response_body={"token": "FAKE_GITHUB_INSTALLATION_TOKEN"},
    )
    env["HTTPS_PROXY"] = "http://127.0.0.1:1080"
    env["FAKE_REQUIRE_PROXY_AWARE"] = "1"

    completed = run_script(env)

    assert completed.returncode == 0
    request = json.loads(request_log.read_text(encoding="utf-8"))
    assert request["proxy"] == env["HTTPS_PROXY"]


def read_http_requests(request_log: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in request_log.read_text(encoding="utf-8").splitlines()
    ]


def test_token_exchange_rejects_cross_origin_redirect_without_forwarding_jwt(
    tmp_path: Path,
) -> None:
    env, request_log, _ = fake_http_environment(
        tmp_path,
        response_body={"message": "redirect"},
        response_status=302,
        response_reason="Found",
        redirect_location="https://credentials.example.invalid/stolen",
    )

    completed = run_script(env)

    assert completed.returncode != 0
    requests = read_http_requests(request_log)
    assert len(requests) == 1
    assert requests[0]["host"] == "api.github.com"
    assert "FAKE_REDIRECTED_GITHUB_TOKEN" not in completed.stdout
    assert "FAKE_REDIRECTED_GITHUB_TOKEN" not in completed.stderr


def test_token_exchange_rejects_https_downgrade_without_forwarding_jwt(
    tmp_path: Path,
) -> None:
    env, request_log, _ = fake_http_environment(
        tmp_path,
        response_body={"message": "redirect"},
        response_status=302,
        response_reason="Found",
        redirect_location=(
            "http://api.github.com/app/installations/67890/access_tokens"
        ),
    )

    completed = run_script(env)

    assert completed.returncode != 0
    requests = read_http_requests(request_log)
    assert len(requests) == 1
    assert requests[0]["host"] == "api.github.com"
    assert "FAKE_REDIRECTED_GITHUB_TOKEN" not in completed.stdout
    assert "FAKE_REDIRECTED_GITHUB_TOKEN" not in completed.stderr


def test_jwt_payload_serializes_controls_and_unicode_as_json(tmp_path: Path) -> None:
    env, request_log, _ = fake_http_environment(
        tmp_path, response_body={"token": "FAKE_GITHUB_INSTALLATION_TOKEN"}
    )
    app_id = 'Iv1."quoted"\b\f\x01雪'
    env["GH_BOT_APP_ID"] = app_id

    completed = run_script(env)

    assert completed.returncode == 0
    request = json.loads(request_log.read_text(encoding="utf-8"))
    jwt = request["headers"]["Authorization"].removeprefix("Bearer ")
    assert decode_jwt_payload(jwt)["iss"] == app_id


def test_token_exchange_reports_http_error_without_echoing_response(
    tmp_path: Path,
) -> None:
    response_secret = "FAKE_GITHUB_ERROR_RESPONSE_SECRET"
    env, request_log, _ = fake_http_environment(
        tmp_path,
        response_body={
            "message": "Bad credentials",
            "credential": response_secret,
        },
        response_status=401,
        response_reason="Unauthorized",
    )

    completed = run_script(env)

    assert completed.returncode == 3
    assert "GitHub token exchange returned HTTP 401" in completed.stderr
    assert "Bad credentials" not in completed.stderr
    assert response_secret not in completed.stderr
    request = json.loads(request_log.read_text(encoding="utf-8"))
    jwt = request["headers"]["Authorization"].removeprefix("Bearer ")
    assert jwt not in completed.stdout
    assert jwt not in completed.stderr


def test_non_success_response_cannot_return_token_like_field(tmp_path: Path) -> None:
    rejected_token = "FAKE_REJECTED_GITHUB_TOKEN"
    env, _, _ = fake_http_environment(
        tmp_path,
        response_body={
            "token": rejected_token,
            "message": "Installation access denied",
        },
        response_status=401,
        response_reason="Unauthorized",
    )

    completed = run_script(env)

    assert completed.returncode == 3
    assert "GitHub token exchange returned HTTP 401" in completed.stderr
    assert "Installation access denied" not in completed.stderr
    assert rejected_token not in completed.stdout
    assert rejected_token not in completed.stderr


def test_success_response_without_token_does_not_echo_response_data(
    tmp_path: Path,
) -> None:
    response_secret = "FAKE_GITHUB_SUCCESS_RESPONSE_SECRET"
    env, _, _ = fake_http_environment(
        tmp_path,
        response_body={
            "message": "Unexpected response",
            "credential": response_secret,
        },
    )

    completed = run_script(env)

    assert completed.returncode == 3
    assert "successful response did not contain a usable token" in completed.stderr
    assert "Unexpected response" not in completed.stderr
    assert response_secret not in completed.stdout
    assert response_secret not in completed.stderr


def test_http_protocol_exception_does_not_echo_response_data(tmp_path: Path) -> None:
    response_sentinel = "FAKE_UNTRUSTED_HTTP_STATUS_LINE"
    env, _, _ = fake_http_environment(
        tmp_path,
        response_body={},
        request_error=response_sentinel,
    )

    completed = run_script(env)

    assert completed.returncode != 0
    assert "GitHub token exchange request failed." in completed.stderr
    assert response_sentinel not in completed.stdout
    assert response_sentinel not in completed.stderr
