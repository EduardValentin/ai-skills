from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import fields
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import ANY, patch

import scripts.ai_skills as cli
import scripts.ai_skills_lib.authored_content as authored_content
import scripts.ai_skills_lib.core as core
import scripts.ai_skills_lib.eval_definitions as eval_definitions
import scripts.ai_skills_lib.static_checks.conformance as conformance
import scripts.ai_skills_lib.static_checks.evals as static_eval_checks
import scripts.ai_skills_lib.static_validation as static_validation
from scripts.ai_skills_lib.config import build_parser
from scripts.ai_skills_lib.core import discover_testable_skills
from scripts.ai_skills_lib.authored_content import (
    AuthoredRepositoryBudget,
    SENSITIVE_TEXT_REDACTION,
    scan_static_secret_issues,
)
from scripts.ai_skills_lib.static_validation import (
    SecretMatch,
    find_static_secret_issues,
    run_reference_conformance,
    run_static_validation,
)


class TemporaryRepository:
    def __init__(self):
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)

    def cleanup(self):
        self._temporary_directory.cleanup()

    def add_skill(
        self,
        name: str = "alpha",
        *,
        group: str = "workflows",
        folder: str | None = None,
        status: str | None = "public-ready",
        compatibility: str | None = None,
        allows_tool_references: str | None = None,
        body: str = "Follow the documented workflow.",
        metadata: dict[str, str] | None = None,
        with_evals: bool = True,
        with_triggers: bool = True,
    ) -> Path:
        skill_root = self.root / "skills" / group / (folder or name)
        skill_root.mkdir(parents=True, exist_ok=True)
        lines = [
            "---",
            f"name: {json.dumps(name)}",
            f"description: {json.dumps(f'Use for {name} workflows.')}",
        ]
        if compatibility is not None:
            lines.append(f"compatibility: {json.dumps(compatibility)}")
        combined_metadata = dict(metadata or {})
        if status is not None:
            combined_metadata["status"] = status
        if allows_tool_references is not None:
            combined_metadata["allows_tool_references"] = allows_tool_references
        if combined_metadata:
            lines.append("metadata:")
            lines.extend(
                f"  {key}: {json.dumps(value)}" for key, value in combined_metadata.items()
            )
        lines.extend(["---", body, ""])
        (skill_root / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")

        evals_root = skill_root / "evals"
        if with_evals or with_triggers:
            evals_root.mkdir(exist_ok=True)
        if with_evals:
            self.write_json(
                evals_root / "evals.json",
                {
                    "skill_name": name,
                    "evals": [
                        {
                            "id": "basic",
                            "prompt": "Perform the workflow.",
                            "expected_output": "A complete workflow result.",
                            "assertions": ["The result completes the requested workflow."],
                            "checks": [],
                        }
                    ],
                },
            )
        if with_triggers:
            self.write_json(
                evals_root / "triggers.json",
                {
                    "skill_name": name,
                    "queries": [
                        {
                            "id": f"{name}-positive",
                            "query": f"Perform the {name} workflow.",
                            "should_trigger": True,
                        },
                        {
                            "id": f"{name}-negative",
                            "query": "Summarize an unrelated note.",
                            "should_trigger": False,
                        },
                    ]
                },
            )
        return skill_root

    @staticmethod
    def write_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def exercise_bundled_path(self, skill_root: Path, path: str) -> None:
        evals_path = skill_root / "evals" / "evals.json"
        document = json.loads(evals_path.read_text(encoding="utf-8"))
        document["evals"][0]["assertions"].append(
            f"The workflow correctly uses `{path}`."
        )
        self.write_json(evals_path, document)

    def declare_basic_case_input(self, skill_root: Path, actor_path: str) -> Path:
        evals_path = skill_root / "evals" / "evals.json"
        document = json.loads(evals_path.read_text(encoding="utf-8"))
        case = document["evals"][0]
        fixture_path = f"fixtures/basic/inputs/{actor_path}"
        case.setdefault("files", []).append(fixture_path)
        case["prompt"] += f" Read `{actor_path}`."
        self.write_json(evals_path, document)
        return skill_root / "evals" / fixture_path


class TemporaryRepositoryTestCase(unittest.TestCase):
    def setUp(self):
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.cleanup)

    def messages(self) -> list[str]:
        return [issue.message for issue in run_static_validation(self.repository.root)]

    def assert_issue(self, fragment: str) -> None:
        messages = self.messages()
        self.assertTrue(
            any(fragment in message for message in messages),
            f"expected issue containing {fragment!r}, got {messages!r}",
        )

    def assert_no_issues(self) -> None:
        self.assertEqual(run_static_validation(self.repository.root), [])


class RepositoryShapeValidationTests(TemporaryRepositoryTestCase):
    def test_rejects_missing_or_empty_canonical_skills_directory(self):
        self.assert_issue("missing canonical skills/ directory")

        (self.repository.root / "skills").mkdir()
        self.assert_issue("contains no discoverable skills")

    def test_accepts_canonical_uppercase_skill_filename(self):
        self.repository.add_skill("alpha")

        messages = self.messages()

        self.assertFalse(
            any("must be named SKILL.md" in message for message in messages),
            messages,
        )

    def test_rejects_authored_mis_cased_skill_filenames(self):
        for authored_name in ("skill.md", "Skill.md"):
            with self.subTest(authored_name=authored_name):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                skill_root = repository.add_skill("alpha")
                intermediate = skill_root / "renaming-skill-document"
                (skill_root / "SKILL.md").rename(intermediate)
                intermediate.rename(skill_root / authored_name)

                messages = [
                    issue.message for issue in run_static_validation(repository.root)
                ]

                self.assertTrue(
                    any("must be named SKILL.md" in message for message in messages),
                    messages,
                )


class RepositoryResourceBudgetTests(TemporaryRepositoryTestCase):
    def test_repository_entry_budget_fails_closed(self):
        self.repository.add_skill("alpha")
        budget = AuthoredRepositoryBudget(
            maximum_entries=5,
            maximum_bytes=1024 * 1024,
        )

        with patch.object(
            static_validation,
            "AuthoredRepositoryBudget",
            return_value=budget,
        ):
            messages = self.messages()

        self.assertTrue(
            any("authored entry inspection limit" in message for message in messages),
            messages,
        )

    def test_repository_aggregate_byte_budget_fails_closed(self):
        self.repository.add_skill("alpha")
        budget = AuthoredRepositoryBudget(
            maximum_entries=10_000,
            maximum_bytes=1,
        )

        with patch.object(
            static_validation,
            "AuthoredRepositoryBudget",
            return_value=budget,
        ):
            messages = self.messages()

        self.assertTrue(
            any(
                "aggregate authored byte inspection limit" in message
                for message in messages
            ),
            messages,
        )


class DiscoveryAndFrontmatterValidationTests(TemporaryRepositoryTestCase):
    def test_discovers_only_two_level_public_skills(self):
        skill_root = self.repository.add_skill("alpha", group="procedural")

        skills = discover_testable_skills(self.repository.root)

        self.assertEqual([skill.name for skill in skills], ["alpha"])
        self.assertEqual(skills[0].root, skill_root)
        self.assertIn("name: \"alpha\"", skills[0].source_text)

    def test_rejects_public_installer_discovery_exclusions_at_both_levels(self):
        for excluded in sorted(
            core.PUBLIC_INSTALLER_DISCOVERY_EXCLUDED_DIRECTORIES
        ):
            for boundary in ("group", "skill"):
                with self.subTest(excluded=excluded, boundary=boundary):
                    repository = TemporaryRepository()
                    self.addCleanup(repository.cleanup)
                    if boundary == "group":
                        repository.add_skill("alpha", group=excluded)
                    else:
                        repository.add_skill(excluded)
                    expected = (
                        "public installer discovery excludes directory "
                        f"skills/{excluded}"
                        if boundary == "group"
                        else (
                            "public installer discovery excludes directory "
                            f"skills/workflows/{excluded}"
                        )
                    )

                    with self.assertRaisesRegex(
                        ValueError,
                        "public installer discovery excludes directory",
                    ):
                        discover_testable_skills(repository.root)

                    messages = [
                        issue.message
                        for issue in run_static_validation(repository.root)
                    ]
                    self.assertTrue(
                        any(expected in message for message in messages),
                        messages,
                    )

    def test_discovery_rejects_skill_documents_over_the_stable_snapshot_limit(self):
        skill_root = self.repository.add_skill(
            "alpha",
            body="A" * 256,
        )
        skill_path = skill_root / "SKILL.md"

        with patch(
            "scripts.ai_skills_lib.core.MAXIMUM_SKILL_DOCUMENT_BYTES",
            128,
        ):
            with self.assertRaisesRegex(ValueError, "SKILL.md exceeds"):
                discover_testable_skills(self.repository.root)
            messages = [
                issue.message for issue in run_static_validation(self.repository.root)
            ]

        self.assertTrue(any("SKILL.md exceeds" in message for message in messages))

    def test_static_context_rejects_skill_source_replacement_after_discovery(self):
        skill_root = self.repository.add_skill("alpha")
        context = static_validation.build_validation_context(
            self.repository.root,
            budget=AuthoredRepositoryBudget(),
        )
        skill_path = skill_root / "SKILL.md"
        replacement = skill_root / "SKILL.replacement"
        replacement.write_text(
            skill_path.read_text(encoding="utf-8")
            + "\n"
            + ("ghp_" + ("a" * 36))
            + "\n",
            encoding="utf-8",
        )
        replacement.replace(skill_path)

        issues = static_validation._run_static_context(context, [])

        self.assertTrue(
            any("SKILL.md changed after discovery" in issue.message for issue in issues),
            issues,
        )

    def test_static_context_rejects_identical_skill_source_replacement(self):
        skill_root = self.repository.add_skill("alpha")
        context = static_validation.build_validation_context(
            self.repository.root,
            budget=AuthoredRepositoryBudget(),
        )
        skill_path = skill_root / "SKILL.md"
        replacement = skill_root / "SKILL.replacement"
        replacement.write_bytes(skill_path.read_bytes())
        replacement.replace(skill_path)

        issues = static_validation._run_static_context(context, [])

        self.assertTrue(
            any("SKILL.md changed after discovery" in issue.message for issue in issues),
            issues,
        )

    def test_static_context_rejects_any_canonical_skills_tree_change(self):
        change_kinds = (
            "addition",
            "removal",
            "replacement",
            "metadata",
            "symlink",
            "content",
        )

        for change_kind in change_kinds:
            with self.subTest(change_kind=change_kind):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                skill_root = repository.add_skill("alpha")
                assets_root = skill_root / "assets"
                assets_root.mkdir()
                target = assets_root / "payload.txt"
                target.write_text("before", encoding="utf-8")
                alternate = assets_root / "alternate.txt"
                alias = assets_root / "alias.txt"
                if change_kind == "symlink":
                    alternate.write_text("second", encoding="utf-8")
                    alias.symlink_to(target.name)

                context = static_validation.build_validation_context(
                    repository.root,
                    budget=AuthoredRepositoryBudget(),
                )

                if change_kind == "addition":
                    (assets_root / "added.txt").write_text("added", encoding="utf-8")
                elif change_kind == "removal":
                    target.unlink()
                elif change_kind == "replacement":
                    replacement = assets_root / "replacement.txt"
                    replacement.write_bytes(target.read_bytes())
                    replacement.replace(target)
                elif change_kind == "metadata":
                    target.chmod(0o600)
                elif change_kind == "symlink":
                    alias.unlink()
                    alias.symlink_to(alternate.name)
                else:
                    target.write_text("after!", encoding="utf-8")

                issues = static_validation._run_static_context(context, [])

                self.assertTrue(
                    any(
                        "canonical skills tree changed after discovery"
                        in issue.message
                        for issue in issues
                    ),
                    issues,
                )

    def test_discovery_requires_an_exact_regular_non_symlink_skill_document(self):
        malformed_entries = (
            "missing",
            "directory",
            "broken-symlink",
            "regular-file-symlink",
            "wrong-case",
        )
        expected = (
            "skills/workflows/alpha requires an exact regular non-symlink SKILL.md"
        )
        valid_document = (
            "---\n"
            "name: alpha\n"
            "description: Use for alpha workflows.\n"
            "metadata:\n"
            "  status: public-ready\n"
            "---\n"
            "Follow the workflow.\n"
        )

        for malformed_entry in malformed_entries:
            with self.subTest(entry=malformed_entry):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                skill_root = repository.root / "skills" / "workflows" / "alpha"
                skill_root.mkdir(parents=True)
                skill_document = skill_root / "SKILL.md"
                if malformed_entry == "directory":
                    skill_document.mkdir()
                elif malformed_entry == "broken-symlink":
                    skill_document.symlink_to(skill_root / "missing.md")
                elif malformed_entry == "regular-file-symlink":
                    target = repository.root / "linked-skill.md"
                    target.write_text(valid_document, encoding="utf-8")
                    skill_document.symlink_to(target)
                elif malformed_entry == "wrong-case":
                    (skill_root / "Skill.md").write_text(
                        valid_document,
                        encoding="utf-8",
                    )

                with self.assertRaisesRegex(ValueError, expected):
                    discover_testable_skills(repository.root)

                messages = [
                    issue.message for issue in run_static_validation(repository.root)
                ]
                self.assertTrue(any(expected in message for message in messages), messages)

    def test_rejects_direct_skill_layout(self):
        direct_root = self.repository.root / "skills" / "alpha"
        direct_root.mkdir(parents=True)
        (direct_root / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: Example workflow.\nmetadata:\n  status: public-ready\n---\n",
            encoding="utf-8",
        )

        self.assert_issue("must use skills/<group>/<skill>/SKILL.md")

    def test_rejects_skill_documents_outside_the_canonical_source_tree(self):
        self.repository.add_skill("alpha")
        alternate = self.repository.root / "alternate" / "alpha" / "SKILL.md"
        alternate.parent.mkdir(parents=True)
        alternate.write_text("duplicate source\n", encoding="utf-8")

        self.assert_issue(
            "outside the canonical skills/<group>/<skill>/SKILL.md source tree"
        )

    def test_static_context_rechecks_restored_out_of_tree_skill_documents(self):
        self.repository.add_skill("alpha")
        alternate = self.repository.root / "alternate" / "alpha" / "SKILL.md"
        alternate.parent.mkdir(parents=True)
        hidden = alternate.with_name("hidden.md")
        hidden.write_text("duplicate source\n", encoding="utf-8")
        context = static_validation.build_validation_context(
            self.repository.root,
            budget=AuthoredRepositoryBudget(),
        )
        hidden.rename(alternate)

        issues = static_validation._run_static_context(context, [])

        self.assertTrue(
            any(
                "outside the canonical skills/<group>/<skill>/SKILL.md source tree"
                in issue.message
                for issue in issues
            ),
            issues,
        )

    def test_rejects_non_directory_entries_at_every_skill_layout_boundary(self):
        boundaries = (
            Path("skills"),
            Path("skills/workflows"),
            Path("skills/workflows/alpha"),
        )

        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                path = repository.root / boundary
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("not a directory\n", encoding="utf-8")
                expected = f"{boundary} must be a contained non-symlink directory"

                with self.assertRaises(ValueError) as raised:
                    discover_testable_skills(repository.root)

                self.assertIn(expected, str(raised.exception))
                messages = [
                    issue.message for issue in run_static_validation(repository.root)
                ]
                self.assertTrue(any(expected in message for message in messages), messages)

    def test_rejects_every_symlink_variant_at_every_skill_layout_boundary(self):
        boundaries = {
            Path("skills"): Path("workflows/alpha"),
            Path("skills/workflows"): Path("alpha"),
            Path("skills/workflows/alpha"): Path(),
        }

        for boundary, target_skill_suffix in boundaries.items():
            for target_kind in ("contained", "escaping", "broken"):
                with self.subTest(boundary=boundary, target_kind=target_kind):
                    repository = TemporaryRepository()
                    self.addCleanup(repository.cleanup)
                    external = tempfile.TemporaryDirectory()
                    self.addCleanup(external.cleanup)
                    link = repository.root / boundary
                    link.parent.mkdir(parents=True, exist_ok=True)
                    if target_kind == "contained":
                        target = repository.root / "layout-targets" / boundary.name
                    elif target_kind == "escaping":
                        target = Path(external.name) / boundary.name
                    else:
                        target = repository.root / "missing-layout-target" / boundary.name

                    if target_kind != "broken":
                        target_skill = target / target_skill_suffix
                        target_skill.mkdir(parents=True)
                        (target_skill / "SKILL.md").write_text(
                            "invalid document that discovery must not read\n",
                            encoding="utf-8",
                        )
                    link.symlink_to(target, target_is_directory=True)
                    expected = (
                        f"{boundary} must be a contained non-symlink directory"
                    )

                    with self.assertRaises(ValueError) as raised:
                        discover_testable_skills(repository.root)

                    self.assertIn(expected, str(raised.exception))
                    messages = [
                        issue.message for issue in run_static_validation(repository.root)
                    ]
                    self.assertTrue(
                        any(expected in message for message in messages), messages
                    )

    def test_discovery_rejects_directory_replacement_during_enumeration(self):
        self.repository.add_skill("alpha")
        group = self.repository.root / "skills" / "workflows"
        moved = self.repository.root / "moved-workflows"
        outside = self.repository.root / "outside-workflows"
        outside.mkdir()
        original_scandir = core.os.scandir
        calls = 0

        def replacing_scandir(directory):
            nonlocal calls
            calls += 1
            if calls == 2:
                group.rename(moved)
                group.symlink_to(outside, target_is_directory=True)
            return original_scandir(directory)

        with patch.object(core.os, "scandir", side_effect=replacing_scandir):
            with self.assertRaisesRegex(
                ValueError,
                "changed during enumeration",
            ):
                discover_testable_skills(self.repository.root)

    def test_authored_walk_does_not_omit_a_restored_directory(self):
        skill = self.repository.add_skill("alpha")
        references = skill / "references"
        references.mkdir()
        expected = references / "guide.md"
        expected.write_text("required reference\n", encoding="utf-8")
        moved = skill / "moved-references"
        original_scandir = authored_content.os.scandir
        references_identity = (
            references.stat().st_dev,
            references.stat().st_ino,
        )
        replaced = False

        def replacing_scandir(directory):
            nonlocal replaced
            if (
                not replaced
                and isinstance(directory, int)
                and (
                    authored_content.os.fstat(directory).st_dev,
                    authored_content.os.fstat(directory).st_ino,
                )
                == references_identity
            ):
                references.rename(moved)
                references.mkdir()
                references.rmdir()
                moved.rename(references)
                replaced = True
            return original_scandir(directory)

        with (
            patch.object(
                authored_content.os,
                "scandir",
                side_effect=replacing_scandir,
            ),
            self.assertRaisesRegex(
                authored_content.AuthoredContentReadError,
                "changed during traversal",
            ),
        ):
            tuple(
                authored_content.walk_authored_files(
                    references,
                    skill,
                )
            )

        self.assertTrue(replaced)
        self.assertEqual(expected.read_text(encoding="utf-8"), "required reference\n")

    def test_rejects_duplicate_names_and_folder_name_mismatches(self):
        self.repository.add_skill("shared", group="one")
        self.repository.add_skill("shared", group="two", folder="alias")

        messages = self.messages()

        self.assertTrue(any("duplicate skill name 'shared'" in message for message in messages))
        self.assertTrue(any("folder name 'alias' must match" in message for message in messages))

    def test_requires_an_approved_status(self):
        self.repository.add_skill("alpha", status=None)
        self.assert_issue("metadata.status is required")

        self.repository.cleanup()
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.cleanup)
        self.repository.add_skill("alpha", status="retired")
        self.assert_issue("metadata.status must be one of")

    def test_rejects_non_boolean_string_tool_reference_metadata(self):
        self.repository.add_skill("alpha", allows_tool_references="yes")

        self.assert_issue("metadata.allows_tool_references must be 'true' or 'false'")

    def test_surfaces_agent_skills_frontmatter_constraints(self):
        invalid_documents = {
            "unknown-field": "---\nname: alpha\ndescription: Valid.\nowner: me\n---\n",
            "invalid-name": "---\nname: Bad_Name\ndescription: Valid.\n---\n",
            "description-limit": (
                "---\nname: alpha\ndescription: " + ("x" * 1025) + "\n---\n"
            ),
            "compatibility-limit": (
                "---\nname: alpha\ndescription: Valid.\ncompatibility: "
                + ("x" * 501)
                + "\n---\n"
            ),
            "metadata-values": (
                "---\nname: alpha\ndescription: Valid.\nmetadata:\n  nested:\n"
                "    value: invalid\n---\n"
            ),
            "allowed-tools": (
                "---\nname: alpha\ndescription: Valid.\nallowed-tools:\n  - shell\n---\n"
            ),
        }

        for label, document in invalid_documents.items():
            with self.subTest(label=label):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                skill_root = repository.root / "skills" / "workflows" / "alpha"
                skill_root.mkdir(parents=True)
                (skill_root / "SKILL.md").write_text(document, encoding="utf-8")

                issues = run_static_validation(repository.root)

                self.assertTrue(issues, label)

    def test_frontmatter_diagnostics_do_not_disclose_unknown_field_names(self):
        skill_root = self.repository.add_skill("alpha")
        secret_field = "ghp_" + ("a" * 36)
        (skill_root / "SKILL.md").write_text(
            (
                "---\n"
                "name: alpha\n"
                "description: Valid.\n"
                f"{secret_field}: value\n"
                "---\n"
            ),
            encoding="utf-8",
        )

        issues = run_static_validation(self.repository.root)

        self.assertTrue(issues)
        self.assertTrue(
            any(
                "unsupported top-level frontmatter field" in issue.message
                for issue in issues
            ),
            issues,
        )
        self.assertTrue(
            all(secret_field not in issue.message for issue in issues),
            issues,
        )


