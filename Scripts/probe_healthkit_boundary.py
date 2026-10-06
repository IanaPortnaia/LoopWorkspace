#!/usr/bin/env python3
"""Run a standalone Swift/HealthKit numerical probe inside an iOS simulator."""

import argparse
import json
import math
import os
from pathlib import Path
import platform
import re
import struct
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MARKER = 'HEALTHKIT_BOUNDARY_PROBE_JSON='
MMOL = 'mmol<180.1558800000541>/L'
MASS = 180.1558800000541
TARGET = 5.55074860726
FIXTURES = {
    'same_exact': (100.0, 'mg/dL', 100.0),
    'same_minus_one': (99.0, 'mg/dL', 100.0),
    'same_plus_one': (101.0, 'mg/dL', 100.0),
    'same_next_down': (math.nextafter(100.0, -math.inf), 'mg/dL', 100.0),
    'same_next_up': (math.nextafter(100.0, math.inf), 'mg/dL', 100.0),
    'cross_exact': (100.0, MMOL, TARGET),
    'cross_minus_one': (99.0, MMOL, TARGET),
    'cross_plus_one': (101.0, MMOL, TARGET),
    'cross_next_down': (math.nextafter(100.0, -math.inf), MMOL, TARGET),
    'cross_next_up': (math.nextafter(100.0, math.inf), MMOL, TARGET),
    'cross_target_next_down': (100.0, MMOL, math.nextafter(TARGET, -math.inf)),
    'cross_target_next_up': (100.0, MMOL, math.nextafter(TARGET, math.inf)),
}


def bits(value):
    return format(struct.unpack('>Q', struct.pack('>d', value))[0], 'x')


def validate_result(payload):
    if payload.get('schema_version') != 1 or payload.get('fixture_set') != 'synthetic_healthkit_target_boundary_v1':
        raise ValueError('Unexpected native probe schema')
    cases = payload.get('cases', [])
    if len(cases) != len(FIXTURES) or {r['id'] for r in cases} != set(FIXTURES):
        raise ValueError('Missing or duplicate native fixtures')
    if payload['molar_mass_input'] != MASS or payload['molar_mass_bits'] != bits(MASS):
        raise ValueError('Molar mass input differs')
    reverse = {'ascending': 'descending', 'same': 'same', 'descending': 'ascending'}
    controls = {'same_exact': 'same', 'same_minus_one': 'ascending', 'same_plus_one': 'descending',
                'cross_minus_one': 'ascending', 'cross_plus_one': 'descending'}
    for row in cases:
        glucose, unit, target = FIXTURES[row['id']]
        if (row['glucose_mgdl_input'] != glucose or row['glucose_input_bits'] != bits(glucose)
                or row['target_unit_input'] != unit or row['target_value_input'] != target
                or row['target_input_bits'] != bits(target)):
            raise ValueError('Native numerical fixture changed')
        comparison = row['native_compare']
        if (comparison not in reverse or row['native_reverse_compare'] != reverse[comparison]
                or row['native_self_compare'] != 'same'
                or row['native_quantity_below_target'] is not (comparison == 'ascending')):
            raise ValueError('Incoherent native comparison')
        if row['id'] in controls and comparison != controls[row['id']]:
            raise ValueError('Ordinary native control failed')
        for field in ('native_target_mgdl', 'native_glucose_mgdl', 'native_glucose_in_target_unit', 'naive_target_mgdl'):
            if not math.isfinite(row[field]) or bits(row[field]) != row[field + '_bits']:
                raise ValueError('Native scalar changed during JSON transport')
        naive = target if unit == 'mg/dL' else target * (MASS / 10)
        if (row['naive_target_mgdl'] != naive
                or row['naive_scalars_below_target'] is not (glucose < naive)
                or row['native_converted_scalars_below_target'] is not (row['native_glucose_mgdl'] < row['native_target_mgdl'])):
            raise ValueError('Scalar comparison or arithmetic differs')
    # The central boundary result is measured, never forced to the expected fix.
    return next(r for r in cases if r['id'] == 'cross_exact')


def parse_log(content):
    lines = [line[len(MARKER):] for line in content.splitlines() if line.startswith(MARKER)]
    if len(lines) != 1:
        raise ValueError('Require exactly one completed native probe result')
    payload = json.loads(lines[0])
    validate_result(payload)
    return payload


