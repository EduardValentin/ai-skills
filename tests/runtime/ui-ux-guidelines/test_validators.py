from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = REPO_ROOT / "skills" / "ui-ux" / "ui-ux-guidelines"
SCRIPTS_DIR = SKILL_DIR / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
NODE = shutil.which("node")


def run_script(name: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [NODE, str(SCRIPTS_DIR / name), *arguments], capture_output=True, text=True, check=False, timeout=180
    )


def browser_available() -> bool:
    probe = "import('./lib/browser.mjs').then(m => m.findBrowser()).catch(() => process.exit(1))"
    return subprocess.run([NODE, "-e", probe], cwd=SCRIPTS_DIR, capture_output=True, check=False).returncode == 0


@unittest.skipIf(NODE is None, "node is not on PATH")
class ContrastTokenTests(unittest.TestCase):
    def test_reference_apca_vectors(self) -> None:
        cases = {("#888888", "#FFFFFF"): 63.1, ("#FFFFFF", "#888888"): 68.5, ("#000000", "#FFFFFF"): 106.0, ("#FFFFFF", "#000000"): 107.9}
        for (foreground, background), expected in cases.items():
            completed = run_script(
                "contrast-audit.mjs", "tokens", "--method", "apca", "--apca-lookup", "none",
                "--pair", f"{foreground}:{background}:discernible", "--verbose",
            )
            report = json.loads(completed.stdout)
            self.assertEqual(report["passes"][0]["measured"]["value"], expected)

    def test_high_contrast_pairs_pass_in_every_color_syntax(self) -> None:
        completed = run_script("contrast-audit.mjs", "tokens", "--input", str(FIXTURES / "pairs-pass.json"))
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertEqual(json.loads(completed.stdout)["summary"]["result"], "pass")

    def test_low_contrast_pairs_fail_with_corrective_values(self) -> None:
        completed = run_script("contrast-audit.mjs", "tokens", "--input", str(FIXTURES / "pairs-fail.json"))
        self.assertEqual(completed.returncode, 1)
        violations = json.loads(completed.stdout)["violations"]
        failed = {(violation["tokenId"], violation["ruleId"]) for violation in violations}
        self.assertIn(("text.muted.light", "CT-WCAG-TEXT-NORMAL"), failed)
        self.assertIn(("icon.close", "CT-APCA-ICON-FINE"), failed)
        for violation in violations:
            self.assertRegex(violation["correctiveValue"], r"^#[0-9A-F]{6}$")
            self.assertGreaterEqual(violation["correctiveMeasured"], violation["expected"]["value"])

    def test_dark_mode_pair_passes_wcag_but_fails_apca(self) -> None:
        completed = run_script("contrast-audit.mjs", "tokens", "--pair", "#8b8b8b:#000000:text:16:400")
        self.assertEqual(completed.returncode, 1)
        violations = json.loads(completed.stdout)["violations"]
        self.assertEqual([violation["ruleId"] for violation in violations], ["CT-APCA-TEXT"])
        self.assertEqual(violations[0]["correctiveTarget"], "foreground")

    def test_unparsable_color_is_a_usage_error(self) -> None:
        completed = run_script("contrast-audit.mjs", "tokens", "--pair", "nope:#ffffff")
        self.assertEqual(completed.returncode, 2)


@unittest.skipIf(NODE is None, "node is not on PATH")
class RenderedPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not browser_available():
            raise unittest.SkipTest("no Chromium-based browser is installed")

    def test_compliant_page_passes_geometry(self) -> None:
        completed = run_script("geometry-audit.mjs", str(FIXTURES / "compliant.html"))
        self.assertEqual(completed.returncode, 0, completed.stdout)
        page = json.loads(completed.stdout)["pages"][0]
        for rule in ("TARGET-SIZE", "REFLOW-OVERFLOW", "LINE-LENGTH", "SPACING-RATIO", "LABEL-ASSOC", "TEXT-RESIZE-200"):
            self.assertIn(rule, page["passedRules"])

    def test_defects_page_fails_geometry(self) -> None:
        completed = run_script("geometry-audit.mjs", str(FIXTURES / "defects.html"))
        self.assertEqual(completed.returncode, 1)
        results = json.loads(completed.stdout)["pages"][0]["results"]
        found = {(result["ruleId"], result["viewport"]) for result in results}
        self.assertIn(("REFLOW-OVERFLOW", "320x800"), found)
        self.assertIn(("TARGET-SIZE", "375x800"), found)
        self.assertIn(("TARGET-GAP-BUTTON", "375x800"), found)
        self.assertIn(("LINE-LENGTH", "1440x900"), found)
        self.assertIn(("BODY-FONT-SIZE", "320x800"), found)
        self.assertIn(("SPACING-RATIO", "1440x900"), found)
        self.assertIn(("LABEL-ASSOC", None), found)
        self.assertIn(("IMG-ALT", None), found)
        self.assertIn(("VIEWPORT-ZOOM", None), found)
        save = next(r for r in results if r["ruleId"] == "TARGET-SIZE" and r["selector"].endswith("button:nth-of-type(1)"))
        self.assertEqual(save["measured"]["height"], 30)
        self.assertEqual(save["corrective"], {"width": 48, "height": 48})

    def test_compliant_page_passes_dom_contrast(self) -> None:
        completed = run_script("contrast-audit.mjs", "dom", "--html", str(FIXTURES / "compliant.html"))
        self.assertEqual(completed.returncode, 0, completed.stdout)

    def test_defects_page_fails_dom_contrast(self) -> None:
        completed = run_script("contrast-audit.mjs", "dom", "--html", str(FIXTURES / "defects.html"), "--viewports", "375")
        self.assertEqual(completed.returncode, 1)
        rules = {violation["ruleId"] for violation in json.loads(completed.stdout)["violations"]}
        self.assertLessEqual({"CT-WCAG-TEXT-NORMAL", "CT-WCAG-INPUT-BORDER", "CT-WCAG-BUTTON-BOUNDARY"}, rules)

    def test_missing_input_is_a_usage_error(self) -> None:
        completed = run_script("geometry-audit.mjs", str(FIXTURES / "absent.html"))
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