class RepositoryPolicyValidationTests(TemporaryRepositoryTestCase):
    def test_config_and_local_required_skills_require_compatibility(self):
        for status in ("config-required", "local-required"):
            with self.subTest(status=status):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                repository.add_skill("alpha", status=status)

                messages = [issue.message for issue in run_static_validation(repository.root)]

                self.assertTrue(any("requires non-empty compatibility" in message for message in messages))

    def test_rejects_public_installer_internal_metadata(self):
        skill_root = self.repository.add_skill(
            "alpha",
            metadata={"internal": "true"},
        )
        skill_path = skill_root / "SKILL.md"
        skill_path.write_text(
            skill_path.read_text(encoding="utf-8").replace(
                '  internal: "true"',
                "  internal: true",
            ),
            encoding="utf-8",
        )

        self.assert_issue("metadata.internal is reserved")

    def test_config_required_compatibility_names_configuration_variables(self):
        self.repository.add_skill(
            "alpha",
            status="config-required",
            compatibility="Requires local configuration.",
        )
        self.assert_issue("must name an environment variable or config-file path variable")

        self.repository.cleanup()
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.cleanup)
        self.repository.add_skill(
            "alpha",
            status="config-required",
            compatibility="Requires APP_CONFIG_PATH to name the local configuration file.",
        )
        self.assert_no_issues()

    def test_requires_both_eval_files(self):
        self.repository.add_skill("alpha", with_evals=False)
        self.assert_issue("missing evals/evals.json")

        self.repository.cleanup()
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.cleanup)
        self.repository.add_skill("alpha", with_triggers=False)
        self.assert_issue("missing evals/triggers.json")

    def test_trigger_schema_requires_positive_and_negative_queries(self):
        skill_root = self.repository.add_skill("alpha")
        trigger_path = skill_root / "evals" / "triggers.json"

        for queries, expected in (
            (
                [{"id": "positive", "query": "Use alpha.", "should_trigger": True}],
                "should_trigger: false",
            ),
            (
                [
                    {
                        "id": "negative",
                        "query": "Do something else.",
                        "should_trigger": False,
                    }
                ],
                "should_trigger: true",
            ),
        ):
            with self.subTest(expected=expected):
                self.repository.write_json(
                    trigger_path,
                    {"skill_name": "alpha", "queries": queries},
                )
                self.assert_issue(expected)

    def test_trigger_schema_rejects_runner_repetition_configuration(self):
        skill_root = self.repository.add_skill("alpha")
        trigger_path = skill_root / "evals" / "triggers.json"
        data = json.loads(trigger_path.read_text(encoding="utf-8"))
        data["runs"] = 3
        self.repository.write_json(trigger_path, data)

        self.assert_issue("additionalProperties")

    def test_references_to_collaborators_require_metadata_opt_in(self):
        bodies = (
            "Use the `beta` skill.",
            "Use the `code-reviewer` agent.",
            "Run this through the Codex harness.",
            "Call the `mcp__linear__get_issue` tool.",
        )
        for body in bodies:
            with self.subTest(body=body):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                repository.add_skill("alpha", body=body)
                if "beta" in body:
                    repository.add_skill("beta")

                messages = [issue.message for issue in run_static_validation(repository.root)]

                self.assertTrue(
                    any("requires metadata.allows_tool_references: 'true'" in message for message in messages),
                    messages,
                )

    def test_tool_reference_opt_in_requires_collaborator_compatibility_or_fallback(self):
        self.repository.add_skill(
            "alpha",
            allows_tool_references="true",
            body="Call the `mcp__linear__get_issue` tool.",
        )
        self.assert_issue("must document collaborator requirements or fallback behavior")

        self.repository.cleanup()
        self.repository = TemporaryRepository()
        self.addCleanup(self.repository.cleanup)
        self.repository.add_skill(
            "alpha",
            compatibility=(
                "Requires the mcp__linear__get_issue tool; if unavailable, use supplied issue data."
            ),
            allows_tool_references="true",
            body="Call the `mcp__linear__get_issue` tool.",
        )
        self.assert_no_issues()

    def test_explicit_skill_references_use_retained_public_names(self):
        self.repository.add_skill(
            "alpha",
            compatibility="Requires the removed-skill skill; stop if it is unavailable.",
            allows_tool_references="true",
            body="Use the `removed-skill` skill.",
        )

        self.assert_issue("references unknown public skill 'removed-skill'")

    def test_valid_retained_skill_reference_passes(self):
        self.repository.add_skill(
            "alpha",
            compatibility="Requires the beta skill; stop if it is unavailable.",
            allows_tool_references="true",
            body="Use the `beta` skill.",
        )
        self.repository.add_skill("beta")

        self.assert_no_issues()

    def test_ordinary_prose_does_not_create_a_skill_reference(self):
        self.repository.add_skill(
            "alpha",
            body="Practice a reusable skill through deliberate repetition.",
        )

        self.assert_no_issues()


