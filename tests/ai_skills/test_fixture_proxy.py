from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from scripts.ai_skills_lib.fixture_proxy import (
    CONTROL_TOKEN_OPERATION_WINDOWS,
    FixtureProxy,
    FixtureProxyError,
    load_fixture_definition,
)
from scripts.ai_skills_lib.sandbox_runtime import (
    CaseWorkspace,
    CommandResult,
    EvalRuntimeManifest,
    SandboxWorker,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = EvalRuntimeManifest.load(REPOSITORY_ROOT / "config" / "eval-runtime.json")


def valid_expectations() -> list[dict[str, object]]:
    return [
        {
            "id": "get-repository",
            "httpRequest": {
                "method": "GET",
                "path": "/2.0/repositories/acme/widget",
                "headers": {"Host": ["api.bitbucket.org"]},
                "queryStringParameters": {"page": ["1"]},
                "body": {
                    "type": "JSON",
                    "json": '{"owner":"acme"}',
                },
            },
            "httpResponse": {
                "statusCode": 200,
                "headers": {"Content-Type": ["application/json"]},
                "body": {"ok": True},
            },
            "times": {"remainingTimes": 1, "unlimited": False},
        }
    ]


def generated_ca(common_name: str) -> bytes:
    from datetime import timedelta
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM)


def worker_and_case(root: Path, identifier: str = "actor-one") -> tuple[SandboxWorker, CaseWorkspace]:
    worker_root = root / identifier
    case_root = worker_root / "case"
    home = case_root / "home"
    codex_home = case_root / "codex-home"
    tmpdir = case_root / "tmp"
    workspace = case_root / "workspace"
    skills = codex_home / "skills"
    bootstrap = case_root / "bootstrap"
    for path in (home, codex_home, tmpdir, workspace, skills, bootstrap):
        path.mkdir(parents=True, exist_ok=True)
    worker = SandboxWorker(
        id=f"{identifier}-id",
        name=identifier,
        role="actor",
        slot=0,
        host_root=worker_root,
    )
    case = CaseWorkspace(
        case_id="fixture-case",
        root=case_root,
        home=home,
        codex_home=codex_home,
        tmpdir=tmpdir,
        workspace=workspace,
        skills=skills,
        bootstrap=bootstrap,
        user_name="ai-eval-1",
        uid=20001,
    )
    return worker, case


class FakeFixtureRuntime:
    def __init__(self, certificates: dict[str, bytes | list[bytes]]) -> None:
        self.manifest = MANIFEST
        self.certificates = certificates
        self.certificate_reads: dict[str, int] = {}
        self.calls: list[tuple[str, tuple[str, ...], tuple[int, ...]]] = []
        self.invalidated: list[str] = []
        self.requests: dict[str, list[dict[str, object]]] = {}
        self.expectations: dict[str, list[dict[str, object]]] = {}
        self.canary_requests: dict[str, list[dict[str, object]]] = {}
        self.canary_expectations: dict[str, list[dict[str, object]]] = {}
        self.configurations: dict[str, dict[str, object]] = {}
        self.status_failures_remaining = 0
        self.actor_calls: list[tuple[str, tuple[str, ...]]] = []
        self.invalidate_error: Exception | None = None
        self.tls_probe_failure = False

    def run_worker_control(
        self,
        worker: SandboxWorker,
        argv: tuple[str, ...],
        *,
        accepted_returncodes: tuple[int, ...] = (0,),
    ) -> CommandResult:
        self.calls.append((worker.id, argv, accepted_returncodes))
        if argv[:2] == ("cat", "--") and argv[-1].endswith("mockserver-ca.pem"):
            certificates = self.certificates[worker.id]
            if isinstance(certificates, bytes):
                certificate = certificates
            else:
                index = self.certificate_reads.get(worker.id, 0)
                certificate = certificates[index]
                self.certificate_reads[worker.id] = index + 1
            return CommandResult(0, certificate.decode(), "")
        if argv[:3] == ("rm", "-rf", "--"):
            shutil.rmtree(Path(argv[-1]), ignore_errors=True)
            return CommandResult(0, "", "")
        if argv[:1] == ("curl",):
            url = argv[argv.index("--url") + 1]
            method = argv[argv.index("--request") + 1]
            if (
                "--write-out" in argv
                and argv[argv.index("--write-out") + 1]
                == "%{ssl_verify_result}"
            ):
                return (
                    CommandResult(60, "20", "certificate verify failed")
                    if self.tls_probe_failure
                    else CommandResult(0, "0", "")
                )
            data_path = (
                Path(argv[argv.index("--data-binary") + 1][1:])
                if "--data-binary" in argv
                else None
            )
            is_canary = ":1081/" in url
            if url.endswith("/mockserver/status") and method != "PUT":
                return CommandResult(22, "", "status requires PUT")
            if url.endswith("/mockserver/status") and self.status_failures_remaining:
                self.status_failures_remaining -= 1
                return CommandResult(7, "", "not ready")
            if url.endswith("/mockserver/reset"):
                if is_canary:
                    self.canary_requests[worker.id] = []
                    self.canary_expectations[worker.id] = []
                else:
                    self.requests[worker.id] = []
                    self.expectations[worker.id] = []
                return CommandResult(0, "{}", "")
            if url.endswith("/mockserver/configuration"):
                configuration = self.configurations.setdefault(
                    worker.id,
                    {
                        "attemptToProxyIfNoMatchingExpectation": False,
                        "preventCertificateDynamicUpdate": True,
                        "sslSubjectAlternativeNameDomains": ["localhost"],
                        "sslSubjectAlternativeNameIps": ["127.0.0.1"],
                    },
                )
                if method == "PUT":
                    assert data_path is not None
                    configuration.update(
                        json.loads(data_path.read_text(encoding="utf-8"))
                    )
                return CommandResult(
                    0,
                    json.dumps(configuration),
                    "",
                )
            if url.endswith("/mockserver/expectation") and method == "PUT":
                assert data_path is not None
                loaded = json.loads(data_path.read_text(encoding="utf-8"))
                normalized = loaded if isinstance(loaded, list) else [loaded]
                if is_canary:
                    self.canary_expectations[worker.id] = normalized
                else:
                    self.expectations[worker.id] = normalized
                return CommandResult(0, "{}", "")
            if "retrieve?type=REQUESTS" in url:
                requests = (
                    self.canary_requests
                    if is_canary
                    else self.requests
                )
                return CommandResult(0, json.dumps(requests.get(worker.id, [])), "")
            if "retrieve?type=ACTIVE_EXPECTATIONS" in url:
                expectations = (
                    self.canary_expectations
                    if is_canary
                    else self.expectations
                )
                return CommandResult(
                    0,
                    json.dumps(expectations.get(worker.id, [])),
                    "",
                )
            return CommandResult(0, "{}", "")
        return CommandResult(0, "", "")

    def invalidate_worker(self, worker: SandboxWorker) -> None:
        self.invalidated.append(worker.id)
        if self.invalidate_error is not None:
            raise self.invalidate_error

    def execute(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
        argv: tuple[str, ...],
        *,
        timeout_seconds: int,
        environment: dict[str, str] | None = None,
    ) -> CommandResult:
        del case, timeout_seconds, environment
        self.actor_calls.append((worker.id, argv))
        if argv[:1] == ("test",):
            return CommandResult(0, "", "")
        if argv[:1] == ("curl",):
            if any("ai-skills-passthrough-canary.invalid" in item for item in argv):
                return CommandResult(0, "404", "")
            return CommandResult(0, "403", "")
        return CommandResult(1, "", "unexpected actor command")


