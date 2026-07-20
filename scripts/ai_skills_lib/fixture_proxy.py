"""Fail-closed MockServer fixtures for isolated model-backed evaluations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import time
from typing import Callable, Protocol

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jsonschema import Draft7Validator
import jwt
from jwt.algorithms import RSAAlgorithm

from scripts.ai_skills_lib.authored_content import (
    BoundedJsonError,
    strict_bounded_json_loads,
)
from scripts.ai_skills_lib.harness import PreparedFile
from scripts.ai_skills_lib.secret_patterns import (
    bounded_redacted_runtime_text,
    redact_runtime_secrets,
)
from scripts.ai_skills_lib.sandbox_runtime import (
    CaseWorkspace,
    CommandResult,
    EvalRuntimeManifest,
    SandboxWorker,
)


CONTROL_AUDIENCE = "ai-skills-fixture-control"
CONTROL_DIRECTORY = "fixture-control"
CONTROL_PORT = 1080
CONTROL_TOKEN_LIFETIME = timedelta(minutes=15)
MAX_FIXTURE_BYTES = 4 * 1024 * 1024
MAX_EVIDENCE_BODY_BYTES = 64 * 1024
MAX_EVIDENCE_EVENT_BYTES = 128 * 1024
MAX_EVIDENCE_TEXT_BYTES = 4096
MAX_EVIDENCE_COLLECTION_ITEMS = 128
STARTUP_ATTEMPTS = 60
STARTUP_INTERVAL_SECONDS = 0.5
STARTUP_RETRY_CODES = (5, 6, 7, 22, 28, 52, 56)
SENSITIVE_NAME = re.compile(
    r"(?:authorization|cookie|credential|password|secret|token|api[_-]?key)", re.IGNORECASE
)
SAFE_EXPECTATION_KEYS = frozenset(
    ("id", "priority", "times", "httpRequest", "httpResponse", "httpError")
)
SAFE_REQUEST_KEYS = frozenset(
    ("secure", "method", "path", "queryStringParameters", "headers", "cookies", "body")
)
SAFE_RESPONSE_KEYS = frozenset(
    ("statusCode", "reasonPhrase", "headers", "cookies", "body")
)
SAFE_ERROR_KEYS = frozenset(("dropConnection", "responseBytes", "streamError", "primary"))


class FixtureProxyError(RuntimeError):
    """Fixture configuration or control evidence is not trustworthy."""

    def __init__(
        self,
        message: str,
        *,
        evidence: Sequence[Mapping[str, object]] = (),
    ) -> None:
        super().__init__(bounded_redacted_runtime_text(message, MAX_EVIDENCE_TEXT_BYTES))
        self.evidence = tuple(evidence)


class FixtureRuntime(Protocol):
    manifest: EvalRuntimeManifest

    def run_worker_control(
        self,
        worker: SandboxWorker,
        argv: tuple[str, ...],
        *,
        accepted_returncodes: tuple[int, ...] = (0,),
    ) -> CommandResult:
        """Run one checked runner-owned command as worker root."""

    def invalidate_worker(self, worker: SandboxWorker) -> None:
        """Remove a worker whose fixture boundary is uncertain."""

    def execute(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
        argv: tuple[str, ...],
        *,
        timeout_seconds: int,
        environment: Mapping[str, str] | None = None,
    ) -> CommandResult:
        """Run one checked actor-visible command in the selected case."""


@dataclass(frozen=True)
class FixtureDefinition:
    expectations: tuple[Mapping[str, object], ...]
    sha256: str
    source: Path


@dataclass(frozen=True)
class FixtureSession:
    worker_id: str
    case_id: str
    definition_sha256: str
    public_ca_sha256: str
    shell_environment: tuple[tuple[str, str], ...]
    expected_requests: tuple[Mapping[str, object], ...] = ()


@dataclass
class _WorkerFixtureState:
    control_dir: Path
    certificate_dir: Path
    jwks_path: Path
    curl_config_path: Path
    expectations_path: Path
    empty_request_path: Path
    private_key: rsa.RSAPrivateKey
    key_id: str
    public_ca_pem: bytes
    public_ca_sha256: str


def load_fixture_definition(
    path: Path,
    *,
    manifest: EvalRuntimeManifest,
    repository_root: Path,
    allowed_fixture_root: Path,
) -> FixtureDefinition:
    """Load one schema-valid, non-executable MockServer expectation set."""
    source = path.resolve()
    allowed_root = allowed_fixture_root.resolve()
    if not source.is_relative_to(allowed_root) or path.is_symlink():
        raise FixtureProxyError("fixture path is outside the declared fixture root")
    if not source.is_file():
        raise FixtureProxyError("fixture initialization file does not exist")
    if source.stat().st_size > MAX_FIXTURE_BYTES:
        raise FixtureProxyError("fixture initialization file is too large")

    try:
        raw_bytes = source.read_bytes()
    except OSError as error:
        raise FixtureProxyError("fixture JSON could not be read") from error
    return load_fixture_definition_bytes(
        raw_bytes,
        source=source,
        manifest=manifest,
        repository_root=repository_root,
    )


def load_fixture_definition_bytes(
    raw_bytes: bytes,
    *,
    source: Path,
    manifest: EvalRuntimeManifest,
    repository_root: Path,
) -> FixtureDefinition:
    """Validate already-frozen fixture bytes without re-reading their source path."""
    if len(raw_bytes) > MAX_FIXTURE_BYTES:
        raise FixtureProxyError("fixture initialization file is too large")
    schema_path = (repository_root.resolve() / manifest.mockserver.schema_path).resolve()
    if not schema_path.is_relative_to(repository_root.resolve()) or not schema_path.is_file():
        raise FixtureProxyError("vendored MockServer schema is unavailable")
    try:
        schema_bytes = schema_path.read_bytes()
    except OSError as error:
        raise FixtureProxyError("vendored MockServer schema is unavailable") from error
    if hashlib.sha256(schema_bytes).hexdigest() != manifest.mockserver.schema_sha256:
        raise FixtureProxyError("vendored MockServer schema hash does not match the runtime pin")
    try:
        schema = strict_bounded_json_loads(
            schema_bytes,
            maximum_bytes=MAX_FIXTURE_BYTES,
        )
        payload = strict_bounded_json_loads(
            raw_bytes,
            maximum_bytes=MAX_FIXTURE_BYTES,
        )
    except BoundedJsonError as error:
        raise FixtureProxyError("fixture JSON is invalid or exceeds parser limits") from error

    try:
        first_error = min(
            Draft7Validator(schema).iter_errors(payload),
            key=lambda item: tuple(
                (type(part).__name__, str(part)) for part in item.path
            ),
            default=None,
        )
    except (MemoryError, OverflowError, RecursionError, RuntimeError) as error:
        raise FixtureProxyError(
            "fixture schema validation exceeded resource limits"
        ) from error
    if first_error is not None:
        location = "/".join(str(part) for part in first_error.path) or "<root>"
        raise FixtureProxyError(
            f"fixture schema validation failed at {location}: {first_error.message}"
        )
    items = payload if isinstance(payload, list) else [payload]
    if not items:
        raise FixtureProxyError("fixture initialization must declare at least one expectation")
    expected_requests = 0
    for expectation in items:
        if not isinstance(expectation, Mapping):
            raise FixtureProxyError("fixture schema produced a non-object expectation")
        _validate_safe_expectation(expectation)
        expected_requests += _expectation_repeat_count(expectation)
        if expected_requests > manifest.mockserver.maximum_expected_requests:
            raise FixtureProxyError("fixture exceeds the manifest total request limit")
    return FixtureDefinition(
        expectations=tuple(dict(item) for item in items),
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        source=source,
    )


class FixtureProxy:
    """Own one authenticated MockServer sidecar per reusable actor worker."""

    def __init__(
        self,
        runtime: FixtureRuntime,
        *,
        repository_root: Path,
        allowed_fixture_root: Path,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.runtime = runtime
        self.repository_root = repository_root.resolve()
        self.allowed_fixture_root = allowed_fixture_root.resolve()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper or time.sleep
        self._states: dict[str, _WorkerFixtureState] = {}
        self._ca_owners: dict[str, str] = {}
        self._state_lock = threading.RLock()

    def preflight(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        """Prove fixture startup, private control state, and control-endpoint denial."""
        self._require_case(worker, case)
        try:
            state = self._ensure_worker_state(worker)
            self._write_control_config(worker, state)
            self._reset_and_verify_empty(worker, state)
            timeout = self.runtime.manifest.limits.preflight_timeout_seconds
            private_state = self.runtime.execute(
                worker,
                case,
                ("test", "!", "-r", str(state.control_dir)),
                timeout_seconds=timeout,
            )
            if private_state.timed_out or private_state.returncode != 0:
                raise FixtureProxyError("actor can read fixture private control state")
            unauthenticated = self.runtime.execute(
                worker,
                case,
                (
                    "curl",
                    "--silent",
                    "--output",
                    "/dev/null",
                    "--write-out",
                    "%{http_code}",
                    f"http://127.0.0.1:{CONTROL_PORT}/mockserver/reset",
                ),
                timeout_seconds=timeout,
            )
            if (
                unauthenticated.timed_out
                or unauthenticated.returncode != 0
                or unauthenticated.stdout.strip() not in {"401", "403"}
            ):
                raise FixtureProxyError(
                    "unauthenticated actor access to fixture control endpoint was not denied"
                )
            self._reset_and_verify_empty(worker, state)
        except Exception as error:
            raise self._quarantine_failure(
                worker,
                error,
                context="fixture preflight failed",
            ) from error

    def prepare_case(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
        initialization_path: Path | PreparedFile,
        case_fixture_root: Path,
    ) -> FixtureSession:
        """Reset, load, and expose one fixture through actor-only shell settings."""
        specific_root = (
            case_fixture_root.absolute()
            if isinstance(initialization_path, PreparedFile)
            else case_fixture_root.resolve()
        )
        if not specific_root.is_relative_to(self.allowed_fixture_root):
            raise FixtureProxyError("case fixture root is outside the configured fixture root")
        if isinstance(initialization_path, PreparedFile):
            if initialization_path.source != (
                specific_root / "mockserverInitialization.json"
            ):
                raise FixtureProxyError(
                    "prepared fixture does not belong to the selected case root"
                )
            definition = load_fixture_definition_bytes(
                initialization_path.content,
                source=initialization_path.source,
                manifest=self.runtime.manifest,
                repository_root=self.repository_root,
            )
        else:
            definition = load_fixture_definition(
                initialization_path,
                manifest=self.runtime.manifest,
                repository_root=self.repository_root,
                allowed_fixture_root=specific_root,
            )
        self._require_case(worker, case)
        try:
            state = self._ensure_worker_state(worker)
            self._write_control_config(worker, state)
            self._reset_and_verify_empty(worker, state)
            payload = json.dumps(
                [_literal_mockserver_expectation(item) for item in definition.expectations],
                sort_keys=True,
                separators=(",", ":"),
            )
            state.expectations_path.write_text(payload, encoding="utf-8")
            state.expectations_path.chmod(0o600)
            self._run(
                worker,
                ("chown", "0:0", str(state.expectations_path)),
            )
            self._run(worker, ("chmod", "0600", str(state.expectations_path)))
            self._curl(
                worker,
                state,
                "PUT",
                "/mockserver/expectation",
                data_path=state.expectations_path,
            )
            public_ca_path = case.bootstrap / "mockserver-ca.pem"
            public_ca_path.write_bytes(state.public_ca_pem)
            public_ca_path.chmod(0o444)
            environment = _fixture_environment(public_ca_path)
            return FixtureSession(
                worker_id=worker.id,
                case_id=case.case_id,
                definition_sha256=definition.sha256,
                public_ca_sha256=state.public_ca_sha256,
                shell_environment=tuple(sorted(environment.items())),
                expected_requests=_expected_request_sequence(definition.expectations),
            )
        except Exception as error:
            raise self._quarantine_failure(
                worker,
                error,
                context="fixture setup failed",
            ) from error

    def collect_and_reset(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
        session: FixtureSession,
    ) -> tuple[Mapping[str, object], ...]:
        """Collect sanitized request evidence, then erase all case fixture state."""
        self._require_case(worker, case)
        if session.worker_id != worker.id or session.case_id != case.case_id:
            raise FixtureProxyError("fixture session does not belong to this worker case")
        with self._state_lock:
            state = self._states.get(worker.id)
        if state is None or state.public_ca_sha256 != session.public_ca_sha256:
            raise FixtureProxyError("fixture worker state is unavailable or changed")
        events: tuple[Mapping[str, object], ...] = ()
        try:
            self._write_control_config(worker, state)
            requests = self._retrieve_array(worker, state, "REQUESTS")
            events = tuple(
                _normalize_request(item, index)
                for index, item in enumerate(
                    requests[:MAX_EVIDENCE_COLLECTION_ITEMS],
                    1,
                )
            )
            if len(requests) > MAX_EVIDENCE_COLLECTION_ITEMS:
                raise FixtureProxyError(
                    "fixture request evidence exceeds the collection limit",
                    evidence=events,
                )
            _verify_request_sequence(session.expected_requests, requests)
            self._reset_and_verify_empty(worker, state)
            self._run(
                worker,
                ("rm", "-f", "--", str(state.expectations_path)),
            )
            return events
        except Exception as error:
            raise self._quarantine_failure(
                worker,
                error,
                context="fixture evidence collection failed",
                evidence=events,
            ) from error

    def discard_worker_state(self, worker: SandboxWorker) -> None:
        """Forget host-side proxy state after the runtime recycles a worker."""
        self._drop_worker_state(worker.id)

    def _drop_worker_state(self, worker_id: str) -> None:
        with self._state_lock:
            state = self._states.pop(worker_id, None)
            if (
                state is not None
                and self._ca_owners.get(state.public_ca_sha256) == worker_id
            ):
                self._ca_owners.pop(state.public_ca_sha256, None)

    def _quarantine_failure(
        self,
        worker: SandboxWorker,
        error: Exception,
        *,
        context: str,
        evidence: Sequence[Mapping[str, object]] = (),
    ) -> FixtureProxyError:
        self._drop_worker_state(worker.id)
        invalidation_failure = None
        try:
            self.runtime.invalidate_worker(worker)
        except Exception as cleanup_error:
            invalidation_failure = redact_runtime_secrets(str(cleanup_error))
        message = str(error) if isinstance(error, FixtureProxyError) else f"{context}: {error}"
        if invalidation_failure:
            message = f"{message}; worker invalidation failed: {invalidation_failure}"
        preserved = error.evidence if isinstance(error, FixtureProxyError) else ()
        return FixtureProxyError(message, evidence=preserved or evidence)

    def _ensure_worker_state(self, worker: SandboxWorker) -> _WorkerFixtureState:
        with self._state_lock:
            state = self._states.get(worker.id)
        if state is not None:
            return state
        state = self._start_sidecar(worker)
        with self._state_lock:
            if worker.id in self._states:
                raise FixtureProxyError("fixture worker state was initialized concurrently")
            self._states[worker.id] = state
        return state

    def _start_sidecar(self, worker: SandboxWorker) -> _WorkerFixtureState:
        control_dir = worker.host_root / CONTROL_DIRECTORY
        certificate_dir = control_dir / "certificates"
        control_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        certificate_dir.mkdir(mode=0o700, exist_ok=True)
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_der = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        key_id = hashlib.sha256(public_der).hexdigest()[:32]
        jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
        jwk.update({"alg": "RS256", "kid": key_id, "use": "sig"})
        jwks_path = control_dir / "jwks.json"
        curl_config_path = control_dir / "curl.conf"
        expectations_path = control_dir / "case-expectations.json"
        empty_request_path = control_dir / "empty-request.json"
        jwks_path.write_text(
            json.dumps({"keys": [jwk]}, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        empty_request_path.write_text("{}", encoding="utf-8")
        for path in (jwks_path, empty_request_path):
            path.chmod(0o600)
        self._run(worker, ("chown", "-R", "0:0", str(control_dir)))
        self._run(worker, ("chmod", "0700", str(control_dir), str(certificate_dir)))
        self._run(worker, ("chmod", "0600", str(jwks_path), str(empty_request_path)))
        container_name = _container_name(worker)
        self._run(worker, ("docker", "pull", self.runtime.manifest.mockserver.image_reference))
        self._run(
            worker,
            ("docker", "rm", "--force", container_name),
            accepted=(0, 1),
        )
        command = _docker_run_command(
            worker,
            self.runtime.manifest,
            container_name=container_name,
            certificate_dir=certificate_dir,
            jwks_path=jwks_path,
        )
        self._run(worker, command)
        partial_state = _WorkerFixtureState(
            control_dir=control_dir,
            certificate_dir=certificate_dir,
            jwks_path=jwks_path,
            curl_config_path=curl_config_path,
            expectations_path=expectations_path,
            empty_request_path=empty_request_path,
            private_key=private_key,
            key_id=key_id,
            public_ca_pem=b"",
            public_ca_sha256="",
        )
        self._write_control_config(worker, partial_state)
        self._wait_until_ready(worker, partial_state)
        self._curl(worker, partial_state, "GET", "/mockserver/proxyConfiguration")
        ca_path = certificate_dir / "mockserver-ca.pem"
        self._run(worker, ("test", "-s", str(ca_path)))
        ca_result = self._run(worker, ("cat", "--", str(ca_path)))
        public_ca_pem = ca_result.stdout.encode("utf-8")
        try:
            certificate = x509.load_pem_x509_certificate(public_ca_pem)
        except ValueError as error:
            raise FixtureProxyError("MockServer did not produce a valid public CA certificate") from error
        fingerprint = certificate.fingerprint(hashes.SHA256()).hex()
        if fingerprint == self.runtime.manifest.mockserver.bundled_default_ca_sha256:
            raise FixtureProxyError("MockServer reused its bundled default CA")
        with self._state_lock:
            owner = self._ca_owners.get(fingerprint)
            if owner is not None and owner != worker.id:
                raise FixtureProxyError("two fixture workers shared the same generated CA")
            self._ca_owners[fingerprint] = worker.id
        partial_state.public_ca_pem = public_ca_pem
        partial_state.public_ca_sha256 = fingerprint
        return partial_state

    def _wait_until_ready(
        self, worker: SandboxWorker, state: _WorkerFixtureState
    ) -> None:
        accepted = (0, *STARTUP_RETRY_CODES)
        for attempt in range(STARTUP_ATTEMPTS):
            result = self._curl(
                worker,
                state,
                "GET",
                "/mockserver/status",
                accepted=accepted,
            )
            if result.returncode == 0:
                return
            if attempt + 1 < STARTUP_ATTEMPTS:
                self.sleeper(STARTUP_INTERVAL_SECONDS)
        raise FixtureProxyError("MockServer did not become ready before the startup deadline")

    def _write_control_config(
        self, worker: SandboxWorker, state: _WorkerFixtureState
    ) -> None:
        now = self.clock().astimezone(timezone.utc)
        token = jwt.encode(
            {
                "iss": "ai-skills-eval",
                "aud": CONTROL_AUDIENCE,
                "sub": worker.id,
                "scope": "fixture-control",
                "iat": int(now.timestamp()),
                "nbf": int(now.timestamp()) - 1,
                "exp": int((now + CONTROL_TOKEN_LIFETIME).timestamp()),
            },
            state.private_key,
            algorithm="RS256",
            headers={"kid": state.key_id},
        )
        state.curl_config_path.write_text(
            "\n".join(
                (
                    "silent",
                    "show-error",
                    "fail-with-body",
                    "connect-timeout = 10",
                    "max-time = 30",
                    f'header = "Authorization: Bearer {token}"',
                    "",
                )
            ),
            encoding="utf-8",
        )
        state.curl_config_path.chmod(0o600)
        self._run(worker, ("chown", "0:0", str(state.curl_config_path)))
        self._run(worker, ("chmod", "0600", str(state.curl_config_path)))

    def _reset_and_verify_empty(
        self, worker: SandboxWorker, state: _WorkerFixtureState
    ) -> None:
        self._curl(worker, state, "PUT", "/mockserver/reset")
        if self._retrieve_array(worker, state, "REQUESTS"):
            raise FixtureProxyError("MockServer request history did not reset")
        if self._retrieve_array(worker, state, "ACTIVE_EXPECTATIONS"):
            raise FixtureProxyError("MockServer expectations did not reset")
        self._run(worker, ("rm", "-f", "--", str(state.expectations_path)))

    def _retrieve_array(
        self, worker: SandboxWorker, state: _WorkerFixtureState, kind: str
    ) -> list[Mapping[str, object]]:
        result = self._curl(
            worker,
            state,
            "PUT",
            f"/mockserver/retrieve?type={kind}",
            data_path=state.empty_request_path,
        )
        try:
            payload = strict_bounded_json_loads(
                result.stdout,
                maximum_bytes=MAX_FIXTURE_BYTES,
            )
        except BoundedJsonError as error:
            raise FixtureProxyError("MockServer retrieval returned invalid JSON") from error
        if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
            raise FixtureProxyError("MockServer retrieval returned an invalid result shape")
        return list(payload)

    def _curl(
        self,
        worker: SandboxWorker,
        state: _WorkerFixtureState,
        method: str,
        endpoint: str,
        *,
        data_path: Path | None = None,
        accepted: tuple[int, ...] = (0,),
    ) -> CommandResult:
        command = [
            "curl",
            "--config",
            str(state.curl_config_path),
            "--request",
            method,
            "--url",
            f"http://127.0.0.1:{CONTROL_PORT}{endpoint}",
        ]
        if data_path is not None:
            command.extend(
                ("--header", "Content-Type: application/json", "--data-binary", f"@{data_path}")
            )
        return self._run(worker, tuple(command), accepted=accepted)

    def _run(
        self,
        worker: SandboxWorker,
        argv: tuple[str, ...],
        *,
        accepted: tuple[int, ...] = (0,),
    ) -> CommandResult:
        result = self.runtime.run_worker_control(
            worker,
            argv,
            accepted_returncodes=accepted,
        )
        if result.timed_out or result.returncode not in accepted:
            raise FixtureProxyError(f"fixture control command failed: {argv[0]}")
        return result

    @staticmethod
    def _require_case(worker: SandboxWorker, case: CaseWorkspace) -> None:
        if case.root.parent != worker.host_root or not case.root.is_dir():
            raise FixtureProxyError("fixture case does not belong to the selected worker")


def _validate_safe_expectation(expectation: Mapping[str, object]) -> None:
    unknown = sorted(set(expectation) - SAFE_EXPECTATION_KEYS)
    if unknown:
        raise FixtureProxyError(
            f"fixture action or option is not allowed: {', '.join(unknown)}"
        )
    actions = [name for name in ("httpResponse", "httpError") if name in expectation]
    if len(actions) != 1:
        raise FixtureProxyError("fixture expectation must use exactly one static response or error action")
    _expectation_repeat_count(expectation)
    request = expectation.get("httpRequest")
    if not isinstance(request, Mapping):
        raise FixtureProxyError("fixture expectation requires an HTTP request matcher")
    unsupported_request = sorted(set(request) - SAFE_REQUEST_KEYS)
    if unsupported_request:
        raise FixtureProxyError(
            f"fixture request matcher is not allowed: {', '.join(unsupported_request)}"
        )
    for field in ("method", "path"):
        value = request.get(field)
        if not isinstance(value, str) or not value:
            raise FixtureProxyError(
                f"fixture request {field} requires a non-empty exact string matcher"
            )
    _validate_exact_multivalue(request.get("headers"), "headers")
    headers = request.get("headers")
    assert headers is None or isinstance(headers, Mapping)
    host_values = [
        _string_tuple(values)
        for name, values in (headers or {}).items()
        if isinstance(name, str) and name.casefold() == "host"
    ]
    if (
        len(host_values) != 1
        or host_values[0] is None
        or len(host_values[0]) != 1
        or not host_values[0][0]
    ):
        raise FixtureProxyError("fixture request requires one exact non-empty Host matcher")
    _validate_exact_multivalue(request.get("queryStringParameters"), "query parameters")
    _validate_exact_multivalue(request.get("cookies"), "cookies")
    _validate_request_body(request.get("body"))
    response = expectation.get("httpResponse")
    if response is not None:
        if not isinstance(response, Mapping):
            raise FixtureProxyError("fixture response must be an object")
        unsupported_response = sorted(set(response) - SAFE_RESPONSE_KEYS)
        if unsupported_response:
            raise FixtureProxyError(
                f"fixture response option is not allowed: {', '.join(unsupported_response)}"
            )
        _validate_response_body(response.get("body"))
    error = expectation.get("httpError")
    if error is not None:
        if not isinstance(error, Mapping):
            raise FixtureProxyError("fixture error must be an object")
        unsupported_error = sorted(set(error) - SAFE_ERROR_KEYS)
        if unsupported_error:
            raise FixtureProxyError(
                f"fixture error option is not allowed: {', '.join(unsupported_error)}"
            )


def _literal_mockserver_expectation(
    expectation: Mapping[str, object],
) -> Mapping[str, object]:
    """Render authored request strings as Java-regex quoted literals for MockServer."""
    rendered = dict(expectation)
    request = expectation.get("httpRequest")
    assert isinstance(request, Mapping)
    literal_request = dict(request)
    for field in ("method", "path"):
        value = request.get(field)
        assert isinstance(value, str)
        literal_request[field] = _java_regex_literal(value)
    for field in ("headers", "queryStringParameters", "cookies"):
        value = request.get(field)
        if not isinstance(value, Mapping):
            continue
        literal_request[field] = {
            _java_regex_literal(str(name)): [
                _java_regex_literal(item) for item in values
            ]
            for name, values in value.items()
            if isinstance(name, str)
            and isinstance(values, list)
            and all(isinstance(item, str) for item in values)
        }
    rendered["httpRequest"] = literal_request
    return rendered


def _java_regex_literal(value: str) -> str:
    return r"\Q" + value.replace(r"\E", r"\E\\E\Q") + r"\E"


def _validate_exact_multivalue(value: object, label: str) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise FixtureProxyError(f"fixture {label} must use exact key/value matchers")
    for key, values in value.items():
        if not isinstance(key, str) or not isinstance(values, list) or not all(
            isinstance(item, str) for item in values
        ):
            raise FixtureProxyError(f"fixture {label} must use exact string lists")


def _validate_request_body(body: object) -> None:
    if body is None or isinstance(body, (str, list)):
        return
    if not isinstance(body, Mapping):
        raise FixtureProxyError("fixture request body matcher is unsupported")
    body_type = body.get("type")
    if body_type is None:
        return
    if body_type == "JSON":
        allowed = {"type", "json", "contentType", "matchType"}
        if set(body) - allowed or body.get("matchType") not in (None, "STRICT"):
            raise FixtureProxyError("fixture request body must use exact JSON matching")
        _require_json_string(body.get("json"), "fixture request JSON body")
        return
    if body_type == "STRING":
        allowed = {"type", "string", "contentType", "subString"}
        if set(body) - allowed or body.get("subString") not in (None, False):
            raise FixtureProxyError("fixture request body must use exact string matching")
        return
    raise FixtureProxyError("fixture request body matcher must use exact JSON or string data")


def _validate_response_body(body: object) -> None:
    if body is None or isinstance(body, (str, list)):
        return
    if not isinstance(body, Mapping):
        raise FixtureProxyError("fixture response body is unsupported")
    body_type = body.get("type")
    if body_type is None:
        return
    if body_type == "FILE":
        raise FixtureProxyError("fixture file response bodies are not allowed")
    allowed = {
        "JSON": {"type", "json", "contentType"},
        "STRING": {"type", "string", "contentType"},
    }.get(body_type)
    if allowed is None or set(body) - allowed:
        raise FixtureProxyError("fixture response body must use literal JSON or string data")
    if body_type == "JSON":
        _require_json_string(body.get("json"), "fixture response JSON body")


def _require_json_string(value: object, label: str) -> object:
    if not isinstance(value, str):
        raise FixtureProxyError(f"{label} must contain JSON text")
    try:
        return strict_bounded_json_loads(
            value,
            maximum_bytes=MAX_FIXTURE_BYTES,
        )
    except BoundedJsonError as error:
        raise FixtureProxyError(f"{label} is invalid") from error


def _expectation_repeat_count(expectation: Mapping[str, object]) -> int:
    times = expectation.get("times")
    if times is None:
        return 1
    if (
        not isinstance(times, Mapping)
        or set(times) != {"remainingTimes", "unlimited"}
        or not isinstance(times.get("remainingTimes"), int)
        or isinstance(times.get("remainingTimes"), bool)
        or times["remainingTimes"] not in range(1, 101)
        or times.get("unlimited") is not False
    ):
        raise FixtureProxyError(
            "fixture times must declare 1 through 100 finite required calls"
        )
    return times["remainingTimes"]


def _expected_request_sequence(
    expectations: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    sequence: list[Mapping[str, object]] = []
    for expectation in expectations:
        request = expectation["httpRequest"]
        assert isinstance(request, Mapping)
        sequence.extend(dict(request) for _ in range(_expectation_repeat_count(expectation)))
    return tuple(sequence)


def _verify_request_sequence(
    expected: Sequence[Mapping[str, object]],
    actual: Sequence[Mapping[str, object]],
) -> None:
    if len(expected) != len(actual):
        raise FixtureProxyError(
            "fixture request sequence did not contain the required number of calls"
        )
    for sequence, (expected_request, actual_request) in enumerate(
        zip(expected, actual, strict=True),
        start=1,
    ):
        if not _request_matches(expected_request, actual_request):
            raise FixtureProxyError(
                f"fixture request sequence did not match at call {sequence}"
            )


def _request_matches(
    expected: Mapping[str, object], actual: Mapping[str, object]
) -> bool:
    for field in ("secure", "method", "path"):
        if field in expected and expected[field] != actual.get(field):
            return False
    for field, case_insensitive_names in (
        ("headers", True),
        ("queryStringParameters", False),
        ("cookies", False),
    ):
        if not _multivalue_subset(
            expected.get(field),
            actual.get(field),
            case_insensitive_names=case_insensitive_names,
        ):
            return False
    return _request_body_value(expected.get("body")) == _request_body_value(
        actual.get("body")
    )


def _multivalue_subset(
    expected: object,
    actual: object,
    *,
    case_insensitive_names: bool,
) -> bool:
    if expected is None:
        return True
    if not isinstance(expected, Mapping) or not isinstance(actual, Mapping):
        return False
    normalized_actual = {
        (str(key).casefold() if case_insensitive_names else str(key)): _string_tuple(value)
        for key, value in actual.items()
        if isinstance(key, str)
    }
    for key, value in expected.items():
        if not isinstance(key, str):
            return False
        normalized_key = key.casefold() if case_insensitive_names else key
        if _string_tuple(value) != normalized_actual.get(normalized_key):
            return False
    return True


def _string_tuple(value: object) -> tuple[str, ...] | None:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return None


def _request_body_value(body: object) -> tuple[str, object] | None:
    if body is None:
        return None
    if isinstance(body, str):
        return ("string", body)
    if isinstance(body, list):
        return ("json", body)
    if not isinstance(body, Mapping):
        return ("unsupported", None)
    body_type = body.get("type")
    if body_type == "JSON":
        value = body.get("json")
        if not isinstance(value, str):
            return ("unsupported", None)
        try:
            return (
                "json",
                strict_bounded_json_loads(
                    value,
                    maximum_bytes=MAX_FIXTURE_BYTES,
                ),
            )
        except BoundedJsonError:
            return ("unsupported", None)
    if body_type == "STRING":
        return ("string", body.get("string"))
    if body_type is None:
        return ("json", dict(body))
    return ("unsupported", None)


def _docker_run_command(
    worker: SandboxWorker,
    manifest: EvalRuntimeManifest,
    *,
    container_name: str,
    certificate_dir: Path,
    jwks_path: Path,
) -> tuple[str, ...]:
    environment = (
        "MOCKSERVER_SERVER_PORT=1080",
        "MOCKSERVER_LOCAL_BOUND_IP=127.0.0.1",
        "MOCKSERVER_DYNAMICALLY_CREATE_CERTIFICATE_AUTHORITY_CERTIFICATE=true",
        "MOCKSERVER_CERTIFICATE_DIRECTORY_TO_SAVE_DYNAMIC_SSL_CERTIFICATE=/certs",
        "MOCKSERVER_ATTEMPT_TO_PROXY_IF_NO_MATCHING_EXPECTATION=false",
        "MOCKSERVER_MATCH_EXACT_CASE=true",
        "MOCKSERVER_CONTROL_PLANE_JWT_AUTHENTICATION_REQUIRED=true",
        "MOCKSERVER_CONTROL_PLANE_JWT_AUTHENTICATION_JWK_SOURCE=/control/jwks.json",
        f"MOCKSERVER_CONTROL_PLANE_JWT_AUTHENTICATION_EXPECTED_AUDIENCE={CONTROL_AUDIENCE}",
        "MOCKSERVER_CONTROL_PLANE_JWT_AUTHENTICATION_REQUIRED_CLAIMS=exp,sub,scope",
        "MOCKSERVER_MCP_ENABLED=false",
        "MOCKSERVER_METRICS_ENABLED=false",
        "MOCKSERVER_ENABLE_CORS_FOR_API=false",
        "MOCKSERVER_ENABLE_CORS_FOR_ALL_RESPONSES=false",
    )
    command = [
        "docker",
        "run",
        "--detach",
        "--rm",
        "--name",
        container_name,
        "--network",
        "host",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        "256",
        "--memory",
        "512m",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m",
        "--volume",
        f"{certificate_dir}:/certs",
        "--volume",
        f"{jwks_path}:/control/jwks.json:ro",
    ]
    for item in environment:
        command.extend(("--env", item))
    command.append(manifest.mockserver.image_reference)
    return tuple(command)


def _fixture_environment(public_ca_path: Path) -> dict[str, str]:
    proxy = f"http://127.0.0.1:{CONTROL_PORT}"
    ca = str(public_ca_path)
    return {
        "HTTP_PROXY": proxy,
        "HTTPS_PROXY": proxy,
        "http_proxy": proxy,
        "https_proxy": proxy,
        "SSL_CERT_FILE": ca,
        "REQUESTS_CA_BUNDLE": ca,
        "NODE_EXTRA_CA_CERTS": ca,
        "CURL_CA_BUNDLE": ca,
    }


def _normalize_request(request: Mapping[str, object], sequence: int) -> Mapping[str, object]:
    headers = request.get("headers")
    header_map = headers if isinstance(headers, Mapping) else {}
    host = _first_header(header_map, "host")
    safe_header_names = sorted(
        _bounded_text(str(name))
        for name in header_map
        if isinstance(name, str) and not SENSITIVE_NAME.search(name)
    )[:MAX_EVIDENCE_COLLECTION_ITEMS]
    query = request.get("queryStringParameters")
    safe_query: dict[str, object] = {}
    if isinstance(query, Mapping):
        for name, value in query.items():
            if not isinstance(name, str):
                continue
            safe_query[_bounded_text(name)] = (
                "[REDACTED]"
                if SENSITIVE_NAME.search(name)
                else _bounded_json_evidence(_redact_json(value))
            )
    body = request.get("body")
    body_json = _request_body_json(body)
    serialized_body = json.dumps(body, sort_keys=True, default=str).encode("utf-8")
    event: dict[str, object] = {
        "event": "fixture_request",
        "sequence": sequence,
        "method": _bounded_text(request["method"]) if isinstance(request.get("method"), str) else None,
        "host": _bounded_text(host) if host is not None else None,
        "path": _bounded_text(request["path"]) if isinstance(request.get("path"), str) else None,
        "query": _bounded_json_evidence(safe_query),
        "header_names": safe_header_names,
        "body_sha256": hashlib.sha256(serialized_body).hexdigest(),
    }
    if body_json is not None:
        event["body_json"] = _redact_json(body_json)
    if len(json.dumps(event, sort_keys=True, default=str).encode("utf-8")) > MAX_EVIDENCE_EVENT_BYTES:
        event.pop("body_json", None)
        event["query"] = {"_omitted": "oversized"}
        event["header_names"] = []
        event["evidence_omitted"] = "oversized request metadata"
    return event


def _first_header(headers: Mapping[object, object], expected: str) -> str | None:
    for name, values in headers.items():
        if isinstance(name, str) and name.casefold() == expected:
            if isinstance(values, list) and values and isinstance(values[0], str):
                return values[0]
            if isinstance(values, str):
                return values
    return None


def _request_body_json(body: object) -> object | None:
    if not isinstance(body, Mapping):
        value = body if isinstance(body, (dict, list)) else None
        return value if _json_size(value) <= MAX_EVIDENCE_BODY_BYTES else None
    value = body.get("json")
    if isinstance(value, str):
        try:
            parsed = strict_bounded_json_loads(
                value,
                maximum_bytes=MAX_EVIDENCE_BODY_BYTES,
            )
            return parsed if _json_size(parsed) <= MAX_EVIDENCE_BODY_BYTES else None
        except BoundedJsonError:
            return None
    if body.get("type") is None:
        value = dict(body)
        return value if _json_size(value) <= MAX_EVIDENCE_BODY_BYTES else None
    return None


def _redact_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            _bounded_text(str(key)): (
                "[REDACTED]"
                if SENSITIVE_NAME.search(str(key))
                else _redact_json(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_json(item) for item in value[:MAX_EVIDENCE_COLLECTION_ITEMS]]
    if isinstance(value, str):
        return _bounded_text(redact_runtime_secrets(value))
    return value


def _bounded_json_evidence(value: object) -> object:
    return value if _json_size(value) <= MAX_EVIDENCE_BODY_BYTES else {"_omitted": "oversized"}


def _json_size(value: object) -> int:
    return len(json.dumps(value, sort_keys=True, default=str).encode("utf-8"))


def _bounded_text(value: str) -> str:
    return bounded_redacted_runtime_text(value, MAX_EVIDENCE_TEXT_BYTES)


def _container_name(worker: SandboxWorker) -> str:
    suffix = hashlib.sha256(worker.id.encode("utf-8")).hexdigest()[:12]
    return f"ai-skills-mockserver-{suffix}"