class PathAndDirectoryValidationTests(TemporaryRepositoryTestCase):
    def test_rejects_secret_shaped_authored_path_components(self):
        skill_root = self.repository.add_skill("alpha")
        secret_directory = "ghp_" + ("b" * 36)
        secret_file = "sk-" + ("c" * 24) + ".md"
        secret_assignment_file = "clientSecret=actual-client-value.md"
        nested_file = (
            skill_root
            / "references"
            / secret_directory
            / secret_file
        )
        nested_file.parent.mkdir(parents=True)
        nested_file.write_text("Benign content.\n", encoding="utf-8")
        (nested_file.parent / secret_assignment_file).write_text(
            "Benign content.\n",
            encoding="utf-8",
        )

        issues = run_static_validation(self.repository.root)
        rendered = repr(issues)

        matching = [
            issue
            for issue in issues
            if "high-confidence secret in an authored path component"
            in issue.message
        ]
        self.assertEqual(len(matching), 3, issues)
        self.assertNotIn(secret_directory, rendered)
        self.assertNotIn(secret_file.removesuffix(".md"), rendered)
        self.assertNotIn("actual-client-value", rendered)

    def test_static_diagnostics_redact_secret_shaped_path_components(self):
        skill_name = "sk-" + ("a" * 24)
        nested_directory_name = "ghp_" + ("b" * 36)
        nested_file_name = "sk-" + ("c" * 24) + ".md"
        assignment_value = "prod-" + "secret-value"
        assignment_file_name = (
            f"API_TOKEN=FAKE_example {assignment_value}.md"
        )
        commented_assignment_file_name = (
            f"API_TOKEN=FAKE_example # {assignment_value}.md"
        )
        multiline_assignment_file_name = (
            f"API_TOKEN=FAKE_example\n{assignment_value}.md"
        )
        skill_root = self.repository.add_skill(skill_name)
        nested_file = (
            skill_root
            / "references"
            / nested_directory_name
            / nested_file_name
        )
        nested_file.parent.mkdir(parents=True)
        nested_file.write_text(
            "Read /Users/private-user/account.json.\n",
            encoding="utf-8",
        )
        (nested_file.parent / assignment_file_name).write_text(
            "Read /Users/private-user/credentials.json.\n",
            encoding="utf-8",
        )
        for filename in (
            commented_assignment_file_name,
            multiline_assignment_file_name,
        ):
            (nested_file.parent / filename).write_text(
                "Read /Users/private-user/credentials.json.\n",
                encoding="utf-8",
            )

        issues = run_static_validation(self.repository.root)

        self.assertTrue(
            any("contains a personal absolute path" in issue.message for issue in issues),
            issues,
        )
        rendered = repr(issues)
        for secret_shaped_component in (
            skill_name,
            nested_directory_name,
            nested_file_name.removesuffix(".md"),
            assignment_value,
        ):
            self.assertNotIn(secret_shaped_component, rendered)
        for issue in issues:
            self.assertEqual(
                find_static_secret_issues(issue.scope, Path("diagnostic-scope")),
                [],
            )
            self.assertEqual(
                find_static_secret_issues(issue.message, Path("diagnostic-message")),
                [],
            )

    def test_rejects_entries_omitted_by_the_public_installer_at_any_depth(self):
        skill_root = self.repository.add_skill("alpha")
        excluded_file = skill_root / "references" / "nested" / "metadata.json"
        excluded_file.parent.mkdir(parents=True)
        excluded_file.write_text("{}\n", encoding="utf-8")
        for name in (".git", "__pycache__", "__pypackages__"):
            directory = skill_root / "assets" / "nested" / name
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "content.txt").write_text("content\n", encoding="utf-8")

        messages = self.messages()

        self.assertTrue(
            any(
                "public installer excludes entry metadata.json" in message
                for message in messages
            )
        )
        for name in (".git", "__pycache__", "__pypackages__"):
            self.assertTrue(
                any(
                    f"public installer excludes directory {name}" in message
                    for message in messages
                ),
                messages,
            )

    def test_rejects_installer_excluded_names_on_directory_symlinks(self):
        skill_root = self.repository.add_skill("alpha")
        assets = skill_root / "assets"
        assets.mkdir()
        target = assets / "shared-cache"
        target.mkdir()
        (target / "content.txt").write_text("content\n", encoding="utf-8")
        for name in (".git", "__pycache__", "__pypackages__"):
            (assets / name).symlink_to(target, target_is_directory=True)

        messages = self.messages()

        for name in (".git", "__pycache__", "__pypackages__"):
            self.assertTrue(
                any(
                    f"public installer excludes directory {name}" in message
                    for message in messages
                ),
                messages,
            )

    def test_rejects_metadata_json_for_every_entry_type(self):
        for entry_type in ("directory", "symlink"):
            with self.subTest(entry_type=entry_type):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                skill_root = repository.add_skill("alpha")
                references = skill_root / "references"
                references.mkdir()
                excluded = references / "metadata.json"
                if entry_type == "directory":
                    excluded.mkdir()
                    (excluded / "content.txt").write_text(
                        "content\n",
                        encoding="utf-8",
                    )
                else:
                    target = skill_root / "assets" / "metadata-source.json"
                    target.parent.mkdir()
                    target.write_text("{}\n", encoding="utf-8")
                    excluded.symlink_to(target)

                messages = [
                    issue.message
                    for issue in run_static_validation(repository.root)
                ]

                self.assertTrue(
                    any(
                        "public installer excludes entry metadata.json"
                        in message
                        for message in messages
                    ),
                    messages,
                )

    def test_rejects_parent_and_missing_local_markdown_references(self):
        self.repository.add_skill(
            "alpha",
            body="Read [outside](../outside.md) and [missing](references/missing.md).",
        )

        messages = self.messages()

        self.assertTrue(any("must not contain '..'" in message for message in messages))
        self.assertTrue(any("referenced local file does not exist" in message for message in messages))

    def test_accepts_existing_skill_relative_markdown_references(self):
        skill_root = self.repository.add_skill(
            "alpha", body="Read [the reference](references/guide.md)."
        )
        references = skill_root / "references"
        references.mkdir()
        (references / "guide.md").write_text("Guidance.\n", encoding="utf-8")
        self.repository.exercise_bundled_path(skill_root, "references/guide.md")

        self.assert_no_issues()

    def test_accepts_reference_definitions_and_escaped_markdown_destinations(self):
        skill_root = self.repository.add_skill(
            "alpha",
            body=(
                "Read [the guide][guide].\n\n"
                "[guide]: references/guide\\ file.md\n"
                "Read [the appendix](references/appendix\\(v2\\).md)."
            ),
        )
        references = skill_root / "references"
        references.mkdir()
        (references / "guide file.md").write_text("Guidance.\n", encoding="utf-8")
        (references / "appendix(v2).md").write_text("Appendix.\n", encoding="utf-8")
        self.repository.exercise_bundled_path(skill_root, "references/guide file.md")

        self.assert_no_issues()

    def test_rejects_missing_reference_definition_destinations(self):
        self.repository.add_skill(
            "alpha",
            body="Read [the missing guide][guide].\n\n[guide]: references/missing\\ file.md",
        )

        self.assert_issue("referenced local file does not exist: references/missing file.md")

    def test_rejects_missing_referenced_scripts(self):
        self.repository.add_skill("alpha", body="Run `scripts/prepare.py`.")

        self.assert_issue("referenced local file does not exist: scripts/prepare.py")

    def test_remote_urls_do_not_create_bundled_path_references(self):
        self.repository.add_skill(
            "alpha",
            body="Read https://example.test/scripts/remote-tool.py for background.",
            allows_tool_references="true",
            compatibility=(
                "Uses the linked public documentation; if unavailable, continue "
                "without it."
            ),
        )

        self.assert_no_issues()

    def test_file_urls_and_windows_paths_are_not_treated_as_external(self):
        self.repository.add_skill(
            "alpha",
            body=(
                "Read [local](file:///Users/example/private.md) and "
                "[windows](C:\\Users\\example\\private.md)."
            ),
        )

        messages = self.messages()

        self.assertTrue(any("must be skill-relative" in message for message in messages))
        self.assertTrue(any("personal absolute path" in message for message in messages))

    def test_bare_file_uri_is_rejected_even_when_its_bundled_suffix_exists(self):
        skill_root = self.repository.add_skill(
            "alpha",
            body=(
                "Read file:///tmp/references/guide.md and "
                "file:/tmp/references/guide.md."
            ),
        )
        guide = skill_root / "references" / "guide.md"
        guide.parent.mkdir()
        guide.write_text("# Guide\n", encoding="utf-8")
        self.repository.exercise_bundled_path(skill_root, "references/guide.md")

        self.assert_issue("local reference must be skill-relative: file:///tmp/references/guide.md")
        self.assert_issue("local reference must be skill-relative: file:/tmp/references/guide.md")

    def test_windows_drive_relative_reference_is_rejected(self):
        self.repository.add_skill(
            "alpha",
            body="Read [private](C:../private.txt).",
        )

        self.assert_issue(
            "reference must be a clean skill-relative path: C:../private.txt"
        )

    def test_bare_windows_drive_bundled_paths_are_not_reduced_to_relative_paths(self):
        skill_root = self.repository.add_skill(
            "alpha",
            body=(
                "Read C:/references/guide.md, C:references/guide.md, "
                "C:\\references\\guide.md, and C:references\\guide.md."
            ),
        )
        guide = skill_root / "references" / "guide.md"
        guide.parent.mkdir()
        guide.write_text("# Guide\n", encoding="utf-8")
        self.repository.exercise_bundled_path(skill_root, "references/guide.md")

        messages = self.messages()

        self.assertGreaterEqual(
            sum(
                "must be a clean skill-relative path" in message
                for message in messages
            ),
            4,
        )

    def test_nested_absolute_paths_are_not_reduced_to_bundled_suffixes(self):
        skill_root = self.repository.add_skill(
            "alpha",
            body=(
                "Run C:/checkout/scripts/tool.py and read "
                "/opt/project/references/guide.md."
            ),
        )
        script = skill_root / "scripts" / "tool.py"
        script.parent.mkdir()
        script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        script.chmod(0o755)
        guide = skill_root / "references" / "guide.md"
        guide.parent.mkdir()
        guide.write_text("# Guide\n", encoding="utf-8")
        self.repository.exercise_bundled_path(skill_root, "scripts/tool.py")
        self.repository.exercise_bundled_path(skill_root, "references/guide.md")

        messages = self.messages()

        self.assertTrue(
            any(
                "clean skill-relative path: C:/checkout/scripts/tool.py" in message
                for message in messages
            ),
            messages,
        )
        self.assertTrue(
            any(
                "clean skill-relative path: /opt/project/references/guide.md"
                in message
                for message in messages
            ),
            messages,
        )

    def test_repeated_windows_separators_are_rejected_as_complete_drive_paths(self):
        skill_root = self.repository.add_skill(
            "alpha",
            body=(
                "Run C://scripts/tool.py and read "
                r"C:\\references\\guide.md."
            ),
        )
        script = skill_root / "scripts" / "tool.py"
        script.parent.mkdir()
        script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        script.chmod(0o755)
        guide = skill_root / "references" / "guide.md"
        guide.parent.mkdir()
        guide.write_text("# Guide\n", encoding="utf-8")
        self.repository.exercise_bundled_path(skill_root, "scripts/tool.py")
        self.repository.exercise_bundled_path(skill_root, "references/guide.md")

        messages = self.messages()

        self.assertGreaterEqual(
            sum(
                "must be a clean skill-relative path" in message
                for message in messages
            ),
            2,
        )

    def test_scripts_have_an_executable_contract(self):
        skill_root = self.repository.add_skill("alpha", body="Run `scripts/prepare.sh`.")
        script = skill_root / "scripts" / "prepare.sh"
        script.parent.mkdir()
        script.write_text("#!/bin/sh\nprintf 'ready\\n'\n", encoding="utf-8")
        script.chmod(0o644)
        self.assert_issue("must be executable")

        script.chmod(0o755)
        self.repository.exercise_bundled_path(skill_root, "scripts/prepare.sh")
        self.assert_no_issues()

    def test_rejects_personal_absolute_paths_in_authored_content(self):
        skill_root = self.repository.add_skill("alpha", body="Use /Users/example/config.json.")
        references = skill_root / "references"
        references.mkdir()
        (references / "guide.md").write_text("See /home/example/setup.\n", encoding="utf-8")
        scripts = skill_root / "scripts"
        scripts.mkdir()
        script = scripts / "run.sh"
        script.write_text("#!/bin/sh\ncd /Users/example/project\n", encoding="utf-8")
        script.chmod(0o755)

        issues = run_static_validation(self.repository.root)

        self.assertGreaterEqual(sum("personal absolute path" in issue.message for issue in issues), 3)

    def test_assets_receive_secret_scanning_without_prose_policy_checks(self):
        skill_root = self.repository.add_skill("alpha")
        assets = skill_root / "assets"
        assets.mkdir()
        credential_shape = "gh" + "p_" + ("a" * 36)
        (assets / "sample.txt").write_text(
            f"{credential_shape}\n/Users/example/not-scanned\n", encoding="utf-8"
        )
        self.repository.exercise_bundled_path(skill_root, "assets/sample.txt")

        messages = self.messages()
        self.assertEqual(
            sum("github-token" in message for message in messages),
            1,
        )
        self.assertFalse(
            any("personal absolute path" in message for message in messages)
        )

    def test_installable_assets_scan_utf16_secret_values(self):
        token = "ghp_" + ("a" * 36)
        for encoding in ("utf-16-le", "utf-16-be"):
            for prefix in (b"", b"x"):
                with self.subTest(encoding=encoding, offset=len(prefix)):
                    repository = TemporaryRepository()
                    self.addCleanup(repository.cleanup)
                    skill_root = repository.add_skill("alpha")
                    asset = skill_root / "assets" / "credential.bin"
                    asset.parent.mkdir()
                    asset.write_bytes(prefix + token.encode(encoding))
                    repository.exercise_bundled_path(
                        skill_root,
                        "assets/credential.bin",
                    )

                    messages = [
                        issue.message
                        for issue in run_static_validation(repository.root)
                    ]

                    self.assertTrue(
                        any("github-token" in message for message in messages)
                    )

    def test_rejects_unsupported_empty_and_placeholder_entries(self):
        skill_root = self.repository.add_skill("alpha")
        unsupported = skill_root / "unsupported"
        unsupported.mkdir()
        (unsupported / "content.txt").write_text("unsupported\n", encoding="utf-8")
        (skill_root / "assets").mkdir()
        references = skill_root / "references"
        references.mkdir()
        (references / ".gitkeep").write_text("", encoding="utf-8")
        (skill_root / "NOTES.txt").write_text("notes\n", encoding="utf-8")

        messages = self.messages()

        for name in ("unsupported", "NOTES.txt"):
            self.assertTrue(any(name in message for message in messages), messages)
        self.assertTrue(any("empty directory" in message for message in messages))
        self.assertTrue(any(".gitkeep placeholders are not allowed" in message for message in messages))

    def test_rejects_broken_and_escaping_symlinks(self):
        skill_root = self.repository.add_skill("alpha")
        assets = skill_root / "assets"
        assets.mkdir()
        (assets / "broken").symlink_to(assets / "missing")
        outside = self.repository.root / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")
        (assets / "outside").symlink_to(outside)

        messages = self.messages()

        self.assertTrue(any("broken symlink" in message for message in messages))
        self.assertTrue(any("symlink target must stay inside" in message for message in messages))

    def test_reports_self_referential_symlinks_without_raising(self):
        skill_root = self.repository.add_skill("alpha")
        assets = skill_root / "assets"
        assets.mkdir()
        (assets / "self").symlink_to("self")

        self.assert_issue("invalid symlink: assets/self")

    def test_reports_two_link_symlink_loops_without_raising(self):
        skill_root = self.repository.add_skill("alpha")
        assets = skill_root / "assets"
        assets.mkdir()
        (assets / "one").symlink_to("two")
        (assets / "two").symlink_to("one")

        messages = self.messages()

        self.assertTrue(any("invalid symlink: assets/one" in message for message in messages))
        self.assertTrue(any("invalid symlink: assets/two" in message for message in messages))

    def test_does_not_traverse_an_escaping_content_root_symlink(self):
        skill_root = self.repository.add_skill("alpha")
        external_references = self.repository.root / "external-references"
        external_references.mkdir()
        credential_shape = "gh" + "p_" + ("a" * 36)
        (external_references / "outside.md").write_text(credential_shape, encoding="utf-8")
        (skill_root / "references").symlink_to(external_references)

        messages = self.messages()

        self.assertTrue(any("symlink target must stay inside" in message for message in messages))
        self.assertFalse(any("high-confidence secret" in message for message in messages))

    def test_scans_contained_file_symlinks_in_authored_content_directories(self):
        skill_root = self.repository.add_skill("alpha")
        assets = skill_root / "assets"
        assets.mkdir()
        credential_shape = "sk" + "-" + ("a" * 32)
        target = assets / "authored-reference.md"
        target.write_text(credential_shape, encoding="utf-8")
        references = skill_root / "references"
        references.mkdir()
        (references / "linked.md").symlink_to(target)

        self.assert_issue("openai-api-key")

    def test_logical_reference_aliases_keep_markdown_specific_validation(self):
        skill_root = self.repository.add_skill("alpha")
        assets = skill_root / "assets"
        assets.mkdir()
        target = assets / "shared-reference.txt"
        target.write_text("Read [missing](references/missing.md).\n", encoding="utf-8")
        references = skill_root / "references"
        references.mkdir()
        (references / "shared.txt").symlink_to(target)
        (references / "shared.md").symlink_to(target)

        self.assert_issue("referenced local file does not exist: references/missing.md")

    def test_applies_the_executable_contract_to_contained_script_symlinks(self):
        skill_root = self.repository.add_skill("alpha")
        assets = skill_root / "assets"
        assets.mkdir()
        target = assets / "prepare.sh"
        target.write_text("#!/bin/sh\nprintf 'ready\\n'\n", encoding="utf-8")
        target.chmod(0o644)
        scripts = skill_root / "scripts"
        scripts.mkdir()
        (scripts / "prepare.sh").symlink_to(target)

        self.assert_issue("scripts/prepare.sh must be executable")

    def test_follows_acyclic_contained_directory_aliases_once(self):
        skill_root = self.repository.add_skill("alpha")
        assets = skill_root / "assets"
        material = assets / "reference-material"
        material.mkdir(parents=True)
        credential_shape = "sk" + "-" + ("a" * 32)
        (material / "guide.md").write_text(credential_shape, encoding="utf-8")
        references = skill_root / "references"
        references.mkdir()
        linked = references / "linked"
        linked.symlink_to(material, target_is_directory=True)

        messages = self.messages()

        self.assertEqual(sum("openai-api-key" in message for message in messages), 2)
        self.assertFalse(
            any("directory symlink cycle" in message for message in messages)
        )

    def test_rejects_contained_directory_symlink_cycles(self):
        skill_root = self.repository.add_skill("alpha")
        material = skill_root / "assets" / "reference-material"
        material.mkdir(parents=True)
        (material / "guide.md").write_text("Guidance.\n", encoding="utf-8")
        references = skill_root / "references"
        references.mkdir()
        linked = references / "linked"
        linked.symlink_to(material, target_is_directory=True)
        cycle = material / "cycle"
        cycle.symlink_to(linked, target_is_directory=True)

        self.assert_issue(
            "directory symlink cycle is not installable: "
            "assets/reference-material/cycle"
        )

    def test_directory_symlinks_keep_directory_specific_content_scans(self):
        skill_root = self.repository.add_skill("alpha")
        assets = skill_root / "assets"
        reference_material = assets / "reference-material"
        script_material = assets / "script-material"
        eval_material = assets / "eval-material"
        for directory in (reference_material, script_material, eval_material):
            directory.mkdir(parents=True)

        github_shape = "gh" + "p_" + ("a" * 36)
        slack_shape = "xo" + "xb-" + ("1" * 12) + "-" + ("a" * 24)
        aws_shape = "AK" + "IA" + ("A" * 16)
        (reference_material / "ignored.txt").write_text(github_shape, encoding="utf-8")
        script = script_material / "authored.txt"
        script.write_text(slack_shape, encoding="utf-8")
        script.chmod(0o755)
        (eval_material / "authored.txt").write_text(aws_shape, encoding="utf-8")

        references = skill_root / "references"
        references.mkdir()
        (references / "linked").symlink_to(reference_material, target_is_directory=True)
        scripts = skill_root / "scripts"
        scripts.mkdir()
        (scripts / "linked").symlink_to(script_material, target_is_directory=True)
        (skill_root / "evals" / "linked").symlink_to(
            eval_material, target_is_directory=True
        )

        messages = self.messages()

        self.assertEqual(sum("github-token" in message for message in messages), 2)
        self.assertEqual(sum("slack-token" in message for message in messages), 2)
        self.assertEqual(sum("aws-access-key-id" in message for message in messages), 2)

    def test_repository_readme_is_not_scanned(self):
        self.repository.add_skill("alpha")
        credential_shape = "sk" + "-" + ("a" * 32)
        (self.repository.root / "README.md").write_text(
            f"Example: {credential_shape}\n/Users/example/readme\n", encoding="utf-8"
        )

        self.assert_no_issues()

    def test_personal_paths_ignore_uris_and_documentation_placeholders(self):
        self.repository.add_skill(
            "alpha",
            body=(
                "See https://example.test/home/alice/setup and "
                "https://example.test/Users/alice/setup.\n"
                "Document /home/<username>/config, /Users/${USER}/config, and "
                r"C:\Users\<username>\config."
            ),
        )

        self.assert_no_issues()

    def test_personal_paths_still_reject_concrete_user_directories(self):
        self.repository.add_skill(
            "alpha",
            body="Use /home/alice/config, /Users/alice/config, and C:\\Users\\alice\\config.",
        )

        issues = run_static_validation(self.repository.root)

        self.assertEqual(sum("personal absolute path" in issue.message for issue in issues), 3)

    def test_personal_path_findings_are_bounded_per_authored_file(self):
        self.repository.add_skill(
            "alpha",
            body="\n".join(
                f"Use /Users/person-{index}/config."
                for index in range(256)
            ),
        )

        issues = run_static_validation(self.repository.root)
        personal_issues = [
            issue
            for issue in issues
            if "personal absolute path" in issue.message
        ]

        self.assertEqual(len(personal_issues), 128)
        self.assertTrue(
            any(
                "exceeds the static personal paths inspection limit" in issue.message
                for issue in issues
            )
        )

    def test_local_reference_inspection_fails_closed_at_its_target_limit(self):
        self.repository.add_skill(
            "alpha",
            body="\n".join(
                "[guide](references/missing.md)"
                for _ in range(1100)
            ),
        )

        messages = self.messages()

        self.assertTrue(
            any(
                "exceeds the static local references inspection limit" in message
                for message in messages
            ),
            messages,
        )