def select_simulator(devices, sdk_version):
    candidates = []
    major_minor = tuple(int(x) for x in sdk_version.split('.')[:2])
    for runtime, entries in devices['devices'].items():
        match = re.search(r'\.iOS-(\d+)-(\d+)(?:-(\d+))?$', runtime)
        if not match:
            continue
        version = tuple(int(x or 0) for x in match.groups())
        for device in entries:
            if device.get('isAvailable') and device['name'].startswith('iPhone'):
                candidates.append((version[:2] == major_minor, version, device['name'], runtime, device))
    if not candidates:
        raise ValueError('No available iPhone simulator; no device fallback permitted')
    _, _, _, runtime, device = max(candidates, key=lambda c: c[:3])
    return runtime, device


def summary(payload, metadata):
    primary = validate_result(payload)
    lines = ['# Native HealthKit Boundary Probe', '',
             'Synthetic numerical fixtures only. No Loop controller changes, HealthStore access, signing or app distribution.', '',
             f"Xcode: {metadata['xcode'].strip().replace(chr(10), '; ')}",
             f"Simulator: {metadata['simulator_name']} / {metadata['simulator_runtime']}",
             f"Reported runtime: {payload['runtime_os']}", '',
             '| Fixture | HealthKit comparison | Native scalar gate | Python-style scalar gate | Native target mg/dL |',
             '| --- | --- | --- | --- | --- |']
    for r in payload['cases']:
        lines.append(f"| {r['id']} | {r['native_compare']} | {r['native_converted_scalars_below_target']} | {r['naive_scalars_below_target']} | {r['native_target_mgdl']!r} |")
    lines += ['', '## Central Boundary', '',
              f"HealthKit quantity comparison blocks the automatic-bolus target gate: **{primary['native_quantity_below_target']}**.",
              f"Python-style scalar comparison blocks it: **{primary['naive_scalars_below_target']}**.", '',
              'This tests the isolated quantity gate on the recorded simulator runtime, not the complete Loop dose decision or clinical outcomes.',
              'Do not replace a comparator or unit conversion until the complete fixture results have been reviewed.']
    return '\n'.join(lines) + '\n'


def run_probe(output):
    if platform.system() != 'Darwin':
        raise RuntimeError('Native execution requires macOS/Xcode; use the dedicated GitHub workflow')
    output.mkdir(parents=True, exist_ok=True)
    counter = 0

    def run(*args, timeout=300):
        nonlocal counter
        counter += 1
        result = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout)
        (output / f'{counter:02d}-{Path(args[0]).name}.log').write_text(result.stdout, encoding='utf-8')
        if result.returncode:
            raise RuntimeError(f'Command failed ({result.returncode}): {args!r}\n{result.stdout}')
        return result.stdout

    xcode = run('xcodebuild', '-version')
    sdk_version = run('xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version').strip()
    sdk = run('xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path').strip()
    runtime, device = select_simulator(json.loads(run('xcrun', 'simctl', 'list', 'devices', 'available', '-j')), sdk_version)
    metadata = dict(xcode=xcode, sdk_version=sdk_version, sdk=sdk, architecture=platform.machine(),
                    simulator_name=device['name'], simulator_runtime=runtime, simulator_udid=device['udid'],
                    git_commit=run('git', 'rev-parse', 'HEAD').strip())
    (output / 'environment.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    if device['state'] != 'Booted':
        run('xcrun', 'simctl', 'boot', device['udid'])
    run('xcrun', 'simctl', 'bootstatus', device['udid'], '-b', timeout=300)
    binary = (output / 'HealthKitBoundaryProbe').resolve()
    run('xcrun', '--sdk', 'iphonesimulator', 'swiftc', '-sdk', sdk,
        '-target', f'{platform.machine()}-apple-ios17.0-simulator', '-Onone',
        '-framework', 'Foundation', '-framework', 'HealthKit',
        str(ROOT / 'Scripts/HealthKitBoundaryProbe.swift'), '-o', str(binary))
    native_log = run('xcrun', 'simctl', 'spawn', device['udid'], str(binary), timeout=120)
    payload = parse_log(native_log)
    (output / 'result.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    report = summary(payload, metadata)
    (output / 'summary.md').write_text(report, encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a', encoding='utf-8') as stream:
            stream.write(report)
    print(report, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/healthkit-boundary-probe')
    args = parser.parse_args()
    run_probe(args.output.resolve())


if __name__ == '__main__':
    main()
