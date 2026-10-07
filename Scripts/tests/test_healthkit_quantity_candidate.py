import json
import math
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import healthkit_quantity_candidate as candidate
import probe_healthkit_quantity_confirmation as confirmation
import probe_healthkit_quantity_matrix as matrix


class QuantityCandidateTests(unittest.TestCase):
    def test_original_native_fixture_compares_and_converts_exactly(self):
        payload = json.loads((Path(__file__).with_name('fixtures') / 'healthkit_boundary_ios26_5.json').read_text())
        for row in payload['cases']:
            with self.subTest(fixture=row['id']):
                left, right, unit = row['glucose_mgdl_input'], row['target_value_input'], row['target_unit_input']
                self.assertEqual(candidate.compare(left, 'mg/dL', right, unit), row['native_compare'])
                self.assertEqual(candidate.compare(right, unit, left, 'mg/dL'), row['native_reverse_compare'])
                self.assertEqual(matrix.bits(candidate.convert(right, unit, 'mg/dL')), row['native_target_mgdl_bits'])
                self.assertEqual(matrix.bits(candidate.convert(left, 'mg/dL', unit)), row['native_glucose_in_target_unit_bits'])

    def test_conversion_operation_order_is_not_collapsed_to_a_ratio(self):
        value = math.nextafter(math.nextafter(40.0, -math.inf), -math.inf)
        self.assertNotEqual(value * 0.01, candidate.convert(value, 'mg/dL', 'g/L'))
        self.assertEqual(candidate.convert(value, 'mg/dL', 'g/L'), value * 10.0 / 1000.0)

    def test_same_unit_arithmetic_keeps_original_double(self):
        value = math.nextafter(0.4, math.inf)
        self.assertEqual(matrix.bits(candidate.convert(value, 'g/L', 'g/L')), matrix.bits(value))
        self.assertEqual(candidate.compare(value, 'g/L', 0.4, 'g/L'), 'same')
        self.assertEqual(candidate.compare(math.nextafter(100.0, math.inf), 'mg/dL', 100.0, 'mg/dL'), 'descending')

    def test_strict_epsilon_boundary(self):
        e = 2 ** -52
        self.assertEqual(candidate.scalar_compare(e / 2, 0.0), 'same')
        self.assertEqual(candidate.scalar_compare(e, 0.0), 'descending')
        self.assertEqual(candidate.scalar_compare(-e, 0.0), 'ascending')

    def test_opposing_conversion_orders_are_not_arbitrarily_ranked(self):
        left, unit, right = math.nextafter(54.0, -math.inf), 'mmol<180.15588>/L', 2.9974042479213
        self.assertGreater(left, candidate.convert(right, unit, 'mg/dL'))
        self.assertLess(candidate.convert(left, 'mg/dL', unit), right)
        self.assertEqual(candidate.compare(left, 'mg/dL', right, unit), 'same')
        self.assertEqual(candidate.compare(right, unit, left, 'mg/dL'), 'same')

    def test_unsupported_nonfinite_boolean_and_overflow_rejected(self):
        for unit in ('mmol/L', 'unknown', 'mmol<0>/L', 'mmol<.>/L'):
            with self.subTest(unit=unit), self.assertRaises(ValueError):
                candidate.convert(100, unit, unit)
        for value in (math.nan, math.inf, -math.inf, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                candidate.convert(value, 'mg/dL', 'g/L')
        with self.assertRaises(ValueError):
            candidate.convert(sys.float_info.max, 'kg/L', 'mg/dL')

    def test_confirmation_is_disjoint_and_contains_absolute_epsilon_cases(self):
        initial = matrix.fixtures()
        confirm = confirmation.fixtures()
        self.assertEqual(len(confirm), 2928)
        self.assertFalse({r['id'] for r in initial} & {r['id'] for r in confirm})
        self.assertFalse(set(confirmation.SEEDS) & set(sum(matrix.SEEDS.values(), ())))
        self.assertEqual(sum(r['split'] == 'epsilon' for r in confirm), 336)
        self.assertTrue(any(r['right_value'] < 0 for r in confirm))


if __name__ == '__main__':
    unittest.main()