class EvalValidationTests(TemporaryRepositoryTestCase):
    def test_rejects_duplicate_keys_in_eval_trigger_and_fixture_json(self):
        for target in ("evals", "triggers", "fixture"):
            with self.subTest(target=target):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                skill_root = repository.add_skill("alpha")
                if target == "evals":
                    path = skill_root / "evals" / "evals.json"
                    path.write_text(
                        '{"skill_name":"alpha","skill_name":"alpha","evals":[]}',
                        encoding="utf-8",
                    )
                elif target == "triggers":
                    path = skill_root / "evals" / "triggers.json"
                    path.write_text(
                        '{"skill_name":"alpha","skill_name":"alpha","queries":[]}',
                        encoding="utf-8",
                    )
                else:
                    path = repository.declare_basic_case_input(
                        skill_root,
                        "duplicate.json",
                    )
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('{"value":1,"value":2}', encoding="utf-8")

                messages = [
                    issue.message for issue in run_static_validation(repository.root)
                ]

                self.assertTrue(
                    any("duplicate object key" in message for message in messages),
                    messages,
                )

    def test_duplicate_json_key_errors_do_not_disclose_the_key(self):
        secret_key = "ghp_" + ("a" * 36)
        document = (
            '{"'
            + secret_key
            + '":1,"'
            + secret_key
            + '":2}'
        )

        with self.assertRaises(authored_content.BoundedJsonError) as raised:
            authored_content.strict_bounded_json_loads(document)

        self.assertIn("duplicate object key", str(raised.exception))
        self.assertNotIn(secret_key, str(raised.exception))

    def test_rejects_an_eval_tree_replaced_during_validation(self):
        skill_root = self.repository.add_skill("alpha")
        real_read = static_eval_checks.read_bounded_authored_bytes
        replaced = False

        def replace_after_read(source, **kwargs):
            nonlocal replaced
            content = real_read(source, **kwargs)
            if not replaced and source.logical_path.name == "evals.json":
                replacement = skill_root / "evals" / "triggers.replacement"
                replacement.write_text(
                    (skill_root / "evals" / "triggers.json").read_text(
                        encoding="utf-8"
                    )
                    + "\n",
                    encoding="utf-8",
                )
                replacement.replace(skill_root / "evals" / "triggers.json")
                replaced = True
            return content

        with patch.object(
            static_eval_checks,
            "read_bounded_authored_bytes",
            side_effect=replace_after_read,
        ):
            messages = self.messages()

        self.assertTrue(replaced)
        self.assertTrue(
            any("eval definition tree changed during validation" in message for message in messages),
            messages,
        )

    def test_required_eval_json_uses_the_bounded_descriptor_reader(self):
        skill_root = self.repository.add_skill("alpha")
        evals_path = skill_root / "evals" / "evals.json"
        original_read_text = Path.read_text

        def reject_unbounded_eval_read(path: Path, *args, **kwargs):
            if path == evals_path:
                raise AssertionError("eval JSON must not use Path.read_text")
            return original_read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", reject_unbounded_eval_read):
            messages = self.messages()

        self.assertFalse(
            any(
                "evals/evals.json contains invalid JSON" in message
                for message in messages
            ),
            messages,
        )

    def test_required_eval_json_must_parse_as_objects_with_expected_lists(self):
        skill_root = self.repository.add_skill("alpha")
        (skill_root / "evals" / "evals.json").write_text("[]", encoding="utf-8")

        self.assert_issue("evals/evals.json schema error")

        (skill_root / "evals" / "evals.json").write_text("{", encoding="utf-8")
        self.assert_issue("invalid JSON")

    def test_eval_fixture_paths_are_contained_and_exist(self):
        skill_root = self.repository.add_skill("alpha")
        self.repository.write_json(
            skill_root / "evals" / "evals.json",
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "missing",
                        "prompt": "Run.",
                        "expected_output": "A result.",
                        "assertions": ["The result is complete."],
                        "files": ["fixtures/missing/inputs/context.txt"],
                        "checks": [],
                    },
                    {
                        "id": "escape",
                        "prompt": "Run.",
                        "expected_output": "A result.",
                        "assertions": ["The result is complete."],
                        "files": ["../outside.json"],
                        "checks": [],
                    },
                ]
            },
        )

        messages = self.messages()

        self.assertTrue(any("actor input does not exist" in message for message in messages))
        self.assertTrue(any("schema error" in message for message in messages))

    def test_auto_discovers_every_unsupported_eval_topology_entry(self):
        bypasses = (
            (
                "arbitrary root file",
                Path("notes.txt"),
                "unsupported evals entry: notes.txt",
            ),
            (
                "extra root JSON",
                Path("extra.json"),
                "unsupported evals entry: extra.json",
            ),
            (
                "arbitrary root directory",
                Path("unsupported/content.txt"),
                "unsupported evals entry: unsupported",
            ),
            (
                "fixture-root file",
                Path("fixtures/orphan.txt"),
                "eval fixture case entry must be a contained non-symlink directory: "
                "evals/fixtures/orphan.txt",
            ),
            (
                "undeclared case tree",
                Path("fixtures/undeclared/context.txt"),
                "fixture tree belongs to undeclared eval case 'undeclared'",
            ),
            (
                "undeclared case JSON",
                Path("fixtures/basic/extra.json"),
                "undeclared eval fixture file: evals/fixtures/basic/extra.json",
            ),
        )

        for label, relative_path, expected in bypasses:
            with self.subTest(label=label):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                skill_root = repository.add_skill("alpha")
                path = skill_root / "evals" / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "{}" if path.suffix == ".json" else "fixture\n",
                    encoding="utf-8",
                )

                messages = [
                    issue.message for issue in run_static_validation(repository.root)
                ]

                self.assertTrue(any(expected in message for message in messages), messages)

    def test_rejects_symlinked_required_eval_files(self):
        for filename in ("evals.json", "triggers.json"):
            for target_kind in ("contained", "escaping", "broken"):
                with self.subTest(filename=filename, target_kind=target_kind):
                    repository = TemporaryRepository()
                    self.addCleanup(repository.cleanup)
                    external = tempfile.TemporaryDirectory()
                    self.addCleanup(external.cleanup)
                    skill_root = repository.add_skill("alpha")
                    path = skill_root / "evals" / filename
                    original = path.read_text(encoding="utf-8")
                    path.unlink()
                    if target_kind == "contained":
                        other_name = (
                            "triggers.json" if filename == "evals.json" else "evals.json"
                        )
                        target = path.with_name(other_name)
                    elif target_kind == "escaping":
                        target = Path(external.name) / filename
                        target.write_text(original, encoding="utf-8")
                    else:
                        target = path.with_name(f"missing-{filename}")
                    path.symlink_to(target)
                    expected = (
                        f"evals/{filename} must be a contained non-symlink regular file"
                    )

                    messages = [
                        issue.message for issue in run_static_validation(repository.root)
                    ]

                    self.assertTrue(
                        any(expected in message for message in messages), messages
                    )

    def test_rejects_every_symlink_variant_at_eval_directory_boundaries(self):
        boundaries = {
            Path("evals"): "evals must be a contained non-symlink directory",
            Path("evals/fixtures"): (
                "evals/fixtures must be a contained non-symlink directory"
            ),
            Path("evals/fixtures/basic"): (
                "eval fixture case entry must be a contained non-symlink directory: "
                "evals/fixtures/basic"
            ),
        }

        for boundary, expected in boundaries.items():
            for target_kind in ("contained", "escaping", "broken"):
                with self.subTest(boundary=boundary, target_kind=target_kind):
                    repository = TemporaryRepository()
                    self.addCleanup(repository.cleanup)
                    external = tempfile.TemporaryDirectory()
                    self.addCleanup(external.cleanup)
                    skill_root = repository.add_skill("alpha")
                    link = skill_root / boundary
                    if boundary == Path("evals"):
                        if target_kind == "contained":
                            target = skill_root / "assets" / "evals-target"
                        elif target_kind == "escaping":
                            target = Path(external.name) / "evals-target"
                        else:
                            target = skill_root / "missing-evals-target"
                        if target_kind == "broken":
                            shutil.rmtree(link)
                        else:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(link), target)
                    else:
                        link.parent.mkdir(parents=True, exist_ok=True)
                        if target_kind == "contained":
                            target = skill_root / "assets" / f"{boundary.name}-target"
                        elif target_kind == "escaping":
                            target = Path(external.name) / f"{boundary.name}-target"
                        else:
                            target = skill_root / f"missing-{boundary.name}-target"
                        if target_kind != "broken":
                            target.mkdir(parents=True)
                            (target / "fixture.txt").write_text(
                                "fixture\n", encoding="utf-8"
                            )
                    link.symlink_to(target, target_is_directory=True)

                    messages = [
                        issue.message for issue in run_static_validation(repository.root)
                    ]

                    self.assertTrue(
                        any(expected in message for message in messages), messages
                    )

    def test_rejects_empty_eval_fixture_directories_at_every_depth(self):
        directories = (
            Path("evals/fixtures"),
            Path("evals/fixtures/basic"),
            Path("evals/fixtures/basic/inputs"),
        )

        for relative_path in directories:
            with self.subTest(relative_path=relative_path):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                skill_root = repository.add_skill("alpha")
                (skill_root / relative_path).mkdir(parents=True)

                messages = [
                    issue.message for issue in run_static_validation(repository.root)
                ]

                expected = f"empty directory is not allowed: {relative_path}"
                self.assertTrue(any(expected in message for message in messages), messages)

    def test_rejects_broken_and_non_case_fixture_symlinks(self):
        for target_kind in ("broken", "escaping", "outside-case"):
            with self.subTest(target_kind=target_kind):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                external = tempfile.TemporaryDirectory()
                self.addCleanup(external.cleanup)
                skill_root = repository.add_skill("alpha")
                case_root = skill_root / "evals" / "fixtures" / "basic"
                case_root.mkdir(parents=True)
                link = case_root / "linked-fixture.txt"
                if target_kind == "broken":
                    target = case_root / "missing.txt"
                    expected = "broken eval fixture symlink"
                elif target_kind == "escaping":
                    target = Path(external.name) / "fixture.txt"
                    target.write_text("fixture\n", encoding="utf-8")
                    expected = "eval fixture symlink target must stay inside its case"
                else:
                    target = skill_root / "assets" / "fixture.txt"
                    target.parent.mkdir()
                    target.write_text("fixture\n", encoding="utf-8")
                    expected = "eval fixture symlink target must stay inside its case"
                link.symlink_to(target)

                messages = [
                    issue.message for issue in run_static_validation(repository.root)
                ]

                self.assertTrue(any(expected in message for message in messages), messages)

    def test_accepts_declared_case_input_schema_and_mockserver_fixture(self):
        skill_root = self.repository.add_skill("alpha")
        actor_input = self.repository.declare_basic_case_input(
            skill_root, "context.json"
        )
        self.repository.write_json(actor_input, {"source": "fixture"})
        schema_path = (
            skill_root / "evals" / "fixtures" / "basic" / "result.schema.json"
        )
        self.repository.write_json(schema_path, {"type": "object"})
        evals_path = skill_root / "evals" / "evals.json"
        document = json.loads(evals_path.read_text(encoding="utf-8"))
        document["evals"][0]["checks"].append(
            {
                "type": "json_schema",
                "path": "result.json",
                "schema": "fixtures/basic/result.schema.json",
            }
        )
        self.repository.write_json(evals_path, document)
        self.repository.write_json(
            skill_root
            / "evals"
            / "fixtures"
            / "basic"
            / "mockserverInitialization.json",
            {
                "id": "get-resource",
                "httpRequest": {
                    "method": "GET",
                    "path": "/resource",
                    "headers": {"Host": ["api.example.test"]},
                },
                "httpResponse": {"statusCode": 200},
            },
        )

        self.assert_no_issues()

    def test_runner_only_schema_aggregate_has_an_exact_byte_limit(self):
        for difference, should_fail in ((0, False), (-1, True)):
            with self.subTest(difference=difference):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                skill_root = repository.add_skill("alpha")
                schema_path = (
                    skill_root
                    / "evals"
                    / "fixtures"
                    / "basic"
                    / "result.schema.json"
                )
                repository.write_json(
                    schema_path,
                    {
                        "type": "object",
                        "description": "x" * 1024,
                    },
                )
                evals_path = skill_root / "evals" / "evals.json"
                document = json.loads(evals_path.read_text(encoding="utf-8"))
                document["evals"][0]["checks"].append(
                    {
                        "type": "json_schema",
                        "path": "result.json",
                        "schema": "fixtures/basic/result.schema.json",
                    }
                )
                repository.write_json(evals_path, document)
                byte_limit = schema_path.stat().st_size + difference

                with patch.object(
                    eval_definitions,
                    "MAX_CASE_DETERMINISTIC_SCHEMA_BYTES",
                    byte_limit,
                ):
                    messages = [
                        issue.message
                        for issue in run_static_validation(repository.root)
                    ]

                has_limit_issue = any(
                    "deterministic schemas exceed" in message
                    for message in messages
                )
                self.assertEqual(has_limit_issue, should_fail, messages)

    def test_deep_runner_only_schema_fails_as_a_bounded_validation_issue(self):
        skill_root = self.repository.add_skill("alpha")
        schema_path = (
            skill_root / "evals" / "fixtures" / "basic" / "result.schema.json"
        )
        schema_path.parent.mkdir(parents=True)
        schema_path.write_text(
            '{"allOf":[' * 80 + '{"type":"object"}' + "]}" * 80,
            encoding="utf-8",
        )
        evals_path = skill_root / "evals" / "evals.json"
        document = json.loads(evals_path.read_text(encoding="utf-8"))
        document["evals"][0]["checks"].append(
            {
                "type": "json_schema",
                "path": "result.json",
                "schema": "fixtures/basic/result.schema.json",
            }
        )
        self.repository.write_json(evals_path, document)

        messages = self.messages()

        self.assertTrue(
            any(
                "runner-only schema is not a valid JSON Schema object"
                in message
                for message in messages
            ),
            messages,
        )

    def test_runner_only_schema_swap_is_rejected_by_the_stable_reader(self):
        skill_root = self.repository.add_skill("alpha")
        schema_path = (
            skill_root / "evals" / "fixtures" / "basic" / "result.schema.json"
        )
        self.repository.write_json(schema_path, {"type": "object"})
        outside = self.repository.root / "outside-schema.json"
        self.repository.write_json(outside, {"type": "object"})
        evals_path = skill_root / "evals" / "evals.json"
        document = json.loads(evals_path.read_text(encoding="utf-8"))
        document["evals"][0]["checks"].append(
            {
                "type": "json_schema",
                "path": "result.json",
                "schema": "fixtures/basic/result.schema.json",
            }
        )
        self.repository.write_json(evals_path, document)
        stable_authored_file = eval_definitions.authored_file
        canonical_schema_path = schema_path.resolve()

        def discover_then_swap(path, root):
            source = stable_authored_file(path, root)
            if (
                path == canonical_schema_path
                and source is not None
                and not schema_path.is_symlink()
            ):
                schema_path.unlink()
                schema_path.symlink_to(outside)
            return source

        with patch.object(
            eval_definitions,
            "authored_file",
            side_effect=discover_then_swap,
        ):
            messages = self.messages()

        self.assertTrue(
            any("runner-only schema" in message for message in messages),
            messages,
        )

    def test_eval_json_rejects_non_fake_secret_values(self):
        skill_root = self.repository.add_skill("alpha")
        unsafe_assignment = "SERVICE_TOKEN=" + "authored" + "-value"
        self.repository.write_json(
            skill_root / "evals" / "evals.json",
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "secret",
                        "prompt": unsafe_assignment,
                        "expected_output": "A result.",
                        "assertions": ["The result is complete."],
                        "checks": [],
                    }
                ],
            },
        )

        self.assert_issue("sensitive-assignment")

        self.repository.write_json(
            skill_root / "evals" / "evals.json",
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "fake",
                        "prompt": "SERVICE_TOKEN=FAKE_authored-value",
                        "expected_output": "A result.",
                        "assertions": ["The result is complete."],
                        "checks": [],
                    }
                ],
            },
        )
        self.assert_no_issues()

    def test_eval_json_scans_secrets_revealed_by_unicode_escapes(self):
        skill_root = self.repository.add_skill("alpha")
        evals_path = skill_root / "evals" / "evals.json"
        document = json.loads(evals_path.read_text(encoding="utf-8"))
        token = "ghp_" + ("a" * 36)
        document["evals"][0]["prompt"] = token
        encoded = json.dumps(document, separators=(",", ":")).replace(
            token,
            r"ghp_\u0061" + ("a" * 35),
        )
        evals_path.write_text(encoded, encoding="utf-8")

        self.assert_issue("after JSON decoding: github-token")

    def test_eval_text_fixtures_reject_non_fake_secret_values(self):
        skill_root = self.repository.add_skill("alpha")
        fixture = self.repository.declare_basic_case_input(
            skill_root, "environment.env"
        )
        fixture.parent.mkdir(parents=True)
        fixture.write_text("SERVICE_TOKEN=" + "authored-value\n", encoding="utf-8")

        self.assert_issue("sensitive-assignment")

    def test_eval_binary_fixtures_reject_non_fake_secret_values(self):
        skill_root = self.repository.add_skill("alpha")
        fixture = self.repository.declare_basic_case_input(skill_root, "sample.bin")
        fixture.parent.mkdir(parents=True)
        fixture.write_bytes(b"\x00SERVICE_TOKEN=authored-value\xff")

        self.assert_issue("sensitive-assignment")

    def test_eval_binary_fixtures_scan_utf16_secret_values(self):
        token = "ghp_" + ("a" * 36)
        for encoding in ("utf-16-le", "utf-16-be"):
            for prefix in (b"", b"x"):
                with self.subTest(encoding=encoding, offset=len(prefix)):
                    repository = TemporaryRepository()
                    self.addCleanup(repository.cleanup)
                    skill_root = repository.add_skill("alpha")
                    fixture = repository.declare_basic_case_input(
                        skill_root,
                        "credential.bin",
                    )
                    fixture.parent.mkdir(parents=True)
                    fixture.write_bytes(prefix + token.encode(encoding))

                    messages = [
                        issue.message
                        for issue in run_static_validation(repository.root)
                    ]

                    self.assertTrue(
                        any("github-token" in message for message in messages)
                    )

    def test_eval_json_fixtures_scan_escaped_credential_keys(self):
        skill_root = self.repository.add_skill("alpha")
        fixture = self.repository.declare_basic_case_input(
            skill_root,
            "credentials.JSON",
        )
        fixture.parent.mkdir(parents=True)
        fixture.write_text(
            r'{"api\u005ftoken":"actual-prod-value"}',
            encoding="utf-8",
        )

        self.assert_issue("after JSON decoding: sensitive-assignment")

    def test_eval_json_scans_escaped_service_prefixed_credential_keys(self):
        skill_root = self.repository.add_skill("alpha")
        fixture = self.repository.declare_basic_case_input(
            skill_root,
            "credentials.JSON",
        )
        fixture.parent.mkdir(parents=True)
        fixture.write_text(
            r'{"github\u0054oken":"actual-prod-value"}',
            encoding="utf-8",
        )

        self.assert_issue("after JSON decoding: sensitive-assignment")

    def test_installable_json_scans_escaped_credential_keys(self):
        skill_root = self.repository.add_skill("alpha")
        asset = skill_root / "assets" / "credentials.JSON"
        asset.parent.mkdir()
        asset.write_text(
            r'{"api\u005ftoken":"actual-prod-value"}',
            encoding="utf-8",
        )

        self.assert_issue(
            "high-confidence secret after JSON decoding sensitive-assignment"
        )

    def test_eval_binary_fixtures_detect_known_tokens_beside_high_bytes(self):
        skill_root = self.repository.add_skill("alpha")
        fixture = self.repository.declare_basic_case_input(skill_root, "sample.bin")
        fixture.parent.mkdir(parents=True)
        fixture.write_bytes(b"\xffghp_" + (b"a" * 36) + b"\xfe")

        self.assert_issue("github-token")

    def test_eval_fixtures_scan_common_credential_assignment_keys(self):
        cases = (
            (
                "credentials.json",
                b'{"api_token":"actual-prod-value"}',
            ),
            (
                "credentials-camel.json",
                b'{"apiKey":"actual-prod-value"}',
            ),
            (
                "environment.env",
                b"DATABASE_PASSWORD=actual-prod-value\n",
            ),
            (
                "credentials.bin",
                b"\xffclient_secret=actual-prod-value\xfe",
            ),
        )
        for filename, content in cases:
            with self.subTest(filename=filename):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                skill_root = repository.add_skill("alpha")
                fixture = repository.declare_basic_case_input(
                    skill_root,
                    filename,
                )
                fixture.parent.mkdir(parents=True)
                fixture.write_bytes(content)

                messages = [
                    issue.message
                    for issue in run_static_validation(repository.root)
                ]
                self.assertTrue(
                    any("sensitive-assignment" in message for message in messages),
                    messages,
                )

    def test_eval_fixture_limit_matches_runtime_preparation(self):
        skill_root = self.repository.add_skill("alpha")
        fixture = self.repository.declare_basic_case_input(skill_root, "sample.bin")
        fixture.parent.mkdir(parents=True)
        fixture.write_bytes(b"\x00" * (3 * 1024 * 1024))

        self.assert_no_issues()

        fixture.write_bytes(b"\x00" * (4 * 1024 * 1024 + 1))
        self.assert_issue("4 MiB eval fixture file limit")

    def test_eval_json_is_parsed_and_scanned_from_one_stable_read(self):
        skill_root = self.repository.add_skill("alpha")
        fixture = self.repository.declare_basic_case_input(
            skill_root,
            "context.json",
        )
        fixture.parent.mkdir(parents=True)
        fixture.write_text('{"status":"ok"}\n', encoding="utf-8")
        schema = (
            skill_root
            / "evals"
            / "fixtures"
            / "basic"
            / "result.schema.json"
        )
        self.repository.write_json(schema, {"type": "object"})
        evals_path = skill_root / "evals" / "evals.json"
        document = json.loads(evals_path.read_text(encoding="utf-8"))
        document["evals"][0]["checks"].append(
            {
                "type": "json_schema",
                "path": "result.json",
                "schema": "fixtures/basic/result.schema.json",
            }
        )
        self.repository.write_json(evals_path, document)
        reads: list[Path] = []
        real_read = static_eval_checks.read_bounded_authored_bytes

        def recording_read(source, *args, **kwargs):
            reads.append(source.logical_path)
            return real_read(source, *args, **kwargs)

        with patch.object(
            static_eval_checks,
            "read_bounded_authored_bytes",
            side_effect=recording_read,
        ):
            self.messages()

        expected_paths = (
            skill_root / "evals" / "evals.json",
            skill_root / "evals" / "triggers.json",
            fixture,
            schema,
        )
        for path in expected_paths:
            self.assertEqual(
                reads.count(path.resolve()),
                1,
                f"{path} must be parsed and scanned from one read",
            )

    def test_authored_file_swap_to_fifo_is_rejected_without_blocking(self):
        skill_root = self.repository.add_skill("alpha")
        reference = skill_root / "references" / "guide.md"
        reference.parent.mkdir()
        reference.write_text("guide\n", encoding="utf-8")
        parked = reference.with_name("guide.parked")
        real_open = authored_content.os.open
        replaced = False

        def replace_with_fifo(path, flags, *args, **kwargs):
            nonlocal replaced
            if Path(path) == reference.resolve() and not replaced:
                reference.rename(parked)
                os.mkfifo(reference)
                replaced = True
            return real_open(path, flags, *args, **kwargs)

        source = authored_content.authored_file(reference, skill_root)
        assert source is not None
        with (
            patch.object(
                authored_content.os,
                "open",
                side_effect=replace_with_fifo,
            ),
            self.assertRaisesRegex(
                authored_content.AuthoredContentReadError,
                "opened safely|changed while it was opened",
            ),
        ):
            authored_content.read_bounded_authored_bytes(
                source,
                maximum_bytes=1024,
                allowed_root=skill_root,
            )

        self.assertTrue(replaced)

    def test_deep_eval_and_fixture_json_fail_as_bounded_validation_issues(self):
        skill_root = self.repository.add_skill("alpha")
        deep_json = "[" * 100 + "0" + "]" * 100
        evals_path = skill_root / "evals" / "evals.json"
        evals_path.write_text(deep_json, encoding="utf-8")

        self.assert_issue("JSON input exceeds the depth limit")

        self.repository.write_json(
            evals_path,
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "basic",
                        "prompt": "Perform the workflow.",
                        "expected_output": "A complete workflow result.",
                        "assertions": ["The result is complete."],
                        "files": ["fixtures/basic/inputs/deep.json"],
                        "checks": [],
                    }
                ],
            },
        )
        fixture = skill_root / "evals" / "fixtures" / "basic" / "inputs" / "deep.json"
        fixture.parent.mkdir(parents=True)
        fixture.write_text(deep_json, encoding="utf-8")

        self.assert_issue("JSON input exceeds the depth limit")

    def test_logical_eval_aliases_keep_json_specific_validation(self):
        skill_root = self.repository.add_skill("alpha")
        assets = skill_root / "assets"
        assets.mkdir()
        target = assets / "shared-eval.txt"
        target.write_text("{", encoding="utf-8")
        evals = skill_root / "evals"
        (evals / "z.txt").symlink_to(target)
        (evals / "a.json").symlink_to(target)

        self.assert_issue("evals/a.json contains invalid JSON")

    def test_mockserver_initialization_uses_the_strict_fixture_policy(self):
        skill_root = self.repository.add_skill("alpha")
        initialization = (
            skill_root
            / "evals"
            / "fixtures"
            / "basic"
            / "mockserverInitialization.json"
        )
        self.repository.write_json(
            initialization,
            {
                "id": "get-resource",
                "httpRequest": {
                    "method": "GET",
                    "path": "/resource",
                    "headers": {"Host": ["api.example.test"]},
                },
                "httpResponse": {"statusCode": 200},
            },
        )
        self.assert_no_issues()

        self.repository.write_json(
            initialization,
            {
                "id": "unsafe-forward",
                "httpRequest": {
                    "method": "GET",
                    "path": "/resource",
                    "headers": {"Host": ["api.example.test"]},
                },
                "httpForward": {"host": "production.example.test", "port": 443},
            },
        )

        self.assert_issue("MockServer fixture is invalid")

    def test_mockserver_initialization_rejects_symlinks(self):
        skill_root = self.repository.add_skill("alpha")
        fixture_root = skill_root / "evals" / "fixtures" / "basic"
        fixture_root.mkdir(parents=True)
        target = fixture_root / "expectations.json"
        self.repository.write_json(
            target,
            {
                "id": "get-resource",
                "httpRequest": {
                    "method": "GET",
                    "path": "/resource",
                    "headers": {"Host": ["api.example.test"]},
                },
                "httpResponse": {"statusCode": 200},
            },
        )
        initialization = fixture_root / "mockserverInitialization.json"
        initialization.write_text("[]", encoding="utf-8")
        self.assert_issue("MockServer fixture is invalid")

        initialization.unlink()
        initialization.symlink_to(target)

        self.assert_issue("MockServer fixture must be a non-symlink regular file")


