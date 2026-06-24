# Replay Export V2 Safety Boundary

## Pinned Source

- Loop: `1f71ec4fa94941abdbd72fd5bd914770faa2e90b`
- LoopKit: `e7e2ee2b546c4d8122014838cb98a0e26dd91208`
- NightscoutService: `7721a8da0de4f69fbc6994bdaa5c860ba9a99ede`

## Purpose

V2 adds the component timelines needed to determine why the Python replay
differs from the prediction Loop actually used for dosing. The export remains
diagnostic only and is stored under `loop.testingDetails.replayCapture`.

## Runtime Boundary

Production changes are limited to:

1. An optional Codable `ReplayPredictionEffects` field on
   `StoredDosingDecision`.
2. One assignment in `LoopDataManager` after both the dosing prediction and
   pending-insulin prediction have already completed.
3. Nightscout serialization of the stored diagnostic field.

The component assignment copies existing calculation results:

- insulin effect used by the dosing prediction
- carb effect
- momentum effect
- retrospective correction effect
- enabled prediction-effect bitmask

The assignment is deliberately after both calls to `predictGlucose`. The
recommendation is then calculated from the existing local `predictedGlucose`
value, not from the diagnostic payload.

V2 does not modify:

- `LoopMath`
- insulin, carb, momentum, or retrospective-correction calculations
- automatic-dose or temp-basal recommendation functions
- correction targets, suspend threshold, or delivery limits
- dose enactment
- pump or CGM communication

## Persistence Compatibility

`replayPredictionEffects` is optional and decoded with `decodeIfPresent`.
Existing stored decisions therefore remain readable. Decisions created by code
without V2 omit the field and preserve their prior encoded representation.

## Failure Behavior

The diagnostic value uses non-throwing struct construction from arrays already
held by `LoopDataManager`. Nightscout capture construction remains optional.
If the diagnostic field is absent, V1-compatible prediction, recommendation,
glucose history, IOB, and COB fields are still exported.

Nightscout upload failures retain existing service behavior and cannot
propagate into prediction, recommendation, or dose enactment.

## Data Volume

V2 exports the four component timelines that directly form the dosing
prediction. It intentionally omits both the separate pending-insulin timeline
and the long insulin-counteraction history. Counteraction velocities affect
carb and retrospective calculations upstream, but they do not enter
`LoopMath.predictGlucose` directly. They can be added in a later schema only if
component comparison shows that the carb or retrospective source needs deeper
instrumentation.

## Required Validation

Before installation:

1. Run `python Scripts/validate_replay_export_patch.py`.
2. Run the `Validate Replay Export` workflow with Xcode 26.4.
3. Require the Nightscout serialization test and replay-effect Codable test to
   pass.
4. Require LoopKit dose-math tests and selected LoopDataManager dosing tests to
   pass.
5. Require an unsigned simulator build of Loop to compile.
6. Confirm a release build succeeds without signing changes.
7. Inspect several V2 Nightscout records and measure payload size before
   extended use.

The validator rejects unexpected files, removals from Loop or LoopKit
production code, and additions containing recommendation or enactment symbols.
The promoted patch is `patches/replay-export-v2.patch`.

No static review can prove absolute safety. Installation remains contingent on
the compile and regression workflow passing.
