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

## Recorded Native Result: October 6, 2026

[GitHub run 37456766056](https://github.com/IanaPortnaia/LoopWorkspace/actions/runs/37456766056)
succeeded at source commit `467fe3a3c784b5eabe6d188e0eec7d379990502a`.
The environment was Xcode 26.5 (17F42), iOS 26.5 simulator (23F77), arm64,
iPhone Air. All 12 fixtures passed the validation contract.

The original downloaded `result.json` SHA256 is
`a3756c52f7d5f7be84e2a501436a4ab6f1cf8926ccc7779ee8cdd311d918c4e4`.
A JSON-reformatted, bit-pattern-validated copy of all numerical results is kept
in `Scripts/tests/fixtures/healthkit_boundary_ios26_5.json`. The recorded fixture
test checks that this evidence is preserved; it is not a substitute for a new
native run on a different runtime.

| Check | Native result |
| --- | --- |
| 100 mg/dL versus cross-unit target | Quantity comparison: equal |
| Target converted by HealthKit to mg/dL | 100.00000000000001 |
| Converted scalar comparison, 100 < target | true |
| 100.nextDown versus cross-unit target | ascending |
| 100.nextUp versus cross-unit target | equal |
| 100.nextUp versus 100 in the same unit | descending |

This is a quantity-comparison discrepancy, not evidence that the existing scalar
conversion should simply round the target to 100. HealthKit's converted scalar
and the Python-style scalar agree exactly for the central fixture, but comparison
of those scalars does not reproduce comparison of the original quantities.
Same-unit and cross-unit neighboring values behave differently, so a generic
epsilon or rounded target is not justified by these results.

Next, expand independent unit/value/order fixtures before selecting a general
quantity-aware Python comparison rule. Preserve raw target units, retain strict
same-unit behavior, and validate any proposed rule against native results rather
than captured dosing outcomes. Then rerun the complete protected replay cohort,
counting both recovered and newly lost commands and downstream history effects.
No replay correction, app change, or clinical claim is made by this probe.

## Independent Quantity Matrix

The workflow now also runs `--matrix`, retaining the original 12-fixture probe.
The new matrix has 3,888 synthetic cases: six glucose-unit encodings, every
ordered unit pair, 12 independent seed values, and nine perturbations per pair.
Perturbations include adjacent representable doubles and ordinary +/-1 mg/dL
controls. No captured outcomes or patient data are used to generate this matrix.

Six development seed values and six different validation seed values are fixed
in source before native execution. These are software-conformance fixtures, not
clinical holdout data. Comparing several rules against the same matrix does not
make their selection an independent validation of physiological predictions.

Each native record retains both comparison directions, self-comparison, both
cross-unit scalar conversions, unit conversion factors, and conversions to four
common units, all with IEEE-754 bit patterns. The validator checks input identity,
coverage, scalar transport and ordinary controls. Cross-unit antisymmetry is
measured rather than assumed. The summary evaluates several predeclared scalar
comparison rules using native outputs; it does not assert those conversions have
already been reproduced in Python. No rule is promoted to replay automatically.

The matrix input, result and summary are included in the existing artifact. Run
all probe checks locally with:

```sh
python -m unittest discover -s Scripts/tests -p 'test_healthkit*.py' -v
```