class SecretPatternTests(unittest.TestCase):
    def test_reports_only_redacted_high_confidence_secret_metadata(self):
        values = {
            "github-token": "gh" + "p_" + ("a" * 36),
            "slack-token": "xo" + "xb-" + ("1" * 12) + "-" + ("a" * 24),
            "aws-access-key-id": "AK" + "IA" + ("A" * 16),
            "openai-api-key": "s" + "k-" + ("a" * 32),
        }
        private_key = (
            "-----BEGIN " + "PRIVATE KEY-----\nZmFrZQ==\n-----END " + "PRIVATE KEY-----"
        )
        text = "\n".join([*values.values(), private_key])

        matches = find_static_secret_issues(text, Path("SKILL.md"))

        self.assertEqual(
            {match.pattern for match in matches},
            {*values, "private-key-block"},
        )
        self.assertEqual(
            [field.name for field in fields(SecretMatch)],
            ["pattern", "category", "confidence", "source", "line", "column"],
        )
        rendered = repr(matches)
        for value in values.values():
            self.assertNotIn(value, rendered)
        self.assertNotIn("ZmFrZQ", rendered)
        self.assertTrue(all(match.confidence == "high" for match in matches))
        self.assertTrue(all(match.line > 0 and match.column > 0 for match in matches))

    def test_known_token_patterns_use_ascii_boundaries(self):
        values = {
            "github-token": "gh" + "p_" + ("a" * 36),
            "slack-token": "xo" + "xb-" + ("a" * 24),
            "aws-access-key-id": "AK" + "IA" + ("A" * 16),
            "openai-api-key": "s" + "k-" + ("a" * 24),
        }

        for expected, token in values.items():
            with self.subTest(expected=expected):
                text = (b"\xff" + token.encode("ascii") + b"\xfe").decode(
                    "latin-1"
                )
                matches = find_static_secret_issues(
                    text,
                    Path("fixture.bin"),
                )
                self.assertEqual(
                    [match.pattern for match in matches],
                    [expected],
                )

    def test_slack_app_tokens_are_detected_in_every_authored_form(self):
        token = (
            "xapp-1-A0123456789-1234567890123-"
            "abcdefghijklmnopqrstuvwxyz0123456789"
        )
        text_findings = find_static_secret_issues(
            token,
            Path("credential.txt"),
        )
        binary_findings = (
            authored_content.find_static_secret_issues_in_bytes(
                b"\xff" + token.encode("ascii") + b"\xfe",
                Path("credential.bin"),
            )
        )
        encoded_token = token.replace("a", r"\u0061", 1)
        decoded_findings = (
            authored_content.find_additional_decoded_json_secret_issues(
                json.loads(f'{{"value":"{encoded_token}"}}'),
                Path("credential.json"),
                maximum_bytes=4096,
            )
        )

        for findings in (text_findings, binary_findings, decoded_findings):
            self.assertEqual(
                [finding.pattern for finding in findings],
                ["slack-token"],
            )

    def test_aws_temporary_credential_documents_are_detected(self):
        access_key_id = "AS" + "IA" + ("A" * 16)
        credential = {
            "AccessKeyId": access_key_id,
            "SecretAccessKey": "actual-secret-value",
            "SessionToken": "actual-session-token-value",
        }

        raw_findings = find_static_secret_issues(
            json.dumps(credential),
            Path("credentials.json"),
        )

        self.assertIn(
            "aws-access-key-id",
            [finding.pattern for finding in raw_findings],
        )
        self.assertGreaterEqual(
            sum(
                finding.pattern == "sensitive-assignment"
                for finding in raw_findings
            ),
            2,
        )

    def test_decoded_aws_credential_keys_are_detected(self):
        encoded = (
            r'{"Access\u004beyId":"ABCDEFGHIJKLMNOPQRST",'
            r'"SecretAccess\u004bey":"actual-secret-value",'
            r'"Session\u0054oken":"actual-session-token-value"}'
        )
        raw_findings = find_static_secret_issues(
            encoded,
            Path("credentials.json"),
        )
        decoded_findings = (
            authored_content.find_additional_decoded_json_secret_issues(
                json.loads(encoded),
                Path("credentials.json"),
                maximum_bytes=4096,
                raw_findings=raw_findings,
            )
        )

        self.assertEqual(raw_findings, [])
        self.assertEqual(
            sum(
                finding.pattern == "sensitive-assignment"
                for finding in decoded_findings
            ),
            3,
        )

    def test_aws_credential_fields_preserve_fake_value_exemptions(self):
        credential = {
            "AccessKeyId": "FAKE_ASIA" + ("A" * 16),
            "SecretAccessKey": "FAKE_documentation-secret",
            "SessionToken": "FAKE_documentation-session",
        }

        self.assertEqual(
            find_static_secret_issues(
                json.dumps(credential),
                Path("credentials.json"),
            ),
            [],
        )

    def test_all_official_github_token_families_are_detected_in_every_form(self):
        tokens = (
            "ghp_" + ("a" * 36),
            "gho_" + ("a" * 36),
            "ghu_" + ("a" * 36),
            "ghs_" + ("a" * 36),
            "ghr_" + ("a" * 76),
            "github_pat_" + ("a" * 82),
            (
                "ghs_123456789_"
                + ("a" * 32)
                + "."
                + ("b" * 32)
                + "."
                + ("c" * 32)
            ),
        )

        for token in tokens:
            with self.subTest(prefix=token.split("_", 1)[0]):
                raw_matches = find_static_secret_issues(
                    token,
                    Path("credential.txt"),
                )
                binary_text = (
                    b"\xff" + token.encode("ascii") + b"\xfe"
                ).decode("latin-1")
                binary_matches = find_static_secret_issues(
                    binary_text,
                    Path("credential.bin"),
                )
                encoded_token = token.replace("a", r"\u0061", 1)
                document = json.loads(f'{{"value":"{encoded_token}"}}')
                decoded_matches = (
                    authored_content.find_additional_decoded_json_secret_issues(
                        document,
                        Path("credential.json"),
                        maximum_bytes=4096,
                        raw_findings=(),
                    )
                )

                self.assertEqual(
                    [match.pattern for match in raw_matches],
                    ["github-token"],
                )
                self.assertEqual(
                    [match.pattern for match in binary_matches],
                    ["github-token"],
                )
                self.assertEqual(
                    [match.pattern for match in decoded_matches],
                    ["github-token"],
                )

    def test_allows_environment_references_placeholders_and_fake_values(self):
        safe_text = "\n".join(
            (
                "LINEAR_API_KEY",
                "${LINEAR_API_KEY}",
                'os.environ["LINEAR_API_KEY"]',
                "process.env.LINEAR_API_KEY",
                "LINEAR_API_KEY=",
                "LINEAR_API_KEY=${LINEAR_API_KEY}",
                "LINEAR_API_KEY=REDACTED",
                "LINEAR_API_KEY=<YOUR_TOKEN>",
                "LINEAR_API_KEY=FAKE_documentation-value",
                "A token, secret, password, and credential are discussed in prose.",
            )
        )

        self.assertEqual(find_static_secret_issues(safe_text, Path("reference.md")), [])

    def test_sensitive_assignments_inspect_the_literal_value(self):
        unsafe_values = (
            "LINEAR_API_KEY=" + "authored-value",
            "SERVICE_TOKEN: " + "authored-value",
            "APP_SECRET='" + "authored-value'",
        )

        for line in unsafe_values:
            with self.subTest(line=line):
                matches = find_static_secret_issues(line, Path("script.sh"))
                self.assertEqual([match.pattern for match in matches], ["sensitive-assignment"])

    def test_sensitive_assignments_cover_structured_keys_and_environment_access(self):
        unsafe_values = (
            '"SERVICE_TOKEN": "' + "authored-value\"",
            'os.environ["SERVICE_TOKEN"] = "' + "authored-value\"",
            "process.env.SERVICE_TOKEN = '" + "authored-value'",
            "SERVICE_TOKEN=" + "ACTUALPRODUCTIONTOKEN",
        )

        for line in unsafe_values:
            with self.subTest(line=line):
                matches = find_static_secret_issues(line, Path("authored.txt"))
                self.assertEqual([match.pattern for match in matches], ["sensitive-assignment"])

    def test_sensitive_assignment_covers_aws_secret_access_key(self):
        unsafe_values = (
            "AWS_SECRET_ACCESS_KEY=" + "authored-value",
            "aws_secret_access_key = " + "authored-value",
            '"aws_secret_access_key": "' + 'authored-value"',
        )

        for unsafe in unsafe_values:
            with self.subTest(unsafe=unsafe):
                matches = find_static_secret_issues(
                    unsafe,
                    Path("environment.env"),
                )
                self.assertEqual(
                    [match.pattern for match in matches],
                    ["sensitive-assignment"],
                )

    def test_sensitive_assignment_covers_case_insensitive_credential_keys(self):
        unsafe_values = (
            '{"api_token":"' + 'actual-prod-value"}',
            "DATABASE_PASSWORD=" + "actual-prod-value",
            "client_secret: " + "actual-prod-value",
            "token: " + "actual-prod-value",
            "credentials='" + "actual-prod-value'",
            "process.env.refresh_token = '" + "actual-prod-value'",
            'os.environ["private_key"] = "' + 'actual-prod-value"',
            'SERVICE_TOKEN = os.getenv("BASE") + "' + 'actual-prod-value"',
            'client_secret: data.get("token") + "' + 'actual-prod-value"',
            "apiKey=" + "actual-prod-value",
            "accessToken=" + "actual-prod-value",
            "clientSecret=" + "actual-prod-value",
            "privateKey=" + "actual-prod-value",
            "refreshToken=" + "actual-prod-value",
            "githubToken=" + "actual-prod-value",
            "linearApiKey=" + "actual-prod-value",
            '"api-key": "' + 'actual-prod-value"',
            'const config = { clientSecret: "' + 'actual-prod-value" };',
            'const config = { api_token: "' + 'actual-prod-value" };',
        )

        for unsafe in unsafe_values:
            with self.subTest(unsafe=unsafe):
                matches = find_static_secret_issues(
                    unsafe,
                    Path("credentials.txt"),
                )
                self.assertEqual(
                    [match.pattern for match in matches],
                    ["sensitive-assignment"],
                )

    def test_case_insensitive_credential_keys_keep_safe_value_exemptions(self):
        safe_values = (
            "api_token=${API_TOKEN}",
            "database_password=FAKE_documentation-value",
            'client_secret="<YOUR_SECRET>"',
            "credentials=REDACTED",
            "process.env.refresh_token = process.env.OTHER_TOKEN",
            'oauth_token = os.environ.get("BITBUCKET_TOKEN", "")',
            "credentials = base64.b64encode(value)",
            'PRIVATE_KEY=$(<"$GH_BOT_PRIVATE_KEY_PATH")',
            "TOKEN=$(printf '%s' \"$RESPONSE\")",
            'token = data.get("token")',
            "OAuth 2 access token: set BITBUCKET_TOKEN",
            "apiKey=FAKE_documentation-value",
            "accessToken=<YOUR_TOKEN>",
            "clientSecret=REDACTED",
            "privateKey=${PRIVATE_KEY}",
            "refreshToken=process.env.OTHER_TOKEN",
            "githubToken=FAKE_documentation-value",
            "linearApiKey=${LINEAR_API_KEY}",
            '"api-key": "<YOUR_TOKEN>"',
            'const config = { clientSecret: "FAKE_documentation-value" };',
            'const config = { api_token: "<YOUR_TOKEN>" };',
            "type Config = { clientSecret: string };",
        )

        for safe in safe_values:
            with self.subTest(safe=safe):
                self.assertEqual(
                    find_static_secret_issues(
                        safe,
                        Path("credentials.txt"),
                    ),
                    [],
                )

    def test_sensitive_assignment_recursively_inspects_call_arguments_and_defaults(self):
        unsafe_values = (
            'API_TOKEN = os.getenv("API_TOKEN", "prod-secret-value")',
            'API_TOKEN = os.getenv("API_TOKEN", default="prod-secret-value")',
            'API_TOKEN = choose(os.getenv("API_TOKEN"), fallback("prod-secret-value"))',
            (
                "API_TOKEN = os.getenv(\n"
                '    "API_TOKEN",\n'
                '    "prod-secret-value",\n'
                ")\n"
            ),
        )
        safe_values = (
            'API_TOKEN = os.getenv("API_TOKEN")',
            'API_TOKEN = os.getenv("API_TOKEN", "")',
            'API_TOKEN = os.getenv("API_TOKEN", "REDACTED")',
            'API_TOKEN = os.getenv("API_TOKEN", fallback_token)',
            (
                "credentials = base64.b64encode(\n"
                '    f"{email}:{api_token}".encode("utf-8")\n'
                ').decode("ascii")\n'
            ),
            "VAULT_TOKEN=FAKE_DEV_TOKEN npm run dev",
        )

        for unsafe in unsafe_values:
            with self.subTest(unsafe=unsafe):
                self.assertEqual(
                    [
                        match.pattern
                        for match in find_static_secret_issues(
                            unsafe,
                            Path("credentials.py"),
                        )
                    ],
                    ["sensitive-assignment"],
                )
        for safe in safe_values:
            with self.subTest(safe=safe):
                self.assertEqual(
                    find_static_secret_issues(safe, Path("credentials.py")),
                    [],
                )

    def test_sensitive_assignment_rejects_calls_and_attributes_on_literal_receivers(self):
        github_token = "ghp_" + ("a" * 36)
        disguised_token = f"FAKE_X{github_token}"
        unsafe_values = (
            f'TOKEN = "{disguised_token}".removeprefix("FAKE_X")',
            f'TOKEN = "{disguised_token}".replace("FAKE_X", "")',
            f'TOKEN = "{disguised_token}".value',
        )

        for unsafe in unsafe_values:
            with self.subTest(unsafe=unsafe):
                self.assertEqual(
                    [
                        finding.pattern
                        for finding in find_static_secret_issues(
                            unsafe,
                            Path("credentials.py"),
                        )
                    ],
                    ["sensitive-assignment"],
                )

    def test_fake_assignment_exemption_requires_the_complete_value_to_be_fake(self):
        unsafe_values = (
            "API_TOKEN=FAKE_example actual-prod-value",
            'API_TOKEN = FAKE_example + "prod-secret-value"',
        )

        for unsafe in unsafe_values:
            with self.subTest(unsafe=unsafe):
                self.assertEqual(
                    [
                        match.pattern
                        for match in find_static_secret_issues(
                            unsafe,
                            Path("credentials.py"),
                        )
                    ],
                    ["sensitive-assignment"],
                )
        self.assertEqual(
            find_static_secret_issues(
                "API_TOKEN=FAKE_example",
                Path("credentials.py"),
            ),
            [],
        )

    def test_safe_assignment_does_not_mask_a_later_assignment(self):
        findings = find_static_secret_issues(
            "TOKEN=FAKE_placeholder env "
            "AWS_SECRET_ACCESS_KEY=actual-prod-value\n",
            Path("script.sh"),
        )

        self.assertEqual(
            [finding.pattern for finding in findings],
            ["sensitive-assignment"],
        )

    def test_sensitive_assignment_fails_closed_on_deep_python_expressions(self):
        authored_expression = "fallback" + (".value" * 1100)

        try:
            findings = find_static_secret_issues(
                f"API_TOKEN = {authored_expression}",
                Path("credentials.py"),
            )
        except RecursionError as error:
            self.fail(f"deep authored expression escaped the bounded scanner: {error}")

        self.assertEqual(
            [finding.pattern for finding in findings],
            ["sensitive-assignment"],
        )

    def test_generic_credential_keys_still_reject_assignment_literals(self):
        unsafe_values = (
            "token=actual-prod-value",
            "credentials='actual-prod-value'",
            '"password": "actual-prod-value"',
        )

        for unsafe in unsafe_values:
            with self.subTest(unsafe=unsafe):
                matches = find_static_secret_issues(
                    unsafe,
                    Path("credentials.txt"),
                )
                self.assertEqual(
                    [match.pattern for match in matches],
                    ["sensitive-assignment"],
                )

    def test_aws_secret_access_key_references_placeholders_and_fake_values_are_allowed(self):
        safe_values = (
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}",
            "AWS_SECRET_ACCESS_KEY=<YOUR_SECRET>",
            "AWS_SECRET_ACCESS_KEY=FAKE_documentation-value",
        )

        for line in safe_values:
            with self.subTest(line=line):
                self.assertEqual(
                    find_static_secret_issues(line, Path("environment.env")),
                    [],
                )

    def test_compound_shell_expressions_are_not_treated_as_pure_references(self):
        unsafe_values = (
            "SERVICE_TOKEN=${OTHER_TOKEN:-" + "authored-value}",
            "SERVICE_TOKEN=$OTHER_TOKEN-" + "authored-value",
            "SERVICE_TOKEN=$(printf " + "authored-value)",
            "SERVICE_TOKEN=FAKE_example$(printf " + "authored-value)",
            "client_secret: ${OTHER_TOKEN} " + "authored-value",
        )

        for line in unsafe_values:
            with self.subTest(line=line):
                matches = find_static_secret_issues(line, Path("environment.env"))
                self.assertEqual([match.pattern for match in matches], ["sensitive-assignment"])

    def test_shell_substitutions_require_exact_safe_commands_and_arguments(self):
        github_token = "ghp_" + ("a" * 36)
        unsafe_values = (
            f'TOKEN=$(printf %s{github_token} "$EMPTY")',
            'TOKEN=$(printf "%s" --prefix=authored-value "$EMPTY")',
            'TOKEN=$(lookup "$OTHER_TOKEN")',
            'TOKEN=$(printf "%s" "$OTHER_TOKEN"',
            'TOKEN=$(printf "%s" "$OTHER_TOKEN")authored-value',
        )

        for unsafe in unsafe_values:
            with self.subTest(unsafe=unsafe):
                self.assertEqual(
                    [
                        finding.pattern
                        for finding in find_static_secret_issues(
                            unsafe,
                            Path("environment.env"),
                        )
                    ],
                    ["sensitive-assignment"],
                )

    def test_shell_substitutions_allow_a_terminated_runtime_decoder_pipeline(self):
        source = (
            "TOKEN=$(printf '%s' \"$RESPONSE\" | python3 -I -S -c '\n"
            "import json\n"
            "import sys\n"
            "data = json.load(sys.stdin)\n"
            'token = data.get("token")\n'
            "print(token)\n"
            "') || exit 3\n"
        )

        self.assertEqual(
            find_static_secret_issues(source, Path("runtime-decoder.sh")),
            [],
        )

    def test_shell_substitutions_reject_extra_python_stdout_calls(self):
        source = (
            "TOKEN=$(printf '%s' \"$RESPONSE\" | python3 -I -S -c '\n"
            "import json\n"
            "import sys\n"
            "data = json.load(sys.stdin)\n"
            'token = data.get("token")\n'
            'sys.stdout.write("actual-prod-value")\n'
            "print(token)\n"
            "') || exit 3\n"
        )

        self.assertEqual(
            [
                finding.pattern
                for finding in find_static_secret_issues(
                    source,
                    Path("runtime-decoder.sh"),
                )
            ],
            ["sensitive-assignment"],
        )

    def test_shell_runtime_decoder_analysis_has_one_shared_work_budget(self):
        assignments = [
            "data = json.load(sys.stdin)",
            "level_0 = data",
            "level_0 = data",
        ]
        for index in range(1, 12):
            assignments.extend(
                (
                    f"level_{index} = level_{index - 1}",
                    f"level_{index} = level_{index - 1}",
                )
            )
        source = (
            "TOKEN=$(printf '%s' \"$RESPONSE\" | python3 -I -S -c '\n"
            "import json\n"
            "import sys\n"
            + "\n".join(assignments)
            + "\nprint(level_11)\n"
            "') || exit 3\n"
        )

        with patch.object(
            authored_content,
            "_MAX_PYTHON_DECODER_EVALUATION_STEPS",
            32,
        ):
            findings = find_static_secret_issues(
                source,
                Path("runtime-decoder.sh"),
            )

        self.assertEqual(
            [finding.pattern for finding in findings],
            ["sensitive-assignment"],
        )

    def test_shell_runtime_decoder_budget_is_shared_across_candidates(self):
        def pipeline(response: str) -> str:
            return (
                f"SERVICE_TOKEN=$(printf '%s' \"${response}\" | python3 -I -S -c '\n"
                "import json\n"
                "import sys\n"
                "data = json.load(sys.stdin)\n"
                'token = data.get("token")\n'
                "print(token)\n"
                "') || exit 3\n"
            )

        source = pipeline("RESPONSE_A") + pipeline("RESPONSE_B")
        with patch.object(
            authored_content,
            "_MAX_PYTHON_DECODER_EVALUATION_STEPS",
            12,
        ):
            findings = find_static_secret_issues(
                source,
                Path("runtime-decoders.sh"),
            )

        self.assertEqual(
            [finding.pattern for finding in findings],
            ["sensitive-assignment"],
        )

    def test_python_assignment_recovery_is_deferred_until_needed(self):
        source = "value = 1\n" * 100
        with patch.object(
            authored_content,
            "_python_assignment_values",
            side_effect=AssertionError("AST recovery must remain lazy"),
        ) as recover:
            findings = find_static_secret_issues(
                source,
                Path("large-safe-module.py"),
            )

        self.assertEqual(findings, [])
        recover.assert_not_called()

    def test_python_assignment_recovery_has_preparse_resource_limits(self):
        self.assertTrue(
            hasattr(
                authored_content,
                "_MAX_PYTHON_ASSIGNMENT_RECOVERY_BYTES",
            )
        )
        self.assertTrue(
            hasattr(
                authored_content,
                "_MAX_PYTHON_ASSIGNMENT_RECOVERY_TOKENS",
            )
        )
        oversized = "x" * (
            authored_content._MAX_PYTHON_ASSIGNMENT_RECOVERY_BYTES + 1
        )
        over_tokenized = "x=1;" * (
            authored_content._MAX_PYTHON_ASSIGNMENT_RECOVERY_TOKENS + 1
        )

        for label, source in (
            ("bytes", oversized),
            ("tokens", over_tokenized),
        ):
            with (
                self.subTest(limit=label),
                patch.object(
                    authored_content.ast,
                    "parse",
                    side_effect=AssertionError(
                        "resource guard must run before ast.parse"
                    ),
                ) as parse,
            ):
                values = authored_content._python_assignment_values(source)

            self.assertEqual(values, {})
            parse.assert_not_called()

    def test_binary_secret_views_are_decoded_and_scanned_lazily(self):
        sentinel = object()
        with patch.object(
            authored_content,
            "_scan_static_secret_byte_view",
            create=True,
            return_value=(sentinel,),
        ) as scan_view:
            findings = authored_content.find_static_secret_issues_in_bytes(
                b"content",
                Path("asset.bin"),
                maximum_findings=1,
            )

        self.assertEqual(findings, [sentinel])
        scan_view.assert_called_once()

    def test_utf32_binary_secret_views_cover_supported_secret_contracts(self):
        cases = (
            ("github-token", "ghp_" + ("a" * 36)),
            ("sensitive-assignment", "SERVICE_TOKEN=authored-value"),
            (
                "private-key-block",
                "-----BEGIN PRIVATE KEY-----\n"
                "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n"
                "-----END PRIVATE KEY-----",
            ),
        )
        for expected_pattern, text in cases:
            for encoding in ("utf-32-le", "utf-32-be"):
                for offset in range(4):
                    with self.subTest(
                        pattern=expected_pattern,
                        encoding=encoding,
                        offset=offset,
                    ):
                        findings = (
                            authored_content.find_static_secret_issues_in_bytes(
                                (b"x" * offset) + text.encode(encoding),
                                Path("asset.bin"),
                            )
                        )

                        self.assertIn(
                            expected_pattern,
                            [finding.pattern for finding in findings],
                        )

    def test_exact_environment_references_remain_allowed_assignment_values(self):
        safe_values = (
            "SERVICE_TOKEN=$OTHER_TOKEN",
            "SERVICE_TOKEN=${OTHER_TOKEN}",
            'SERVICE_TOKEN=os.environ["OTHER_TOKEN"]',
            "SERVICE_TOKEN=process.env.OTHER_TOKEN",
            "SERVICE_TOKEN={{ OTHER_TOKEN }}",
        )

        for line in safe_values:
            with self.subTest(line=line):
                self.assertEqual(
                    find_static_secret_issues(line, Path("authored.txt")), []
                )

    def test_quoted_authorization_headers_allow_exact_shell_variable_expansions(self):
        safe_headers = (
            'curl -H "Authorization: Bearer $JWT"',
            "curl -H 'Authorization: Bearer ${JWT}'",
            '  -H "Authorization: Bearer $JWT" \\',
            'headers={"Authorization": f"Bearer {oauth_token}"}',
            'headers={"Authorization": f"Basic {credentials}"}',
            '"Authorization": f"Bearer {jwt}",',
        )

        for header in safe_headers:
            with self.subTest(header=header):
                self.assertEqual(find_static_secret_issues(header, Path("script.sh")), [])

    def test_quoted_authorization_headers_reject_and_redact_literal_credentials(self):
        literal = "opaque-authorization-value"
        unsafe_headers = (
            f'curl -H "Authorization: Bearer {literal}"',
            f"curl -H 'Authorization: Bearer {literal}'",
            f'  -H "Authorization: Bearer {literal}" \\',
            f'headers={{"Authorization": f"Bearer {literal}"}}',
        )

        for header in unsafe_headers:
            with self.subTest(header=header):
                result = scan_static_secret_issues(header, Path("script.sh"))
                self.assertEqual(
                    [match.pattern for match in result.findings], ["authorization-value"]
                )
                self.assertNotIn(literal, result.durable_text)
                self.assertIn(SENSITIVE_TEXT_REDACTION, result.durable_text)

    def test_encrypted_private_key_blocks_always_fail_redacted(self):
        private_key = (
            "-----BEGIN "
            + "ENCRYPTED PRIVATE KEY-----\nZmFrZQ==\n-----END "
            + "ENCRYPTED PRIVATE KEY-----"
        )

        matches = find_static_secret_issues(private_key, Path("fixture.pem"))

        self.assertEqual([match.pattern for match in matches], ["private-key-block"])
        self.assertNotIn("ZmFrZQ", repr(matches))

    def test_unterminated_private_key_blocks_fail_and_redact_through_eof(self):
        private_key = (
            "prefix\n-----BEGIN PRIVATE KEY-----\n"
            "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n"
        )

        result = scan_static_secret_issues(private_key, Path("fixture.pem"))

        self.assertEqual(
            [match.pattern for match in result.findings],
            ["private-key-block"],
        )
        self.assertEqual(
            result.durable_text,
            "prefix\n" + SENSITIVE_TEXT_REDACTION,
        )
        self.assertNotIn("MIIEvQ", repr(result.findings))

    def test_openpgp_private_key_blocks_fail_closed_and_unterminated(self):
        for label in ("PGP PRIVATE KEY BLOCK", "PGP SECRET KEY BLOCK"):
            closed = (
                f"-----BEGIN {label}-----\n"
                "ZmFrZQ==\n"
                f"-----END {label}-----"
            )
            unterminated = (
                f"prefix\n-----BEGIN {label}-----\n"
                "ZmFrZQ==\n"
            )
            with self.subTest(label=label, state="closed"):
                result = scan_static_secret_issues(
                    closed,
                    Path("fixture.asc"),
                )
                self.assertEqual(
                    [finding.pattern for finding in result.findings],
                    ["private-key-block"],
                )
                self.assertNotIn("ZmFrZQ", result.durable_text)
            with self.subTest(label=label, state="unterminated"):
                result = scan_static_secret_issues(
                    unterminated,
                    Path("fixture.asc"),
                )
                self.assertEqual(
                    [finding.pattern for finding in result.findings],
                    ["private-key-block"],
                )
                self.assertEqual(
                    result.durable_text,
                    "prefix\n" + SENSITIVE_TEXT_REDACTION,
                )


