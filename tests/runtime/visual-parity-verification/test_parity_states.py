from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "skills" / "ui-ux" / "visual-parity-verification" / "scripts"))

import parity_states  # noqa: E402


def steps(*kinds_and_values):
    return [{kind: value} for kind, value in kinds_and_values]


class LoadTests(unittest.TestCase):
    def test_absent_file_is_empty(self) -> None:
        self.assertEqual(parity_states.load_states(Path("/nonexistent/parity-states.json")), {})

    def test_non_object_json_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "parity-states.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(parity_states.StatesError):
                parity_states.load_states(path)


class ResolveTests(unittest.TestCase):
    def test_list_state_applies_to_both_sides(self) -> None:
        states = {"open": steps(("click", "#a"))}
        self.assertEqual(parity_states.resolve_state(states, "open", "prototype"), steps(("click", "#a")))
        self.assertEqual(parity_states.resolve_state(states, "open", "real"), steps(("click", "#a")))

    def test_missing_side_is_empty(self) -> None:
        states = {"seed": {"prototype": steps(("click", "#dev"))}}
        self.assertEqual(parity_states.resolve_state(states, "seed", "real"), [])

    def test_use_splices_steps_in_place(self) -> None:
        states = {"frag": steps(("click", "#a"), ("click", "#b")), "state": steps(("use", "frag"), ("hover", "#c"))}
        self.assertEqual(parity_states.resolve_state(states, "state", "real"), steps(("click", "#a"), ("click", "#b"), ("hover", "#c")))

    def test_use_from_a_side_takes_that_side(self) -> None:
        states = {
            "seed": {"prototype": steps(("click", "#dev")), "real": steps(("click", "#login"))},
            "state": {"prototype": steps(("use", "seed"), ("click", "#x")), "real": steps(("use", "seed"))},
        }
        self.assertEqual(parity_states.resolve_state(states, "state", "prototype"), steps(("click", "#dev"), ("click", "#x")))
        self.assertEqual(parity_states.resolve_state(states, "state", "real"), steps(("click", "#login")))

    def test_unknown_use_and_unknown_state_raise(self) -> None:
        with self.assertRaises(parity_states.StatesError):
            parity_states.resolve_state({"a": steps(("use", "b"))}, "a", "real")
        with self.assertRaises(parity_states.StatesError):
            parity_states.resolve_state({}, "missing", "real")

    def test_cycle_raises_naming_the_chain(self) -> None:
        states = {"a": steps(("use", "b")), "b": steps(("use", "a"))}
        with self.assertRaises(parity_states.StatesError) as caught:
            parity_states.resolve_state(states, "a", "real")
        self.assertIn("a -> b -> a", str(caught.exception))

    def test_state_sides_resolves_both(self) -> None:
        states = {"s": {"real": steps(("press", "Tab"))}}
        self.assertEqual(parity_states.state_sides(states, "s"), {"prototype": [], "real": steps(("press", "Tab"))})


class ValidateTests(unittest.TestCase):
    def problems(self, states):
        return parity_states.validate_states(states)

    def test_valid_file_has_no_problems(self) -> None:
        states = {"frag": steps(("click", "#a")), "s": {"prototype": steps(("use", "frag"), ("fill", ["#f", "x"]))}}
        self.assertEqual(self.problems(states), ([], []))

    def test_bad_name_shape_and_kind_are_reported(self) -> None:
        states = {
            "bad name": steps(("click", "#a")),
            "two": [{"click": "#a", "hover": "#b"}],
            "kind": [{"dance": "#a"}],
            "fill": [{"fill": "#a"}],
            "wait": [{"wait": "soon"}],
            "side": {"left": []},
        }
        problems, _ = self.problems(states)
        for fragment in ('state "bad name": name', 'state "two": step 0 has 2 keys', 'state "kind": step 0: unknown kind "dance"', 'state "fill": step 0: "fill" expects [selector, text]', 'state "wait": step 0: "wait" expects milliseconds', 'state "side": unknown side "left"'):
            self.assertTrue(any(fragment in p for p in problems), (fragment, problems))

    def test_unknown_use_and_cycle_are_problems(self) -> None:
        problems, _ = self.problems({"a": steps(("use", "zzz")), "b": steps(("use", "c")), "c": steps(("use", "b"))})
        self.assertTrue(any('state "a": use "zzz" is not defined' in p for p in problems), problems)
        self.assertTrue(any("cycle" in p for p in problems), problems)

    def test_fixed_wait_and_long_state_warn(self) -> None:
        long_state = steps(*[("click", f"#{i}") for i in range(13)])
        _, warnings = self.problems({"slow": steps(("wait", 500)), "long": long_state})
        self.assertTrue(any('state "slow": step 0 is a fixed wait' in w for w in warnings), warnings)
        self.assertTrue(any('state "long": real resolves to 13 steps' in w for w in warnings), warnings)


if __name__ == "__main__":
    unittest.main()
