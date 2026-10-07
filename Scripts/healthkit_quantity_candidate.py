"""Empirical iOS 26.5 quantity-conformance candidate, not vendor source code.

Do not use this diagnostic module for treatment decisions. Its constants and
arithmetic are frozen before the independent confirmation probe is executed.
"""

import math
import re
import sys


EPSILON = sys.float_info.epsilon


def coefficient(unit):
    """Concentration coefficient in mg/L; preserve operation order."""
    fixed = {'mg/dL': 10.0, 'mg/L': 1.0, 'g/L': 1000.0, 'kg/L': 1000000.0}
    if unit in fixed:
        return fixed[unit]
    match = re.fullmatch(r'(mmol|mol)<([0-9.]+)>/L', unit)
    if not match:
        raise ValueError('Unsupported glucose quantity unit: ' + str(unit))
    mass = float(match.group(2))
    result = mass if match.group(1) == 'mmol' else mass * 1000.0
    if not math.isfinite(result) or result <= 0:
        raise ValueError('Invalid glucose molar mass')
    return result


def finite(value):
    if isinstance(value, bool):
        raise ValueError('Quantity must be a finite number')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Quantity must be a finite number')
    return value


def convert(value, source_unit, target_unit):
    value = finite(value)
    source = coefficient(source_unit)
    target = coefficient(target_unit)
    if source_unit == target_unit:
        return value
    # Combining these two operations into a precomputed ratio changes ULPs.
    return finite((value * source) / target)


def scalar_compare(left, right):
    left, right = finite(left), finite(right)
    delta = left - right
    if abs(delta) < EPSILON:
        return 'same'
    return 'ascending' if left < right else 'descending'


def compare(left, left_unit, right, right_unit):
    left, right = finite(left), finite(right)
    forward = scalar_compare(left, convert(right, right_unit, left_unit))
    reverse = scalar_compare(convert(left, left_unit, right_unit), right)
    return forward if forward == reverse else 'same'
