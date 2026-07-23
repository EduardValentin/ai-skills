from pathlib import Path
import unittest

from scripts.ai_skills_lib.frontmatter import parse_skill_frontmatter


class FrontmatterTests(unittest.TestCase):
    def test_parses_spec_frontmatter_with_metadata(self):
        text = """---
name: ticket-workflow
description: Use when working a ticket end to end.
compatibility: Requires configured issue tracker access.
metadata:
  status: local-required
  allows_tool_references: "true"
---
Body
"""
        parsed = parse_skill_frontmatter(text, Path("skills/workflows/ticket-workflow/SKILL.md"))
        self.assertEqual(parsed["name"], "ticket-workflow")
        self.assertEqual(parsed["description"], "Use when working a ticket end to end.")
        self.assertEqual(parsed["compatibility"], "Requires configured issue tracker access.")
        self.assertEqual(parsed["metadata"]["status"], "local-required")
        self.assertEqual(parsed["metadata"]["allows_tool_references"], "true")

    def test_parses_yaml_scalar_forms_comments_and_escaped_description(self):
        text = """---
# A comment preceding the document content.
name: 'sample-skill'
description: "Use when reviewing an existing document — checking each \\\"section/item\\\" since the last update ✓."
compatibility: >
  Requires a current document and public
  references.
allowed-tools: 'web__run, finance'
metadata:
  status: "local-required" # retained status
  note: |
    Review filings first.
    Keep Unicode punctuation: §.
---
Body
"""
        parsed = parse_skill_frontmatter(text, Path("skills/examples/sample-skill/SKILL.md"))
        self.assertEqual(parsed["name"], "sample-skill")
        self.assertEqual(
            parsed["description"],
            'Use when reviewing an existing document — checking each "section/item" since the last update ✓.',
        )
        self.assertEqual(parsed["compatibility"], "Requires a current document and public references.\n")
        self.assertEqual(parsed["allowed-tools"], "web__run, finance")
        self.assertEqual(parsed["metadata"]["note"], "Review filings first.\nKeep Unicode punctuation: §.\n")

    def test_converts_strict_yaml_parse_errors_to_source_aware_value_errors(self):
        source = Path("skills/workflows/ticket-workflow/SKILL.md")
        malformed_documents = (
            "---\nname: ticket-workflow\nname: duplicate\ndescription: Valid description.\n---\nBody\n",
            "---\n{name: ticket-workflow, description: Valid description.}\n---\nBody\n",
        )

        for text in malformed_documents:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, r"skills/workflows/ticket-workflow/SKILL.md: invalid YAML frontmatter"):
                    parse_skill_frontmatter(text, source)

    def test_rejects_whitespace_only_description_and_compatibility(self):
        whitespace_only_prose = (
            "---\nname: ticket-workflow\ndescription: '   '\n---\nBody\n",
            "---\nname: ticket-workflow\ndescription: Valid description.\ncompatibility: ' \t '\n---\nBody\n",
        )

        for text in whitespace_only_prose:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "must be a non-empty scalar string"):
                    parse_skill_frontmatter(text, Path("skills/workflows/ticket-workflow/SKILL.md"))

    def test_allows_empty_allowed_tools_scalar(self):
        text = """---
name: ticket-workflow
description: Use when working a ticket end to end.
allowed-tools: ""
---
Body
"""
        parsed = parse_skill_frontmatter(text, Path("skills/workflows/ticket-workflow/SKILL.md"))
        self.assertEqual(parsed["allowed-tools"], "")

    def test_rejects_nested_metadata_values(self):
        text = """---
name: ticket-workflow
description: Use when working a ticket end to end.
metadata:
  status: local-required
  unsupported:
    nested: value
---
Body
"""
        with self.assertRaisesRegex(ValueError, "metadata values must be scalar strings"):
            parse_skill_frontmatter(text, Path("skills/workflows/ticket-workflow/SKILL.md"))

    def test_rejects_non_mapping_metadata(self):
        text = """---
name: ticket-workflow
description: Use when working a ticket end to end.
metadata: local-required
---
Body
"""
        with self.assertRaisesRegex(ValueError, "metadata must be a mapping"):
            parse_skill_frontmatter(text, Path("skills/workflows/ticket-workflow/SKILL.md"))

    def test_rejects_custom_top_level_field(self):
        text = """---
name: ticket-workflow
description: Use when working a ticket end to end.
tier: local-required
---
Body
"""
        with self.assertRaisesRegex(ValueError, "unsupported top-level frontmatter field"):
            parse_skill_frontmatter(text, Path("skills/workflows/ticket-workflow/SKILL.md"))

    def test_requires_frontmatter_delimiters(self):
        with self.assertRaisesRegex(ValueError, "missing YAML frontmatter"):
            parse_skill_frontmatter("name: bad\n", Path("SKILL.md"))

    def test_rejects_malformed_delimiters_and_empty_documents(self):
        with self.assertRaisesRegex(ValueError, "missing YAML frontmatter"):
            parse_skill_frontmatter("---\nname: bad\nBody\n", Path("SKILL.md"))
        with self.assertRaisesRegex(ValueError, "frontmatter must be a mapping"):
            parse_skill_frontmatter("---\n---\nBody\n", Path("SKILL.md"))

    def test_rejects_invalid_name_constraints(self):
        text = """---
name: bad--name
description: Use when working a ticket end to end.
---
Body
"""
        with self.assertRaisesRegex(ValueError, "invalid name"):
            parse_skill_frontmatter(text, Path("skills/workflows/bad--name/SKILL.md"))

    def test_rejects_overlong_description(self):
        text = "---\nname: ticket-workflow\ndescription: " + ("x" * 1025) + "\n---\nBody\n"
        with self.assertRaisesRegex(ValueError, "description"):
            parse_skill_frontmatter(text, Path("skills/workflows/ticket-workflow/SKILL.md"))


if __name__ == "__main__":
    unittest.main()
