#!/usr/bin/env python3
"""Encoding, validation, and HTTPS transport for bitbucket-cloud-pr.sh."""

from __future__ import annotations

import base64
import http.client
import json
import os
import posixpath
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import quote, unquote_to_bytes, urlencode, urlsplit, urlunsplit


API_HOST = "api.bitbucket.org"
API_PORT = 443
REPOSITORY_PATH_PREFIX = "/2.0/repositories/"
WORKSPACE_PATTERN = re.compile(r"[a-z0-9_-]+", re.ASCII)
REPOSITORY_SLUG_PATTERN = re.compile(r"[A-Za-z0-9._-]+", re.ASCII)
POSITIVE_INTEGER_PATTERN = re.compile(r"[1-9][0-9]*", re.ASCII)
PERCENT_ESCAPE_PATTERN = re.compile(r"%[0-9A-F]{2}")
MAX_TASK_IDENTIFIER_UTF8_BYTES = 255
FORBIDDEN_PATH_SEGMENT_CHARACTERS = frozenset(":/?#[]@\\%")
VALID_PULL_REQUEST_STATES = frozenset(
    {"OPEN", "MERGED", "DECLINED", "SUPERSEDED"}
)


class HelperError(Exception):
    """A safe error that can be shown without exposing request secrets."""


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: urllib.request.Request,
        response: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> None:
        raise urllib.error.HTTPError(
            request.full_url,
            code,
            "Bitbucket API redirects are disabled",
            headers,
            response,
        )


def read_stdin_text() -> str:
    try:
        return sys.stdin.buffer.read().decode("utf-8")
    except UnicodeDecodeError as error:
        raise HelperError(f"Input must be valid UTF-8: {error}") from error


def write_text(value: str) -> None:
    sys.stdout.buffer.write(value.encode("utf-8"))


def encode_slug(kind: str) -> None:
    value = read_stdin_text()
    if kind == "workspace":
        pattern = WORKSPACE_PATTERN
        description = "lowercase ASCII letters, digits, hyphens, or underscores"
    elif kind == "repository":
        pattern = REPOSITORY_SLUG_PATTERN
        description = "ASCII letters, digits, periods, hyphens, or underscores"
        if len(value) > 62:
            raise HelperError("Repository slug must be at most 62 characters")
        if set(value) != {"-"} and (
            value.startswith("-") or value.endswith("-") or "--" in value
        ):
            raise HelperError("Invalid repository slug hyphen placement")
    else:
        raise HelperError(f"Unknown slug kind: {kind}")

    if value in {".", ".."} or pattern.fullmatch(value) is None:
        raise HelperError(f"Invalid {kind} slug; expected {description}")

    # Encode the validated value as one segment, never as a partially trusted path.
    write_text(quote(value, safe=""))


def validate_positive_integer(kind: str) -> None:
    value = read_stdin_text()
    if POSITIVE_INTEGER_PATTERN.fullmatch(value) is None:
        raise HelperError(f"Invalid {kind}; expected a positive decimal integer")
    write_text(value)


def encode_task_identifier() -> None:
    value = read_stdin_text()
    if not value:
        raise HelperError("Task identifier is required")
    if len(value.encode("utf-8")) > MAX_TASK_IDENTIFIER_UTF8_BYTES:
        raise HelperError(
            "Task identifier must be at most "
            f"{MAX_TASK_IDENTIFIER_UTF8_BYTES} UTF-8 bytes"
        )
    if value in {".", ".."}:
        raise HelperError("Task identifier must not be a dot segment")
    if any(
        ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F
        for character in value
    ):
        raise HelperError("Task identifier must not contain control characters")
    if any(
        character in FORBIDDEN_PATH_SEGMENT_CHARACTERS for character in value
    ):
        raise HelperError("Task identifier must not contain URL delimiters")

    write_text(quote(value, safe="-._~"))


def build_pull_request_query() -> None:
    raw = sys.stdin.buffer.read().split(b"\0")
    if len(raw) != 2:
        raise HelperError("Branch query requires a branch name and state")
    try:
        branch_name, state = (value.decode("utf-8") for value in raw)
    except UnicodeDecodeError as error:
        raise HelperError(f"Query values must be valid UTF-8: {error}") from error
    if not branch_name:
        raise HelperError("Branch name is required")
    if state not in VALID_PULL_REQUEST_STATES:
        allowed = ", ".join(sorted(VALID_PULL_REQUEST_STATES))
        raise HelperError(f"Invalid pull request state; expected one of: {allowed}")

    branch_literal = json.dumps(branch_name, ensure_ascii=False)
    state_literal = json.dumps(state)
    expression = (
        f"source.branch.name = {branch_literal} AND state = {state_literal}"
    )
    write_text(urlencode({"q": expression}, encoding="utf-8", errors="strict"))


