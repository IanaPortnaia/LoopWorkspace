"""Independent synthetic quantities; no captured decisions or patient data."""

import json
import math
from pathlib import Path
import struct


NAME = 'synthetic_healthkit_quantity_matrix_v1'
UNITS = (
    ('mg/dL', 1.0), ('g/L', 100.0), ('mg/L', 0.1),
    ('mmol<180.1558800000541>/L', 180.1558800000541 / 10),
    ('mmol<180.15588>/L', 180.15588 / 10),
    ('mol<180.1558800000541>/L', 180.1558800000541 * 100),
)
SEEDS = {'development': (40.0, 54.0, 70.0, 100.0, 180.0, 400.0),
         'validation': (65.0, 83.7, 111.1, 137.0, 225.0, 312.5)}
COMMON = ('mg/dL', 'g/L', 'kg/L', 'mol<180.1558800000541>/L')
RELATIONS = {'ascending', 'same', 'descending'}


def bits(value):
    return format(struct.unpack('>Q', struct.pack('>d', value))[0], 'x')


def relation(left, right):
    return 'ascending' if left < right else ('descending' if left > right else 'same')


def next_float(value, steps):
    for _ in range(abs(steps)):
        value = math.nextafter(value, math.inf if steps > 0 else -math.inf)
    return value


def fixtures():
    rows = []
    for split, seeds in SEEDS.items():
        for seed in seeds:
            for left_unit, left_scale in UNITS:
                for right_unit, right_scale in UNITS:
                    left, right = seed / left_scale, seed / right_scale
                    variants = [(f'left_ulp_{n}', next_float(left, n), right) for n in (-2, -1, 0, 1, 2)]
                    variants += [(f'right_ulp_{n}', left, next_float(right, n)) for n in (-1, 1)]
                    variants += [(f'far_{n}', (seed + n) / left_scale, right) for n in (-1, 1)]
                    for variant, lhs, rhs in variants:
                        rows.append(dict(id=f'{split}/{seed}/{left_unit}/{right_unit}/{variant}',
                                         split=split, seed_mgdl=seed, variant=variant,
                                         left_unit=left_unit, left_value=lhs, left_value_bits=bits(lhs),
                                         right_unit=right_unit, right_value=rhs, right_value_bits=bits(rhs)))
    return rows


def check_number(row, name):
    value = row[name]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or bits(value) != row[name + '_bits']:
        raise ValueError('Invalid or altered native scalar: ' + name)


def validate_result(payload):
    expected = {r['id']: r for r in fixtures()}
    rows = payload.get('cases', [])
    if payload.get('schema_version') != 1 or payload.get('fixture_set') != NAME:
        raise ValueError('Unexpected quantity matrix schema')
    if len(rows) != len(expected) or {r['id'] for r in rows} != set(expected):
        raise ValueError('Missing or duplicated quantity matrix fixtures')
    for row in rows:
        if any(row.get(key) != value for key, value in expected[row['id']].items()):
            raise ValueError('Changed matrix input')
        if row['native_compare'] not in RELATIONS or row['native_reverse_compare'] not in RELATIONS or row['native_self_compare'] != 'same':
            raise ValueError('Invalid native relation')
        # Cross-unit antisymmetry is measured, not assumed.
        if row['left_unit'] == row['right_unit']:
            if row['native_compare'] != relation(row['left_value'], row['right_value']):
                raise ValueError('Same-unit control failed')
        if row['variant'] in ('far_-1', 'far_1'):
            if row['native_compare'] != ('ascending' if row['variant'] == 'far_-1' else 'descending'):
                raise ValueError('Ordinary magnitude control failed')
        for field in ('left_value', 'right_value', 'left_in_right', 'right_in_left', 'left_to_right_factor', 'right_to_left_factor'):
            check_number(row, field)
        common = row['common_units']
        if len(common) != len(COMMON) or [c['unit'] for c in common] != list(COMMON):
            raise ValueError('Changed common units')
        for values in common:
            for field in ('left', 'right', 'left_factor', 'right_factor'):
                check_number(values, field)
    return rows


def summary(payload):
    rows = validate_result(payload)
    reverse = {'ascending': 'descending', 'descending': 'ascending', 'same': 'same'}
    asymmetric = sum(r['native_reverse_compare'] != reverse[r['native_compare']] for r in rows)
    lines = ['# Native Quantity Matrix', '', f'{len(rows)} synthetic cases; reverse-comparison asymmetries: {asymmetric}.',
             'Development and validation seed values were fixed before native execution.', '',
             'The table measures simple candidate rules using native conversion outputs, not a verified Python port.', '',
             '| Rule | Development disagreements | Validation disagreements |', '| --- | ---: | ---: |']
    rules = {
        'Convert left to right unit': lambda r: relation(r['left_in_right'], r['right_value']),
        'Convert right to left unit': lambda r: relation(r['left_value'], r['right_in_left']),
    }
    for i, name in enumerate(COMMON):
        rules['Both to ' + name] = lambda r, i=i: relation(r['common_units'][i]['left'], r['common_units'][i]['right'])
    for name, rule in rules.items():
        counts = [sum(rule(r) != r['native_compare'] for r in rows if r['split'] == split) for split in SEEDS]
        lines.append(f'| {name} | {counts[0]} | {counts[1]} |')
    return '\n'.join(lines) + '\n'


def run_matrix(output, run, sdk, device_id, architecture):
    source = Path(__file__).with_name('HealthKitQuantityMatrix.swift')
    input_path = (output / 'matrix-input.json').resolve()
    result_path = (output / 'matrix-result.json').resolve()
    input_path.write_text(json.dumps(dict(schema_version=1, fixture_set=NAME, cases=fixtures()), indent=2), encoding='utf-8')
    binary = (output / 'HealthKitQuantityMatrix').resolve()
    run('xcrun', '--sdk', 'iphonesimulator', 'swiftc', '-sdk', sdk,
        '-target', f'{architecture}-apple-ios17.0-simulator', '-Onone',
        '-framework', 'Foundation', '-framework', 'HealthKit', str(source), '-o', str(binary))
    log = run('xcrun', 'simctl', 'spawn', device_id, str(binary), str(input_path), str(result_path), timeout=120)
    if log.splitlines().count(f'HEALTHKIT_QUANTITY_MATRIX_COUNT={len(fixtures())}') != 1:
        raise ValueError('Native matrix did not report completion')
    payload = json.loads(result_path.read_text(encoding='utf-8'))
    report = summary(payload)
    (output / 'matrix-summary.md').write_text(report, encoding='utf-8')
    return report
