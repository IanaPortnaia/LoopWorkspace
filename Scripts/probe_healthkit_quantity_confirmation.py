"""Fresh confirmation fixtures fixed after exploratory matrix, before execution."""

import hashlib
import json
from pathlib import Path

import healthkit_quantity_candidate as candidate
import probe_healthkit_quantity_matrix as matrix


NAME = 'synthetic_healthkit_quantity_confirmation_v1'
SEEDS = (33.125, 47.9, 61.25, 96.875, 127.03125, 167.3, 201.75, 357.125)


def fixtures():
    rows = matrix.fixtures({'confirmation': SEEDS})
    epsilon = 2.0 ** -52
    for unit, _ in matrix.UNITS:
        for raw in (0.0, 2.0 ** -16, 0.25, 0.5, 1.0, 2.0, -0.5):
            for sign in (-1, 1):
                for multiple in (0.5, 1.0, 2.0, 8.0):
                    left = raw + sign * multiple * epsilon
                    rows.append(dict(id=f'epsilon/{unit}/{raw}/{sign}/{multiple}',
                                     split='epsilon', variant='absolute_epsilon',
                                     left_unit=unit, left_value=left, left_value_bits=matrix.bits(left),
                                     right_unit=unit, right_value=raw, right_value_bits=matrix.bits(raw)))
    return rows


def assess(payload, expected_rows=None, fixture_set=NAME):
    rows = matrix.validate_result(payload, fixtures() if expected_rows is None else expected_rows, fixture_set)
    comparisons, conversions = [], []
    for row in rows:
        left, right, lu, ru = row['left_value'], row['right_value'], row['left_unit'], row['right_unit']
        if candidate.compare(left, lu, right, ru) != row['native_compare']:
            comparisons.append((row['id'], 'forward'))
        if candidate.compare(right, ru, left, lu) != row['native_reverse_compare']:
            comparisons.append((row['id'], 'reverse'))
        probes = [('left_in_right', candidate.convert(left, lu, ru), row['left_in_right_bits']),
                  ('right_in_left', candidate.convert(right, ru, lu), row['right_in_left_bits'])]
        for common in row['common_units']:
            probes += [(common['unit'] + '/left', candidate.convert(left, lu, common['unit']), common['left_bits']),
                       (common['unit'] + '/right', candidate.convert(right, ru, common['unit']), common['right_bits'])]
        for name, value, expected_bits in probes:
            if matrix.bits(value) != expected_bits:
                conversions.append((row['id'], name))
    return dict(cases=len(rows), comparison_checks=2 * len(rows), conversion_checks=10 * len(rows),
                comparison_mismatches=comparisons, conversion_mismatches=conversions,
                candidate_sha256=hashlib.sha256(Path(candidate.__file__).read_bytes()).hexdigest(),
                passed=not comparisons and not conversions)


def run_confirmation(output, run, sdk, device_id, architecture):
    envelope = dict(schema_version=1, fixture_set=NAME, cases=fixtures())
    payload = matrix.execute_matrix(output, run, sdk, device_id, architecture, envelope, 'confirmation')
    result = assess(payload)
    development = json.loads((output / 'matrix-result.json').read_text(encoding='utf-8'))
    result['exploratory_matrix'] = assess(development, matrix.fixtures(), matrix.NAME)
    (output / 'confirmation-validation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    report = (f"# Quantity Candidate Confirmation\n\nCases: {result['cases']}; "
              f"comparison mismatches: {len(result['comparison_mismatches'])}; "
              f"conversion mismatches: {len(result['conversion_mismatches'])}.\n\n"
              f"Frozen candidate SHA256: `{result['candidate_sha256']}`.\n\n"
              'This is native software conformance on the recorded runtime, not complete Loop or clinical validation.\n')
    (output / 'confirmation-summary.md').write_text(report, encoding='utf-8')
    if not result['passed'] or not result['exploratory_matrix']['passed']:
        raise ValueError('Quantity candidate fails exact native conformance; retain the failed evidence')
    return report
