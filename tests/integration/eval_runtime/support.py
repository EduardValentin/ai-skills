from __future__ import annotations

from pathlib import Path

from scripts.ai_skills_lib.harness import HarnessArtifactBinding


def prepare_artifact_binding(
    attempt_root: Path,
    repository_root: Path,
) -> HarnessArtifactBinding:
    """Create the exact durable output directories used by a captured actor run."""
    outputs = attempt_root / "outputs"
    outputs.mkdir(parents=True)
    attempt = attempt_root.stat()
    output = outputs.stat()
    repository = repository_root.stat()
    return HarnessArtifactBinding(
        attempt_identity=(attempt.st_dev, attempt.st_ino, attempt.st_mode),
        outputs_identity=(output.st_dev, output.st_ino, output.st_mode),
        repository_identity=(repository.st_dev, repository.st_ino),
    )
