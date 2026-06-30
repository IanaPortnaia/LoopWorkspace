# Replay Export Schema 5 Safety Boundary

## Pinned Source

- Loop: `1f71ec4fa94941abdbd72fd5bd914770faa2e90b`
- LoopKit: `e7e2ee2b546c4d8122014838cb98a0e26dd91208`
- NightscoutService: `7721a8da0de4f69fbc6994bdaa5c860ba9a99ede`

## Purpose

Schema 5 exports the component timelines and intermediate discrepancy sources
needed to determine why the Python replay differs from the prediction Loop
actually used for dosing. The export remains diagnostic only and is stored
under `loop.testingDetails.replayCapture`.

V3 corrected the incomplete V2 lifecycle behavior. V2 attached component
timelines only when `LoopDataManager` calculated a fresh prediction. In normal
operation, a status update can calculate and cache the prediction immediately
before the dosing loop. The dosing loop then reuses the cached prediction, and
the V2 stored decision omitted its component timelines.

V4 additionally stores the exact non-pending dosing prediction inside the same
diagnostic object as the component timelines. This avoids conflating Loop's
existing stored status prediction, which may include pending insulin in cached
cycles, with the prediction used to calculate the automatic dose.

Schema 5 extends that diagnostic object with the insulin-counteraction velocity
timeline and summed retrospective glucose discrepancies used upstream by carb
absorption and retrospective correction.

## Runtime Boundary

Production changes are limited to:

1. An optional Codable `ReplayPredictionEffects` field on
   `StoredDosingDecision`.
2. A diagnostic cache in `LoopDataManager`, created only after both the dosing
   prediction and pending-insulin prediction have completed.
3. Copying that cached diagnostic value into each new stored decision alongside
   the cached prediction.
4. Clearing the diagnostic cache whenever the associated prediction changes, so
   stale replay effects cannot survive a later partial prediction failure.
5. Nightscout serialization of the stored diagnostic field.
6. Preferential Nightscout replay export of the diagnostic dosing prediction
   when it is available, with fallback to the prior stored prediction for older
   records.

The component assignment copies existing calculation results:

- insulin effect used by the dosing prediction
- carb effect
- momentum effect
- retrospective correction effect
- insulin-counteraction velocities
- summed retrospective glucose discrepancies
- enabled prediction-effect bitmask
- exact non-pending dosing prediction paired with those component timelines

The cache assignment is deliberately after both calls to `predictGlucose`.
The recommendation is then calculated from the existing local
`predictedGlucose` value, not from the diagnostic payload. Cached effects are
copied rather than reconstructed from potentially newer input arrays.

Schema 5 does not modify:

- `LoopMath`
- insulin, carb, momentum, or retrospective-correction calculations
- automatic-dose or temp-basal recommendation functions
- correction targets, suspend threshold, or delivery limits
- dose enactment
- pump or CGM communication

## Persistence Compatibility

`replayPredictionEffects` is optional and decoded with `decodeIfPresent`.
Existing stored decisions therefore remain readable. Decisions created by code
without replay export omit the field and preserve their prior encoded
representation. The nested diagnostic prediction and added Schema 5 diagnostic
arrays are optional/defaulted so older records without them still decode.

## Failure Behavior

The diagnostic value uses non-throwing struct construction from arrays already
held by `LoopDataManager`. Nightscout capture construction remains optional.
If the diagnostic field is absent, V1-compatible prediction, recommendation,
glucose history, IOB, and COB fields are still exported.

Nightscout upload failures retain existing service behavior and cannot
propagate into prediction, recommendation, or dose enactment.

## Data Volume

Schema 5 exports the four component timelines that directly form the dosing
prediction, the exact non-pending prediction paired with those timelines, and
the upstream insulin-counteraction and retrospective-discrepancy timelines.
It still omits the separate pending-insulin prediction timeline because that
timeline is not used for automatic-dose calculation.

## Required Validation

Before installation:

1. Run `python Scripts/validate_replay_export_patch.py`.
2. Run the `Validate Replay Export` workflow with Xcode 26.4.
3. Require the Nightscout serialization test and replay-effect Codable test to
   pass.
4. Require the cached-prediction dosing regression assertion to pass, proving
   the stored loop decision retains its component timelines after
   `getLoopState()` primes the prediction cache.
5. Require LoopKit dose-math tests and selected LoopDataManager dosing tests to
   pass.
6. Require an unsigned simulator build of Loop to compile.
7. Confirm a release build succeeds without signing changes.
8. Inspect several Schema 5 Nightscout records and measure payload size before
   extended use.

The validator rejects unexpected files, removals from Loop or LoopKit
production code, and additions containing recommendation or enactment symbols.
The promoted patch is `patches/replay-export-v4.patch`.

The patch also lengthens selected `LoopDataManagerDosingTests` async waits from
1 second to 5 seconds. This is test-only and avoids false failures on slower
GitHub-hosted macOS runners while preserving the same dosing assertions.

No static review can prove absolute safety. Installation remains contingent on
the compile and regression workflow passing.
