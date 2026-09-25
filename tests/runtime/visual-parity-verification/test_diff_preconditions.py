from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import support  # noqa: E402


def simple_root(**overrides):
    defaults = dict(role="region", name="Orders", width=640, height=300)
    merged = {**defaults, **overrides}
    return support.node("section", **merged)


def surface_children():
    return [
        support.node("h2", role="heading", name="Orders", own_text="Orders"),
        support.node("p", own_text="Body"),
        support.node("button", role="button", name="Save"),
    ]


class DiffPreconditionTests(unittest.TestCase):
    def run_pair(self, proto, real):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proto_path = support.write_json(root / "prototype.json", proto)
            real_path = support.write_json(root / "real.json", real)
            out = root / "diff.json"
            completed = support.run_diff("--prototype", str(proto_path), "--real", str(real_path), "--out", str(out))
            result = support.read_json(out) if out.exists() else None
            return completed, result

    def test_viewport_mismatch_is_blocked(self) -> None:
        proto = support.snapshot(simple_root(), width=1440)
        real = support.snapshot(simple_root(), width=1024)
        completed, result = self.run_pair(proto, real)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertEqual(result["blocked"]["reason"], "condition-mismatch")
        self.assertEqual(result["blocked"]["detail"][0], {"condition": "viewport.width", "prototype": 1440, "real": 1024})
        self.assertIn("BLOCKED", completed.stdout)

    def test_color_scheme_mismatch_is_blocked(self) -> None:
        proto = support.snapshot(simple_root(), color_scheme="light")
        real = support.snapshot(simple_root(), color_scheme="dark")
        _, result = self.run_pair(proto, real)
        self.assertEqual(result["blocked"]["detail"][0]["condition"], "colorScheme")

    def test_root_role_mismatch_is_blocked(self) -> None:
        proto = support.snapshot(simple_root())
        real = support.snapshot(support.node("nav", role="navigation", name="Orders", width=640, height=300))
        _, result = self.run_pair(proto, real)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertEqual(result["blocked"]["reason"], "roots-incompatible")
        self.assertEqual(result["blocked"]["detail"]["prototype"]["role"], "region")
        self.assertEqual(result["blocked"]["detail"]["real"]["role"], "navigation")

    def test_root_size_beyond_factor_two_is_blocked(self) -> None:
        proto = support.snapshot(simple_root())
        real = support.snapshot(simple_root(width=100))
        _, result = self.run_pair(proto, real)
        self.assertEqual(result["blocked"]["reason"], "roots-incompatible")

    def test_root_without_role_on_one_side_is_compatible(self) -> None:
        proto = support.snapshot(simple_root())
        real = support.snapshot(support.node("section", width=640, height=300))
        _, result = self.run_pair(proto, real)
        self.assertNotEqual(result["verdict"], "BLOCKED")

    def test_root_tag_mismatch_is_blocked(self) -> None:
        proto = support.snapshot(simple_root())
        real = support.snapshot(support.node("div", role="region", name="Orders", width=640, height=300))
        _, result = self.run_pair(proto, real)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertEqual(result["blocked"]["reason"], "roots-incompatible")
        self.assertEqual(result["blocked"]["detail"]["prototype"]["tag"], "section")
        self.assertEqual(result["blocked"]["detail"]["real"]["tag"], "div")

    def test_wrapper_root_around_the_surface_is_blocked_by_child_signature(self) -> None:
        proto = support.snapshot(simple_root(children=surface_children()))
        real = support.snapshot(support.node("section", width=640, height=300, children=[
            support.node("section", role="region", name="Orders", width=640, height=300, children=surface_children()),
        ]))
        _, result = self.run_pair(proto, real)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertEqual(result["blocked"]["reason"], "roots-incompatible")
        detail = result["blocked"]["detail"]
        self.assertEqual(detail["prototype"]["childSignature"], ["heading", "p", "button"])
        self.assertEqual(detail["real"]["childSignature"], ["region"])
        self.assertEqual(detail["prototype"]["width"], 640)
        self.assertEqual(detail["real"]["height"], 300)

    def test_child_signature_is_read_through_depth_one_wrappers(self) -> None:
        proto = support.snapshot(simple_root(children=surface_children()))
        real = support.snapshot(simple_root(children=[support.node("div", wrapper=True, children=surface_children())]))
        _, result = self.run_pair(proto, real)
        self.assertNotEqual(result["verdict"], "BLOCKED")

    def test_child_signature_sharing_at_least_half_is_compatible(self) -> None:
        proto = support.snapshot(simple_root(children=surface_children()))
        real = support.snapshot(simple_root(children=[
            support.node("h2", role="heading", name="Orders", own_text="Orders"),
            support.node("p", own_text="Body"),
            support.node("a", role="link", name="Save"),
        ]))
        _, result = self.run_pair(proto, real)
        self.assertNotEqual(result["verdict"], "BLOCKED")

    def test_identical_snapshots_match(self) -> None:
        proto = support.snapshot(simple_root())
        real = support.snapshot(simple_root())
        completed, result = self.run_pair(proto, real)
        self.assertEqual(result["verdict"], "MATCH")
        self.assertEqual(result["conditions"]["viewport"], {"width": 1440, "height": 900})
        self.assertTrue(completed.stdout.startswith("MATCH"))

    def test_unreadable_input_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            completed = support.run_diff("--prototype", f"{temp}/missing.json", "--real", f"{temp}/missing.json", "--out", f"{temp}/out.json")
            self.assertEqual(completed.returncode, 2)
            self.assertIn("missing.json", completed.stderr)

    def test_missing_pairings_file_is_not_an_error(self) -> None:
        proto = support.snapshot(simple_root())
        real = support.snapshot(simple_root())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proto_path = support.write_json(root / "prototype.json", proto)
            real_path = support.write_json(root / "real.json", real)
            out = root / "diff.json"
            completed = support.run_diff(
                "--prototype", str(proto_path), "--real", str(real_path), "--out", str(out),
                "--pairings", str(root / "missing-pairings.json"), "--row", "L1",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = support.read_json(out)
            self.assertEqual(result["verdict"], "MATCH")

    def test_gzip_base64_encoded_snapshots_match(self) -> None:
        proto = support.snapshot(simple_root())
        real = support.snapshot(simple_root())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proto_path = support.write_compressed_snapshot(root / "prototype.json", proto)
            real_path = support.write_compressed_snapshot(root / "real.json", real)
            out = root / "diff.json"
            completed = support.run_diff("--prototype", str(proto_path), "--real", str(real_path), "--out", str(out))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = support.read_json(out)
            self.assertEqual(result["verdict"], "MATCH")
            self.assertTrue(completed.stdout.startswith("MATCH"))

    def test_invalid_base64_encoded_snapshot_exits_two(self) -> None:
        proto = support.snapshot(simple_root())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proto_path = root / "prototype.json"
            proto_path.write_text(json.dumps("not-valid-base64!!!"), encoding="utf-8")
            real_path = support.write_json(root / "real.json", proto)
            out = root / "diff.json"
            completed = support.run_diff("--prototype", str(proto_path), "--real", str(real_path), "--out", str(out))
            self.assertEqual(completed.returncode, 2)
            self.assertIn("prototype.json", completed.stderr)

    def test_truncated_compressed_snapshot_exits_two(self) -> None:
        proto = support.snapshot(simple_root())
        real = support.snapshot(simple_root())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proto_path = support.write_compressed_snapshot(root / "prototype.json", proto)
            real_path = support.write_compressed_snapshot(root / "real.json", real)
            gzip_bytes = base64.b64decode(json.loads(proto_path.read_text(encoding="utf-8")))
            truncated = base64.b64encode(gzip_bytes[:10]).decode("ascii")
            proto_path.write_text(json.dumps(truncated), encoding="utf-8")
            out = root / "diff.json"
            completed = support.run_diff("--prototype", str(proto_path), "--real", str(real_path), "--out", str(out))
            self.assertEqual(completed.returncode, 2)
            self.assertIn("prototype.json", completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)

    def test_corrupted_compressed_snapshot_exits_two(self) -> None:
        proto = support.snapshot(simple_root())
        real = support.snapshot(simple_root())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proto_path = support.write_compressed_snapshot(root / "prototype.json", proto)
            real_path = support.write_compressed_snapshot(root / "real.json", real)
            gzip_bytes = bytearray(base64.b64decode(json.loads(proto_path.read_text(encoding="utf-8"))))
            for index in range(12, 40):
                gzip_bytes[index] ^= 0xFF
            corrupted = base64.b64encode(bytes(gzip_bytes)).decode("ascii")
            proto_path.write_text(json.dumps(corrupted), encoding="utf-8")
            out = root / "diff.json"
            completed = support.run_diff("--prototype", str(proto_path), "--real", str(real_path), "--out", str(out))
            self.assertEqual(completed.returncode, 2)
            self.assertIn("prototype.json", completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)

    def test_pairings_without_row_is_ignored_with_a_warning(self) -> None:
        proto = support.snapshot(simple_root())
        real = support.snapshot(simple_root())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proto_path = support.write_json(root / "prototype.json", proto)
            real_path = support.write_json(root / "real.json", real)
            out = root / "diff.json"
            pairings_path = support.write_json(root / "pairings.json", {"L1": {}})
            completed = support.run_diff(
                "--prototype", str(proto_path), "--real", str(real_path), "--out", str(out),
                "--pairings", str(pairings_path),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("--row", completed.stderr)
