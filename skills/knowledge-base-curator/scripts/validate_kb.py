#!/usr/bin/env python3
"""Validate references and package invariants; does not certify business facts."""
import argparse
import json
from pathlib import Path
from kb_common import load, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    try:
        report = validate(load(args.input), args.input.resolve().parent)
    except (OSError, ValueError) as exc:
        report = {'valid': False, 'errors': [str(exc)]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
