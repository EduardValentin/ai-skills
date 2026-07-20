from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import scripts.ai_skills_lib.local_installs as local_installs
from scripts.ai_skills_lib.local_installs import (
    inspect_codex_local_installs,
    repository_source_identifiers,
    run_local_install_check,
)


def _skill_text(name: str, body: str = "Instructions.") -> str:
    return f"---\nname: {name}\ndescription: Test skill.\n---\n\n{body}\n"


class LocalInstallDiagnosticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.home = self.root / "home"
        self.codex_home = self.home / ".codex"
        self.source = self.repository / "skills" / "workflows" / "ticket-writing"
        self._write_skill(self.source, "ticket-writing")

    def _write_skill(self, root: Path, name: str, body: str = "Instructions.") -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "SKILL.md").write_text(_skill_text(name, body), encoding="utf-8")

    def _copy_source(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.source, destination)

    def _write_lock(
        self,
        path: Path,
        skills: dict[str, object],
        *,
        version: object = 3,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": version, "skills": skills}),
            encoding="utf-8",
        )

    def _inspect(self, *, inspection_hook=None):
        arguments = {
            "home": self.home,
            "codex_home": self.codex_home,
            "lock_path": self.home / ".agents" / ".skill-lock.json",
        }
        if inspection_hook is not None:
            arguments["inspection_hook"] = inspection_hook
        return inspect_codex_local_installs(
            self.repository,
            **arguments,
        )

    def _run_check(self, environ: dict[str, str]) -> tuple[int, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = run_local_install_check(
                self.repository,
                harness="codex",
                environ=environ,
            )
        return exit_code, output.getvalue()

    def test_canonical_copy_and_codex_symlink_are_one_current_install(self) -> None:
        canonical = self.home / ".agents" / "skills" / "ticket-writing"
        self._copy_source(canonical)
        link = self.codex_home / "skills" / "ticket-writing"
        link.parent.mkdir(parents=True)
        link.symlink_to(canonical, target_is_directory=True)

        report = self._inspect()

        self.assertEqual(report.issues, ())
        self.assertEqual(report.current, (("ticket-writing", canonical),))

    def test_whole_codex_skill_root_alias_is_one_current_install(self) -> None:
        canonical_root = self.home / ".agents" / "skills"
        canonical = canonical_root / "ticket-writing"
        self._copy_source(canonical)
        codex_skills = self.codex_home / "skills"
        codex_skills.parent.mkdir(parents=True)
        codex_skills.symlink_to(canonical_root, target_is_directory=True)

        report = self._inspect()

        self.assertEqual(report.issues, ())
        self.assertEqual(report.current, (("ticket-writing", canonical),))

    def test_whole_skill_root_alias_to_unconfigured_directory_is_rejected(self) -> None:
        outside_root = self.root / "outside-skills"
        self._write_skill(outside_root / "ticket-writing", "ticket-writing")
        codex_skills = self.codex_home / "skills"
        codex_skills.parent.mkdir(parents=True)
        codex_skills.symlink_to(outside_root, target_is_directory=True)

        report = self._inspect()

        self.assertTrue(
            any(
                issue.scope == str(codex_skills)
                and "must be a non-symlink directory" in issue.message
                for issue in report.issues
            )
        )
        self.assertTrue(
            any("missing from Codex skill roots" in issue.message for issue in report.issues)
        )

    def test_missing_skill_fails(self) -> None:
        report = self._inspect()

        self.assertIn("missing", report.issues[0].message)

    def test_stale_copy_fails(self) -> None:
        installed = self.codex_home / "skills" / "ticket-writing"
        self._copy_source(installed)
        (installed / "SKILL.md").write_text(
            _skill_text("ticket-writing", "Old instructions."), encoding="utf-8"
        )

        report = self._inspect()

        self.assertIn("stale content", report.issues[0].message)

    def test_distinct_active_copies_are_duplicates(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        self._copy_source(self.home / ".agents" / "skills" / "ticket-writing")

        report = self._inspect()

        self.assertIn("duplicate active installs", report.issues[0].message)

    def test_hard_linked_skill_files_in_distinct_directories_are_duplicates(self) -> None:
        first = self.codex_home / "skills" / "ticket-writing"
        second = self.home / ".agents" / "skills" / "ticket-writing"
        self._copy_source(first)
        second.mkdir(parents=True)
        os.link(first / "SKILL.md", second / "SKILL.md")

        report = self._inspect()

        self.assertIn("duplicate active installs", report.issues[0].message)

    def test_unrelated_skill_is_ignored(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        self._write_skill(
            self.codex_home / "skills" / "third-party", "third-party"
        )

        report = self._inspect()

        self.assertEqual(report.issues, ())

    def test_unsafe_skill_symlink_is_rejected_without_following_it(self) -> None:
        outside = self.root / "outside" / "ticket-writing"
        self._write_skill(outside, "ticket-writing")
        link = self.codex_home / "skills" / "ticket-writing"
        link.parent.mkdir(parents=True)
        link.symlink_to(outside, target_is_directory=True)
        before = hashlib.sha256((outside / "SKILL.md").read_bytes()).hexdigest()

        report = self._inspect()

        self.assertTrue(any("unsafe installed path" in issue.message for issue in report.issues))
        self.assertEqual(before, hashlib.sha256((outside / "SKILL.md").read_bytes()).hexdigest())

    def test_malformed_expected_install_is_reported(self) -> None:
        installed = self.codex_home / "skills" / "ticket-writing"
        installed.mkdir(parents=True)
        (installed / "SKILL.md").write_text("not frontmatter\n", encoding="utf-8")

        report = self._inspect()

        self.assertTrue(
            any("invalid installed SKILL.md" in issue.message for issue in report.issues)
        )

    def test_lock_proves_old_repository_install_is_extra(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        old = self.home / ".agents" / "skills" / "old-ticket-writing"
        self._write_skill(old, "old-ticket-writing")
        lock = self.home / ".agents" / ".skill-lock.json"
        lock.write_text(
            json.dumps(
                {
                    "version": 3,
                    "skills": {
                        "old-ticket-writing": {
                            "source": str(self.repository),
                            "sourceUrl": "https://github.com/EduardValentin/ai-skills",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        report = self._inspect()

        self.assertTrue(any("extra active install" in issue.message for issue in report.issues))

    def test_bare_git_remote_path_does_not_collide_with_lock_github_shorthand(self) -> None:
        git_directory = self.repository / ".git"
        git_directory.mkdir()
        (git_directory / "config").write_text(
            '[remote "origin"]\n\turl = owner/repository\n',
            encoding="utf-8",
        )
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        old = self.home / ".agents" / "skills" / "old-ticket-writing"
        self._write_skill(old, "old-ticket-writing")
        self._write_lock(
            self.home / ".agents" / ".skill-lock.json",
            {"old-ticket-writing": {"source": "owner/repository"}},
        )

        report = self._inspect()

        self.assertEqual(report.issues, ())

    def test_lock_github_shorthand_matches_an_explicit_github_remote(self) -> None:
        git_directory = self.repository / ".git"
        git_directory.mkdir()
        (git_directory / "config").write_text(
            '[remote "origin"]\n\turl = https://github.com/owner/repository.git\n',
            encoding="utf-8",
        )
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        old = self.home / ".agents" / "skills" / "old-ticket-writing"
        self._write_skill(old, "old-ticket-writing")
        self._write_lock(
            self.home / ".agents" / ".skill-lock.json",
            {"old-ticket-writing": {"source": "owner/repository"}},
        )

        report = self._inspect()

        self.assertTrue(
            any(
                "extra active install attributed to this repository" in issue.message
                for issue in report.issues
            )
        )

    def test_unsupported_lock_versions_cannot_attribute_an_extra(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        old = self.home / ".agents" / "skills" / "old-ticket-writing"
        self._write_skill(old, "old-ticket-writing")
        lock = self.home / ".agents" / ".skill-lock.json"

        for version in (None, 2, True, 3.0, "3"):
            with self.subTest(version=version):
                document: dict[str, object] = {
                    "skills": {
                        "old-ticket-writing": {
                            "source": str(self.repository),
                        }
                    }
                }
                if version is not None:
                    document["version"] = version
                lock.write_text(json.dumps(document), encoding="utf-8")

                report = self._inspect()

                messages = [issue.message for issue in report.issues]
                self.assertTrue(any("skill lock version" in message for message in messages))
                self.assertFalse(any("extra active install" in message for message in messages))

    def test_newer_integer_lock_version_can_attribute_an_extra(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        old = self.home / ".agents" / "skills" / "old-ticket-writing"
        self._write_skill(old, "old-ticket-writing")
        self._write_lock(
            self.home / ".agents" / ".skill-lock.json",
            {
                "old-ticket-writing": {
                    "source": str(self.repository),
                }
            },
            version=4,
        )

        report = self._inspect()

        self.assertTrue(any("extra active install" in issue.message for issue in report.issues))

    def test_malformed_attributed_extra_is_reported(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        old = self.home / ".agents" / "skills" / "old-ticket-writing"
        old.mkdir(parents=True)
        (old / "SKILL.md").write_text("not frontmatter\n", encoding="utf-8")
        self._write_lock(
            self.home / ".agents" / ".skill-lock.json",
            {
                "old-ticket-writing": {
                    "source": str(self.repository),
                }
            },
        )

        report = self._inspect()

        self.assertTrue(
            any(
                issue.scope == "old-ticket-writing"
                and "invalid installed SKILL.md" in issue.message
                for issue in report.issues
            )
        )

    def test_escaping_attributed_extra_is_reported(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        outside = self.root / "outside" / "old-ticket-writing"
        self._write_skill(outside, "old-ticket-writing")
        old = self.home / ".agents" / "skills" / "old-ticket-writing"
        old.parent.mkdir(parents=True)
        old.symlink_to(outside, target_is_directory=True)
        self._write_lock(
            self.home / ".agents" / ".skill-lock.json",
            {
                "old-ticket-writing": {
                    "source": str(self.repository),
                }
            },
        )

        report = self._inspect()

        self.assertTrue(
            any(
                issue.scope == "old-ticket-writing"
                and "unsafe installed path" in issue.message
                for issue in report.issues
            )
        )

    def test_attributed_extra_without_skill_file_is_reported(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        old = self.home / ".agents" / "skills" / "old-ticket-writing"
        old.mkdir(parents=True)
        self._write_lock(
            self.home / ".agents" / ".skill-lock.json",
            {
                "old-ticket-writing": {
                    "source": str(self.repository),
                }
            },
        )

        report = self._inspect()

        self.assertTrue(
            any(
                issue.scope == "old-ticket-writing"
                and "missing regular SKILL.md" in issue.message
                for issue in report.issues
            )
        )

    def test_inspector_uses_only_the_explicit_lock_path(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        old = self.home / ".agents" / "skills" / "old-ticket-writing"
        self._write_skill(old, "old-ticket-writing")
        fallback_lock = self.home / ".agents" / ".skill-lock.json"
        fallback_lock.write_text("not json", encoding="utf-8")
        explicit_lock = self.root / "state" / "skills" / ".skill-lock.json"
        explicit_lock.parent.mkdir(parents=True)
        explicit_lock.write_text(
            json.dumps(
                {
                    "version": 3,
                    "skills": {
                        "old-ticket-writing": {
                            "source": str(self.repository),
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        report = inspect_codex_local_installs(
            self.repository,
            home=self.home,
            codex_home=self.codex_home,
            lock_path=explicit_lock,
        )

        messages = [issue.message for issue in report.issues]
        self.assertTrue(any("extra active install" in message for message in messages))
        self.assertFalse(any("invalid skill lock" in message for message in messages))

    def test_malformed_lock_is_reported(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        lock = self.home / ".agents" / ".skill-lock.json"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text('{"skills": {"x": {}, "x": {}}}', encoding="utf-8")

        report = self._inspect()

        self.assertTrue(any("invalid skill lock" in issue.message for issue in report.issues))

    def test_nested_symlink_makes_matching_copy_untrustworthy(self) -> None:
        installed = self.codex_home / "skills" / "ticket-writing"
        self._copy_source(installed)
        external = self.root / "external.txt"
        external.write_text("external", encoding="utf-8")
        (installed / "linked.txt").symlink_to(external)

        report = self._inspect()

        self.assertTrue(any("contains a symlink" in issue.message for issue in report.issues))

    def test_candidate_swap_before_descriptor_open_cannot_escape_root(self) -> None:
        installed = self.codex_home / "skills" / "ticket-writing"
        self._copy_source(installed)
        outside = self.root / "outside" / "ticket-writing"
        self._write_skill(outside, "ticket-writing")
        parked = self.root / "parked-install"
        swapped = False

        def swap_candidate(event: str, path: Path) -> None:
            nonlocal swapped
            if event == "candidate-entry-observed" and path == installed and not swapped:
                installed.rename(parked)
                installed.symlink_to(outside, target_is_directory=True)
                swapped = True

        report = self._inspect(inspection_hook=swap_candidate)

        self.assertTrue(swapped)
        self.assertTrue(any("unsafe installed path" in issue.message for issue in report.issues))
        self.assertFalse(report.current)

    def test_candidate_path_swap_after_descriptor_open_uses_open_directory(self) -> None:
        installed = self.codex_home / "skills" / "ticket-writing"
        self._copy_source(installed)
        outside = self.root / "outside" / "ticket-writing"
        self._write_skill(outside, "ticket-writing", "Outside instructions.")
        parked = self.root / "parked-install"
        swapped = False

        def swap_candidate(event: str, path: Path) -> None:
            nonlocal swapped
            if event == "candidate-directory-opened" and path == installed and not swapped:
                installed.rename(parked)
                installed.symlink_to(outside, target_is_directory=True)
                swapped = True

        report = self._inspect(inspection_hook=swap_candidate)

        self.assertTrue(swapped)
        self.assertEqual(report.issues, ())
        self.assertEqual(report.current, (("ticket-writing", installed),))

    def test_manifest_entry_swap_to_symlink_is_not_followed(self) -> None:
        (self.source / "payload.txt").write_text("source payload", encoding="utf-8")
        installed = self.codex_home / "skills" / "ticket-writing"
        self._copy_source(installed)
        payload = installed / "payload.txt"
        outside = self.root / "outside.txt"
        outside.write_text("source payload", encoding="utf-8")
        parked = self.root / "parked-payload.txt"
        swapped = False

        def swap_file(event: str, path: Path) -> None:
            nonlocal swapped
            if event == "manifest-entry-observed" and path == payload and not swapped:
                payload.rename(parked)
                payload.symlink_to(outside)
                swapped = True

        report = self._inspect(inspection_hook=swap_file)

        self.assertTrue(swapped)
        self.assertTrue(any("contains a symlink" in issue.message for issue in report.issues))
        self.assertFalse(report.current)

    def test_manifest_path_swap_after_descriptor_open_is_detected(self) -> None:
        (self.source / "payload.txt").write_text("source payload", encoding="utf-8")
        installed = self.codex_home / "skills" / "ticket-writing"
        self._copy_source(installed)
        payload = installed / "payload.txt"
        outside = self.root / "outside.txt"
        outside.write_text("different payload", encoding="utf-8")
        parked = self.root / "parked-payload.txt"
        swapped = False

        def swap_file(event: str, path: Path) -> None:
            nonlocal swapped
            if event == "manifest-file-opened" and path == payload and not swapped:
                payload.rename(parked)
                payload.symlink_to(outside)
                swapped = True

        report = self._inspect(inspection_hook=swap_file)

        self.assertTrue(swapped)
        self.assertTrue(
            any("changed while being read: payload.txt" in issue.message for issue in report.issues)
        )
        self.assertFalse(report.current)

    def test_lock_path_swap_after_descriptor_open_is_detected(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        old = self.home / ".agents" / "skills" / "old-ticket-writing"
        self._write_skill(old, "old-ticket-writing")
        lock = self.home / ".agents" / ".skill-lock.json"
        self._write_lock(
            lock,
            {
                "old-ticket-writing": {
                    "source": str(self.repository),
                }
            },
        )
        parked = self.root / "parked-lock.json"
        replacement = self.root / "replacement-lock.json"
        replacement.write_text("not json", encoding="utf-8")
        swapped = False

        def swap_lock(event: str, path: Path) -> None:
            nonlocal swapped
            if event == "lock-file-opened" and path == lock and not swapped:
                lock.rename(parked)
                lock.symlink_to(replacement)
                swapped = True

        report = self._inspect(inspection_hook=swap_lock)

        self.assertTrue(swapped)
        messages = [issue.message for issue in report.issues]
        self.assertTrue(
            any(
                "invalid skill lock" in message and "changed while being read" in message
                for message in messages
            )
        )
        self.assertFalse(any("extra active install" in message for message in messages))

    def test_lock_swap_before_descriptor_open_is_not_followed(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        old = self.home / ".agents" / "skills" / "old-ticket-writing"
        self._write_skill(old, "old-ticket-writing")
        lock = self.home / ".agents" / ".skill-lock.json"
        self._write_lock(
            lock,
            {"old-ticket-writing": {"source": str(self.repository)}},
        )
        parked = self.root / "parked-lock.json"
        replacement = self.root / "replacement-lock.json"
        self._write_lock(
            replacement,
            {"old-ticket-writing": {"source": str(self.repository)}},
        )
        swapped = False

        def swap_lock(event: str, path: Path) -> None:
            nonlocal swapped
            if event == "lock-entry-observed" and path == lock and not swapped:
                lock.rename(parked)
                lock.symlink_to(replacement)
                swapped = True

        report = self._inspect(inspection_hook=swap_lock)

        self.assertTrue(swapped)
        messages = [issue.message for issue in report.issues]
        self.assertTrue(any("invalid skill lock" in message for message in messages))
        self.assertFalse(any("extra active install" in message for message in messages))

    def test_skill_fifo_is_rejected_without_blocking(self) -> None:
        installed = self.codex_home / "skills" / "ticket-writing"
        installed.mkdir(parents=True)
        os.mkfifo(installed / "SKILL.md")

        report = self._inspect()

        self.assertTrue(any("missing regular SKILL.md" in issue.message for issue in report.issues))

    def test_nested_fifo_is_rejected_without_blocking(self) -> None:
        installed = self.codex_home / "skills" / "ticket-writing"
        self._copy_source(installed)
        os.mkfifo(installed / "payload")

        report = self._inspect()

        self.assertTrue(any("contains a special file" in issue.message for issue in report.issues))

    def test_oversized_lock_is_bounded_without_path_read_bytes(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        lock = self.home / ".agents" / ".skill-lock.json"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_bytes(b"x" * 65)

        with (
            patch.object(local_installs, "_MAX_LOCK_BYTES", 64),
            patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded path read")),
        ):
            report = self._inspect()

        self.assertTrue(
            any("skill lock exceeds the size limit" in issue.message for issue in report.issues)
        )

    def test_skill_root_entry_count_is_capped(self) -> None:
        skills_root = self.codex_home / "skills"
        self._copy_source(skills_root / "ticket-writing")
        for index in range(3):
            (skills_root / f"third-party-{index}").mkdir()

        with patch.object(local_installs, "_MAX_ROOT_ENTRIES", 2, create=True):
            report = self._inspect()

        self.assertTrue(
            any("skill root exceeds the entry limit" in issue.message for issue in report.issues)
        )

    def test_manifest_hashing_has_an_aggregate_read_limit(self) -> None:
        installed = self.codex_home / "skills" / "ticket-writing"
        self._copy_source(installed)
        source_bytes = sum(
            path.stat().st_size for path in self.source.rglob("*") if path.is_file()
        )

        with patch.object(
            local_installs,
            "_MAX_AGGREGATE_READ_BYTES",
            (source_bytes * 2) - 1,
            create=True,
        ):
            report = self._inspect()

        self.assertTrue(any("aggregate read limit" in issue.message for issue in report.issues))
        self.assertFalse(report.current)

    def test_unrelated_third_party_skill_content_is_never_opened(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        unrelated = self.codex_home / "skills" / "third-party"
        unrelated.mkdir()
        os.mkfifo(unrelated / "SKILL.md")

        report = self._inspect()

        self.assertEqual(report.issues, ())

    def test_repository_discovery_never_uses_shared_path_reader(self) -> None:
        self._copy_source(self.codex_home / "skills" / "ticket-writing")

        with (
            patch.object(
                local_installs,
                "discover_testable_skills",
                side_effect=AssertionError("shared pathname discovery used"),
                create=True,
            ),
            patch.object(
                Path,
                "read_text",
                side_effect=AssertionError("unanchored pathname read used"),
            ),
        ):
            report = self._inspect()

        self.assertEqual(report.issues, ())

    def test_repository_skill_file_symlink_is_rejected_before_read(self) -> None:
        outside = self.root / "outside-SKILL.md"
        outside.write_text(_skill_text("ticket-writing"), encoding="utf-8")
        skill_file = self.source / "SKILL.md"
        skill_file.unlink()
        skill_file.symlink_to(outside)

        with self.assertRaisesRegex(
            ValueError,
            "requires a regular non-symlink SKILL.md",
        ):
            self._inspect()

    def test_repository_broken_skill_file_symlink_is_rejected(self) -> None:
        skill_file = self.source / "SKILL.md"
        skill_file.unlink()
        skill_file.symlink_to(self.root / "missing-SKILL.md")

        with self.assertRaisesRegex(
            ValueError,
            "requires a regular non-symlink SKILL.md",
        ):
            self._inspect()

    def test_repository_oversized_skill_file_is_rejected_before_allocation(self) -> None:
        size_limit = (self.source / "SKILL.md").stat().st_size - 1

        with patch.object(local_installs, "_MAX_FRONTMATTER_BYTES", size_limit):
            with self.assertRaisesRegex(
                ValueError,
                "SKILL.md exceeds the diagnostic size limit",
            ):
                self._inspect()

    def test_repository_skill_fifo_is_rejected_without_blocking(self) -> None:
        skill_file = self.source / "SKILL.md"
        skill_file.unlink()
        os.mkfifo(skill_file)

        with self.assertRaisesRegex(
            ValueError,
            "requires a regular non-symlink SKILL.md",
        ):
            self._inspect()

    def test_repository_skill_swap_before_descriptor_open_is_not_followed(self) -> None:
        skill_file = self.source / "SKILL.md"
        parked = self.root / "parked-source-SKILL.md"
        outside = self.root / "outside-SKILL.md"
        outside.write_text(_skill_text("ticket-writing"), encoding="utf-8")
        swapped = False

        def swap_source(event: str, path: Path) -> None:
            nonlocal swapped
            if event == "manifest-entry-observed" and path == skill_file and not swapped:
                skill_file.rename(parked)
                skill_file.symlink_to(outside)
                swapped = True

        with self.assertRaisesRegex(ValueError, "contains a symlink: SKILL.md"):
            self._inspect(inspection_hook=swap_source)
        self.assertTrue(swapped)

    def test_repository_skill_swap_after_descriptor_open_is_detected(self) -> None:
        skill_file = self.source / "SKILL.md"
        parked = self.root / "parked-source-SKILL.md"
        outside = self.root / "outside-SKILL.md"
        outside.write_text(_skill_text("ticket-writing", "Outside."), encoding="utf-8")
        swapped = False

        def swap_source(event: str, path: Path) -> None:
            nonlocal swapped
            if event == "manifest-file-opened" and path == skill_file and not swapped:
                skill_file.rename(parked)
                skill_file.symlink_to(outside)
                swapped = True

        with self.assertRaisesRegex(ValueError, "changed while being read: SKILL.md"):
            self._inspect(inspection_hook=swap_source)
        self.assertTrue(swapped)

    def test_repository_source_manifest_is_retained_after_discovery(self) -> None:
        installed = self.codex_home / "skills" / "ticket-writing"
        self._copy_source(installed)
        source_skill = self.source / "SKILL.md"
        changed = False

        def change_source_after_snapshot(event: str, path: Path) -> None:
            nonlocal changed
            if event == "repository-skills-discovered" and not changed:
                source_skill.write_text(
                    _skill_text("ticket-writing", "Changed after snapshot."),
                    encoding="utf-8",
                )
                changed = True

        report = self._inspect(inspection_hook=change_source_after_snapshot)

        self.assertTrue(changed)
        self.assertEqual(report.issues, ())
        self.assertEqual(report.current, (("ticket-writing", installed),))

    def test_repository_path_swap_after_descriptor_anchor_fails(self) -> None:
        parked = self.root / "parked-repository"
        swapped = False

        def swap_repository(event: str, path: Path) -> None:
            nonlocal swapped
            if event == "repository-directory-opened" and not swapped:
                self.repository.rename(parked)
                replacement = self.repository / "skills" / "workflows" / "ticket-writing"
                self._write_skill(replacement, "ticket-writing", "Replacement.")
                swapped = True

        with self.assertRaisesRegex(
            ValueError,
            "repository root changed while being inspected",
        ):
            self._inspect(inspection_hook=swap_repository)
        self.assertTrue(swapped)

    def test_repository_path_swap_after_identifier_discovery_fails(self) -> None:
        parked = self.root / "parked-repository"
        swapped = False

        def swap_repository(event: str, path: Path) -> None:
            nonlocal swapped
            if event == "repository-identifiers-derived" and not swapped:
                self.repository.rename(parked)
                replacement = self.repository / "skills" / "workflows" / "ticket-writing"
                self._write_skill(replacement, "ticket-writing", "Replacement.")
                swapped = True

        with self.assertRaisesRegex(
            ValueError,
            "repository root changed while being inspected",
        ):
            self._inspect(inspection_hook=swap_repository)
        self.assertTrue(swapped)

    def test_source_manifest_entry_budget_is_shared_across_skills(self) -> None:
        (self.source / "empty-a").touch()
        second = self.repository / "skills" / "workflows" / "second-skill"
        self._write_skill(second, "second-skill")
        (second / "empty-b").touch()

        with patch.object(
            local_installs,
            "_MAX_AGGREGATE_MANIFEST_ENTRIES",
            3,
            create=True,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "aggregate manifest entry limit",
            ):
                self._inspect()

    def test_installed_manifest_entry_budget_is_shared_across_skills(self) -> None:
        second = self.repository / "skills" / "workflows" / "second-skill"
        self._write_skill(second, "second-skill")
        self._copy_source(self.codex_home / "skills" / "ticket-writing")
        self._copy_source(self.codex_home / "skills" / "second-skill")
        shutil.copy2(second / "SKILL.md", self.codex_home / "skills" / "second-skill" / "SKILL.md")

        with patch.object(
            local_installs,
            "_MAX_AGGREGATE_MANIFEST_ENTRIES",
            3,
            create=True,
        ):
            report = self._inspect()

        self.assertTrue(
            any("aggregate manifest entry limit" in issue.message for issue in report.issues)
        )
        self.assertLess(len(report.current), 2)

    def test_unrelated_repository_source_entries_are_bounded(self) -> None:
        skills_root = self.repository / "skills"
        (skills_root / "unrelated-a").mkdir()
        (skills_root / "unrelated-b").mkdir()

        with patch.object(local_installs, "_MAX_SOURCE_ENTRIES", 2, create=True):
            with self.assertRaisesRegex(ValueError, "repository source exceeds the entry limit"):
                self._inspect()

    def test_runner_reports_ok_with_captured_output_and_zero_exit(self) -> None:
        installed = self.home / ".agents" / "skills" / "ticket-writing"
        self._copy_source(installed)

        exit_code, output = self._run_check({"HOME": str(self.home)})

        self.assertEqual(exit_code, 0)
        self.assertIn(f"ticket-writing: current ({installed})", output)
        self.assertIn("check-local-installs codex: OK (1 skills)", output)

    def test_runner_reports_missing_with_failure_exit(self) -> None:
        exit_code, output = self._run_check({"HOME": str(self.home)})

        self.assertEqual(exit_code, 1)
        self.assertIn("missing from Codex skill roots", output)
        self.assertIn("check-local-installs codex: FAILED", output)

    def test_runner_reports_stale_with_failure_exit(self) -> None:
        installed = self.home / ".codex" / "skills" / "ticket-writing"
        self._copy_source(installed)
        (installed / "SKILL.md").write_text(
            _skill_text("ticket-writing", "Old instructions."),
            encoding="utf-8",
        )

        exit_code, output = self._run_check({"HOME": str(self.home)})

        self.assertEqual(exit_code, 1)
        self.assertIn("stale content", output)
        self.assertIn("check-local-installs codex: FAILED", output)

    def test_runner_reports_duplicate_with_failure_exit(self) -> None:
        self._copy_source(self.home / ".codex" / "skills" / "ticket-writing")
        self._copy_source(self.home / ".agents" / "skills" / "ticket-writing")

        exit_code, output = self._run_check({"HOME": str(self.home)})

        self.assertEqual(exit_code, 1)
        self.assertIn("duplicate active installs", output)
        self.assertIn("check-local-installs codex: FAILED", output)

    def test_runner_reports_malformed_lock_with_failure_exit(self) -> None:
        self._copy_source(self.home / ".agents" / "skills" / "ticket-writing")
        lock = self.home / ".agents" / ".skill-lock.json"
        lock.write_text("not json", encoding="utf-8")

        exit_code, output = self._run_check({"HOME": str(self.home)})

        self.assertEqual(exit_code, 1)
        self.assertIn("invalid skill lock", output)
        self.assertIn("check-local-installs codex: FAILED", output)

    def test_runner_uses_injected_codex_home(self) -> None:
        configured_codex_home = self.root / "configured-codex"
        installed = configured_codex_home / "skills" / "ticket-writing"
        self._copy_source(installed)
        self._write_skill(
            self.home / ".codex" / "skills" / "ticket-writing",
            "ticket-writing",
            "Stale default install.",
        )

        exit_code, output = self._run_check(
            {
                "HOME": str(self.home),
                "CODEX_HOME": str(configured_codex_home),
            }
        )

        self.assertEqual(exit_code, 0)
        self.assertIn(f"ticket-writing: current ({installed})", output)
        self.assertNotIn("Stale default install", output)

    def test_runner_uses_xdg_state_lock_instead_of_home_fallback(self) -> None:
        self._copy_source(self.home / ".agents" / "skills" / "ticket-writing")
        old = self.home / ".agents" / "skills" / "old-ticket-writing"
        self._write_skill(old, "old-ticket-writing")
        fallback_lock = self.home / ".agents" / ".skill-lock.json"
        fallback_lock.write_text("not json", encoding="utf-8")
        xdg_state_home = self.root / "state"
        self._write_lock(
            xdg_state_home / "skills" / ".skill-lock.json",
            {"old-ticket-writing": {"source": str(self.repository)}},
        )

        exit_code, output = self._run_check(
            {
                "HOME": str(self.home),
                "XDG_STATE_HOME": str(xdg_state_home),
            }
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("extra active install attributed to this repository", output)
        self.assertNotIn("invalid skill lock", output)


class RepositorySourceIdentifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _git(self, repository: Path, *arguments: str) -> None:
        subprocess.run(
            ("git", "-C", str(repository), *arguments),
            check=True,
            capture_output=True,
            text=True,
        )

    def test_linked_worktree_includes_proven_main_checkout_source(self) -> None:
        main_checkout = self.root / "main-checkout"
        main_checkout.mkdir()
        self._git(main_checkout, "init", "--initial-branch=main")
        self._git(main_checkout, "config", "user.name", "Test User")
        self._git(main_checkout, "config", "user.email", "test@example.invalid")
        (main_checkout / "tracked.txt").write_text("tracked\n", encoding="utf-8")
        self._git(main_checkout, "add", "tracked.txt")
        self._git(main_checkout, "commit", "-m", "initial")
        linked_worktree = self.root / "linked-worktree"
        self._git(
            main_checkout,
            "worktree",
            "add",
            "-b",
            "test-worktree",
            str(linked_worktree),
        )

        identifiers = repository_source_identifiers(linked_worktree)

        self.assertIn(f"path:{linked_worktree.resolve()}", identifiers)
        self.assertIn(f"path:{main_checkout.resolve()}", identifiers)

    def test_non_git_directory_does_not_infer_a_main_checkout(self) -> None:
        repository = self.root / "repository"
        repository.mkdir()

        identifiers = repository_source_identifiers(repository)

        self.assertIn(f"path:{repository.resolve()}", identifiers)
        self.assertNotIn(f"path:{self.root.resolve()}", identifiers)

    def test_bare_owner_repo_origin_is_resolved_as_a_relative_git_path(self) -> None:
        repository = self.root / "repository"
        git_directory = repository / ".git"
        git_directory.mkdir(parents=True)
        (git_directory / "config").write_text(
            '[remote "origin"]\n\turl = owner/repository\n',
            encoding="utf-8",
        )

        identifiers = repository_source_identifiers(repository)

        self.assertIn(
            f"path:{(repository / 'owner' / 'repository').resolve(strict=False)}",
            identifiers,
        )
        self.assertNotIn("github:owner/repository", identifiers)

    def test_oversized_common_directory_metadata_is_rejected_before_allocation(self) -> None:
        repository = self.root / "repository"
        repository.mkdir()
        git_directory = self.root / "git-directory"
        git_directory.mkdir()
        (repository / ".git").write_text(
            "gitdir: ../git-directory\n",
            encoding="utf-8",
        )
        (git_directory / "commondir").write_bytes(b"x" * 65)

        with (
            patch.object(local_installs, "_MAX_GIT_PATH_BYTES", 64, create=True),
            patch.object(
                subprocess,
                "run",
                side_effect=AssertionError("Git subprocess used"),
            ),
            patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("unbounded pathname read used"),
            ),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "git common directory metadata exceeds the size limit",
            ):
                repository_source_identifiers(repository)

    def test_oversized_remote_metadata_is_rejected_before_allocation(self) -> None:
        repository = self.root / "repository"
        git_directory = repository / ".git"
        git_directory.mkdir(parents=True)
        (git_directory / "config").write_bytes(b"x" * 65)

        with (
            patch.object(local_installs, "_MAX_GIT_CONFIG_BYTES", 64, create=True),
            patch.object(
                subprocess,
                "run",
                side_effect=AssertionError("Git subprocess used"),
            ),
            patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("unbounded pathname read used"),
            ),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "git config exceeds the size limit",
            ):
                repository_source_identifiers(repository)


if __name__ == "__main__":
    unittest.main()
