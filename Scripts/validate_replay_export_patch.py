#!/usr/bin/env python3
"""Validate that replay-export V4 remains outside Loop's control logic."""

from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "replay-export-v4.patch"
ALLOWED_PATHS = {
    "LoopKit/LoopKit/DosingDecisionStore.swift",
    "LoopKit/LoopKitTests/DosingDecisionStoreTests.swift",
    "Loop/Loop/Managers/LoopDataManager.swift",
    "Loop/LoopTests/Managers/LoopDataManagerDosingTests.swift",
    "NightscoutService/NightscoutServiceKit/Extensions/StoredDosingDecision.swift",
    "NightscoutService/NightscoutServiceKitTests/BolusRemoteNotificationTestCase.swift",
}
EXPECTED_SUBMODULE_COMMITS = {
    "Loop": "1f71ec4fa94941abdbd72fd5bd914770faa2e90b",
    "LoopKit": "e7e2ee2b546c4d8122014838cb98a0e26dd91208",
    "NightscoutService": "7721a8da0de4f69fbc6994bdaa5c860ba9a99ede",
}


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


def changed_lines_by_path(text: str, prefix: str) -> dict[str, list[str]]:
    changed: dict[str, list[str]] = {}
    current_path: str | None = None
    for line in text.splitlines():
        match = re.match(r"^diff --git a/(.+?) b/(.+?)$", line)
        if match:
            current_path = match.group(2)
            changed.setdefault(current_path, [])
            continue
        if current_path and line.startswith(prefix) and not line.startswith(prefix * 3):
            changed[current_path].append(line[1:])
    return changed


text = PATCH.read_text(encoding="utf-8")
changed_paths = set(re.findall(r"^diff --git a/(.+?) b/(.+?)$", text, re.MULTILINE))
expected_changed_paths = {(path, path) for path in ALLOWED_PATHS}
if changed_paths != expected_changed_paths:
    fail(f"unexpected changed paths: {sorted(changed_paths)}")

added = changed_lines_by_path(text, "+")
removed = changed_lines_by_path(text, "-")

loop_manager_path = "Loop/Loop/Managers/LoopDataManager.swift"
expected_loop_manager_additions = [
    "if predictedGlucose == nil {",
    "replayPredictionEffects = nil",
    "}",
    "private var replayPredictionEffects: StoredDosingDecision.ReplayPredictionEffects?",
    "dosingDecision.replayPredictionEffects = replayPredictionEffects",
    "let replayPredictionEffects = StoredDosingDecision.ReplayPredictionEffects(",
    "enabledEffectsRawValue: settings.enabledEffects.rawValue,",
    "prediction: predictedGlucose,",
    "insulin: insulinEffect ?? [],",
    "carbs: carbEffect ?? [],",
    "momentum: glucoseMomentumEffect ?? [],",
    "retrospection: retrospectiveGlucoseEffect",
    ")",
    "self.replayPredictionEffects = replayPredictionEffects",
    "dosingDecision.replayPredictionEffects = replayPredictionEffects",
]
actual_loop_manager_additions = [
    line.strip() for line in added.get(loop_manager_path, []) if line.strip()
]
if actual_loop_manager_additions != expected_loop_manager_additions:
    fail(f"unexpected LoopDataManager additions: {actual_loop_manager_additions}")
if removed.get(loop_manager_path):
    fail(f"LoopDataManager lines were removed: {removed[loop_manager_path]}")

loop_manager_test_path = "Loop/LoopTests/Managers/LoopDataManagerDosingTests.swift"
expected_loop_manager_test_additions = [
    "func waitOnDataQueue(timeout: TimeInterval = 5.0) {",
    "wait(for: [exp], timeout: 5.0)",
    "wait(for: [exp], timeout: 5.0)",
    "wait(for: [exp], timeout: 5.0)",
    "wait(for: [exp], timeout: 5.0)",
    "wait(for: [exp], timeout: 5.0)",
    "wait(for: [exp], timeout: 5.0)",
    "XCTAssertNotNil(dosingDecisionStore.dosingDecisions[0].replayPredictionEffects)",
    "XCTAssertNotNil(dosingDecisionStore.dosingDecisions[0].replayPredictionEffects?.prediction)",
    "wait(for: [exp], timeout: 5.0)",
    "wait(for: [exp], timeout: 5.0)",
    "wait(for: [exp], timeout: 5.0)",
]
actual_loop_manager_test_additions = [
    line.strip() for line in added.get(loop_manager_test_path, []) if line.strip()
]
if actual_loop_manager_test_additions != expected_loop_manager_test_additions:
    fail(
        "unexpected LoopDataManager dosing-test additions: "
        f"{actual_loop_manager_test_additions}"
    )