class _FakeSkillsRefDistribution:
    def __init__(self, root: Path, commit: str) -> None:
        self._root = root
        self._commit = commit

    def locate_file(self, path: str) -> Path:
        return self._root / path

    def read_text(self, filename: str) -> str | None:
        if filename != "direct_url.json":
            return None
        return json.dumps(
            {
                "subdirectory": "skills-ref",
                "url": "https://github.com/agentskills/agentskills.git",
                "vcs_info": {
                    "commit_id": self._commit,
                    "requested_revision": self._commit,
                    "vcs": "git",
                },
            }
        )


class ReferenceConformanceTests(TemporaryRepositoryTestCase):
    def test_importing_conformance_does_not_execute_reference_validator(self):
        repository_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attacker = root / "site-packages"
            marker = root / "reference-validator-imported"
            package = attacker / "skills_ref"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('loaded', encoding='utf-8')\n",
                encoding="utf-8",
            )
            command = (
                "import sys\n"
                f"sys.path[:0] = [{str(repository_root)!r}, {str(attacker)!r}]\n"
                "import scripts.ai_skills_lib.static_checks.conformance\n"
            )

            completed = subprocess.run(
                [sys.executable, "-I", "-c", command],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(marker.exists())

    def test_preflight_imports_verified_sources_instead_of_a_shadow_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            distribution_root = root / "site-packages"
            installed_module = distribution_root / "skills_ref" / "__init__.py"
            installed_module.parent.mkdir(parents=True)
            verified_source = b"def validate(path):\n    return []\n"
            installed_module.write_bytes(verified_source)
            attacker_root = root / "attacker"
            attacker_module = attacker_root / "skills_ref" / "__init__.py"
            attacker_module.parent.mkdir(parents=True)
            marker = root / "shadow-package-imported"
            attacker_module.write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('loaded', encoding='utf-8')\n",
                encoding="utf-8",
            )

            distribution = _FakeSkillsRefDistribution(
                distribution_root,
                conformance.EXPECTED_SKILLS_REF_COMMIT,
            )
            with (
                patch.object(
                    conformance.importlib_metadata,
                    "distribution",
                    return_value=distribution,
                ),
                patch.object(
                    conformance,
                    "_EXPECTED_SKILLS_REF_SOURCES",
                    {
                        "__init__.py": (
                            len(verified_source),
                            hashlib.sha256(verified_source).hexdigest(),
                        )
                    },
                ),
                patch.object(
                    sys,
                    "path",
                    [str(attacker_root), *sys.path],
                ),
            ):
                reference = conformance.preflight_reference_conformance()

            self.assertEqual(reference.validate(Path("skill")), [])
            self.assertFalse(marker.exists())

    def test_preflight_rejects_a_stale_reference_validator_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            distribution_root = Path(directory) / "site-packages"
            distribution_root.mkdir(parents=True)

            distribution = _FakeSkillsRefDistribution(
                distribution_root,
                "0" * 40,
            )
            with patch.object(
                conformance.importlib_metadata,
                "distribution",
                return_value=distribution,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "pip install -r requirements-test.txt",
                ):
                    conformance.preflight_reference_conformance()

    def test_preflight_rejects_tampered_source_before_import(self):
        with tempfile.TemporaryDirectory() as directory:
            distribution_root = Path(directory) / "site-packages"
            module_path = distribution_root / "skills_ref" / "__init__.py"
            module_path.parent.mkdir(parents=True)
            module_path.write_text(
                "raise RuntimeError('tampered source executed')\n",
                encoding="utf-8",
            )
            expected_source = b"def validate(path):\n    return []\n"
            distribution = _FakeSkillsRefDistribution(
                distribution_root,
                conformance.EXPECTED_SKILLS_REF_COMMIT,
            )
            with (
                patch.object(
                    conformance.importlib_metadata,
                    "distribution",
                    return_value=distribution,
                ),
                patch.object(
                    conformance,
                    "_EXPECTED_SKILLS_REF_SOURCES",
                    {
                        "__init__.py": (
                            len(expected_source),
                            hashlib.sha256(expected_source).hexdigest(),
                        )
                    },
                ),
                patch.object(
                    conformance.importlib,
                    "import_module",
                    side_effect=AssertionError(
                        "tampered source must fail before import"
                    ),
                ) as import_module,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "pip install -r requirements-test.txt",
                ):
                    conformance.preflight_reference_conformance()

            import_module.assert_not_called()

    def test_pinned_reference_validator_accepts_a_valid_discovered_skill(self):
        self.repository.add_skill("alpha")

        self.assertEqual(run_reference_conformance(self.repository.root), [])

    def test_reference_failures_are_grouped_by_skill_and_preserve_messages(self):
        skill_root = self.repository.add_skill("alpha")
        reference_message = "Reference validator detail is preserved."
        inspected: list[tuple[Path, str]] = []

        def validate_snapshot(path: Path) -> list[str]:
            inspected.append(
                (
                    path,
                    (path / "SKILL.md").read_text(encoding="utf-8"),
                )
            )
            return [reference_message]

        reference = type(
            "ReferenceValidator",
            (),
            {"validate": staticmethod(validate_snapshot)},
        )()
        with patch.object(
            conformance,
            "preflight_reference_conformance",
            return_value=reference,
        ):
            issues = run_reference_conformance(self.repository.root)

        self.assertEqual(len(issues), 1)
        self.assertIn("alpha", issues[0].scope)
        self.assertEqual(issues[0].message, reference_message)
        self.assertEqual(len(inspected), 1)
        self.assertEqual(inspected[0][0].name, "alpha")
        self.assertNotEqual(inspected[0][0], skill_root.resolve())
        self.assertEqual(
            inspected[0][1],
            (skill_root / "SKILL.md").read_text(encoding="utf-8"),
        )

    def test_pre_model_gate_runs_static_then_reference_from_one_context(self):
        self.repository.add_skill("alpha")
        order: list[str] = []
        gate = getattr(static_validation, "run_pre_model_validation", None)
        self.assertIsNotNone(gate, "shared pre-model validation gate is missing")

        with (
            patch.object(
                static_validation,
                "_run_static_context",
                side_effect=lambda context, issues: order.append("static") or [],
            ),
            patch.object(
                static_validation,
                "validate_reference_conformance",
                side_effect=lambda context: order.append("reference") or [],
            ),
            patch.object(
                static_validation,
                "build_validation_context",
                wraps=static_validation.build_validation_context,
            ) as build_context,
        ):
            issues = gate(self.repository.root)

        self.assertEqual(issues, [])
        self.assertEqual(order, ["static", "reference"])
        build_context.assert_called_once_with(
            self.repository.root.resolve(),
            budget=ANY,
        )

    def test_pre_model_gate_rechecks_skill_source_after_reference_conformance(self):
        skill_root = self.repository.add_skill("alpha")
        skill_path = skill_root / "SKILL.md"

        def replace_source(_context):
            replacement = skill_root / "SKILL.replacement"
            replacement.write_bytes(skill_path.read_bytes())
            replacement.replace(skill_path)
            return []

        with patch.object(
            static_validation,
            "validate_reference_conformance",
            side_effect=replace_source,
        ):
            issues = static_validation.run_pre_model_validation(
                self.repository.root
            )

        self.assertTrue(
            any("SKILL.md changed after discovery" in issue.message for issue in issues),
            issues,
        )

    def test_pre_model_gate_rechecks_out_of_tree_skills_after_conformance(self):
        self.repository.add_skill("alpha")
        alternate = self.repository.root / "alternate" / "alpha" / "SKILL.md"
        alternate.parent.mkdir(parents=True)
        hidden = alternate.with_name("hidden.md")
        hidden.write_text("duplicate source\n", encoding="utf-8")

        def restore_out_of_tree_skill(_context):
            hidden.rename(alternate)
            return []

        with patch.object(
            static_validation,
            "validate_reference_conformance",
            side_effect=restore_out_of_tree_skill,
        ):
            issues = static_validation.run_pre_model_validation(
                self.repository.root
            )

        self.assertTrue(
            any(
                "outside the canonical skills/<group>/<skill>/SKILL.md source tree"
                in issue.message
                for issue in issues
            ),
            issues,
        )


