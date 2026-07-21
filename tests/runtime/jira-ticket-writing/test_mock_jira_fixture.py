"""Runtime contracts for the offline Jira collaborator eval fixture."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = (
    REPO_ROOT
    / "skills"
    / "integrations"
    / "jira-ticket-writing"
    / "evals"
    / "fixtures"
    / "authorized-update-with-mock-jira"
    / "inputs"
    / "bin"
    / "jira"
)


def valid_payload() -> dict[str, object]:
    return {
        "fields": {
            "summary": "Preserve saved layer state when reopening the map",
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Retain the selected saved layer and show a provider "
                                    "warning. Changing layer definitions is out of scope."
                                ),
                            }
                        ],
                    }
                ],
            },
            "customfield_10091": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "taskList",
                        "attrs": {"localId": "acceptance-list"},
                        "content": [
                            {
                                "type": "taskItem",
                                "attrs": {
                                    "localId": "retain-selected-layer",
                                    "state": "TODO",
                                },
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "The selected saved layer remains visible.",
                                    }
                                ],
                            },
                            {
                                "type": "taskItem",
                                "attrs": {
                                    "localId": "show-provider-warning",
                                    "state": "TODO",
                                },
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "A provider failure displays a clear warning.",
                                    }
                                ],
                            },
                        ],
                    }
                ],
            },
        }
    }


@pytest.fixture
def staged_jira(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "jira"
    shutil.copy2(FIXTURE, executable)

    assert os.access(executable, os.X_OK)
    return executable, tmp_path


def run_jira(
    staged_jira: tuple[Path, Path], *arguments: str
) -> subprocess.CompletedProcess[str]:
    executable, workspace = staged_jira
    return subprocess.run(
        [str(executable), *arguments],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )


def write_payload(workspace: Path, payload: dict[str, object]) -> Path:
    path = workspace / "fields.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def read_metadata_and_issue(staged_jira: tuple[Path, Path]) -> None:
    metadata = run_jira(
        staged_jira, "metadata", "--project", "MAP", "--issue-type", "Story"
    )
    issue = run_jira(staged_jira, "issue", "view", "MAP-42")

    assert metadata.returncode == 0
    assert json.loads(metadata.stdout)["project"]["key"] == "MAP"
    assert issue.returncode == 0
    assert json.loads(issue.stdout)["version"] == 7


def update_arguments(payload_path: Path, *, dry_run: bool = False) -> list[str]:
    arguments = [
        "issue",
        "update",
        "MAP-42",
        "--fields-file",
        str(payload_path),
        "--expected-version",
        "7",
    ]
    if dry_run:
        arguments.append("--dry-run")
    return arguments


def state_dir(staged_jira: tuple[Path, Path]) -> Path:
    return staged_jira[1] / "jira-ticket-writing-fixture-state"


def test_required_reads_dry_run_and_update_sequence_succeeds(
    staged_jira: tuple[Path, Path],
) -> None:
    payload_path = write_payload(staged_jira[1], valid_payload())

    read_metadata_and_issue(staged_jira)
    dry_run = run_jira(staged_jira, *update_arguments(payload_path, dry_run=True))

    assert dry_run.returncode == 0
    assert json.loads(dry_run.stdout) == {
        "dryRun": True,
        "valid": True,
        "key": "MAP-42",
        "expectedVersion": 7,
    }
    assert (state_dir(staged_jira) / "dry-run-passed").is_file()
    assert not (state_dir(staged_jira) / "updated").exists()

    update = run_jira(staged_jira, *update_arguments(payload_path))

    assert update.returncode == 0
    assert json.loads(update.stdout) == {
        "updated": True,
        "key": "MAP-42",
        "previousVersion": 7,
        "version": 8,
    }
    assert (state_dir(staged_jira) / "updated").is_file()
    invocations = (state_dir(staged_jira) / "tool-invocations.log").read_text(
        encoding="utf-8"
    )
    assert invocations.splitlines() == [
        "jira metadata --project MAP --issue-type Story",
        "jira issue view MAP-42",
        f"jira issue update MAP-42 --fields-file {payload_path} "
        "--expected-version 7 --dry-run",
        f"jira issue update MAP-42 --fields-file {payload_path} "
        "--expected-version 7",
    ]


@pytest.mark.parametrize(
    "completed_read",
    [
        pytest.param(None, id="neither-read"),
        pytest.param("metadata", id="issue-not-read"),
        pytest.param("issue", id="metadata-not-read"),
    ],
)
def test_update_rejects_when_a_required_read_is_missing(
    staged_jira: tuple[Path, Path], completed_read: str | None
) -> None:
    payload_path = write_payload(staged_jira[1], valid_payload())
    if completed_read == "metadata":
        completed = run_jira(
            staged_jira, "metadata", "--project", "MAP", "--issue-type", "Story"
        )
        assert completed.returncode == 0
    elif completed_read == "issue":
        completed = run_jira(staged_jira, "issue", "view", "MAP-42")
        assert completed.returncode == 0

    rejected = run_jira(
        staged_jira, *update_arguments(payload_path, dry_run=True)
    )

    assert rejected.returncode == 3
    assert (
        rejected.stderr
        == "Project metadata and current issue must be read before update.\n"
    )
    assert not (state_dir(staged_jira) / "dry-run-passed").exists()
    assert not (state_dir(staged_jira) / "updated").exists()


def test_update_rejects_a_stale_version_after_a_successful_dry_run(
    staged_jira: tuple[Path, Path],
) -> None:
    payload_path = write_payload(staged_jira[1], valid_payload())
    read_metadata_and_issue(staged_jira)
    dry_run = run_jira(staged_jira, *update_arguments(payload_path, dry_run=True))
    assert dry_run.returncode == 0

    rejected = run_jira(
        staged_jira,
        "issue",
        "update",
        "MAP-42",
        "--fields-file",
        str(payload_path),
        "--expected-version",
        "6",
    )

    assert rejected.returncode == 3
    assert rejected.stderr == "The update must use current fake issue version 7.\n"
    assert not (state_dir(staged_jira) / "updated").exists()


PayloadMutation = Callable[[dict[str, object]], None]


def remove_acceptance_field(payload: dict[str, object]) -> None:
    del payload["fields"]["customfield_10091"]  # type: ignore[index]


def remove_task_list(payload: dict[str, object]) -> None:
    acceptance = payload["fields"]["customfield_10091"]  # type: ignore[index]
    acceptance["content"] = [  # type: ignore[index]
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Not a native task list."}],
        }
    ]


def mark_task_complete(payload: dict[str, object]) -> None:
    acceptance = payload["fields"]["customfield_10091"]  # type: ignore[index]
    task = acceptance["content"][0]["content"][0]  # type: ignore[index]
    task["attrs"]["state"] = "DONE"


def duplicate_local_id(payload: dict[str, object]) -> None:
    acceptance = payload["fields"]["customfield_10091"]  # type: ignore[index]
    tasks = acceptance["content"][0]["content"]  # type: ignore[index]
    tasks[1]["attrs"]["localId"] = tasks[0]["attrs"]["localId"]


@pytest.mark.parametrize(
    ("mutate", "expected_error"),
    [
        pytest.param(
            remove_acceptance_field,
            "payload fields must be exactly summary, description, and "
            "customfield_10091",
            id="incomplete-fields",
        ),
        pytest.param(
            remove_task_list,
            "customfield_10091 must contain an ADF taskList",
            id="missing-task-list",
        ),
        pytest.param(
            mark_task_complete,
            "every taskItem must have TODO state",
            id="completed-task",
        ),
        pytest.param(
            duplicate_local_id,
            "taskList and taskItem localId values must be unique",
            id="duplicate-local-id",
        ),
    ],
)
def test_dry_run_rejects_malformed_payloads(
    staged_jira: tuple[Path, Path],
    mutate: PayloadMutation,
    expected_error: str,
) -> None:
    payload = copy.deepcopy(valid_payload())
    mutate(payload)
    payload_path = write_payload(staged_jira[1], payload)
    read_metadata_and_issue(staged_jira)

    rejected = run_jira(
        staged_jira, *update_arguments(payload_path, dry_run=True)
    )

    assert rejected.returncode != 0
    assert expected_error in rejected.stderr
    assert not (state_dir(staged_jira) / "dry-run-passed").exists()
    assert not (state_dir(staged_jira) / "updated").exists()


def test_write_revalidates_payload_after_a_successful_dry_run(
    staged_jira: tuple[Path, Path],
) -> None:
    payload = valid_payload()
    payload_path = write_payload(staged_jira[1], payload)
    read_metadata_and_issue(staged_jira)
    dry_run = run_jira(staged_jira, *update_arguments(payload_path, dry_run=True))
    assert dry_run.returncode == 0

    remove_acceptance_field(payload)
    write_payload(staged_jira[1], payload)
    rejected = run_jira(staged_jira, *update_arguments(payload_path))

    assert rejected.returncode != 0
    assert "payload fields must be exactly" in rejected.stderr
    assert not (state_dir(staged_jira) / "updated").exists()


def test_write_requires_a_successful_dry_run(
    staged_jira: tuple[Path, Path],
) -> None:
    payload_path = write_payload(staged_jira[1], valid_payload())
    read_metadata_and_issue(staged_jira)

    rejected = run_jira(staged_jira, *update_arguments(payload_path))

    assert rejected.returncode == 3
    assert rejected.stderr == "A successful dry run is required before the fake update.\n"
    assert not (state_dir(staged_jira) / "dry-run-passed").exists()
    assert not (state_dir(staged_jira) / "updated").exists()
