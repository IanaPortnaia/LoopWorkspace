#!/usr/bin/env python3
"""Fail-closed Schema 7 overlay and simulator validation for upstream syncs."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BUILD_HOOK = 'sh("python3", "#{GITHUB_WORKSPACE}/Scripts/replay_export.py", "validate-build")'
WORKFLOWS = ("build_loop.yml", "build_loop_auto.yml")
DOSE_MATH_CLASSES = ("RecommendTempBasalTests", "RecommendBolusTests")
LOOP_TESTS = (
    "testForecastFromLiveCaptureInputData", "testFlatAndStable", "testHighAndStable",
    "testHighAndFalling", "testHighAndRisingWithCOB", "testLowAndFallingWithCOB",
    "testLowWithLowTreatment", "testValidateMaxTempBasalDoesntCancelTempBasalIfHigher",
    "testValidateMaxTempBasalCancelsTempBasalIfLower", "testOpenLoopCancelsTempBasal",
    "testReceivedUnreliableCGMReadingCancelsTempBasal",
    "testLoopEnactsTempBasalWithoutManualBolusRecommendation",
    "testLoopRecommendsTempBasalWithoutEnactingIfOpenLoop",
    "testIsClosedLoopAvoidsTriggeringTempBasalCancelOnCreation",
    "testAutoBolusMaxIOBClamping", "testTempBasalMaxIOBClamping",
)


class ValidationError(RuntimeError):
    pass


def command(root, *args, check=True):
    result = subprocess.run(args, cwd=root, capture_output=True, text=True, encoding="utf-8")
    if check and result.returncode:
        raise ValidationError(f"Command failed: {' '.join(args)}\n{result.stdout}{result.stderr}")
    return result


def safe_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValidationError(f"Path escapes workspace: {relative}")
    return path


def manifest(root):
    result = json.loads((root / "replay-export/manifest.json").read_text(encoding="utf-8"))
    if result.get("schema_version") != 7:
        raise ValidationError("Unreviewed replay schema")
    return result


def patch_bytes(root, config):
    path = safe_path(root, config["patch"])
    # Git may check out CRLF on Windows; patch identity is defined with LF.
    data = path.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(data).hexdigest() != config["patch_sha256"]:
        raise ValidationError("Replay patch differs from the reviewed manifest")
    names = re.findall(rb"^diff --git a/(\S+) b/(\S+)$", data, re.MULTILINE)
    if (not names or any(a != b for a, b in names)
            or {b.decode() for _, b in names} != set(config["overlay_paths"])
            or len(names) != len(config["overlay_paths"])):
        raise ValidationError("Unexpected replay patch paths")
    for name in config["overlay_paths"]:
        safe_path(root, name)
    allowed = {path.name, "save_patches_here.md"}
    if {p.name for p in (root / "patches").iterdir()} != allowed:
        raise ValidationError("Unexpected patch files; legacy or extra patches require review")
    return path, data


def xcode_path(root):
    paths = []
    for name in WORKFLOWS:
        content = (root / ".github/workflows" / name).read_text(encoding="utf-8")
        found = re.findall(r"xcode-select --switch (/Applications/Xcode_\d+(?:\.\d+)+\.app/Contents/Developer)", content)
        if len(found) != 1:
            raise ValidationError(f"Cannot determine build Xcode from {name}; review upstream workflow")
        if "git apply ./patches/*" not in content:
            raise ValidationError(f"Upstream patch application hook changed in {name}")
        paths.extend(found)
    if len(set(paths)) != 1:
        raise ValidationError("Manual and automatic build Xcode versions differ")
    return paths[0]


def verify_build_hook(root):
    source = (root / "fastlane/Fastfile").read_text(encoding="utf-8")
    lane = source.split("lane :build_loop do", 1)
    if len(lane) != 2 or not lane[1].lstrip().startswith(BUILD_HOOK):
        raise ValidationError("Required pre-signing replay validation hook is missing")
    return xcode_path(root)


def verify_upstream(root, config):
    for module, url in config["upstream_modules"].items():
        actual_url = command(root, "git", "config", "-f", ".gitmodules", "--get", f"submodule.{module}.url").stdout.strip()
        if actual_url != url:
            raise ValidationError(f"{module} must use upstream, not a custom submodule fork")
        expected = command(root, "git", "rev-parse", f"HEAD:{module}").stdout.strip()
        actual = command(root / module, "git", "rev-parse", "HEAD").stdout.strip()
        if actual != expected:
            raise ValidationError(f"{module} checkout differs from the workspace gitlink")
    for relative, expected in config["protected_upstream_blobs"].items():
        module, path = relative.split("/", 1)
        actual = command(root / module, "git", "rev-parse", f"HEAD:{path}").stdout.strip()
        if actual != expected:
            raise ValidationError(f"Upstream core source changed: {relative}. Review before rebuilding.")


def overlay_state(root, path):
    forward = command(root, "git", "apply", "--check", str(path), check=False)
    if forward.returncode == 0:
        return "clean"
    reverse = command(root, "git", "apply", "--reverse", "--check", str(path), check=False)
    if reverse.returncode == 0:
        return "applied"
    raise ValidationError("Replay patch is incompatible or only partially applied. No fallback is allowed.\n"
                          + forward.stderr + reverse.stderr)


def canonical_changes(data):
    """Ignore upstream line numbers/blob IDs, never added/removed code or context."""
    return b"\n".join(line for line in data.splitlines()
                      if not line.startswith((b"index ", b"@@ ")))


def verify_diffs(root, config, state):
    expected = set(config["overlay_paths"]) if state == "applied" else set()
    actual = set()
    for module in config["upstream_modules"]:
        command(root / module, "git", "diff", "--check", "HEAD")
        changed = command(root / module, "git", "diff", "--name-only", "HEAD").stdout.splitlines()
        actual.update(f"{module}/{p}" for p in changed)
    if actual != expected:
        raise ValidationError("Submodule modifications differ from the reviewed overlay")
    if state == "applied":
        # Reverse applicability alone accepts extra edits in another hunk of the
        # same file. Compare complete normalized diffs with the reviewed patch.
        _, data = patch_bytes(root, config)
        actual_patch = b""
        for module in config["upstream_modules"]:
            result = command(root / module, "git", "diff", "HEAD", "--binary", "--full-index",
                             f"--src-prefix=a/{module}/", f"--dst-prefix=b/{module}/")
            actual_patch += result.stdout.replace("\r\n", "\n").encode()
        if canonical_changes(actual_patch) != canonical_changes(data):
            raise ValidationError("Applied changes differ from the reviewed replay overlay")


def prepare(root, apply=False, require_applied=False):
    config = manifest(root)
    path, _ = patch_bytes(root, config)
    verify_build_hook(root)
    verify_upstream(root, config)
    state = overlay_state(root, path)
    verify_diffs(root, config, state)
    if require_applied and state != "applied":
        raise ValidationError("Build workflow did not apply the required Schema 7 overlay")
    if apply and state == "clean":
        command(root, "git", "apply", str(path))
        state = overlay_state(root, path)
        if state != "applied":
            raise ValidationError("Replay overlay was not fully applied")
        verify_diffs(root, config, state)
    print(f"Replay Schema 7 overlay: {state}; core source and build hooks verified.", flush=True)
    return config


def assert_test_summary(summary, minimum):
    passed = summary.get("passedTests")
    failed = summary.get("failedTests")
    skipped = summary.get("skippedTests")
    if (type(passed) is not int or type(failed) is not int
            or type(skipped) is not int or passed < minimum or failed != 0 or skipped != 0):
        raise ValidationError(f"Missing, skipped, or failed required tests: {summary}")


def verify_dose_test_selectors(root):
    source = (root / "LoopKit/LoopKitTests/DoseMathTests.swift").read_text(encoding="utf-8")
    for name in DOSE_MATH_CLASSES:
        if not re.search(r"(?m)^class " + re.escape(name) + r"\s*:\s*XCTestCase\b", source):
            raise ValidationError(f"Required dose test class is missing: {name}")


def run_xcode(root, args):
    print("Running: " + " ".join(args), flush=True)
    result = subprocess.run(args, cwd=root)
    if result.returncode:
        raise ValidationError(f"Simulator Xcode validation failed ({result.returncode})")


def simulator_build_options(device_id, result_dir):
    # The test host needs its Siri/HealthKit entitlements. Disabling signing
    # entirely strips them; ad-hoc simulator signing needs no Apple identity.
    return ["-workspace", "LoopWorkspace.xcworkspace", "-destination",
            f"platform=iOS Simulator,id={device_id}", "-derivedDataPath", str(result_dir / "DerivedData"),
            "CODE_SIGNING_ALLOWED=YES", "CODE_SIGN_IDENTITY=-", "CODE_SIGN_STYLE=Manual",
            "DEVELOPMENT_TEAM=", "PROVISIONING_PROFILE_SPECIFIER=", "PROVISIONING_PROFILE="]


def validate(root, build=False):
    if sys.platform != "darwin":
        raise ValidationError("Simulator Xcode validation requires the GitHub macOS runner")
    config = prepare(root, apply=not build, require_applied=build)
    verify_dose_test_selectors(root)
    expected_xcode = xcode_path(root)
    if command(root, "xcode-select", "-p").stdout.strip() != expected_xcode:
        raise ValidationError("Validation must use the same Xcode as the release build")
    devices = json.loads(command(root, "xcrun", "simctl", "list", "devices", "available", "-j").stdout)
    iphones = [d["udid"] for group in devices["devices"].values() for d in group
               if d.get("isAvailable", False) and d["name"].startswith("iPhone")]
    if not iphones:
        raise ValidationError("No available iPhone simulator")
    out = root / "artifacts"
    out.mkdir(exist_ok=True)
    result_dir = Path(tempfile.mkdtemp(prefix="replay-validation-", dir=out))
    common = simulator_build_options(iphones[0], result_dir)
    suites = [
        ("NightscoutReplayValidation", "export", ["NightscoutServiceKitTests/ReplayCaptureTestCase"], 2),
        ("ReplayCoreRegression", "dose-math", ["LoopKitTests/" + name for name in DOSE_MATH_CLASSES], 57),
        ("ReplayCoreRegression", "persistence", ["LoopKitTests/StoredDosingDecisionCodableTests/testReplayPredictionEffectsCodable"], 1),
        ("ReplayCoreRegression", "loop-dosing", ["LoopTests/LoopDataManagerDosingTests/" + name for name in LOOP_TESTS], len(LOOP_TESTS)),
    ]
    summaries = {}
    for scheme, label, selected, minimum in suites:
        bundle = result_dir / f"{label}.xcresult"
        args = ["xcodebuild", "test", "-scheme", scheme, *common,
                "-parallel-testing-enabled", "NO", "-resultBundlePath", str(bundle)]
        args.extend("-only-testing:" + test for test in selected)
        run_xcode(root, args)
        summary = json.loads(command(root, "xcrun", "xcresulttool", "get", "test-results", "summary",
                                     "--path", str(bundle)).stdout)
        assert_test_summary(summary, minimum)
        summaries[label] = summary
    run_xcode(root, ["xcodebuild", "build", "-scheme", "Loop", *common])
    receipt = {"workspace_commit": command(root, "git", "rev-parse", "HEAD").stdout.strip(),
               "patch_sha256": config["patch_sha256"], "xcode": expected_xcode,
               "schema_version": 7, "suites": summaries, "simulator_build_passed": True,
               "signing_mode": "ad-hoc-simulator-only", "distribution_signing": False}
    (result_dir / "validation.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"Simulator replay validation passed: {result_dir / 'validation.json'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "apply", "verify-applied", "xcode-path", "validate", "validate-build"])
    args = parser.parse_args()
    try:
        if args.action == "xcode-path":
            print(xcode_path(ROOT))
        elif args.action in ("validate", "validate-build"):
            validate(ROOT, build=args.action == "validate-build")
        else:
            prepare(ROOT, apply=args.action == "apply", require_applied=args.action == "verify-applied")
    except (ValidationError, OSError, ValueError, KeyError) as exc:
        print(f"Replay validation stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
