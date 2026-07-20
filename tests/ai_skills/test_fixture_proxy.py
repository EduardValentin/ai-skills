from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from scripts.ai_skills_lib.fixture_proxy import (
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
    def __init__(self, certificates: dict[str, bytes]) -> None:
        self.manifest = MANIFEST
        self.certificates = certificates
        self.calls: list[tuple[str, tuple[str, ...], tuple[int, ...]]] = []
        self.invalidated: list[str] = []
        self.requests: dict[str, list[dict[str, object]]] = {}
        self.status_failures_remaining = 0
        self.actor_calls: list[tuple[str, tuple[str, ...]]] = []
        self.invalidate_error: Exception | None = None

    def run_worker_control(
        self,
        worker: SandboxWorker,
        argv: tuple[str, ...],
        *,
        accepted_returncodes: tuple[int, ...] = (0,),
    ) -> CommandResult:
        self.calls.append((worker.id, argv, accepted_returncodes))
        if argv[:2] == ("cat", "--") and argv[-1].endswith("mockserver-ca.pem"):
            return CommandResult(0, self.certificates[worker.id].decode(), "")
        if argv[:1] == ("curl",):
            url = argv[argv.index("--url") + 1]
            if url.endswith("/mockserver/status") and self.status_failures_remaining:
                self.status_failures_remaining -= 1
                return CommandResult(7, "", "not ready")
            if url.endswith("/mockserver/reset"):
                self.requests[worker.id] = []
                return CommandResult(0, "{}", "")
            if "retrieve?type=REQUESTS" in url:
                return CommandResult(0, json.dumps(self.requests.get(worker.id, [])), "")
            if "retrieve?type=ACTIVE_EXPECTATIONS" in url:
                return CommandResult(0, "[]", "")
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

        commands = [argv for _, argv in runtime.actor_calls]
        self.assertTrue(any(argv[:1] == ("test",) for argv in commands))
        self.assertTrue(any(argv[:1] == ("curl",) for argv in commands))
        self.assertEqual(runtime.invalidated, [])

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
            self.assertIn("127.0.0.1", rendered)
            self.assertIn("MOCKSERVER_DYNAMICALLY_CREATE_CERTIFICATE_AUTHORITY_CERTIFICATE=true", docker_run)
            self.assertIn("MOCKSERVER_ATTEMPT_TO_PROXY_IF_NO_MATCHING_EXPECTATION=false", docker_run)
            self.assertIn("MOCKSERVER_CONTROL_PLANE_JWT_AUTHENTICATION_REQUIRED=true", docker_run)
            self.assertIn("MOCKSERVER_MATCH_EXACT_CASE=true", docker_run)
            self.assertNotIn("Authorization: Bearer", rendered)

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
                            "headers": {"Host": [".*.example.com"]},
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
            [r"\Q.*.example.com\E"],
        )
        self.assertEqual(session.expected_requests[0]["path"], "/v1/.*")

    def test_reuses_one_sidecar_but_resets_and_reloads_each_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, first_case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = FakeFixtureRuntime({worker.id: generated_ca("worker-one")})
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture.parent,
            )

            proxy.prepare_case(worker, first_case, fixture, fixture.parent)
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

            proxy.prepare_case(worker, second_case, fixture, fixture.parent)

        docker_runs = [argv for _, argv, _ in runtime.calls if argv[:2] == ("docker", "run")]
        reset_calls = [argv for _, argv, _ in runtime.calls if argv[:1] == ("curl",) and "/reset" in " ".join(argv)]
        expectation_calls = [
            argv
            for _, argv, _ in runtime.calls
            if argv[:1] == ("curl",) and "/expectation" in " ".join(argv)
        ]
        self.assertEqual(len(docker_runs), 1)
        self.assertEqual(len(reset_calls), 2)
        self.assertEqual(len(expectation_calls), 2)

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

    def test_refreshes_control_credentials_before_post_run_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker, case = worker_and_case(root)
            fixture = self._fixture(root)
            runtime = FakeFixtureRuntime({worker.id: generated_ca("worker-one")})
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
            now[0] += timedelta(minutes=16)

            proxy.collect_and_reset(worker, case, session)
            second_token = (
                (worker.host_root / "fixture-control" / "curl.conf")
                .read_text(encoding="utf-8")
                .split("Bearer ", 1)[1]
                .split('"', 1)[0]
            )

        self.assertNotEqual(first_token, second_token)
        self.assertGreater(
            jwt.decode(second_token, options={"verify_signature": False})["exp"],
            int(now[0].timestamp()),
        )


if __name__ == "__main__":
    unittest.main()
