# Isolated HealthKit Boundary Probe

This test-only workflow resolves a numerical question identified in the Python
replay. It does not modify or build Loop, apply the replay overlay, read patient
data, access HealthStore, use signing secrets or distribute an app.

The key synthetic fixture compares a quantity of 100 mg/dL with the target
5.55074860726 in `mmol<180.1558800000541>/L`. Algebraic conversion in Python can
place the target one ULP above 100 mg/dL. Loop's quantity comparison delegates
to native HealthKit `compare`, whose behavior must be measured rather than
replaced by an outcome-fitted tolerance.

## Execution

The dedicated `HealthKit Boundary Probe` workflow runs on a GitHub macOS runner,
using the Xcode selected by the existing build workflows. A standalone Swift
executable is compiled against the iOS simulator SDK and executed with `simctl
spawn` inside an available iPhone simulator. The runtime matching the SDK major
and minor version is preferred. The selected runtime, architecture, SDK, Xcode
and source commit are recorded. No physical-device fallback exists.

For initial validation, pushes to `codex/healthkit-boundary-probe` touching the
probe files trigger the workflow. It can also be manually dispatched once the
workflow is present on the default branch. The existing phone-app workflows and
replay overlay are unchanged.

```powershell
python -m unittest discover -s Scripts/tests -p test_healthkit_boundary_probe.py -v
```

On a Mac with the selected Xcode and iPhone simulator installed:

```sh
python3 Scripts/probe_healthkit_boundary.py
```

The Swift program refuses non-simulator compilation. The Python runner refuses
native execution on Windows or Linux; local parser tests are not native tests.

## Evidence and Limits

Twelve fixtures cover same-unit identity, ordinary values one mg/dL away,
neighboring representable doubles, the cross-unit boundary and neighboring
target values. Ordinary controls must pass. The central boundary outcome is
not predetermined: ascending, equal and descending answers are preserved.

The result distinguishes three questions:

- Does `HKQuantity.compare` consider glucose below the target?
- Do plain scalar comparisons of HealthKit-converted values agree?
- Does the Python-style multiply/divide conversion agree?

Both comparison directions, self-comparison, raw inputs and IEEE-754 bit
patterns are retained. Validation rejects missing fixtures, failed controls,
inconsistent comparisons or numeric precision loss during JSON transport.

Artifacts include result JSON, environment JSON, command logs and a Markdown
summary. They contain synthetic constants, not capture IDs, timestamps, profiles
or glucose histories. The executable itself is not uploaded.

Passing this probe validates the isolated behavior on the recorded simulator
runtime. It does not establish equivalence on every iOS version, complete Loop
decision parity or clinical benefit. Any Python correction needs its own scoped
regression run after these results are inspected.
