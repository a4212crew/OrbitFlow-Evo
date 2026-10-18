"""Offline developer diagnostic for bounded execution logs; never connects.

Example: python scripts/configuration_execution_timings.py LOG [LOG ...] --run-id ID
Only known timing stages/categories, safe identifiers and numeric aggregates are printed. Retain
rotated logs externally if a long run outlives the shared logging retention.
"""
import argparse
from collections import defaultdict
import json
import math
import hashlib
import ipaddress
import re
import sys
from pathlib import Path

STAGES = frozenset('template_stage stage_pre_observation stage_post_observation row_apply connection connection_admission_wait connection_retry_wait shell_setup identification initial_preflight protected_backup_collection protected_backup_write pre_row_observation pre_row_plan pre_row_drift_checks scoped_evidence approved_command mode_recovery_command mode_validation post_row_verification row_verification full_observation interface_collection vlan_config_collection normalized_snapshot snapshot_reuse vlan_lookup configuration_read cli_command save_exchange device_save row_total device_total run_total'.split())
CATEGORIES = frozenset('- session_setup configuration_read vlan_read interface_read mode approved_or_other'.split())
DIMENSIONS = ('run_id', 'device_family', 'management_ip', 'template_id', 'row_id', 'stage_id')
MAX_SAMPLES = 100_000
FAMILIES = frozenset(('C3750X', 'C3850', 'EdgeSwitch'))
TEMPLATES = frozenset(f'{family}.{function}.v2' for family, functions in (
    ('c3750x', ('vlan_database', 'access_port', 'trunk_port', 'interface_description')),
    ('c3850x', ('vlan_database', 'access_port', 'trunk_port', 'interface_description')),
    ('edgeswitch', ('vlan_database', 'vlan_port', 'interface_description')))
    for function in functions)


def _dimension(record, name):
    value = record.get(name, '-')
    if not isinstance(value, str) or value == '-':
        return '-'
    if name == 'stage_id':
        return value if re.fullmatch(r'stage-[1-9][0-9]{0,5}', value) else '-'
    if name == 'device_family':
        return value if value in FAMILIES else '-'
    if name == 'template_id':
        return value if value in TEMPLATES else '-'
    if name == 'management_ip':
        try:
            if '%' in value:  # IPv6 scope labels are arbitrary text, not an address.
                return '-'
            return str(ipaddress.ip_address(value))
        except ValueError:
            return '-'
    # Generated IDs are hex. Custom/legacy identifiers remain correlatable
    # without reflecting arbitrary (possibly secret-bearing) log text.
    if re.fullmatch(r'[a-f0-9]{16,64}', value):
        return value
    if name == 'run_id' and re.fullmatch(r'\d{8}T\d{6}_\d{6}Z_[a-f0-9]{32}', value):
        return value
    return 'sha256:' + hashlib.sha256(value.encode()).hexdigest()[:24]


def _lines(stream):
    """Bound parsing memory even for corrupt or concatenated raw-output lines."""
    while True:
        line = stream.readline(65537)
        if not line:
            return
        if len(line) > 65536:
            while line and not line.endswith('\n'):
                line = stream.readline(65537)
            continue
        yield line


def summarize(paths, run_id=None, *, group_by=(), warnings=None):
    """Exact distributions with a hard 100,000-sample memory bound.

    Each stage/category is independent; no summed parent/child totals. Only
    cli_command/configuration_read counts physical configuration CLI exchanges.
    Missing dimensions stay unknown, never inferred from another row/device.
    """
    if len(set(group_by)) != len(group_by) or any(k not in DIMENSIONS for k in group_by):
        raise ValueError('invalid grouping')
    paths = tuple(Path(path).resolve() for path in paths)
    supplied_paths = set(paths)
    warnings = warnings if warnings is not None else []
    values = defaultdict(list)
    count = 0
    seen_paths = set()
    seen_records = set()
    for path in paths:
        path = Path(path).resolve()
        if path in seen_paths:
            warnings.append('Duplicate input path ignored.')
            continue
        seen_paths.add(path)
        if not path.is_file():
            warnings.append('Requested log missing; results are incomplete.')
            continue
        # Retention is bounded; even all surviving rotations cannot prove that
        # older samples survive. Never present a partial run as complete.
        for sibling in path.parent.glob('execution.log*'):
            if sibling.is_file() and sibling.resolve() not in supplied_paths:
                warnings.append('Retained rotation omitted; results may be incomplete.')
                break
        with path.open(encoding='utf-8') as stream:
            for line in _lines(stream):
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict) or record.get('message') != 'Execution timing':
                        continue
                    if run_id is not None and record.get('run_id') != run_id:
                        continue
                    key = (record.get('stage'), record.get('command_category', '-'))
                    if key[0] not in STAGES or key[1] not in CATEGORIES:
                        continue
                    elapsed = float(record['elapsed_seconds'])
                    if not math.isfinite(elapsed) or elapsed < 0:
                        continue
                except (ValueError, KeyError, TypeError, RecursionError):
                    continue
                count += 1
                if count > MAX_SAMPLES:
                    raise ValueError('timing sample limit exceeded; select fewer logs or a run ID')
                if isinstance(record.get('timestamp'), str):
                    fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).digest()
                    if fingerprint in seen_records:
                        warnings.append('Duplicate timestamped timing record ignored.')
                        continue
                    seen_records.add(fingerprint)
                values[(*key, *(_dimension(record, k) for k in group_by))].append(elapsed)
    result = []
    for key, samples in sorted(values.items()):
        stage, category, *dimensions = key
        samples.sort()
        middle = len(samples) // 2
        median_seconds = samples[middle] if len(samples) % 2 else samples[middle-1] + (samples[middle]-samples[middle-1])/2
        result.append(dict(zip(group_by, dimensions), stage=stage, command_category=category, count=len(samples),
                           min_seconds=samples[0], median_seconds=median_seconds,
                           p95_seconds=samples[math.ceil(len(samples)*.95)-1],
                           max_seconds=samples[-1]))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', nargs='+', help='execution.log and/or retained execution.log.1 through .3')
    parser.add_argument('--run-id', help='exact retained manifest run_id; default all runs in supplied files')
    parser.add_argument('--group-by', nargs='+', choices=DIMENSIONS, default=list(DIMENSIONS[:3]),
                        help='default run_id device_family management_ip; add template_id row_id for row attribution')
    args = parser.parse_args(argv)
    try:
        warnings = []
        result = summarize(args.logs, args.run_id, group_by=args.group_by, warnings=warnings)
    except (OSError, ValueError):
        parser.exit(2, 'Timing extraction failed (unreadable log or sample limit).\n')
    for warning in dict.fromkeys(warnings):
        print('Warning: ' + warning, file=sys.stderr)
    print('Warning: Retention may have removed older samples; completeness is not guaranteed. '
          'Nested stages overlap: compare distributions; do not sum stages. '
          'Physical configuration reads: cli_command / configuration_read only.', file=sys.stderr)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
