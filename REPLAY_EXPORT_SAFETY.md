# Replay Export V1 Safety Boundary

## Pinned Source

- LoopWorkspace: `a2b527d5cde65fc693225702e9aa056fad3e9841`
- Loop: `40ae514ef2cb6ee8cf0a62177de3072a460ee2e4`
- LoopKit: `e7e2ee2b546c4d8122014838cb98a0e26dd91208`
- NightscoutService: `7721a8da0de4f69fbc6994bdaa5c860ba9a99ede`
- NightscoutKit package: `ca8e2cea82ab465282cd180ce01d64c1cf25478d`

## Runtime Boundary

V1 production code modifies only:

`NightscoutService/NightscoutServiceKit/Extensions/StoredDosingDecision.swift`

The patch also adds assertions to the existing NightscoutService test target in:

`NightscoutService/NightscoutServiceKitTests/BolusRemoteNotificationTestCase.swift`

The feature branch adds a validation-only workspace scheme named
`NightscoutReplayValidation`. It references the existing NightscoutService
framework and unit-test targets and is not used by the normal Loop build.

`ReplayCoreRegression` is also validation-only. It exposes the existing
LoopKit dose-math tests and LoopDataManager dosing tests without changing
either test target or the normal Loop scheme.

The workflow explicitly selects sixteen safety-relevant LoopDataManager tests.
It excludes manual-bolus recommendation tests and the settings-notification
test because their one-second asynchronous expectations are nondeterministic
on the hosted runner. They do not exercise automatic dosing or Nightscout
serialization. The selected tests cover automatic bolus, temp basal, IOB
limits, prediction fixtures, open-loop behavior, low-glucose handling, and
unreliable CGM handling.

The patch reads an already completed `.loop` `StoredDosingDecision` while
Nightscout device-status JSON is being created. It adds
`loop.testingDetails.replayCapture`.

It does not modify:

- `LoopDataManager`
- `LoopMath`
- `DoseMath`
- automatic-dose recommendation generation
- temp-basal or bolus enactment
- pump communication
- LoopKit persistence models

## Failure Behavior

Capture construction is non-throwing and optional. If no completed `.loop`
decision is paired with the status upload, `testingDetails` remains absent.
Nightscout upload failures retain the existing NightscoutService behavior and
cannot propagate into Loop prediction or dose enactment.

## Exported V1 Data

- status and loop-decision timestamps and UUIDs
- exact pre-command dosing prediction stored by Loop
- exact automatic-dose recommendation stored by Loop
- the two-hour glucose history available locally for that decision
- IOB and COB
- settings UUID
- warning and error identifiers

## Required Validation

Before installation:

1. Run `python3 Scripts/validate_replay_export_patch.py`.
2. Run the `Validate Replay Export` workflow. It applies the staged patch only
   inside its disposable runner and does not archive or distribution-sign an
   application. The hosted Loop tests use normal local simulator signing so
   the test host retains its required Siri entitlement.
3. Run Loop, LoopKit, and NightscoutService tests.
4. Confirm a release build succeeds without changing signing configuration.
5. Compare an unmodified and instrumented build using identical Loop dosing
   fixtures; predictions and recommendations must be byte-for-byte equivalent.
6. Install only after the exported JSON has been inspected from a non-dosing
   test or simulator environment.

No static review can provide absolute assurance. Installation remains blocked
until compilation and behavioral-equivalence tests pass.

The patch remains under `replay-export/`, outside the build workflow's
auto-applied `patches/` directory. Promotion into `patches/` is a separate
change made only after validation succeeds.