expected_loop_manager_test_removals = [
    "func waitOnDataQueue(timeout: TimeInterval = 1.0) {",
    "wait(for: [exp], timeout: 1.0)",
    "wait(for: [exp], timeout: 1.0)",
    "wait(for: [exp], timeout: 1.0)",
    "wait(for: [exp], timeout: 1.0)",
    "wait(for: [exp], timeout: 1.0)",
    "wait(for: [exp], timeout: 1.0)",
    "wait(for: [exp], timeout: 1.0)",
    "wait(for: [exp], timeout: 1.0)",
    "wait(for: [exp], timeout: 1.0)",
]
actual_loop_manager_test_removals = [
    line.strip() for line in removed.get(loop_manager_test_path, []) if line.strip()
]
if actual_loop_manager_test_removals != expected_loop_manager_test_removals:
    fail(
        "unexpected LoopDataManager dosing-test removals: "
        f"{actual_loop_manager_test_removals}"
    )

loopkit_model_path = "LoopKit/LoopKit/DosingDecisionStore.swift"
if removed.get(loopkit_model_path):
    fail(f"StoredDosingDecision lines were removed: {removed[loopkit_model_path]}")

nightscout_path = "NightscoutService/NightscoutServiceKit/Extensions/StoredDosingDecision.swift"
expected_nightscout_removal = [
    "                                   failureReason: automaticDoseDecision?.loopStatusFailureReason),",
    "    ",
]
if removed.get(nightscout_path) != expected_nightscout_removal:
    fail(f"unexpected Nightscout production removals: {removed.get(nightscout_path)}")

required_markers = [
    '"schemaVersion": 4',
    "ReplayPredictionEffects: Codable, Equatable",
    "public let prediction: [PredictedGlucoseValue]?",
    "let replayPredictionEffects = StoredDosingDecision.ReplayPredictionEffects",
    "prediction: predictedGlucose",
    "prediction: diagnosticPrediction",
    "replayPredictionEffects?.prediction ?? predictedGlucose",
    "dosingDecision.replayPredictionEffects = replayPredictionEffects",
    "XCTAssertNotNil(dosingDecisionStore.dosingDecisions[0].replayPredictionEffects)",
    "XCTAssertNotNil(dosingDecisionStore.dosingDecisions[0].replayPredictionEffects?.prediction)",
    '"predictionEffects"',
    '"insulin"',
    '"retrospection"',
    "testingDetails: replayCaptureTestingDetails",
]
for marker in required_markers:
    if marker not in text:
        fail(f"missing required marker: {marker}")

added_production = "\n".join(
    line
    for path, lines in added.items()
    if "Tests/" not in path and "Tests\\" not in path
    for line in lines
)
for forbidden in [
    "func predictGlucose(",
    ".recommendedAutomaticDose(",
    ".recommendedTempBasal(",
    "enactRecommendedAutomaticDose(",
    "enactBolus(",
    "enactTempBasal(",
    "delegate?.loopDataManager",
]:
    if forbidden in added_production:
        fail(f"forbidden control-path symbol in production additions: {forbidden}")

for submodule, expected_commit in EXPECTED_SUBMODULE_COMMITS.items():
    actual_commit = run("git", "-C", submodule, "rev-parse", "HEAD")
    if actual_commit != expected_commit:
        fail(
            f"{submodule} commit changed; review and re-pin before building "
            f"(expected {expected_commit}, found {actual_commit})"
        )

run("git", "apply", "--check", "--whitespace=fix", str(PATCH))
print("Replay-export V4 patch preserves prediction components and the exact diagnostic dosing prediction across Loop's cache path.")
