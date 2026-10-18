"""Offline developer diagnostic for bounded execution logs; never connects.

Example: python scripts/configuration_execution_timings.py LOG [LOG ...] --run-id ID
Only known timing stages/categories and numeric aggregates are printed. Retain
rotated logs externally if a long run outlives the shared logging retention.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from statistics import median

STAGES = frozenset('connection connection_admission_wait connection_retry_wait shell_setup identification initial_preflight protected_backup_collection protected_backup_write pre_row_observation pre_row_plan pre_row_drift_checks scoped_evidence approved_command mode_recovery_command mode_validation post_row_verification row_verification full_observation interface_collection vlan_config_collection normalized_snapshot snapshot_reuse vlan_lookup configuration_read cli_command save_exchange device_save row_total device_total run_total'.split())
CATEGORIES = frozenset('- session_setup configuration_read vlan_read interface_read mode approved_or_other'.split())


def summarize(paths, run_id=None):
    """At most 100,000 samples; stage/category groups only, no device text."""
    values = defaultdict(list)
    count = 0
    for path in paths:
        with Path(path).open(encoding='utf-8') as stream:
            for line in stream:
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
                except (ValueError, KeyError, TypeError):
                    continue
                count += 1
                if count > 100_000:
                    raise ValueError('timing sample limit exceeded; select fewer logs or a run ID')
                values[key].append(elapsed)
    result = []
    for (stage, category), samples in sorted(values.items()):
        samples.sort()
        result.append(dict(stage=stage, command_category=category, count=len(samples),
                           min_seconds=samples[0], median_seconds=median(samples),
                           p95_seconds=samples[math.ceil(len(samples)*.95)-1],
                           max_seconds=samples[-1]))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', nargs='+', help='execution.log and/or retained execution.log.1 through .3')
    parser.add_argument('--run-id', help='exact retained manifest run_id; default all runs in supplied files')
    args = parser.parse_args(argv)
    try:
        result = summarize(args.logs, args.run_id)
    except (OSError, ValueError):
        parser.exit(2, 'Timing extraction failed (unreadable log or sample limit).\n')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
