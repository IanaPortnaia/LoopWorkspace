#!/usr/bin/env python3
"""Compatibility entry point for the current replay overlay safety checks."""
import sys

from replay_export import ROOT, ValidationError, prepare


if __name__ == "__main__":
    try:
        prepare(ROOT)
    except (ValidationError, OSError, ValueError, KeyError) as exc:
        print(f"Replay validation stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
