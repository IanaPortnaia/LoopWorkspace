// Public HealthKit API only; synthetic input, no HealthStore or Loop controller.
import Foundation
import HealthKit

#if !targetEnvironment(simulator)
#error("Run this diagnostic only in an iOS simulator")
#endif

func relation(_ result: ComparisonResult) -> String {
    switch result {
    case .orderedAscending: return "ascending"
    case .orderedSame: return "same"
    case .orderedDescending: return "descending"
    }
}

func save(_ value: Double, _ name: String, _ row: inout [String: Any]) {
    row[name] = value
    row[name + "_bits"] = String(value.bitPattern, radix: 16)
}

let input = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
let envelope = try JSONSerialization.jsonObject(with: input) as! [String: Any]
let cases = envelope["cases"] as! [[String: Any]]
let commonUnits = ["mg/dL", "g/L", "kg/L", "mol<180.1558800000541>/L"]
var rows: [[String: Any]] = []
for source in cases {
    // Decimal JSON -> NSNumber parsing can move adjacent doubles by several ULPs.
    // Use the independently checked binary inputs, not a second decimal conversion.
    let leftValue = Double(bitPattern: UInt64(source["left_value_bits"] as! String, radix: 16)!)
    let rightValue = Double(bitPattern: UInt64(source["right_value_bits"] as! String, radix: 16)!)
    let leftUnit = HKUnit(from: source["left_unit"] as! String)
    let rightUnit = HKUnit(from: source["right_unit"] as! String)
    let left = HKQuantity(unit: leftUnit, doubleValue: leftValue)
    let right = HKQuantity(unit: rightUnit, doubleValue: rightValue)
    var row = source
    save(leftValue, "left_value", &row)
    save(rightValue, "right_value", &row)
    row["native_compare"] = relation(left.compare(right))
    row["native_reverse_compare"] = relation(right.compare(left))
    row["native_self_compare"] = relation(left.compare(left))
    save(left.doubleValue(for: rightUnit), "left_in_right", &row)
    save(right.doubleValue(for: leftUnit), "right_in_left", &row)
    let leftOne = HKQuantity(unit: leftUnit, doubleValue: 1)
    let rightOne = HKQuantity(unit: rightUnit, doubleValue: 1)
    save(leftOne.doubleValue(for: rightUnit), "left_to_right_factor", &row)
    save(rightOne.doubleValue(for: leftUnit), "right_to_left_factor", &row)
    var common: [[String: Any]] = []
    for name in commonUnits {
        let unit = HKUnit(from: name)
        var values: [String: Any] = ["unit": name]
        save(left.doubleValue(for: unit), "left", &values)
        save(right.doubleValue(for: unit), "right", &values)
        save(leftOne.doubleValue(for: unit), "left_factor", &values)
        save(rightOne.doubleValue(for: unit), "right_factor", &values)
        common.append(values)
    }
    row["common_units"] = common
    rows.append(row)
}
let output: [String: Any] = [
    "schema_version": 1,
    "fixture_set": envelope["fixture_set"]!,
    "runtime_os": ProcessInfo.processInfo.operatingSystemVersionString,
    "cases": rows,
]
let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
try data.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
print("HEALTHKIT_QUANTITY_MATRIX_COUNT=\(rows.count)")
