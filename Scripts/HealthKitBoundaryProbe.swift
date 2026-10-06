// Synthetic numerical fixtures only. No HealthStore, Loop controller or patient data.
import Foundation
import HealthKit

#if !targetEnvironment(simulator)
#error("Run this diagnostic only in an iOS simulator")
#endif

func comparisonName(_ result: ComparisonResult) -> String {
    switch result {
    case .orderedAscending: return "ascending"
    case .orderedSame: return "same"
    case .orderedDescending: return "descending"
    }
}

func bits(_ value: Double) -> String {
    return String(value.bitPattern, radix: 16)
}

let mass = 180.1558800000541
let sourceTarget = 5.55074860726
let mgdl = HKUnit(from: "mg/dL")
let mmolUnitString = "mmol<180.1558800000541>/L"
let cases: [(String, Double, String, Double)] = [
    ("same_exact", 100, "mg/dL", 100),
    ("same_minus_one", 99, "mg/dL", 100),
    ("same_plus_one", 101, "mg/dL", 100),
    ("same_next_down", Double(100).nextDown, "mg/dL", 100),
    ("same_next_up", Double(100).nextUp, "mg/dL", 100),
    ("cross_exact", 100, mmolUnitString, sourceTarget),
    ("cross_minus_one", 99, mmolUnitString, sourceTarget),
    ("cross_plus_one", 101, mmolUnitString, sourceTarget),
    ("cross_next_down", Double(100).nextDown, mmolUnitString, sourceTarget),
    ("cross_next_up", Double(100).nextUp, mmolUnitString, sourceTarget),
    ("cross_target_next_down", 100, mmolUnitString, sourceTarget.nextDown),
    ("cross_target_next_up", 100, mmolUnitString, sourceTarget.nextUp),
]

let rows: [[String: Any]] = cases.map { name, glucoseValue, targetUnitString, targetValue in
    let unit = HKUnit(from: targetUnitString)
    let glucose = HKQuantity(unit: mgdl, doubleValue: glucoseValue)
    let target = HKQuantity(unit: unit, doubleValue: targetValue)
    let nativeTarget = target.doubleValue(for: mgdl)
    let nativeGlucose = glucose.doubleValue(for: mgdl)
    let sourceGlucose = glucose.doubleValue(for: unit)
    let naiveTarget = targetUnitString == "mg/dL" ? targetValue : targetValue * (mass / 10)
    return [
        "id": name,
        "glucose_mgdl_input": glucoseValue,
        "glucose_input_bits": bits(glucoseValue),
        "target_unit_input": targetUnitString,
        "target_value_input": targetValue,
        "target_input_bits": bits(targetValue),
        "healthkit_target_unit": unit.unitString,
        "native_compare": comparisonName(glucose.compare(target)),
        "native_reverse_compare": comparisonName(target.compare(glucose)),
        "native_self_compare": comparisonName(target.compare(target)),
        "native_target_mgdl": nativeTarget,
        "native_target_mgdl_bits": bits(nativeTarget),
        "native_glucose_mgdl": nativeGlucose,
        "native_glucose_mgdl_bits": bits(nativeGlucose),
        "native_glucose_in_target_unit": sourceGlucose,
        "native_glucose_in_target_unit_bits": bits(sourceGlucose),
        "naive_target_mgdl": naiveTarget,
        "naive_target_mgdl_bits": bits(naiveTarget),
        "native_quantity_below_target": glucose.compare(target) == .orderedAscending,
        "native_converted_scalars_below_target": nativeGlucose < nativeTarget,
        "naive_scalars_below_target": glucoseValue < naiveTarget,
    ]
}

let output: [String: Any] = [
    "schema_version": 1,
    "fixture_set": "synthetic_healthkit_target_boundary_v1",
    "runtime_os": ProcessInfo.processInfo.operatingSystemVersionString,
    "molar_mass_input": mass,
    "molar_mass_bits": bits(mass),
    "cases": rows,
]
let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
print("HEALTHKIT_BOUNDARY_PROBE_JSON=" + String(decoding: data, as: UTF8.self))
