from __future__ import annotations

import unittest

from scripts.ai_skills_lib.bounded_json import (
    BoundedJsonError,
    strict_bounded_json_loads,
)


class BoundedJsonTests(unittest.TestCase):
    def test_rejects_escaped_unpaired_surrogates(self) -> None:
        for document in ('"\\ud800"', '"\\udc00"'):
            with self.subTest(document=document):
                with self.assertRaises(BoundedJsonError) as raised:
                    strict_bounded_json_loads(document)

                self.assertEqual(raised.exception.kind, "invalid")

    def test_accepts_a_valid_escaped_surrogate_pair(self) -> None:
        self.assertEqual(
            strict_bounded_json_loads('"\\ud83d\\ude00"'),
            chr(0x1F600),
        )


if __name__ == "__main__":
    unittest.main()
