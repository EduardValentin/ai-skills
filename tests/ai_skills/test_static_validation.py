from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import fields
from io import StringIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import scripts.ai_skills as cli
import scripts.ai_skills_lib.static_validation as static_validation
from scripts.ai_skills_lib.config import build_parser
from scripts.ai_skills_lib.core import discover_testable_skills
from scripts.ai_skills_lib.authored_content import (
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


class DiscoveryAndFrontmatterValidationTests(TemporaryRepositoryTestCase):
    def test_discovers_only_two_level_public_skills(self):
        skill_root = self.repository.add_skill("alpha", group="procedural")

        skills = discover_testable_skills(self.repository.root)

        self.assertEqual([skill.name for skill in skills], ["alpha"])
        self.assertEqual(skills[0].root, skill_root)

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
        direct_root = self.repository.root / "skills" / "legacy"
        direct_root.mkdir(parents=True)
        (direct_root / "SKILL.md").write_text(
            "---\nname: legacy\ndescription: Legacy workflow.\nmetadata:\n  status: public-ready\n---\n",
            encoding="utf-8",
        )

        self.assert_issue("must use skills/<group>/<skill>/SKILL.md")

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


class RepositoryPolicyValidationTests(TemporaryRepositoryTestCase):
    def test_config_and_local_required_skills_require_compatibility(self):
        for status in ("config-required", "local-required"):
            with self.subTest(status=status):
                repository = TemporaryRepository()
                self.addCleanup(repository.cleanup)
                repository.add_skill("alpha", status=status)

                messages = [issue.message for issue in run_static_validation(repository.root)]

                self.assertTrue(any("requires non-empty compatibility" in message for message in messages))

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

    def test_assets_receive_containment_checks_but_not_content_scanning(self):
        skill_root = self.repository.add_skill("alpha")
        assets = skill_root / "assets"
        assets.mkdir()
        credential_shape = "gh" + "p_" + ("a" * 36)
        (assets / "sample.txt").write_text(
            f"{credential_shape}\n/Users/example/not-scanned\n", encoding="utf-8"
        )
        self.repository.exercise_bundled_path(skill_root, "assets/sample.txt")

        self.assert_no_issues()

    def test_rejects_unknown_legacy_empty_and_placeholder_entries(self):
        skill_root = self.repository.add_skill("alpha")
        for name in ("commands", "phases", "schema", "workflow", "agents", "tests"):
            directory = skill_root / name
            directory.mkdir()
            (directory / "content.txt").write_text("legacy\n", encoding="utf-8")
        (skill_root / "assets").mkdir()
        references = skill_root / "references"
        references.mkdir()
        (references / ".gitkeep").write_text("", encoding="utf-8")
        (skill_root / "NOTES.txt").write_text("notes\n", encoding="utf-8")

        messages = self.messages()

        for name in ("commands", "phases", "schema", "workflow", "agents", "tests", "NOTES.txt"):
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

    def test_follows_contained_directory_symlinks_once_without_cycles(self):
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
        (material / "cycle").symlink_to(linked, target_is_directory=True)

        messages = self.messages()

        self.assertEqual(sum("openai-api-key" in message for message in messages), 1)

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

        self.assertFalse(any("github-token" in message for message in messages))
        self.assertEqual(sum("slack-token" in message for message in messages), 1)
        self.assertEqual(sum("aws-access-key-id" in message for message in messages), 1)

    def test_rejects_duplicate_harness_sources_and_dist(self):
        self.repository.add_skill("alpha")
        duplicate_paths = (
            self.repository.root / "plugins" / "sample" / "skills" / "alpha" / "SKILL.md",
            self.repository.root / "codex" / "skills" / "alpha" / "SKILL.md",
            self.repository.root / "claude" / "skills" / "alpha" / "SKILL.md",
        )
        for path in duplicate_paths:
            path.parent.mkdir(parents=True)
            path.write_text("duplicate\n", encoding="utf-8")
        (self.repository.root / "dist").mkdir()

        messages = self.messages()

        self.assertEqual(sum("duplicate public skill source" in message for message in messages), 3)
        self.assertTrue(any("dist/ must not exist" in message for message in messages))

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


class EvalValidationTests(TemporaryRepositoryTestCase):
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
                Path("legacy/content.txt"),
                "unsupported evals entry: legacy",
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

    def test_eval_text_fixtures_reject_non_fake_secret_values(self):
        skill_root = self.repository.add_skill("alpha")
        fixture = self.repository.declare_basic_case_input(
            skill_root, "environment.env"
        )
        fixture.parent.mkdir(parents=True)
        fixture.write_text("SERVICE_TOKEN=" + "authored-value\n", encoding="utf-8")

        self.assert_issue("sensitive-assignment")

    def test_eval_binary_fixtures_are_not_content_scanned(self):
        skill_root = self.repository.add_skill("alpha")
        fixture = self.repository.declare_basic_case_input(skill_root, "sample.bin")
        fixture.parent.mkdir(parents=True)
        fixture.write_bytes(b"\x00SERVICE_TOKEN=authored-value\xff")

        self.assert_no_issues()

    def test_eval_fixture_limit_matches_runtime_preparation(self):
        skill_root = self.repository.add_skill("alpha")
        fixture = self.repository.declare_basic_case_input(skill_root, "sample.bin")
        fixture.parent.mkdir(parents=True)
        fixture.write_bytes(b"\x00" * (3 * 1024 * 1024))

        self.assert_no_issues()

        fixture.write_bytes(b"\x00" * (4 * 1024 * 1024 + 1))
        self.assert_issue("4 MiB eval fixture file limit")

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

    def test_compound_shell_expressions_are_not_treated_as_pure_references(self):
        unsafe_values = (
            "SERVICE_TOKEN=${OTHER_TOKEN:-" + "authored-value}",
            "SERVICE_TOKEN=$OTHER_TOKEN-" + "authored-value",
            "SERVICE_TOKEN=$(printf " + "authored-value)",
            "SERVICE_TOKEN=FAKE_example$(printf " + "authored-value)",
        )

        for line in unsafe_values:
            with self.subTest(line=line):
                matches = find_static_secret_issues(line, Path("environment.env"))
                self.assertEqual([match.pattern for match in matches], ["sensitive-assignment"])

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


class ReferenceConformanceTests(TemporaryRepositoryTestCase):
    def test_pinned_reference_validator_accepts_a_valid_discovered_skill(self):
        self.repository.add_skill("alpha")

        self.assertEqual(run_reference_conformance(self.repository.root), [])

    def test_reference_failures_are_grouped_by_skill_and_preserve_messages(self):
        skill_root = self.repository.add_skill("alpha")
        reference_message = "Reference validator detail is preserved."

        with patch(
            "scripts.ai_skills_lib.static_checks.conformance.skills_ref.validate",
            return_value=[reference_message],
        ) as validate:
            issues = run_reference_conformance(self.repository.root)

        self.assertEqual(len(issues), 1)
        self.assertIn("alpha", issues[0].scope)
        self.assertEqual(issues[0].message, reference_message)
        validate.assert_called_once_with(skill_root.resolve())

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
        build_context.assert_called_once_with(self.repository.root.resolve())


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
