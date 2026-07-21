import unittest

from account_export import export_account


class AccountExportTests(unittest.TestCase):
    def test_empty_owner_export_is_empty(self):
        self.assertEqual(export_account("acct-owner", "acct-owner", []), [])


if __name__ == "__main__":
    unittest.main()
