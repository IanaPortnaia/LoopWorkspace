from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


FILE = Path(__file__).resolve().parents[1] / 'probe_healthkit_boundary.py'
SPEC = importlib.util.spec_from_file_location('probe_healthkit_boundary', FILE)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def fixture():
    rows = []
    for name, (glucose, unit, target) in probe.FIXTURES.items():
        native_target = target if unit == 'mg/dL' else 100.0
        naive = target if unit == 'mg/dL' else target * (probe.MASS / 10)
        relation = 'ascending' if glucose < native_target else ('descending' if glucose > native_target else 'same')
        row = dict(id=name, glucose_mgdl_input=glucose, glucose_input_bits=probe.bits(glucose),
                   target_unit_input=unit, target_value_input=target, target_input_bits=probe.bits(target),
                   native_compare=relation,
                   native_reverse_compare={'ascending': 'descending', 'same': 'same', 'descending': 'ascending'}[relation],
                   native_self_compare='same', native_target_mgdl=native_target,
                   native_glucose_mgdl=glucose, native_glucose_in_target_unit=glucose,
                   naive_target_mgdl=naive, native_quantity_below_target=relation == 'ascending',
                   native_converted_scalars_below_target=glucose < native_target,
                   naive_scalars_below_target=glucose < naive)
        for field in ('native_target_mgdl', 'native_glucose_mgdl', 'native_glucose_in_target_unit', 'naive_target_mgdl'):
            row[field + '_bits'] = probe.bits(row[field])
        rows.append(row)
    return dict(schema_version=1, fixture_set='synthetic_healthkit_target_boundary_v1', cases=rows,
                molar_mass_input=probe.MASS, molar_mass_bits=probe.bits(probe.MASS), runtime_os='Test runtime')


class HealthKitProbeTests(unittest.TestCase):
    def test_recorded_ios26_5_native_result_retains_quantity_scalar_difference(self):
        path = Path(__file__).with_name('fixtures') / 'healthkit_boundary_ios26_5.json'
        payload = json.loads(path.read_text(encoding='utf-8'))
        row = probe.validate_result(payload)
        self.assertEqual(row['native_compare'], 'same')
        self.assertFalse(row['native_quantity_below_target'])
        self.assertTrue(row['native_converted_scalars_below_target'])
        self.assertEqual(row['native_target_mgdl'], row['naive_target_mgdl'])
        rows = {r['id']: r for r in payload['cases']}
        self.assertEqual(rows['same_next_up']['native_compare'], 'descending')
        self.assertEqual(rows['cross_next_up']['native_compare'], 'same')

    def test_complete_result_and_unmodified_input(self):
        payload = fixture(); before = deepcopy(payload)
        self.assertEqual(probe.validate_result(payload)['id'], 'cross_exact')
        self.assertEqual(payload, before)

    def test_central_native_answer_is_measured_not_forced(self):
        for relation in ('ascending', 'same', 'descending'):
            p = fixture(); row = next(r for r in p['cases'] if r['id'] == 'cross_exact')
            row['native_compare'] = relation
            row['native_reverse_compare'] = {'ascending': 'descending', 'same': 'same', 'descending': 'ascending'}[relation]
            row['native_quantity_below_target'] = relation == 'ascending'
            self.assertEqual(probe.validate_result(p)['native_compare'], relation)

    def test_ordinary_controls_cannot_all_pass_as_equal(self):
        p = fixture(); r = next(r for r in p['cases'] if r['id'] == 'cross_minus_one')
        r.update(native_compare='same', native_reverse_compare='same', native_quantity_below_target=False)
        with self.assertRaisesRegex(ValueError, 'control'): probe.validate_result(p)

    def test_lost_duplicate_or_changed_input_rejected(self):
        for change in ('missing', 'duplicate', 'input', 'mass', 'input_bits'):
            p = fixture()
            if change == 'missing': p['cases'].pop()
            if change == 'duplicate': p['cases'][-1] = p['cases'][0]
            if change == 'input': p['cases'][0]['glucose_mgdl_input'] = 90
            if change == 'mass': p['molar_mass_input'] = 180
            if change == 'input_bits': p['cases'][0]['glucose_input_bits'] = '0'
            with self.subTest(change=change), self.assertRaises(ValueError): probe.validate_result(p)

    def test_scalar_transport_and_boolean_corruption_rejected(self):
        for key, value in (('native_target_mgdl_bits', '0'), ('native_quantity_below_target', True),
                           ('naive_scalars_below_target', True), ('native_target_mgdl', float('inf')),
                           ('native_reverse_compare', 'ascending')):
            p = fixture(); p['cases'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): probe.validate_result(p)

    def test_log_requires_one_complete_result(self):
        text = probe.MARKER + json.dumps(fixture())
        self.assertEqual(len(probe.parse_log('runtime log\n' + text + '\n')['cases']), 12)
        for bad in ('', text + '\n' + text, probe.MARKER + '{}'):
            with self.assertRaises(ValueError): probe.parse_log(bad)

    def test_simulator_prefers_matching_sdk_not_newest_unrelated_runtime(self):
        def device(name, udid, available=True):
            return dict(name=name, udid=udid, isAvailable=available, state='Shutdown')
        data = dict(devices={
            'com.apple.CoreSimulator.SimRuntime.iOS-26-5': [device('iPhone 17', 'match')],
            'com.apple.CoreSimulator.SimRuntime.iOS-27-0': [device('iPhone 18', 'newer')],
            'com.apple.CoreSimulator.SimRuntime.watchOS-26-5': [device('iPhone invalid', 'watch')],
        })
        self.assertEqual(probe.select_simulator(data, '26.5')[1]['udid'], 'match')
        self.assertEqual(probe.select_simulator(data, '26.4')[1]['udid'], 'newer')
        data['devices']['com.apple.CoreSimulator.SimRuntime.iOS-26-5'][0]['isAvailable'] = False
        self.assertEqual(probe.select_simulator(data, '26.5')[1]['udid'], 'newer')
        with self.assertRaises(ValueError): probe.select_simulator(dict(devices={}), '26.5')

    def test_non_macos_host_cannot_claim_native_execution(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(probe.platform, 'system', return_value='Windows'):
            with self.assertRaisesRegex(RuntimeError, 'macOS'): probe.run_probe(Path(folder))

    def test_summary_retains_runtime_and_scope_limit(self):
        content = probe.summary(fixture(), dict(xcode='Xcode Test\nBuild Test',
                                simulator_name='iPhone Test', simulator_runtime='iOS Test'))
        self.assertIn('not the complete Loop dose decision', content)
        self.assertIn('HealthKit quantity comparison blocks', content)
        self.assertIn('Test runtime', content)


if __name__ == '__main__':
    unittest.main()
