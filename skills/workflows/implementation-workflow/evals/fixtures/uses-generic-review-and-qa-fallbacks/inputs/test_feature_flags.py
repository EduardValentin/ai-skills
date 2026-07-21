import unittest

from feature_flags import visible_flag_names


FLAGS = [
    {"name": "search-v2", "audience": "public", "enabled": True},
    {"name": "staged-import", "audience": "public", "enabled": False},
    {"name": "billing-console", "audience": "private", "enabled": True},
]


class FeatureFlagTests(unittest.TestCase):
    def test_operator_sees_only_enabled_public_flags(self):
        self.assertEqual(visible_flag_names("operator", FLAGS), ["search-v2"])

    def test_admin_sees_every_flag(self):
        self.assertEqual(
            visible_flag_names("admin", FLAGS),
            ["billing-console", "search-v2", "staged-import"],
        )


if __name__ == "__main__":
    unittest.main()
