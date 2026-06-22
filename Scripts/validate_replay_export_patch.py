#!/usr/bin/env python3
"""Reject replay-export patches that cross the read-only serialization boundary."""

from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "replay-export-v1.patch"
ALLOWED_PATHS = {
    "NightscoutService/NightscoutServiceKit/Extensions/StoredDosingDecision.swift",
    "NightscoutService/NightscoutServiceKitTests/BolusRemoteNotificationTestCase.swift",
}
EXPECTED_SUBMODULE_COMMIT = "7721a8da0de4f69fbc6994bdaa5c860ba9a99ede"


def fail(message: str) -> None:
    print(f"replay-export safety check failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def run(*args: str) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        fail(f"{' '.join(args)}\n{result.stdout}{result.stderr}")
    return result.stdout.strip()


text = PATCH.read_text(encoding="utf-8")
changed_paths = set(re.findall(r"^diff --git a/(.+?) b/(.+?)$", text, re.MULTILINE))
expected_changed_paths = {(path, path) for path in ALLOWED_PATHS}
if changed_paths != expected_changed_paths:
    fail(f"unexpected changed paths: {sorted(changed_paths)}")

removed_lines = [
    line
    for line in text.splitlines()
    if line.startswith("-") and not line.startswith("---")
]
expected_removed = [
    "-                                   failureReason: automaticDoseDecision?.loopStatusFailureReason),"
]
if removed_lines != expected_removed:
    fail(f"unexpected removed lines: {removed_lines}")

required_markers = [
    '"schemaVersion": 1',
    '"captureRole": "completedLoopDecision"',
    '"loopDecisionSyncIdentifier"',
    '"dosingPrediction"',
    '"automaticDoseRecommendation"',
    "testingDetails: replayCaptureTestingDetails",
]
for marker in required_markers:
    if marker not in text:
        fail(f"missing required marker: {marker}")

for forbidden in [
    "func predictGlucose(",
    ".recommendedAutomaticDose(",
    ".recommendedTempBasal(",
    "enactRecommendedAutomaticDose(",
    "enactBolus(",
    "enactTempBasal(",
]:
    if forbidden in text:
        fail(f"forbidden control-path symbol in patch: {forbidden}")

actual_submodule_commit = run("git", "-C", "NightscoutService", "rev-parse", "HEAD")
if actual_submodule_commit != EXPECTED_SUBMODULE_COMMIT:
    fail(
        "NightscoutService commit changed; review and re-pin the patch before building "
        f"(expected {EXPECTED_SUBMODULE_COMMIT}, found {actual_submodule_commit})"
    )

run("git", "apply", "--check", "--whitespace=fix", str(PATCH))
print("Replay-export patch is confined to the approved read-only serialization boundary.")
