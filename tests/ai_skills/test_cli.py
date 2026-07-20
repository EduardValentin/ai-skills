from __future__ import annotations

import unittest
from unittest.mock import patch

import scripts.ai_skills as cli


class RuntimeValidationCliTests(unittest.TestCase):
    def test_validate_runtime_dispatches_only_to_model_free_runner(self) -> None:
        model_backed_error = AssertionError("model-backed handler must not run")

        with (
            patch.object(cli, "run_runtime_validation", return_value=1, create=True) as run_runtime,
            patch.object(cli, "run_trigger_query_harness", side_effect=model_backed_error),
            patch.object(cli, "run_behavior_eval_harness", side_effect=model_backed_error),
            patch.object(cli, "run_all_evaluation_harness", side_effect=model_backed_error),
        ):
            result = cli.main(["validate", "runtime"])

        self.assertEqual(result, 1)
        run_runtime.assert_called_once_with(cli.REPOSITORY_ROOT)

    def test_ci_all_runs_runtime_validation_as_a_deterministic_phase(self) -> None:
        order: list[str] = []

        with (
            patch.object(
                cli,
                "run_unit_tests",
                side_effect=lambda root: order.append("unit") or 0,
            ),
            patch.object(
                cli,
                "run_runtime_validation",
                side_effect=lambda root: order.append("runtime") or 1,
            ),
            patch.object(
                cli,
                "run_ci_validation",
                side_effect=lambda root: order.append("validation") or [],
            ),
        ):
            result = cli.main(["validate", "ci-all"])

        self.assertEqual(result, 1)
        self.assertEqual(order, ["validation", "unit", "runtime"])

    def test_runtime_failure_blocks_validate_all_model_backed_handler(self) -> None:
        with (
            patch.object(cli, "run_ci_validation", return_value=[]),
            patch.object(cli, "run_unit_tests", return_value=0),
            patch.object(cli, "run_runtime_validation", return_value=1) as run_runtime,
            patch.object(cli, "run_all_evaluation_harness") as run_model_backed,
        ):
            result = cli.main(["validate", "all", "--harness", "codex"])

        self.assertEqual(result, 1)
        run_runtime.assert_called_once_with(cli.REPOSITORY_ROOT)
        run_model_backed.assert_not_called()

    def test_check_local_installs_dispatches_to_read_only_diagnostic(self) -> None:
        with patch.object(cli, "run_local_install_check", return_value=1) as check:
            result = cli.main(["check-local-installs", "--harness", "codex"])

        self.assertEqual(result, 1)
        check.assert_called_once_with(cli.REPOSITORY_ROOT, harness="codex")


if __name__ == "__main__":
    unittest.main()
