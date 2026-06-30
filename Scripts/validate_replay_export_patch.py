#!/usr/bin/env python3
"""Validate that replay-export Schema 5 remains diagnostic-only."""

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


def patch_applies_or_is_already_applied() -> None:
    apply_result = subprocess.run(
        ["git", "apply", "--check", "--whitespace=fix", str(PATCH)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if apply_result.returncode == 0:
        return

    reverse_result = subprocess.run(
        ["git", "apply", "--reverse", "--check", "--whitespace=fix", str(PATCH)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if reverse_result.returncode == 0:
        return

    fail(
        "patch neither applies cleanly nor matches the already-applied working tree\n"
        f"apply check:\n{apply_result.stdout}{apply_result.stderr}\n"
        f"reverse check:\n{reverse_result.stdout}{reverse_result.stderr}"
    )


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


text = PATCH.read_text(encoding="utf-8-sig")
changed_paths = set(re.findall(r"^diff --git a/(.+?) b/(.+?)$", text, re.MULTILINE))
expected_changed_paths = {(path, path) for path in ALLOWED_PATHS}
if changed_paths != expected_changed_paths:
    fail(f"unexpected changed paths: {sorted(changed_paths)}")

added = changed_lines_by_path(text, "+")
removed = changed_lines_by_path(text, "-")

required_markers = [
    '"schemaVersion": 5',
    "ReplayPredictionEffects: Codable, Equatable",
    "ReplayCounteractionEffect: Codable, Equatable",
    "ReplayGlucoseChange: Codable, Equatable",
    "public let prediction: [PredictedGlucoseValue]?",
    "public let insulinCounteractionEffects: [ReplayCounteractionEffect]",
    "public let retrospectiveGlucoseDiscrepancies: [ReplayGlucoseChange]",
    "let replayPredictionEffects = StoredDosingDecision.ReplayPredictionEffects",
    "prediction: predictedGlucose",
    "insulin: insulinEffect ?? []",
    "carbs: carbEffect ?? []",
    "momentum: glucoseMomentumEffect ?? []",
    "retrospection: retrospectiveGlucoseEffect",
    "insulinCounteractionEffects: insulinCounteractionEffects.map",
    "retrospectiveGlucoseDiscrepancies: (retrospectiveGlucoseDiscrepanciesSummed ?? []).map",
    "replayPredictionEffects?.prediction ?? predictedGlucose",
    "dosingDecision.replayPredictionEffects = replayPredictionEffects",
    '"predictionEffects"',
    '"insulinCounteraction"',
    '"retrospectiveGlucoseDiscrepancies"',
    "testingDetails: replayCaptureTestingDetails",
    'XCTAssertEqual(capture["schemaVersion"] as? Int, 5)',
]
for marker in required_markers:
    if marker not in text:
        fail(f"missing required marker: {marker}")

for path in [
    "Loop/Loop/Managers/LoopDataManager.swift",
    "LoopKit/LoopKit/DosingDecisionStore.swift",
    "NightscoutService/NightscoutServiceKit/Extensions/StoredDosingDecision.swift",
]:
    if path not in added:
        fail(f"missing production changes for {path}")

nightscout_path = "NightscoutService/NightscoutServiceKit/Extensions/StoredDosingDecision.swift"
expected_nightscout_removal = [
    '                                   failureReason: automaticDoseDecision?.loopStatusFailureReason),',
    "    ",
]
if removed.get(nightscout_path) != expected_nightscout_removal:
    fail(f"unexpected Nightscout production removals: {removed.get(nightscout_path)}")

loop_manager_path = "Loop/Loop/Managers/LoopDataManager.swift"
if removed.get(loop_manager_path):
    fail(f"LoopDataManager production lines were removed: {removed[loop_manager_path]}")

loopkit_model_path = "LoopKit/LoopKit/DosingDecisionStore.swift"
if removed.get(loopkit_model_path):
    fail(f"StoredDosingDecision production lines were removed: {removed[loopkit_model_path]}")

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

patch_applies_or_is_already_applied()
print("Replay-export Schema 5 patch remains diagnostic-only and applies cleanly or is already applied.")
