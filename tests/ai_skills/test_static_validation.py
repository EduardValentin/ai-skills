from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import fields
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scripts.ai_skills as cli
from scripts.ai_skills_lib.config import build_parser
from scripts.ai_skills_lib.core import discover_testable_skills
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
                {"evals": [{"id": "basic", "prompt": "Perform the workflow."}]},
            )
        if with_triggers:
            self.write_json(
                evals_root / "triggers.json",
                {
                    "queries": [
                        {"query": "Perform the alpha workflow.", "should_trigger": True},
                        {"query": "Summarize an unrelated note.", "should_trigger": False},
                    ]
                },
            )
        return skill_root

    @staticmethod
    def write_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")


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


class DiscoveryAndFrontmatterValidationTests(TemporaryRepositoryTestCase):
    def test_discovers_only_two_level_public_skills(self):
        skill_root = self.repository.add_skill("alpha", group="procedural")

        skills = discover_testable_skills(self.repository.root)

        self.assertEqual([skill.name for skill in skills], ["alpha"])
        self.assertEqual(skills[0].root, skill_root)

    def test_rejects_direct_skill_layout(self):
        direct_root = self.repository.root / "skills" / "legacy"
        direct_root.mkdir(parents=True)
        (direct_root / "SKILL.md").write_text(
            "---\nname: legacy\ndescription: Legacy workflow.\nmetadata:\n  status: public-ready\n---\n",
            encoding="utf-8",
        )

        self.assert_issue("must use skills/<group>/<skill>/SKILL.md")

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
            ([{"query": "Use alpha.", "should_trigger": True}], "should_trigger: false"),
            ([{"query": "Do something else.", "should_trigger": False}], "should_trigger: true"),
        ):
            with self.subTest(expected=expected):
                self.repository.write_json(trigger_path, {"queries": queries})
                self.assert_issue(expected)

    def test_trigger_schema_rejects_runner_repetition_configuration(self):
        skill_root = self.repository.add_skill("alpha")
        trigger_path = skill_root / "evals" / "triggers.json"
        data = json.loads(trigger_path.read_text(encoding="utf-8"))
        data["runs"] = 3
        self.repository.write_json(trigger_path, data)

        self.assert_issue("runner repetition configuration")

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

        self.assert_issue("evals/evals.json must contain an 'evals' list")

        (skill_root / "evals" / "evals.json").write_text("{", encoding="utf-8")
        self.assert_issue("invalid JSON")

    def test_eval_fixture_paths_are_contained_and_exist(self):
        skill_root = self.repository.add_skill("alpha")
        self.repository.write_json(
            skill_root / "evals" / "evals.json",
            {
                "evals": [
                    {"id": "missing", "prompt": "Run.", "fixture": "evals/fixtures/missing.json"},
                    {"id": "escape", "prompt": "Run.", "fixture": "../outside.json"},
                ]
            },
        )

        messages = self.messages()

        self.assertTrue(any("fixture path does not exist" in message for message in messages))
        self.assertTrue(any("fixture path must stay inside" in message for message in messages))

    def test_eval_json_rejects_non_fake_secret_values(self):
        skill_root = self.repository.add_skill("alpha")
        unsafe_assignment = "SERVICE_TOKEN=" + "authored" + "-value"
        self.repository.write_json(
            skill_root / "evals" / "evals.json",
            {"evals": [{"id": "secret", "prompt": unsafe_assignment}]},
        )

        self.assert_issue("sensitive-assignment")

        self.repository.write_json(
            skill_root / "evals" / "evals.json",
            {"evals": [{"id": "fake", "prompt": "SERVICE_TOKEN=FAKE_authored-value"}]},
        )
        self.assert_no_issues()

    def test_eval_text_fixtures_reject_non_fake_secret_values(self):
        skill_root = self.repository.add_skill("alpha")
        fixture = skill_root / "evals" / "fixtures" / "environment.env"
        fixture.parent.mkdir()
        fixture.write_text("SERVICE_TOKEN=" + "authored-value\n", encoding="utf-8")

        self.assert_issue("sensitive-assignment")

    def test_eval_binary_fixtures_are_not_content_scanned(self):
        skill_root = self.repository.add_skill("alpha")
        fixture = skill_root / "evals" / "fixtures" / "sample.bin"
        fixture.parent.mkdir()
        fixture.write_bytes(b"\x00SERVICE_TOKEN=authored-value\xff")

        self.assert_no_issues()


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


class CliValidationTests(TemporaryRepositoryTestCase):
    def test_validate_runs_default_once_and_accepts_uniform_supported_counts(self):
        parser = build_parser()

        self.assertEqual(parser.parse_args(["validate", "triggers"]).runs, 1)
        for runs in (1, 2, 3):
            with self.subTest(runs=runs):
                args = parser.parse_args(["validate", "triggers", "--runs", str(runs)])
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
            patch.object(
                cli,
                "preflight_reference_conformance",
                side_effect=lambda: order.append("preflight"),
                create=True,
            ),
            patch.object(cli, "run_unit_tests", side_effect=lambda root: order.append("unit") or 0),
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
        self.assertEqual(order, ["preflight", "unit", "validation"])
        self.assertIn("validate ci-all: OK", output.getvalue())

    def test_ci_all_preflights_skills_ref_before_other_phases(self):
        output = StringIO()
        setup_command = "python3 -m pip install -r requirements-test.txt"
        order: list[str] = []

        with (
            patch.object(cli, "REPOSITORY_ROOT", self.repository.root),
            patch.object(
                cli,
                "preflight_reference_conformance",
                side_effect=RuntimeError(setup_command),
                create=True,
            ),
            patch.object(cli, "run_unit_tests", side_effect=lambda root: order.append("unit") or 0),
            patch.object(
                cli,
                "run_ci_validation",
                side_effect=lambda root: order.append("validation") or [],
                create=True,
            ),
            redirect_stdout(output),
        ):
            result = cli.main(["validate", "ci-all"])

        self.assertEqual(result, 1)
        self.assertEqual(order, [])
        self.assertIn(setup_command, output.getvalue())

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