class FixtureDefinitionTests(unittest.TestCase):
    def test_fixture_domain_errors_never_expose_high_confidence_values(self) -> None:
        credential = "gh" + "p_" + ("a" * 36)

        error = FixtureProxyError(f"fixture failed for {credential}")

        self.assertNotIn(credential, str(error))
        self.assertIn("[REDACTED]", str(error))

    def test_validates_the_official_pinned_schema_offline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_root = root / "fixtures"
            fixture_root.mkdir()
            path = fixture_root / "mockserverInitialization.json"
            path.write_text(json.dumps(valid_expectations()), encoding="utf-8")

            definition = load_fixture_definition(
                path,
                manifest=MANIFEST,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture_root,
            )

        self.assertEqual(definition.expectations[0]["id"], "get-repository")
        self.assertEqual(len(definition.sha256), 64)

    def test_rejects_nonfinite_and_resource_hostile_fixture_json_boundedly(self) -> None:
        hostile_documents = (
            "NaN",
            "Infinity",
            "[" * 200 + "0" + "]" * 200,
            "9" * 5000,
        )
        with tempfile.TemporaryDirectory() as directory:
            fixture_root = Path(directory)
            path = fixture_root / "mockserverInitialization.json"
            for document in hostile_documents:
                with self.subTest(prefix=document[:12]):
                    path.write_text(document, encoding="utf-8")
                    with self.assertRaises(FixtureProxyError) as raised:
                        load_fixture_definition(
                            path,
                            manifest=MANIFEST,
                            repository_root=REPOSITORY_ROOT,
                            allowed_fixture_root=fixture_root,
                        )
                    self.assertIn("parser limits", str(raised.exception))
                    self.assertLess(len(str(raised.exception)), 128)

    def test_rejects_nonfinite_json_embedded_in_exact_body_matchers(self) -> None:
        document = valid_expectations()
        document[0]["httpRequest"]["body"]["json"] = '{"score": NaN}'
        with tempfile.TemporaryDirectory() as directory:
            fixture_root = Path(directory)
            path = fixture_root / "mockserverInitialization.json"
            path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(FixtureProxyError, "request JSON body is invalid"):
                load_fixture_definition(
                    path,
                    manifest=MANIFEST,
                    repository_root=REPOSITORY_ROOT,
                    allowed_fixture_root=fixture_root,
                )

    def test_rejects_empty_or_underspecified_request_matchers(self) -> None:
        invalid_requests = (
            {},
            {"method": "GET", "path": "/resource"},
            {"path": "/resource", "headers": {"Host": ["api.example.com"]}},
            {"method": "GET", "headers": {"Host": ["api.example.com"]}},
            {"method": "", "path": "/resource", "headers": {"Host": ["api.example.com"]}},
            {"method": "GET", "path": "", "headers": {"Host": ["api.example.com"]}},
            {
                "method": "GET",
                "path": "/resource",
                "headers": {"Host": ["api.example.com", "backup.example.com"]},
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            fixture_root = Path(directory)
            for index, request in enumerate(invalid_requests):
                with self.subTest(index=index):
                    path = fixture_root / f"underspecified-{index}.json"
                    path.write_text(
                        json.dumps(
                            {
                                "httpRequest": request,
                                "httpResponse": {"statusCode": 200},
                            }
                        ),
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(FixtureProxyError, "method|path|Host"):
                        load_fixture_definition(
                            path,
                            manifest=MANIFEST,
                            repository_root=REPOSITORY_ROOT,
                            allowed_fixture_root=fixture_root,
                        )

    def test_rejects_fixture_definitions_over_the_total_request_limit(self) -> None:
        expectations = []
        for index in range(MANIFEST.mockserver.maximum_expected_requests + 1):
            expectations.append(
                {
                    "id": f"request-{index}",
                    "httpRequest": {
                        "method": "GET",
                        "path": f"/resource/{index}",
                        "headers": {"Host": ["api.example.com"]},
                    },
                    "httpResponse": {"statusCode": 200},
                }
            )
        with tempfile.TemporaryDirectory() as directory:
            fixture_root = Path(directory)
            path = fixture_root / "mockserverInitialization.json"
            path.write_text(json.dumps(expectations), encoding="utf-8")

            with self.assertRaisesRegex(FixtureProxyError, "total request limit"):
                load_fixture_definition(
                    path,
                    manifest=MANIFEST,
                    repository_root=REPOSITORY_ROOT,
                    allowed_fixture_root=fixture_root,
                )

    def test_rejects_schema_invalid_or_unsafe_mockserver_actions(self) -> None:
        invalid_cases = (
            ({"httpRequest": {"method": 42}, "httpResponse": {"statusCode": 200}}, "schema"),
            (
                {
                    "httpRequest": {"method": "GET", "path": "/"},
                    "httpForward": {"host": "production.example.com", "port": 443},
                },
                "action",
            ),
            (
                {
                    "httpRequest": {"method": "GET", "path": "/"},
                    "httpResponseTemplate": {"template": "return request;", "templateType": "JAVASCRIPT"},
                },
                "action",
            ),
            (
                {
                    "httpRequest": {
                        "method": "GET",
                        "path": "/",
                        "headers": {"Host": ["api.example.com"]},
                    },
                    "httpResponse": {"body": {"type": "FILE", "filePath": "/etc/passwd"}},
                },
                "file",
            ),
            (
                {
                    "httpRequest": {
                        "method": "GET",
                        "path": "/",
                        "headers": {"Host": ["api.example.com"]},
                    },
                    "httpResponse": {
                        "delay": {
                            "template": "{{ request.path.length }}",
                            "templateType": "MUSTACHE",
                        }
                    },
                },
                "response option",
            ),
            (
                {
                    "httpRequest": {
                        "method": "GET",
                        "path": "/",
                        "headers": {"Host": ["api.example.com"]},
                    },
                    "httpError": {
                        "delay": {
                            "template": "$request.path.length()",
                            "templateType": "VELOCITY",
                        },
                        "dropConnection": True,
                    },
                },
                "error option",
            ),
            (
                {
                    "httpRequest": {
                        "method": "POST",
                        "path": "/",
                        "headers": {"Host": ["api.example.com"]},
                        "body": {
                            "type": "JSON",
                            "json": '{"ok":true}',
                            "matchType": "ONLY_MATCHING_FIELDS",
                        },
                    },
                    "httpResponse": {"statusCode": 200},
                },
                "request body",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_root = root / "fixtures"
            fixture_root.mkdir()
            for index, (payload, message) in enumerate(invalid_cases):
                with self.subTest(index=index):
                    path = fixture_root / f"invalid-{index}.json"
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(FixtureProxyError, message):
                        load_fixture_definition(
                            path,
                            manifest=MANIFEST,
                            repository_root=REPOSITORY_ROOT,
                            allowed_fixture_root=fixture_root,
                        )

    def test_rejects_a_fixture_outside_the_declared_fixture_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_root = root / "fixtures"
            fixture_root.mkdir()
            outside = root / "outside.json"
            outside.write_text(json.dumps(valid_expectations()), encoding="utf-8")

            with self.assertRaisesRegex(FixtureProxyError, "outside"):
                load_fixture_definition(
                    outside,
                    manifest=MANIFEST,
                    repository_root=REPOSITORY_ROOT,
                    allowed_fixture_root=fixture_root,
                )


class FixtureProxyLifecycleTests(unittest.TestCase):
    def _fixture(self, root: Path) -> Path:
        fixture_root = root / "fixtures"
        fixture_root.mkdir()
        path = fixture_root / "mockserverInitialization.json"
        path.write_text(json.dumps(valid_expectations()), encoding="utf-8")
        return path

    def test_preflight_proves_private_control_state_and_unauthenticated_denial(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = FakeFixtureRuntime({worker.id: generated_ca("worker-one")})
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )

            proxy.preflight(worker, case)
            self.assertIn(worker.id, proxy._states)
            proxy.retire_preflight(worker)

        commands = [argv for _, argv in runtime.actor_calls]
        self.assertTrue(any(argv[:1] == ("test",) for argv in commands))
        self.assertTrue(any(argv[:1] == ("curl",) for argv in commands))
        reset = next(
            argv
            for argv in commands
            if argv[:1] == ("curl",)
            and argv[-1].endswith("/mockserver/reset")
        )
        self.assertEqual(reset[reset.index("--request") + 1], "PUT")
        status_methods = [
            argv[argv.index("--request") + 1]
            for _, argv, _ in runtime.calls
            if argv[:1] == ("curl",)
            and argv[argv.index("--url") + 1].endswith("/mockserver/status")
        ]
        self.assertTrue(status_methods)
        self.assertEqual(set(status_methods), {"PUT"})
        self.assertEqual(runtime.invalidated, [])
        self.assertNotIn(worker.id, proxy._states)
        self.assertTrue(
            any(
                argv[:3] == ("docker", "rm", "--force")
                and "canary" not in argv[-1]
                for _, argv, _ in runtime.calls
            )
        )
        self.assertTrue(
            any(
                argv[:3] == ("test", "!", "-e")
                and argv[-1].endswith("fixture-control")
                for _, argv, _ in runtime.calls
            )
        )

    def test_preflight_does_not_mutate_fixture_projection_after_actor_execution(self) -> None:
        class ProtectedProjectionRuntime(FakeFixtureRuntime):
            def __init__(self, certificates):
                super().__init__(certificates)
                self.actor_started = False

            def run_worker_control(
                self,
                worker,
                argv,
                *,
                accepted_returncodes=(0,),
            ):
                if (
                    self.actor_started
                    and argv[:1] in {("chown",), ("chmod",), ("rm",)}
                    and any(
                        item == str(worker.host_root)
                        or item.startswith(f"{worker.host_root}/")
                        for item in argv
                    )
                ):
                    return CommandResult(30, "", "read-only projection")
                return super().run_worker_control(
                    worker,
                    argv,
                    accepted_returncodes=accepted_returncodes,
                )

            def execute(
                self,
                worker,
                case,
                argv,
                *,
                timeout_seconds,
                environment=None,
            ):
                self.actor_started = True
                return super().execute(
                    worker,
                    case,
                    argv,
                    timeout_seconds=timeout_seconds,
                    environment=environment,
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = ProtectedProjectionRuntime(
                {worker.id: generated_ca("worker-one")}
            )
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )

            proxy.preflight(worker, case)
            self.assertIn(worker.id, proxy._states)
            runtime.actor_started = False
            proxy.retire_preflight(worker)

        self.assertEqual(runtime.invalidated, [])
        self.assertNotIn(worker.id, proxy._states)

    def test_preflight_retirement_failure_drops_state_and_invalidates_worker(
        self,
    ) -> None:
        class ControlRemovalFailureRuntime(FakeFixtureRuntime):
            def run_worker_control(
                self,
                worker,
                argv,
                *,
                accepted_returncodes=(0,),
            ):
                if (
                    argv[:3] == ("rm", "-rf", "--")
                    and argv[-1] == str(worker.host_root / "fixture-control")
                ):
                    self.calls.append((worker.id, argv, accepted_returncodes))
                    return CommandResult(30, "", "read-only worker projection")
                return super().run_worker_control(
                    worker,
                    argv,
                    accepted_returncodes=accepted_returncodes,
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = ControlRemovalFailureRuntime(
                {worker.id: generated_ca("worker-one")}
            )
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )
            proxy.preflight(worker, case)

            with self.assertRaisesRegex(
                FixtureProxyError,
                "fixture control command failed",
            ):
                proxy.retire_preflight(worker)

        self.assertEqual(runtime.invalidated, [worker.id])
        self.assertNotIn(worker.id, proxy._states)

    def test_preflight_rejects_actor_access_to_the_actual_put_reset_operation(self) -> None:
        class PutResetAllowedRuntime(FakeFixtureRuntime):
            def execute(self, worker, case, argv, *, timeout_seconds, environment=None):
                if (
                    argv[:1] == ("curl",)
                    and argv[-1].endswith("/mockserver/reset")
                ):
                    method = (
                        argv[argv.index("--request") + 1]
                        if "--request" in argv
                        else "GET"
                    )
                    if method == "PUT":
                        self.expectations[worker.id] = []
                        return CommandResult(0, "200", "")
                    return CommandResult(0, "403", "")
                return super().execute(
                    worker,
                    case,
                    argv,
                    timeout_seconds=timeout_seconds,
                    environment=environment,
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = PutResetAllowedRuntime(
                {worker.id: generated_ca("worker-one")}
            )
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )

            with self.assertRaisesRegex(
                FixtureProxyError,
                "control endpoint was not denied",
            ):
                proxy.preflight(worker, case)

        self.assertEqual(runtime.invalidated, [worker.id])

    def test_preflight_rejects_effective_passthrough_configuration(self) -> None:
        class PassthroughConfigurationRuntime(FakeFixtureRuntime):
            def run_worker_control(
                self,
                worker,
                argv,
                *,
                accepted_returncodes=(0,),
            ):
                if (
                    argv[:1] == ("curl",)
                    and "--url" in argv
                    and argv[argv.index("--url") + 1].endswith(
                        "/mockserver/configuration"
                    )
                ):
                    self.calls.append((worker.id, argv, accepted_returncodes))
                    return CommandResult(
                        0,
                        json.dumps(
                            {"attemptToProxyIfNoMatchingExpectation": True}
                        ),
                        "",
                    )
                return super().run_worker_control(
                    worker,
                    argv,
                    accepted_returncodes=accepted_returncodes,
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = PassthroughConfigurationRuntime(
                {worker.id: generated_ca("worker-one")}
            )
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )

            with self.assertRaisesRegex(
                FixtureProxyError,
                "effective configuration",
            ):
                proxy.preflight(worker, case)

        self.assertEqual(runtime.invalidated, [worker.id])

    def test_preflight_canary_detects_an_unmatched_forward(self) -> None:
        class ForwardingRuntime(FakeFixtureRuntime):
            def execute(self, worker, case, argv, *, timeout_seconds, environment=None):
                if any(
                    "ai-skills-passthrough-canary.invalid" in item
                    for item in argv
                ):
                    self.canary_requests.setdefault(worker.id, []).append(
                        {
                            "method": "GET",
                            "path": "/ai-skills-no-passthrough-canary",
                        }
                    )
                    return CommandResult(0, "204", "")
                return super().execute(
                    worker,
                    case,
                    argv,
                    timeout_seconds=timeout_seconds,
                    environment=environment,
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = ForwardingRuntime(
                {worker.id: generated_ca("worker-one")}
            )
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )

            with self.assertRaisesRegex(
                FixtureProxyError,
                "forwarded an unmatched request",
            ):
                proxy.preflight(worker, case)

        self.assertEqual(runtime.invalidated, [worker.id])
        canary_removals = [
            argv
            for _, argv, _ in runtime.calls
            if argv[:3] == ("docker", "rm", "--force")
            and "canary" in argv[-1]
        ]
        canary_run = next(
            argv
            for _, argv, _ in runtime.calls
            if argv[:2] == ("docker", "run")
            and "canary" in argv[argv.index("--name") + 1]
        )
        self.assertGreaterEqual(len(canary_removals), 2)
        self.assertIn(
            ("--log-driver", "none"),
            tuple(zip(canary_run, canary_run[1:])),
        )

    def test_preflight_recycles_worker_when_canary_cleanup_is_unproven(self) -> None:
        class UnprovenCanaryCleanupRuntime(FakeFixtureRuntime):
            def __init__(self, certificates):
                super().__init__(certificates)
                self.canary_removals = 0
                self.failed_final_removal = False

            def run_worker_control(
                self,
                worker,
                argv,
                *,
                accepted_returncodes=(0,),
            ):
                is_canary = "canary" in argv[-1] if argv else False
                if argv[:3] == ("docker", "rm", "--force") and is_canary:
                    self.calls.append((worker.id, argv, accepted_returncodes))
                    self.canary_removals += 1
                    if self.canary_removals == 2:
                        self.failed_final_removal = True
                        return CommandResult(1, "", "daemon error")
                    return CommandResult(1, "", "not found")
                if (
                    argv[:3] == ("docker", "ps", "--all")
                    and self.failed_final_removal
                ):
                    self.calls.append((worker.id, argv, accepted_returncodes))
                    return CommandResult(0, "still-running-container\n", "")
                return super().run_worker_control(
                    worker,
                    argv,
                    accepted_returncodes=accepted_returncodes,
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = UnprovenCanaryCleanupRuntime(
                {worker.id: generated_ca("worker-one")}
            )
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )

            with self.assertRaisesRegex(
                FixtureProxyError,
                "canary container remains",
            ):
                proxy.preflight(worker, case)

        self.assertEqual(runtime.invalidated, [worker.id])
        self.assertEqual(runtime.canary_removals, 2)

    def test_starts_pinned_fail_closed_sidecar_and_exposes_only_public_ca(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = FakeFixtureRuntime({worker.id: generated_ca("worker-one")})
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )

            session = proxy.prepare_case(worker, case, fixture, fixture.parent)

            control_dir = worker.host_root / "fixture-control"
            jwks = json.loads((control_dir / "jwks.json").read_text(encoding="utf-8"))
            curl_config = (control_dir / "curl.conf").read_text(encoding="utf-8")
            token = curl_config.split("Bearer ", 1)[1].split('"', 1)[0]
            public_key = jwt.PyJWK(jwks["keys"][0]).key
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience="ai-skills-fixture-control",
            )

            self.assertEqual(claims["sub"], worker.id)
            self.assertFalse(any("PRIVATE KEY" in path.read_text(errors="ignore") for path in control_dir.iterdir() if path.is_file()))
            self.assertTrue((case.bootstrap / "mockserver-ca.pem").is_file())
            self.assertEqual(dict(session.shell_environment)["HTTPS_PROXY"], "http://127.0.0.1:1080")
            self.assertEqual(
                dict(session.shell_environment)["SSL_CERT_FILE"],
                str(case.bootstrap / "mockserver-ca.pem"),
            )

            docker_run = next(
                argv
                for _, argv, _ in runtime.calls
                if argv[:2] == ("docker", "run")
            )
            rendered = " ".join(docker_run)
            self.assertIn(MANIFEST.mockserver.image_reference, docker_run)
            self.assertIn(
                ("--log-driver", "none"),
                tuple(zip(docker_run, docker_run[1:])),
            )
            self.assertIn("127.0.0.1", rendered)
            self.assertIn("MOCKSERVER_DYNAMICALLY_CREATE_CERTIFICATE_AUTHORITY_CERTIFICATE=true", docker_run)
            self.assertIn(
                "MOCKSERVER_PREVENT_CERTIFICATE_DYNAMIC_UPDATE=true",
                docker_run,
            )
            self.assertIn("MOCKSERVER_ATTEMPT_TO_PROXY_IF_NO_MATCHING_EXPECTATION=false", docker_run)
            self.assertIn("MOCKSERVER_CONTROL_PLANE_JWT_AUTHENTICATION_REQUIRED=true", docker_run)
            self.assertIn("MOCKSERVER_MATCH_EXACT_CASE=true", docker_run)
            self.assertNotIn("Authorization: Bearer", rendered)

    def test_proves_declared_tls_subjects_with_real_proxy_handshakes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = FakeFixtureRuntime(
                {worker.id: generated_ca("worker-one")}
            )
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )

            proxy.prepare_case(worker, case, fixture, fixture.parent)

        probes = [
            argv
            for _, argv, _ in runtime.calls
            if argv[:1] == ("curl",)
            and "--write-out" in argv
            and argv[argv.index("--write-out") + 1]
            == "%{ssl_verify_result}"
        ]
        self.assertEqual(len(probes), 1)
        self.assertEqual(
            probes[0][probes[0].index("--url") + 1],
            (
                "https://api.bitbucket.org/"
                ".well-known/ai-skills-fixture-tls-probe"
            ),
        )

    def test_tls_handshake_failure_invalidates_the_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = FakeFixtureRuntime(
                {worker.id: generated_ca("worker-one")}
            )
            runtime.tls_probe_failure = True
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )

            with self.assertRaises(FixtureProxyError):
                proxy.prepare_case(worker, case, fixture, fixture.parent)

        self.assertEqual(runtime.invalidated, [worker.id])
        self.assertNotIn(worker.id, proxy._states)

    def test_recreated_sidecar_must_not_reuse_the_retired_ca(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = FakeFixtureRuntime(
                {worker.id: generated_ca("reused-worker-ca")}
            )
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )
            session = proxy.prepare_case(
                worker,
                case,
                fixture,
                fixture.parent,
            )
            runtime.requests[worker.id] = [
                {
                    "method": "GET",
                    "path": "/2.0/repositories/acme/widget",
                    "headers": {"Host": ["api.bitbucket.org"]},
                    "queryStringParameters": {"page": ["1"]},
                    "body": {"type": "JSON", "json": '{"owner":"acme"}'},
                }
            ]
            proxy.collect_and_reset(worker, case, session)

            with self.assertRaisesRegex(
                FixtureProxyError,
                "retired certificate authority",
            ):
                proxy.prepare_case(worker, case, fixture, fixture.parent)

        self.assertEqual(runtime.invalidated, [worker.id])
        self.assertNotIn(worker.id, proxy._states)

    def test_uploads_authored_request_strings_as_literal_matchers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            fixture.write_text(
                json.dumps(
                    {
                        "httpRequest": {
                            "method": "GET",
                            "path": "/v1/.*",
                            "headers": {"Host": ["api.example.com"]},
                        },
                        "httpResponse": {"statusCode": 200},
                    }
                ),
                encoding="utf-8",
            )
            runtime = FakeFixtureRuntime({worker.id: generated_ca("worker-one")})
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )

            session = proxy.prepare_case(worker, case, fixture, fixture.parent)
            uploaded = json.loads(
                (worker.host_root / "fixture-control" / "case-expectations.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(uploaded[0]["httpRequest"]["path"], r"\Q/v1/.*\E")
        self.assertEqual(
            uploaded[0]["httpRequest"]["headers"][r"\QHost\E"],
            [r"\Qapi.example.com\E"],
        )
        self.assertEqual(session.expected_requests[0]["path"], "/v1/.*")

    def test_interruption_after_expectation_upload_recycles_worker_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = FakeFixtureRuntime(
                {
                    worker.id: [
                        generated_ca("preflight"),
                        generated_ca("first-case"),
                    ]
                }
            )
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )
            proxy.preflight(worker, case)
            proxy.retire_preflight(worker)
            original_curl = proxy._curl

            def interrupt_after_upload(*args, **kwargs):
                result = original_curl(*args, **kwargs)
                if args[2:4] == ("PUT", "/mockserver/expectation"):
                    raise KeyboardInterrupt()
                return result

            with (
                mock.patch.object(proxy, "_curl", side_effect=interrupt_after_upload),
                self.assertRaises(KeyboardInterrupt),
            ):
                proxy.prepare_case(worker, case, fixture, fixture.parent)

        self.assertIn(worker.id, runtime.invalidated)
        self.assertNotIn(worker.id, proxy._states)
        self.assertEqual(runtime.certificate_reads[worker.id], 2)

    def test_interruption_after_request_capture_recycles_worker_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = FakeFixtureRuntime({worker.id: generated_ca("worker-one")})
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )
            session = proxy.prepare_case(worker, case, fixture, fixture.parent)
            runtime.requests[worker.id] = [
                {
                    "method": "GET",
                    "path": "/2.0/repositories/acme/widget",
                    "headers": {"Host": ["api.bitbucket.org"]},
                    "queryStringParameters": {"page": ["1"]},
                    "body": {"type": "JSON", "json": '{"owner":"acme"}'},
                }
            ]
            original_reset = proxy._reset_and_verify_empty

            def interrupt_after_reset(*args, **kwargs):
                result = original_reset(*args, **kwargs)
                raise KeyboardInterrupt()

            with (
                mock.patch.object(
                    proxy,
                    "_reset_and_verify_empty",
                    side_effect=interrupt_after_reset,
                ),
                self.assertRaises(KeyboardInterrupt),
            ):
                proxy.collect_and_reset(worker, case, session)

        self.assertIn(worker.id, runtime.invalidated)
        self.assertNotIn(worker.id, proxy._states)

    def test_reuses_worker_with_a_fresh_sidecar_and_ca_for_each_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, first_case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = FakeFixtureRuntime(
                {
                    worker.id: [
                        generated_ca("worker-one-first"),
                        generated_ca("worker-one-second"),
                    ]
                }
            )
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )

            first_session = proxy.prepare_case(
                worker,
                first_case,
                fixture,
                fixture.parent,
            )
            first_ca = (first_case.bootstrap / "mockserver-ca.pem").read_bytes()
            runtime.requests[worker.id] = [
                {
                    "method": "GET",
                    "path": "/2.0/repositories/acme/widget",
                    "headers": {"Host": ["api.bitbucket.org"]},
                    "queryStringParameters": {"page": ["1"]},
                    "body": {"type": "JSON", "json": '{"owner":"acme"}'},
                }
            ]
            proxy.collect_and_reset(worker, first_case, first_session)
            second_root = root / "second-case"
            _, second_case = worker_and_case(second_root, "actor-two")
            second_case = CaseWorkspace(
                **{
                    **second_case.__dict__,
                    "root": worker.host_root / "second-case",
                    "home": worker.host_root / "second-case" / "home",
                    "codex_home": worker.host_root / "second-case" / "codex-home",
                    "tmpdir": worker.host_root / "second-case" / "tmp",
                    "workspace": worker.host_root / "second-case" / "workspace",
                    "skills": worker.host_root / "second-case" / "codex-home" / "skills",
                    "bootstrap": worker.host_root / "second-case" / "bootstrap",
                    "case_id": "fixture-case-two",
                    "user_name": "ai-eval-2",
                    "uid": 20002,
                }
            )
            for path in (
                second_case.home,
                second_case.codex_home,
                second_case.tmpdir,
                second_case.workspace,
                second_case.skills,
                second_case.bootstrap,
            ):
                path.mkdir(parents=True, exist_ok=True)

            second_definition = valid_expectations()
            second_definition[0]["httpRequest"]["headers"]["Host"] = [
                "api.github.com"
            ]
            fixture.write_text(
                json.dumps(second_definition),
                encoding="utf-8",
            )
            proxy.prepare_case(worker, second_case, fixture, fixture.parent)
            second_ca = (second_case.bootstrap / "mockserver-ca.pem").read_bytes()

        docker_runs = [argv for _, argv, _ in runtime.calls if argv[:2] == ("docker", "run")]
        sidecar_removals = [
            argv
            for _, argv, _ in runtime.calls
            if argv[:3] == ("docker", "rm", "--force")
            and "canary" not in argv[-1]
        ]
        expectation_calls = [
            argv
            for _, argv, _ in runtime.calls
            if argv[:1] == ("curl",) and "/expectation" in " ".join(argv)
        ]
        self.assertEqual(len(docker_runs), 2)
        self.assertGreaterEqual(len(sidecar_removals), 3)
        self.assertEqual(len(expectation_calls), 2)
        self.assertNotEqual(first_ca, second_ca)
        self.assertEqual(runtime.certificate_reads[worker.id], 2)
        self.assertEqual(
            runtime.configurations[worker.id][
                "sslSubjectAlternativeNameDomains"
            ],
            ["api.github.com"],
        )
        self.assertNotIn(
            "api.bitbucket.org",
            runtime.configurations[worker.id][
                "sslSubjectAlternativeNameDomains"
            ],
        )

    def test_waits_for_cold_mockserver_startup_with_a_bounded_probe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = FakeFixtureRuntime({worker.id: generated_ca("worker-one")})
            runtime.status_failures_remaining = 2
            sleeps: list[float] = []
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
                sleeper=sleeps.append,
            )

            proxy.prepare_case(worker, case, fixture, fixture.parent)

        status_calls = [
            argv
            for _, argv, _ in runtime.calls
            if argv[:1] == ("curl",) and "/status" in " ".join(argv)
        ]
        self.assertEqual(len(status_calls), 3)
        self.assertEqual(sleeps, [0.5, 0.5])

    def test_rejects_the_bundled_default_ca_and_shared_ca_between_workers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self._fixture(root)
            first_worker, first_case = worker_and_case(root, "first")
            second_worker, second_case = worker_and_case(root, "second")
            shared = generated_ca("shared")
            runtime = FakeFixtureRuntime(
                {first_worker.id: shared, second_worker.id: shared}
            )
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )
            proxy.prepare_case(first_worker, first_case, fixture, fixture.parent)

            with self.assertRaisesRegex(FixtureProxyError, "shared"):
                proxy.prepare_case(second_worker, second_case, fixture, fixture.parent)

        self.assertIn(second_worker.id, runtime.invalidated)

    def test_rejects_the_manifest_pinned_bundled_default_ca(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self._fixture(root)
            worker, case = worker_and_case(root)
            certificate_pem = generated_ca("pinned-default")
            fingerprint = x509.load_pem_x509_certificate(certificate_pem).fingerprint(
                hashes.SHA256()
            ).hex()
            runtime = FakeFixtureRuntime({worker.id: certificate_pem})
            runtime.manifest = replace(
                MANIFEST,
                mockserver=replace(
                    MANIFEST.mockserver,
                    bundled_default_ca_sha256=fingerprint,
                ),
            )
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )

            with self.assertRaisesRegex(FixtureProxyError, "bundled default CA"):
                proxy.prepare_case(worker, case, fixture, fixture.parent)

        self.assertIn(worker.id, runtime.invalidated)

    def test_collects_sanitized_request_evidence_and_resets_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            fixture.write_text(
                json.dumps(
                    [
                        {
                            "id": "graphql-request",
                            "httpRequest": {
                                "method": "POST",
                                "path": "/graphql/FAKE_path_secret",
                                "headers": {"Host": ["api.example.com"]},
                                "body": {
                                    "type": "JSON",
                                    "json": json.dumps(
                                        {
                                            "operationName": "FindIssue",
                                            "apiToken": "FAKE_secret",
                                            "comment": "FAKE_sk-abcdefghijklmnopqrstuv",
                                            "FAKE_object_key": "ordinary",
                                        }
                                    ),
                                },
                            },
                            "httpResponse": {"statusCode": 200},
                            "times": {"remainingTimes": 1, "unlimited": False},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            runtime = FakeFixtureRuntime({worker.id: generated_ca("worker-one")})
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )
            session = proxy.prepare_case(worker, case, fixture, fixture.parent)
            runtime.requests[worker.id] = [
                {
                    "method": "POST",
                    "path": "/graphql/FAKE_path_secret",
                    "headers": {
                        "Host": ["api.example.com"],
                        "Authorization": ["Bearer FAKE_secret"],
                        "Content-Type": ["application/json"],
                    },
                    "queryStringParameters": {"page": ["1"], "token": ["FAKE_secret"]},
                    "body": {
                        "type": "JSON",
                        "json": (
                            '{"operationName":"FindIssue","apiToken":"FAKE_secret",'
                            '"comment":"FAKE_sk-abcdefghijklmnopqrstuv",'
                            '"FAKE_object_key":"ordinary"}'
                        ),
                    },
                }
            ]

            events = proxy.collect_and_reset(worker, case, session)

        serialized = json.dumps(events)
        self.assertIn("api.example.com", serialized)
        self.assertIn("FindIssue", serialized)
        self.assertNotIn("FAKE_secret", serialized)
        self.assertNotIn("FAKE_path_secret", serialized)
        self.assertNotIn("FAKE_object_key", serialized)
        self.assertNotIn("abcdefghijklmnopqrstuv", serialized)
        self.assertNotIn("Bearer", serialized)
        self.assertIn("[REDACTED]", serialized)
        self.assertTrue(any(event.get("event") == "fixture_request" for event in events))
        self.assertTrue(any("/reset" in " ".join(argv) for _, argv, _ in runtime.calls))
        self.assertNotIn(worker.id, proxy._states)
        self.assertIn(worker.id, proxy._retired_ca_sha256)

    def test_omits_oversized_request_body_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            body = {"payload": "x" * (70 * 1024)}
            fixture.write_text(
                json.dumps(
                    [
                        {
                            "httpRequest": {
                                "method": "POST",
                                "path": "/large",
                                "headers": {"Host": ["api.example.com"]},
                                "body": {"type": "JSON", "json": json.dumps(body)},
                            },
                            "httpResponse": {"statusCode": 200},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            runtime = FakeFixtureRuntime({worker.id: generated_ca("worker-one")})
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )
            session = proxy.prepare_case(worker, case, fixture, fixture.parent)
            runtime.requests[worker.id] = [
                {
                    "method": "POST",
                    "path": "/large",
                    "headers": {"Host": ["api.example.com"]},
                    "body": {"type": "JSON", "json": json.dumps(body)},
                }
            ]

            events = proxy.collect_and_reset(worker, case, session)

        self.assertNotIn("body_json", events[0])
        self.assertLess(len(json.dumps(events).encode("utf-8")), 10 * 1024)

    def test_rejects_missing_unexpected_and_out_of_order_fixture_calls(self) -> None:
        invalid_requests = (
            [],
            [
                {
                    "method": "GET",
                    "path": "/unexpected",
                    "headers": {"Host": ["api.bitbucket.org"]},
                }
            ],
            [
                {
                    "method": "GET",
                    "path": "/2.0/repositories/acme/widget",
                    "headers": {"Host": ["api.bitbucket.org"]},
                    "queryStringParameters": {"page": ["1"]},
                    "body": {"type": "JSON", "json": '{"owner":"acme"}'},
                },
                {
                    "method": "GET",
                    "path": "/extra",
                    "headers": {"Host": ["api.bitbucket.org"]},
                },
            ],
        )
        for index, requests in enumerate(invalid_requests):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                worker, case = worker_and_case(root)
                fixture = self._fixture(root)
                runtime = FakeFixtureRuntime({worker.id: generated_ca(f"worker-{index}")})
                proxy = FixtureProxy(
                    runtime,
                    repository_root=REPOSITORY_ROOT,
                    allowed_fixture_root=fixture.parent,
                )
                session = proxy.prepare_case(worker, case, fixture, fixture.parent)
                runtime.requests[worker.id] = requests

                with self.assertRaisesRegex(FixtureProxyError, "request sequence") as caught:
                    proxy.collect_and_reset(worker, case, session)

                self.assertIn(worker.id, runtime.invalidated)
                if requests:
                    self.assertEqual(len(caught.exception.evidence), len(requests))
                    self.assertTrue(
                        all(
                            event.get("event") == "fixture_request"
                            for event in caught.exception.evidence
                        )
                    )

    def test_caps_preserved_evidence_for_excess_fixture_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = FakeFixtureRuntime({worker.id: generated_ca("worker-one")})
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )
            session = proxy.prepare_case(worker, case, fixture, fixture.parent)
            runtime.requests[worker.id] = [
                {
                    "method": "GET",
                    "path": f"/unexpected/{index}",
                    "headers": {"Host": ["api.example.com"]},
                }
                for index in range(129)
            ]

            with self.assertRaises(FixtureProxyError) as caught:
                proxy.collect_and_reset(worker, case, session)

        self.assertEqual(len(caught.exception.evidence), 128)

    def test_preserves_fixture_evidence_when_worker_invalidation_also_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = FakeFixtureRuntime({worker.id: generated_ca("worker-one")})
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )
            session = proxy.prepare_case(worker, case, fixture, fixture.parent)
            runtime.requests[worker.id] = [
                {
                    "method": "GET",
                    "path": "/unexpected",
                    "headers": {"Host": ["api.example.com"]},
                }
            ]
            runtime.invalidate_error = RuntimeError("worker removal failed")

            with self.assertRaises(FixtureProxyError) as caught:
                proxy.collect_and_reset(worker, case, session)

        self.assertEqual(len(caught.exception.evidence), 1)
        self.assertIn("worker removal failed", str(caught.exception))

    def test_rejects_a_fixture_call_sequence_in_the_wrong_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            fixture.write_text(
                json.dumps(
                    [
                        {
                            "httpRequest": {
                                "method": "GET",
                                "path": "/first",
                                "headers": {"Host": ["api.example.com"]},
                            },
                            "httpResponse": {"statusCode": 200},
                        },
                        {
                            "httpRequest": {
                                "method": "GET",
                                "path": "/second",
                                "headers": {"Host": ["api.example.com"]},
                            },
                            "httpResponse": {"statusCode": 200},
                        },
                    ]
                ),
                encoding="utf-8",
            )
            runtime = FakeFixtureRuntime({worker.id: generated_ca("worker-one")})
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )
            session = proxy.prepare_case(worker, case, fixture, fixture.parent)
            runtime.requests[worker.id] = [
                {
                    "method": "GET",
                    "path": "/second",
                    "headers": {"Host": ["api.example.com"]},
                },
                {
                    "method": "GET",
                    "path": "/first",
                    "headers": {"Host": ["api.example.com"]},
                },
            ]

            with self.assertRaisesRegex(FixtureProxyError, "call 1"):
                proxy.collect_and_reset(worker, case, session)

    def test_collection_retires_only_runner_private_control_state(self) -> None:
        class ProtectedProjectionRuntime(FakeFixtureRuntime):
            def __init__(self, certificates):
                super().__init__(certificates)
                self.projection_protected = False

            def run_worker_control(
                self,
                worker,
                argv,
                *,
                accepted_returncodes=(0,),
            ):
                if (
                    self.projection_protected
                    and argv[:1] in {("chown",), ("chmod",)}
                    and any(str(worker.host_root) in item for item in argv)
                ):
                    return CommandResult(30, "", "read-only projection")
                if (
                    self.projection_protected
                    and argv[:3] == ("rm", "-rf", "--")
                    and argv[-1] != str(worker.host_root / "fixture-control")
                ):
                    return CommandResult(30, "", "read-only projection")
                return super().run_worker_control(
                    worker,
                    argv,
                    accepted_returncodes=accepted_returncodes,
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = ProtectedProjectionRuntime(
                {worker.id: generated_ca("worker-one")}
            )
            now = [datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc)]
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
                clock=lambda: now[0],
            )
            session = proxy.prepare_case(worker, case, fixture, fixture.parent)
            first_token = (
                (worker.host_root / "fixture-control" / "curl.conf")
                .read_text(encoding="utf-8")
                .split("Bearer ", 1)[1]
                .split('"', 1)[0]
            )
            runtime.requests[worker.id] = [
                {
                    "method": "GET",
                    "path": "/2.0/repositories/acme/widget",
                    "headers": {"Host": ["api.bitbucket.org"]},
                    "queryStringParameters": {"page": ["1"]},
                    "body": {"type": "JSON", "json": '{"owner":"acme"}'},
                }
            ]
            now[0] += timedelta(
                seconds=(
                        MANIFEST.limits.actor_timeout_seconds
                        + (
                            MANIFEST.limits.preflight_timeout_seconds
                            * CONTROL_TOKEN_OPERATION_WINDOWS
                        )
                )
            )
            runtime.projection_protected = True

            proxy.collect_and_reset(worker, case, session)

        self.assertGreater(
            jwt.decode(first_token, options={"verify_signature": False})["exp"],
            int(now[0].timestamp()),
        )
        self.assertFalse((worker.host_root / "fixture-control").exists())


if __name__ == "__main__":
    unittest.main()
