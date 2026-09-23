import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import replay_export as replay


class ReplayGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "patches").mkdir()
        (self.root / "fastlane").mkdir()
        (self.root / ".github/workflows").mkdir(parents=True)
        self.data = b"diff --git a/Loop/a.swift b/Loop/a.swift\n--- a/Loop/a.swift\n+++ b/Loop/a.swift\n@@ -1 +1 @@\n-old\n+new\n"
        (self.root / "patches/replay.patch").write_bytes(self.data)
        (self.root / "patches/save_patches_here.md").write_text("patches\n")
        self.config = {"patch": "patches/replay.patch", "patch_sha256": hashlib.sha256(self.data).hexdigest(),
                       "overlay_paths": ["Loop/a.swift"], "upstream_modules": {"Loop": "url"}}
        self.workflow = "sudo xcode-select --switch /Applications/Xcode_26.5.app/Contents/Developer\ngit apply ./patches/*\n"
        for name in replay.WORKFLOWS:
            (self.root / ".github/workflows" / name).write_text(self.workflow)
        (self.root / "fastlane/Fastfile").write_text("lane :build_loop do\n  " + replay.BUILD_HOOK + "\nend\n")

    def result(self, code=0, stdout="", stderr=""):
        return subprocess.CompletedProcess([], code, stdout, stderr)

    def test_reviewed_patch_and_crlf_have_same_identity(self):
        replay.patch_bytes(self.root, self.config)
        (self.root / self.config["patch"]).write_bytes(self.data.replace(b"\n", b"\r\n"))
        replay.patch_bytes(self.root, self.config)

    def test_changed_patch_is_rejected(self):
        (self.root / self.config["patch"]).write_bytes(self.data + b"+extra\n")
        with self.assertRaisesRegex(replay.ValidationError, "reviewed manifest"):
            replay.patch_bytes(self.root, self.config)

    def test_legacy_patch_next_to_new_patch_is_rejected(self):
        (self.root / "patches/old.patch").write_text("old")
        with self.assertRaisesRegex(replay.ValidationError, "Unexpected patch files"):
            replay.patch_bytes(self.root, self.config)

    def test_patch_path_mismatch_is_rejected(self):
        with self.assertRaisesRegex(replay.ValidationError, "Unexpected replay patch paths"):
            replay.patch_bytes(self.root, dict(self.config, overlay_paths=["Loop/b.swift"]))

    def test_escaping_path_is_rejected(self):
        with self.assertRaisesRegex(replay.ValidationError, "escapes workspace"):
            replay.safe_path(self.root, "../outside")

    def test_build_and_validation_follow_same_xcode(self):
        self.assertEqual(replay.verify_build_hook(self.root), "/Applications/Xcode_26.5.app/Contents/Developer")
        for name in replay.WORKFLOWS:
            (self.root / ".github/workflows" / name).write_text(self.workflow.replace("26.5", "27.1"))
        self.assertIn("27.1", replay.xcode_path(self.root))

    def test_conflicting_xcode_versions_are_rejected(self):
        (self.root / ".github/workflows/build_loop_auto.yml").write_text(self.workflow.replace("26.5", "27.1"))
        with self.assertRaisesRegex(replay.ValidationError, "versions differ"):
            replay.xcode_path(self.root)

    def test_missing_workflow_patch_hook_is_rejected(self):
        (self.root / ".github/workflows/build_loop_auto.yml").write_text(self.workflow.splitlines()[0])
        with self.assertRaisesRegex(replay.ValidationError, "patch application hook changed"):
            replay.xcode_path(self.root)

    def test_missing_or_late_release_guard_is_rejected(self):
        for text in ["lane :build_loop do\nend", "lane :build_loop do\n  setup_ci\n  " + replay.BUILD_HOOK]:
            (self.root / "fastlane/Fastfile").write_text(text)
            with self.assertRaisesRegex(replay.ValidationError, "pre-signing"):
                replay.verify_build_hook(self.root)

    def test_partial_patch_fails_without_attempting_apply(self):
        with patch.object(replay, "command", return_value=self.result(1, stderr="conflict")) as cmd:
            with self.assertRaisesRegex(replay.ValidationError, "partially applied"):
                replay.overlay_state(self.root, self.root / "patches/replay.patch")
        self.assertEqual(cmd.call_count, 2)
        self.assertTrue(all("--check" in call.args for call in cmd.call_args_list))

    def test_clean_and_applied_states(self):
        with patch.object(replay, "command", return_value=self.result()):
            self.assertEqual(replay.overlay_state(self.root, Path("a")), "clean")
        with patch.object(replay, "command", side_effect=[self.result(1), self.result()]):
            self.assertEqual(replay.overlay_state(self.root, Path("a")), "applied")

    def test_review_required_when_core_blob_changes(self):
        config = {"upstream_modules": {}, "protected_upstream_blobs": {"Loop/a.swift": "old"}}
        with patch.object(replay, "command", return_value=self.result(stdout="new\n")):
            with self.assertRaisesRegex(replay.ValidationError, "core source changed"):
                replay.verify_upstream(self.root, config)

    def test_wrong_submodule_head_is_rejected(self):
        config = {"upstream_modules": {"Loop": "official"}, "protected_upstream_blobs": {}}
        with patch.object(replay, "command", side_effect=[self.result(stdout=s) for s in ["official", "expected", "wrong"]]):
            with self.assertRaisesRegex(replay.ValidationError, "gitlink"):
                replay.verify_upstream(self.root, config)

    def test_fork_url_is_rejected(self):
        config = {"upstream_modules": {"Loop": "official"}, "protected_upstream_blobs": {}}
        with patch.object(replay, "command", return_value=self.result(stdout="custom-fork")):
            with self.assertRaisesRegex(replay.ValidationError, "upstream"):
                replay.verify_upstream(self.root, config)

    def test_extra_edit_in_same_file_fails_reviewed_diff(self):
        fake = self.data.replace(b"+new", b"+unexpected")
        with patch.object(replay, "command", side_effect=[self.result(), self.result(stdout="a.swift\n"), self.result(stdout=fake.decode())]):
            with self.assertRaisesRegex(replay.ValidationError, "Applied changes differ"):
                replay.verify_diffs(self.root, self.config, "applied")

    def test_canonical_diff_does_not_ignore_changed_context(self):
        shifted = self.data.replace(b"@@ -1 +1 @@", b"@@ -5 +5 @@")
        self.assertEqual(replay.canonical_changes(self.data), replay.canonical_changes(shifted))
        self.assertNotEqual(replay.canonical_changes(self.data), replay.canonical_changes(self.data.replace(b"+new", b"+other")))

    def test_absent_skipped_failed_or_zero_tests_cannot_pass(self):
        good = {"passedTests": 16, "failedTests": 0, "skippedTests": 0}
        replay.assert_test_summary(good, 16)
        for bad in [{}, dict(good, passedTests=0), dict(good, passedTests=15), dict(good, failedTests=1),
                    dict(good, skippedTests=1), dict(good, passedTests=True)]:
            with self.subTest(bad=bad), self.assertRaises(replay.ValidationError):
                replay.assert_test_summary(bad, 16)

    def test_release_cannot_silently_apply_a_missing_overlay(self):
        with patch.object(replay, "manifest", return_value=self.config), \
             patch.object(replay, "patch_bytes", return_value=(Path("a"), b"")), \
             patch.object(replay, "verify_build_hook"), patch.object(replay, "verify_upstream"), \
             patch.object(replay, "overlay_state", return_value="clean"), \
             patch.object(replay, "verify_diffs"), patch.object(replay, "command") as cmd:
            with self.assertRaisesRegex(replay.ValidationError, "did not apply"):
                replay.prepare(self.root, require_applied=True)
            cmd.assert_not_called()

    def test_already_applied_overlay_is_idempotent(self):
        with patch.object(replay, "manifest", return_value=self.config), \
             patch.object(replay, "patch_bytes", return_value=(Path("a"), b"")), \
             patch.object(replay, "verify_build_hook"), patch.object(replay, "verify_upstream"), \
             patch.object(replay, "overlay_state", return_value="applied"), \
             patch.object(replay, "verify_diffs"), patch.object(replay, "command") as cmd:
            replay.prepare(self.root, apply=True)
            cmd.assert_not_called()

    def test_non_macos_cannot_claim_xcode_validation(self):
        with patch.object(replay.sys, "platform", "win32"):
            with self.assertRaisesRegex(replay.ValidationError, "macOS runner"):
                replay.validate(self.root)

    def test_real_manifest_and_build_hooks_are_current(self):
        config = replay.manifest(replay.ROOT)
        replay.patch_bytes(replay.ROOT, config)
        replay.verify_build_hook(replay.ROOT)


if __name__ == "__main__":
    unittest.main()
