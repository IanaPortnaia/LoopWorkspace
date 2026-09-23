# Sync-Friendly Replay Export

## Normal Updates

Merge the initial integration PR using **Create a merge commit**, not squash or
rebase. This preserves the upstream v3.14.8 ancestry so future fork syncs do not
try to merge the same upstream history again.

After this integration is merged, use the fork's **main** branch:

1. Use GitHub's **Sync fork / Update branch**, preserving local commits. Never
   choose a discard/reset option that removes the customization commits.
2. Let **Validate Replay Export** finish successfully for the updated commit.
3. Run **Build Loop Manual** from **main**. The automatic upstream build uses
   the same customization and mandatory validation gate.
4. After installing a new app, check that Schema 7 captures, source settings,
   carb statuses and prediction components continue to arrive in Nightscout.

Do not keep building the old `replay-export-schema6-local` branch: it is retained
as the pre-update reference, but does not receive updates when main is synced.
No changes to pump settings or the installed app are made by this integration.

Ordinary compatible updates need no recurring manual merges of three forked
submodules. This is not a promise that every future upstream release can update
without review. A patch conflict, changed protected algorithm file, changed build
hook, missing Xcode or failed/skipped tests deliberately stops the build. Do not
disable the guard or build without the export to bypass such a failure.

## Layout

- Workspace submodule URLs and gitlinks follow the official upstream release.
- `patches/replay-export-schema7.patch` contains the existing, source-merged
  diagnostic export and upload-size fix. Upstream's existing Customize Loop step
  applies it in both manual and automatic workflows.
- `replay-export/manifest.json` records the reviewed patch digest, allowed paths,
  protected upstream core-file blob IDs and the previous working workspace.
- `Scripts/replay_export.py` validates the overlay, upstream checkouts, build
  hooks and selected Xcode, and runs simulator regression tests without
  distribution credentials.
- One line at the start of `fastlane/Fastfile`'s `build_loop` lane runs mandatory
  validation before the lane's signing, App Store lookup and archive operations.
- `.github/workflows/validate_replay_export.yml` runs without distribution
  credentials on pull requests, pushes to main and manual validation dispatch.
- The obsolete Schema 5 patch is kept outside the active patch directory under
  `replay-export/archive/`. It is never applied on top of Schema 7.

The upstream manual/automatic build workflows are intentionally unmodified.
Their Xcode path is read by validation, not copied into a separate pinned version.
Both must select the same Xcode. At integration time this is Xcode 26.5.

## Local Checks

```sh
python3 -m unittest discover -s Scripts/tests -v
python3 Scripts/replay_export.py check
python3 Scripts/replay_export.py apply
python3 Scripts/replay_export.py verify-applied
```

`apply` is idempotent only for the fully reviewed overlay. A partially applied
patch or unrelated tracked changes in the three affected submodules is an error.
It does not reset or clean the checkout.

On the GitHub macOS runner, after selecting the reported Xcode:

```sh
python3 Scripts/replay_export.py xcode-path
python3 Scripts/replay_export.py validate
```

`validate-build` additionally requires that the standard build workflow has
already applied the overlay. It refuses to silently repair a missing Customize
Loop step. Successful Xcode validation produces a simulator-build/test receipt
under `artifacts/replay-validation-*/validation.json`. Validation uses ad-hoc
simulator signing (identity `-`, no team or provisioning profile) to preserve
Siri/HealthKit entitlements in the test host. It does not use an Apple signing
certificate or upload a build. This receipt describes engineering tests, not
clinical validation or successful device installation.

## Review After an Incompatible Update

Inspect the upstream change and merge the diagnostic additions against the new
source. Review the resulting diff before replacing the patch and manifest.
Protected baseline hashes must never be automatically refreshed merely to turn
the check green. Re-run persistence, export, dose-math, selected Loop dosing
tests and a simulator app build. Revalidate sandbox source assumptions if core
prediction or dosing mechanisms changed.

The prior known-working workspace is
`2737c4d1d944ccf0bea14ec723918680e0b94a8a`; its existing branch is not deleted.
The first integration targets upstream v3.14.8. The overlay was generated from
clean three-way merges of the old custom Loop, LoopKit and NightscoutService
sources onto the submodule revisions selected by that release. No new dosing
algorithm or treatment-setting changes are part of the overlay migration.
