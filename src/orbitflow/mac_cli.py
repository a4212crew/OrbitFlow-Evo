"""Read-only MAC lookup using the existing non-secret console profile."""
import argparse
from pathlib import Path
from orbitflow.environment import PROFILE, load_profile, validate_session, validate_paths
from orbitflow.mac_lookup import run_lookup, resolve_target, validate_vlan, export_mac_spool, TargetResolutionError
from orbitflow.capabilities.mac import normalize_mac
from orbitflow.config import ExecutionConfig
from orbitflow.targets import load_targets
from orbitflow.transport import TransportConfig


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    for action in ('search', 'list'):
        sub = actions.add_parser(action)
        sub.add_argument('--profile', type=Path, default=PROFILE)
        sub.add_argument('--devices', type=Path)
        sub.add_argument('--xr-location', default='0/RP0/CPU0')
        sub.add_argument('--confirm', action='store_true', help='Confirm read-only network collection')
        if action == 'search':
            sub.add_argument('--mac', required=True, type=normalize_mac)
            sub.add_argument('--ip', required=True)
        else:
            sub.add_argument('--vlan', required=True, type=validate_vlan)
            sub.add_argument('--concurrency', type=int, choices=range(1, 6), default=1)
            sub.add_argument('--rows', help='Comma-separated one-based workbook device row positions; default all')
    export = actions.add_parser('export')
    export.add_argument('spool', type=Path)
    export.add_argument('output', type=Path)
    export.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.action == 'export':
            result = export_mac_spool(args.spool, args.output, allow_partial=args.allow_partial)
        else:
            settings = load_profile(args.profile)
            targets = load_targets(args.devices or settings['paths']['devices'], isolate_invalid=True)
            if args.action == 'search':
                targets = [resolve_target(targets, args.ip)]
            elif args.rows:
                positions = [int(p) - 1 for p in args.rows.split(',')]
                if len(set(positions)) != len(positions) or any(p < 0 or p >= len(targets) for p in positions):
                    raise ValueError('Invalid target rows')
                targets = [targets[p] for p in sorted(positions)]
            if not args.confirm:
                parser.error('--confirm is required for network collection')
            validate_session(settings)
            validate_paths(settings)
            result = run_lookup(targets, TransportConfig(**settings['teleport']), mac=getattr(args, 'mac', None),
                                vlan=getattr(args, 'vlan', None), xr_location=args.xr_location,
                                inventory_path=settings['paths']['inventory'],
                                execution_config=ExecutionConfig(getattr(args, 'concurrency', 1), **settings['execution']))
        print(result)
        return result
    except TargetResolutionError as error:
        raise SystemExit(str(error)) from None
    except (OSError, ValueError, RuntimeError):
        raise SystemExit('MAC lookup failed. Check profile, input, Teleport session and retained MAC run.') from None


if __name__ == '__main__':
    main()
