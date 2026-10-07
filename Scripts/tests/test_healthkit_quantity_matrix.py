from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest


FILE = Path(__file__).resolve().parents[1] / 'probe_healthkit_quantity_matrix.py'
SPEC = importlib.util.spec_from_file_location('matrix_probe', FILE)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def fake_result():
    # Parser controls only; these calculated rows are not native evidence.
    scales = dict(probe.UNITS)
    common_scales = dict(scales, **{'kg/L': 100000.0})
    rows = []
    for source in probe.fixtures():
        row = dict(source)
        left, right = row['left_value'], row['right_value']
        lf, rf = scales[row['left_unit']], scales[row['right_unit']]
        row['native_compare'] = probe.relation(left, right) if lf == rf else probe.relation(left * lf, right * rf)
        row['native_reverse_compare'] = {'ascending': 'descending', 'same': 'same', 'descending': 'ascending'}[row['native_compare']]
        row['native_self_compare'] = 'same'
        row.update(left_in_right=left * (lf / rf), right_in_left=right * (rf / lf),
                   left_to_right_factor=lf / rf, right_to_left_factor=rf / lf)
        for key in ('left_in_right', 'right_in_left', 'left_to_right_factor', 'right_to_left_factor'):
            row[key + '_bits'] = probe.bits(row[key])
        row['common_units'] = []
        for unit in probe.COMMON:
            factor = common_scales[unit]
            data = dict(unit=unit, left=left * (lf / factor), right=right * (rf / factor),
                        left_factor=lf / factor, right_factor=rf / factor)
            for key in ('left', 'right', 'left_factor', 'right_factor'):
                data[key + '_bits'] = probe.bits(data[key])
            row['common_units'].append(data)
        rows.append(row)
    return dict(schema_version=1, fixture_set=probe.NAME, cases=rows)


class QuantityMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = fake_result()

    def test_fixed_independent_coverage(self):
        rows = probe.fixtures()
        self.assertEqual(len(rows), 3888)
        self.assertEqual(len({r['id'] for r in rows}), len(rows))
        self.assertFalse(set(probe.SEEDS['development']) & set(probe.SEEDS['validation']))
        self.assertEqual({r['split'] for r in rows}, set(probe.SEEDS))
        self.assertEqual(len(probe.validate_result(self.payload)), 3888)

    def test_missing_duplicate_or_modified_input_rejected(self):
        for change in ('missing', 'duplicate', 'input', 'bits'):
            p = deepcopy(self.payload)
            if change == 'missing': p['cases'].pop()
            if change == 'duplicate': p['cases'][-1] = p['cases'][0]
            if change == 'input': p['cases'][0]['left_value'] = 42
            if change == 'bits': p['cases'][0]['left_in_right_bits'] = '0'
            with self.subTest(change=change), self.assertRaises(ValueError):
                probe.validate_result(p)

    def test_failed_same_unit_and_ordinary_controls_rejected(self):
        for predicate in (lambda r: r['left_unit'] == r['right_unit'] and r['variant'] == 'left_ulp_0',
                          lambda r: r['variant'] == 'far_-1'):
            p = deepcopy(self.payload)
            row = next(r for r in p['cases'] if predicate(r))
            row['native_compare'] = 'ascending' if row['variant'] == 'left_ulp_0' else 'same'
            with self.assertRaisesRegex(ValueError, 'control'):
                probe.validate_result(p)

    def test_same_unit_neighbor_is_observed_not_assumed_strict(self):
        p = deepcopy(self.payload)
        row = next(r for r in p['cases'] if r['left_unit'] == r['right_unit'] == 'g/L' and r['variant'] == 'left_ulp_1')
        row.update(native_compare='same', native_reverse_compare='same')
        self.assertEqual(len(probe.validate_result(p)), 3888)
        self.assertIn('strict scalar order: 1', probe.summary(p))

    def test_nonfinite_or_changed_common_unit_rejected(self):
        for change in ('nonfinite', 'unit', 'missing'):
            p = deepcopy(self.payload)
            data = p['cases'][0]['common_units']
            if change == 'nonfinite': data[0]['left'] = float('inf')
            if change == 'unit': data[0]['unit'] = 'unsupported'
            if change == 'missing': data.pop()
            with self.subTest(change=change), self.assertRaises(ValueError):
                probe.validate_result(p)

    def test_cross_unit_asymmetry_is_measured_not_rejected(self):
        p = deepcopy(self.payload)
        row = next(r for r in p['cases'] if r['left_unit'] != r['right_unit'] and r['variant'] == 'left_ulp_0')
        row.update(native_compare='ascending', native_reverse_compare='ascending')
        self.assertEqual(len(probe.validate_result(p)), 3888)
        self.assertIn('asymmetries: 1', probe.summary(p))

    def test_summary_does_not_claim_python_parity(self):
        report = probe.summary(self.payload)
        self.assertIn('not a verified Python port', report)
        self.assertIn('Validation disagreements', report)


if __name__ == '__main__':
    unittest.main()