def build_json_body(kind: str) -> None:
    value = read_stdin_text()
    if not value:
        raise HelperError(f"{kind.replace('-', ' ').title()} text is required")
    if kind == "comment":
        body = {"content": {"raw": value}}
    elif kind == "description":
        body = {"description": value}
    else:
        raise HelperError(f"Unknown JSON body kind: {kind}")
    write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")))


def build_inline_comment_body(path: str, line: str) -> None:
    """Build a comment body anchored to one line of the pull request diff.

    The comment text arrives on stdin; `path` and `line` are structural
    anchors, never content. `to` targets the line in the destination
    (post-merge) version of the file, which is what a reviewer reads.
    """
    value = read_stdin_text()
    if not value:
        raise HelperError("Comment text is required")
    if not path:
        raise HelperError("Inline comment path is required")
    if path.startswith("/"):
        raise HelperError("Inline comment path must be repository-relative")
    if any(
        ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F
        for character in path
    ):
        raise HelperError("Inline comment path must not contain control characters")
    if POSITIVE_INTEGER_PATTERN.fullmatch(line) is None:
        raise HelperError(
            "Invalid inline comment line; expected a positive decimal integer"
        )
    body = {
        "content": {"raw": value},
        "inline": {"path": path, "to": int(line)},
    }
    write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")))


def validate_percent_escapes(value: str, component: str) -> None:
    index = 0
    while index < len(value):
        if value[index] != "%":
            index += 1
            continue
        escape = value[index : index + 3]
        if PERCENT_ESCAPE_PATTERN.fullmatch(escape) is None:
            raise HelperError(f"Refusing noncanonical Bitbucket API {component}")
        index += 3


def validate_canonical_path(path: str) -> None:
    if not path.startswith(REPOSITORY_PATH_PREFIX):
        raise HelperError("Refusing Bitbucket API URL outside /2.0/repositories/")
    if posixpath.normpath(path) != path:
        raise HelperError("Refusing non-normalized Bitbucket API path")

    segments = path.split("/")
    if segments[0] or any(not segment for segment in segments[1:]):
        raise HelperError("Refusing non-normalized Bitbucket API path")

    for segment in segments[1:]:
        validate_percent_escapes(segment, "path")
        try:
            decoded = unquote_to_bytes(segment).decode("utf-8")
        except UnicodeDecodeError as error:
            raise HelperError("Refusing invalid UTF-8 in Bitbucket API path") from error
        if decoded in {".", ".."} or any(
            delimiter in decoded
            for delimiter in FORBIDDEN_PATH_SEGMENT_CHARACTERS
        ):
            raise HelperError("Refusing delimiters or dot segments in Bitbucket API path")
        if quote(decoded, safe="-._~") != segment:
            raise HelperError("Refusing noncanonical Bitbucket API path encoding")


def validate_query(query: str) -> None:
    if not query:
        return
    try:
        query.encode("ascii")
    except UnicodeEncodeError as error:
        raise HelperError("Refusing unencoded UTF-8 in Bitbucket API query") from error
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in query):
        raise HelperError("Refusing control characters in Bitbucket API query")
    validate_percent_escapes(query, "query")


def validate_api_url(url: str, expected_path: str) -> str:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise HelperError("Refusing untrusted Bitbucket API URL") from error

    trusted_authority = (
        parsed.scheme == "https"
        and parsed.hostname == API_HOST
        and port in (None, API_PORT)
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    )
    if not trusted_authority:
        raise HelperError("Refusing untrusted Bitbucket API URL")
    if parsed.path != expected_path:
        raise HelperError("Refusing Bitbucket API URL with an unexpected path")

    validate_canonical_path(expected_path)
    validate_query(parsed.query)
    authority = API_HOST if port is None else f"{API_HOST}:{API_PORT}"
    canonical_url = urlunsplit(
        ("https", authority, expected_path, parsed.query, "")
    )
    if canonical_url != url:
        raise HelperError("Refusing noncanonical Bitbucket API URL")

    target = expected_path
    if parsed.query:
        target = f"{target}?{parsed.query}"
    return target


