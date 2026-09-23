# Replay Export Schema 7 Safety Boundary

See [the update guide](replay-export/README.md) for the sync/build procedure.

## Preservation and Scope

The source customizations from working workspace
`2737c4d1d944ccf0bea14ec723918680e0b94a8a` are preserved as a reviewed patch over
upstream v3.14.8. The Loop, LoopKit and NightscoutService source merges were clean.
Applying the generated patch was verified to reproduce those merged source
trees exactly. No custom submodule references are required in the workspace.

The overlay preserves optional replay persistence, cached-decision coherence,
native prediction/effect export, source dose/carb entries, carb statuses and
settings snapshots, bounded diagnostic payloads, and the one-device-status-per-
upload fix. The primary Nightscout path remains `loop.testingDetails.replayCapture`.
The obsolete Schema 5 patch is archived outside `patches/`.

No new changes to Loop prediction, recommendation, targets, insulin response,
delivery limits, dose enactment or pump/CGM settings are introduced by this
packaging migration. The upstream release itself includes pump connectivity and
other changes; its safety cannot be inferred solely from replay tests.

## Fail-Closed Build Gate

The validator requires:

1. The exact reviewed patch digest and allowed file set, with no additional
   active patches or unrelated tracked submodule modifications.
2. Official upstream submodule URLs and checkouts matching workspace gitlinks.
3. Unchanged protected upstream core-file blob IDs. New upstream changes to these
   files require explicit review, even when the patch still applies.
4. Full patch applicability or a fully applied patch. Partial application fails.
5. The pre-signing Fastlane guard and upstream patch hooks in both build workflows.
6. The same Xcode selected by both build workflows and unsigned validation.
7. Passing Nightscout replay serialization, replay Codable persistence, LoopKit
   dose-math and 16 selected LoopDataManager dosing regression tests.
8. A successful unsigned simulator build of Loop.

The test gate rejects zero, missing, skipped or failed required tests. It does not
retry a failed test until it happens to pass. Both upstream release workflows
invoke the same guarded Fastlane build lane. Signing/archive work inside that
lane cannot begin after a validation failure. Earlier certificate-maintenance
jobs in upstream workflows are unchanged.

Validation runs on every pull request and main update, with no distribution
credentials. A release build repeats the validation rather than trusting a green
check from a different commit or toolchain. Existing protected historical replay
datasets are not modified by this repository migration.

## Limits

These checks reduce integration risk; they cannot prove absolute device or
clinical safety. UI-only tests and a successful archive do not substitute for
on-device operation and export checks after installation. GitHub sync must merge
the fork's commits, not discard them. Unforeseen upstream restructuring can still
require a maintenance patch. Such an update must stop visibly rather than drop
the export or bypass the checks.

This integration does not build, upload or install a release automatically as
part of its pull-request validation. Before merging, inspect both CI jobs and
their test/build evidence. After installation, verify current Schema 7 captures
and recheck the sandbox's recorded source version before combining validation
results across app versions.
