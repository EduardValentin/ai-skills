"""Shared Docker Sandboxes runtime lifecycle for model-backed evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import uuid

from scripts.ai_skills_lib.harness import HarnessAdapter
from scripts.ai_skills_lib.secret_patterns import bounded_redacted_runtime_text


EVALUATION_CLEANUP_FAILURE_MAXIMUM_BYTES = 8192


class EvaluationRuntimeError(RuntimeError):
    """Raised when the shared evaluation runtime cannot start or clean up."""


@dataclass
class CodexEvaluationRuntime:
    """One invocation-owned Codex runtime shared by trigger and behavior runners."""

    manifest: object
    adapter: HarnessAdapter
    runtime: object
    staging_root: Path

    @classmethod
    def create(
        cls,
        repository_root: Path,
        results_root: Path,
        *,
        invocation_label: str,
        max_concurrency: int,
    ) -> CodexEvaluationRuntime:
        from scripts.ai_skills_lib.codex_harness import CodexHarnessAdapter
        from scripts.ai_skills_lib.fixture_proxy import FixtureProxy
        from scripts.ai_skills_lib.sandbox_runtime import (
            EvalRuntimeManifest,
            SandboxRuntime,
            SubprocessRunner,
        )

        manifest = EvalRuntimeManifest.load(
            repository_root / "config" / "eval-runtime.json"
        )
        staging_root = (
            results_root.parent / f".ai-skills-workers-{uuid.uuid4().hex[:12]}"
        )
        runtime = SandboxRuntime(
            manifest=manifest,
            process=SubprocessRunner(manifest.limits.maximum_captured_output_bytes),
            repository_root=repository_root,
            results_root=results_root,
            staging_root=staging_root,
            invocation_id=f"{invocation_label}-{uuid.uuid4().hex[:10]}",
            max_concurrency=max_concurrency,
        )
        fixture_proxy = FixtureProxy(
            runtime,
            repository_root=repository_root,
            allowed_fixture_root=repository_root / "skills",
        )
        adapter = CodexHarnessAdapter(
            runtime,
            allowed_skill_root=repository_root / "skills",
            fixture_proxy=fixture_proxy,
        )
        return cls(
            manifest=manifest,
            adapter=adapter,
            runtime=runtime,
            staging_root=staging_root,
        )

    def close(self) -> None:
        """Discard host staging only after all sandbox cleanup is trustworthy."""
        try:
            self.runtime.close()
        except BaseException as error:
            cleanup_completed = (
                getattr(self.runtime, "sandbox_cleanup_completed", False) is True
            )
            if cleanup_completed:
                try:
                    self._remove_staging()
                except EvaluationRuntimeError as staging_error:
                    if not isinstance(error, Exception):
                        error.add_note(str(staging_error))
                        raise
                    raise staging_error from error
            if not isinstance(error, Exception):
                if not cleanup_completed:
                    error.add_note(
                        "sandbox cleanup is unresolved; worker staging was retained"
                    )
                raise
            diagnostic = bounded_redacted_runtime_text(
                f"sandbox cleanup failed: {error}",
                EVALUATION_CLEANUP_FAILURE_MAXIMUM_BYTES,
            )
            raise EvaluationRuntimeError(diagnostic) from error
        self._remove_staging()

    def _remove_staging(self) -> None:
        if self.staging_root.exists():
            try:
                shutil.rmtree(self.staging_root)
            except OSError as error:
                diagnostic = bounded_redacted_runtime_text(
                    f"worker staging cleanup failed: {error}",
                    EVALUATION_CLEANUP_FAILURE_MAXIMUM_BYTES,
                )
                raise EvaluationRuntimeError(diagnostic) from error