def auth_headers() -> dict[str, str]:
    oauth_token = os.environ.get("BITBUCKET_TOKEN", "")
    email = os.environ.get("BITBUCKET_EMAIL", "")
    api_token = os.environ.get("BITBUCKET_API_TOKEN", "")
    if oauth_token:
        if not oauth_token.isascii() or any(
            not 0x21 <= ord(character) <= 0x7E for character in oauth_token
        ):
            raise HelperError("BITBUCKET_TOKEN contains invalid header characters")
        return {"Authorization": f"Bearer {oauth_token}"}
    if email and api_token:
        credentials = base64.b64encode(
            f"{email}:{api_token}".encode("utf-8")
        ).decode("ascii")
        return {"Authorization": f"Basic {credentials}"}
    raise HelperError(
        "Set BITBUCKET_TOKEN or BITBUCKET_EMAIL + BITBUCKET_API_TOKEN"
    )


def request(method: str, url: str, expected_path: str) -> None:
    if method not in {"GET", "POST", "PUT"}:
        raise HelperError(f"Unsupported HTTP method: {method}")
    target = validate_api_url(url, expected_path)
    body = sys.stdin.buffer.read()
    headers = {"Accept": "application/json", **auth_headers()}
    if body:
        headers["Content-Type"] = "application/json"

    request_object = urllib.request.Request(
        url,
        data=body or None,
        headers=headers,
        method=method,
    )
    opener = urllib.request.build_opener(_RejectRedirects())
    try:
        with opener.open(request_object, timeout=30) as response:
            status = response.status
            response_body = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        raise HelperError(
            f"Bitbucket API request failed with HTTP {status}"
        ) from error
    except (ValueError, UnicodeError) as error:
        raise HelperError("Bitbucket API request contained invalid data") from error
    except (OSError, urllib.error.URLError, http.client.HTTPException) as error:
        raise HelperError("Bitbucket API request failed") from error

    if not 200 <= status < 300:
        raise HelperError(f"Bitbucket API request failed with HTTP {status}")
    sys.stdout.buffer.write(response_body)


def comments_next_url(expected_path: str) -> None:
    try:
        page = json.loads(sys.stdin.buffer.read())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HelperError(f"Invalid JSON in Bitbucket comments response: {error}") from error
    if not isinstance(page, dict) or not isinstance(page.get("values"), list):
        raise HelperError("Invalid Bitbucket comments page shape")

    next_url = page.get("next")
    if next_url is None:
        return
    if not isinstance(next_url, str) or not next_url:
        raise HelperError("Invalid next URL in Bitbucket comments response")
    try:
        validate_api_url(next_url, expected_path)
    except HelperError as error:
        raise HelperError("Refusing untrusted comments pagination URL") from error
    write_text(next_url)


def combine_comment_pages() -> None:
    raw_pages = [raw for raw in sys.stdin.buffer.read().split(b"\0") if raw]
    if not raw_pages:
        raise HelperError("Bitbucket returned no comments pages")

    pages = []
    for raw_page in raw_pages:
        try:
            page = json.loads(raw_page)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HelperError(
                f"Invalid JSON in Bitbucket comments response: {error}"
            ) from error
        if not isinstance(page, dict) or not isinstance(page.get("values"), list):
            raise HelperError("Invalid Bitbucket comments page shape")
        pages.append(page)

    combined = dict(pages[0])
    combined["values"] = [value for page in pages for value in page["values"]]
    combined.pop("next", None)
    combined.pop("previous", None)
    combined["page"] = 1
    combined["pagelen"] = len(combined["values"])
    combined.setdefault("size", len(combined["values"]))
    write_text(json.dumps(combined, ensure_ascii=False, separators=(",", ":")))


def main() -> None:
    if len(sys.argv) < 2:
        raise HelperError("Missing helper command")
    command, *arguments = sys.argv[1:]
    if command == "encode-slug" and len(arguments) == 1:
        encode_slug(arguments[0])
    elif command == "encode-task-identifier" and not arguments:
        encode_task_identifier()
    elif command == "positive-integer" and len(arguments) == 1:
        validate_positive_integer(arguments[0])
    elif command == "build-query" and not arguments:
        build_pull_request_query()
    elif command == "json-body" and len(arguments) == 1:
        build_json_body(arguments[0])
    elif command == "inline-comment-body" and len(arguments) == 2:
        build_inline_comment_body(arguments[0], arguments[1])
    elif command == "validate-url" and len(arguments) == 2:
        validate_api_url(arguments[0], arguments[1])
    elif command == "request" and len(arguments) == 3:
        request(arguments[0], arguments[1], arguments[2])
    elif command == "comments-next-url" and len(arguments) == 1:
        comments_next_url(arguments[0])
    elif command == "combine-comment-pages" and not arguments:
        combine_comment_pages()
    else:
        raise HelperError(f"Invalid arguments for helper command: {command}")


if __name__ == "__main__":
    try:
        main()
    except HelperError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