class CliValidationTests(TemporaryRepositoryTestCase):
    def test_validate_runs_default_once_and_accepts_uniform_supported_counts(self):
        parser = build_parser()

        self.assertEqual(
            parser.parse_args(["validate", "triggers", "--harness", "codex"]).runs,
            1,
        )
        for runs in (1, 2, 3):
            with self.subTest(runs=runs):
                args = parser.parse_args(
                    [
                        "validate",
                        "triggers",
                        "--harness",
                        "codex",
                        "--runs",
                        str(runs),
                    ]
                )
                self.assertEqual(args.runs, runs)

    def test_validate_static_uses_a_controlled_repository_root(self):
        self.repository.add_skill("alpha")
        output = StringIO()

        with patch.object(cli, "REPOSITORY_ROOT", self.repository.root), redirect_stdout(output):
            result = cli.main(["validate", "static"])

        self.assertEqual(result, 0)
        self.assertIn("validate static: OK", output.getvalue())

    def test_validate_ci_all_orchestrates_available_deterministic_phases_in_order(self):
        order: list[str] = []
        output = StringIO()

        with (
            patch.object(cli, "REPOSITORY_ROOT", self.repository.root),
            patch.object(cli, "run_unit_tests", side_effect=lambda root: order.append("unit") or 0),
            patch.object(
                cli,
                "run_runtime_validation",
                side_effect=lambda root: order.append("runtime") or 0,
            ),
            patch.object(
                cli,
                "run_ci_validation",
                side_effect=lambda root: order.append("validation") or [],
                create=True,
            ),
            redirect_stdout(output),
        ):
            result = cli.main(["validate", "ci-all"])

        self.assertEqual(result, 0)
        self.assertEqual(order, ["validation", "unit", "runtime"])
        self.assertIn("validate ci-all: OK", output.getvalue())

    def test_ci_all_stops_when_conformance_validation_preflight_is_unavailable(self):
        output = StringIO()
        setup_command = "python3 -m pip install -r requirements-test.txt"
        order: list[str] = []

        with (
            patch.object(cli, "REPOSITORY_ROOT", self.repository.root),
            patch.object(cli, "run_unit_tests", side_effect=lambda root: order.append("unit") or 0),
            patch.object(
                cli,
                "run_runtime_validation",
                side_effect=lambda root: order.append("runtime") or 0,
            ),
            patch.object(
                cli,
                "run_ci_validation",
                side_effect=RuntimeError(setup_command),
            ),
            redirect_stdout(output),
        ):
            result = cli.main(["validate", "ci-all"])

        self.assertEqual(result, 1)
        self.assertEqual(order, [])
        self.assertIn(setup_command, output.getvalue())

    def test_ci_all_runs_reference_conformance_preflight_exactly_once(self):
        self.repository.add_skill("alpha")

        with (
            patch.object(cli, "REPOSITORY_ROOT", self.repository.root),
            patch.object(cli, "run_unit_tests", return_value=0),
            patch.object(cli, "run_runtime_validation", return_value=0),
            patch(
                "scripts.ai_skills_lib.static_checks.conformance."
                "preflight_reference_conformance"
            ) as preflight,
            redirect_stdout(StringIO()),
        ):
            result = cli.main(["validate", "ci-all"])

        self.assertEqual(result, 0)
        preflight.assert_called_once_with()

    def test_ci_all_discovers_skills_once_for_static_and_reference_checks(self):
        self.repository.add_skill("alpha")
        output = StringIO()

        from scripts.ai_skills_lib.core import discover_testable_skills

        with (
            patch.object(cli, "REPOSITORY_ROOT", self.repository.root),
            patch.object(cli, "run_unit_tests", return_value=0),
            patch(
                "scripts.ai_skills_lib.static_checks.context.discover_testable_skills",
                wraps=discover_testable_skills,
            ) as discover,
            redirect_stdout(output),
        ):
            result = cli.main(["validate", "ci-all"])

        self.assertEqual(result, 0)
        self.assertEqual(discover.call_count, 1)


if __name__ == "__main__":
    unittest.main()
