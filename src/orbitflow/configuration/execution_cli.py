"""Explicit approved predefined apply, or offline execution-report recovery."""
import argparse
from pathlib import Path
from time import monotonic
from collections import Counter

from orbitflow.progress import Progress, console_progress
from orbitflow.configuration.execution import ApplySettings, ExecutionService, export_results, operator_summary, render_summary
from orbitflow.configuration.v2.planning import load
from orbitflow.configuration.plans import require
from orbitflow.logging import module_logger


def _counts(values):
    return ', '.join(f'{key}={value}' for key, value in sorted(values.items()) if value) or 'none'


def outcome_summary(spool, elapsed, *, skipped=0):
    """Stream actual durable outcomes; verification and save failures remain distinct."""
    devices, rows = Counter(), Counter()
    for record in spool.records():
        payload = record.get('payload') or {}
        statuses = [row.get('status', 'Unknown') for row in payload.get('rows', [])]
        rows.update(statuses)
        save = payload.get('save') or {}
        if 'Unknown' in statuses or save.get('status') == 'Unknown':
            status = 'Unknown'
        elif record['status'] == 'success':
            status = 'Completed'
        elif 'Verified' in statuses:
            status = 'Partial'
        else:
            status = 'Failed'
        devices[status] += 1
    missing = max(0, spool.manifest['target_count'] - sum(devices.values()))
    devices['Unknown'] += missing
    interrupted = not spool.manifest.get('collection_complete', False)
    label = ('Interrupted' if interrupted else 'Unknown' if devices['Unknown'] else
             'Partial' if devices['Partial'] or (devices['Completed'] and devices['Failed']) else
             'Failed' if devices['Failed'] else 'Completed')
    return f'Execution {label} | devices: {_counts(devices)} | rows: {_counts(rows)}; skipped={skipped} | total elapsed: {elapsed:.1f}s'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    report = sub.add_parser('report', help='offline report regeneration; no connection')
    report.add_argument('run_path', type=Path)
    report.add_argument('output', type=Path)
    apply = sub.add_parser('execute', help='prepare summary, then explicitly confirm apply')
    apply.add_argument('plan', type=Path)
    apply.add_argument('workbook', type=Path)
    apply.add_argument('--expected-digest', required=True)
    apply.add_argument('--devices', type=Path, default=Path('devices.xlsx'))
    apply.add_argument('--apply-concurrency', type=int, default=1)
    apply.add_argument('--command-timeout', type=float, default=30.0)
    apply.add_argument('--save-timeout', type=float, default=300.0)
    apply.add_argument('--connection-start-interval', type=float, default=1.0)
    apply.add_argument('--connection-retry-delay', type=float, default=5.0)
    apply.add_argument('--authority-dir', default='data/configuration/execution')
    apply.add_argument('--inventory-path', default='data/inventory/inventory.json')
    apply.add_argument('--run-root', default='outputs/runs/configuration_execution')
    apply.add_argument('--backups-dir', help='Explicit external backup root; default: RUN/backups')
    for name in ('proxy', 'cluster', 'bastion-host', 'bastion-user'):
        apply.add_argument('--' + name, required=True)
    apply.add_argument('--teleport-key-path', type=Path)
    apply.add_argument('--teleport-cert-path', type=Path)
    args = parser.parse_args(argv)
    with module_logger('configuration', 'execution') as (logger, _):
        try:
            if args.command == 'report':
                with Progress(console_progress) as progress:
                    progress.emit('-', 'report_generation')
                    print(export_results(args.run_path, args.output))
                    progress.emit('-', 'report_complete')
                return
            settings = ApplySettings(args.apply_concurrency, args.command_timeout, args.save_timeout,
                                     args.connection_start_interval, args.connection_retry_delay)
            service = ExecutionService(args.authority_dir)
            prepared = service.prepare_workbook(load(args.plan), args.workbook, expected_digest=args.expected_digest, settings=settings)
            print(render_summary(operator_summary(prepared)))
            require(prepared['status'] == 'awaiting_confirmation', 'confirmation already consumed')
            if input('Confirm execution? [y/N]: ').strip().lower() != 'y':
                logger.info('Execution declined')
                print('Execution declined; no device connection.')
                return
            from orbitflow.targets import load_device_credentials
            from orbitflow.transport import TransportConfig
            ips = sorted({entry['request']['inputs']['management_ip'] for entry in prepared['summary']['selected']})
            credentials = load_device_credentials(args.devices, ips) if ips else {}
            transport = TransportConfig(args.proxy, args.cluster, args.bastion_host, args.bastion_user,
                                        teleport_key_path=args.teleport_key_path, teleport_cert_path=args.teleport_cert_path)
            completed_rows, completed_devices = Counter(), Counter()
            def show_progress(event):
                if event['stage'] == 'row_result':
                    completed_rows[event.get('status', 'Unknown')] += 1
                elif event['stage'] == 'device_complete':
                    completed_devices[event.get('status', 'Unknown')] += 1
                console_progress(event)
            started = monotonic()
            try:
                spool = service.confirm(prepared['reference'], summary_digest=prepared['summary_digest'], apply=True,
                                        credentials=credentials, transport_config=transport, inventory_path=args.inventory_path,
                                        run_root=args.run_root, backups_dir=args.backups_dir, progress=show_progress)
            except BaseException:
                completed_devices['Unknown/incomplete'] += max(0, len(ips)-sum(completed_devices.values()))
                completed_rows['Unknown/incomplete'] += max(0, len(prepared['summary']['selected'])-sum(completed_rows.values()))
                print(f'Execution interrupted/failed | devices: {_counts(completed_devices)} | rows: {_counts(completed_rows)}; skipped={len(prepared["summary"]["skipped"])}; see retained run and logs | total elapsed: {monotonic()-started:.1f}s', flush=True)
                raise
            print(outcome_summary(spool, monotonic()-started, skipped=len(prepared['summary']['skipped'])), flush=True)
            with Progress(console_progress) as progress:
                progress.emit('-', 'report_generation')
                print(export_results(spool.path, spool.path / 'execution-results.xlsx'))
                progress.emit('-', 'report_complete')
        except Exception as exc:
            logger.error('Execution command failed', extra={'error_category': type(exc).__name__})
            parser.exit(2, f'Execution failed ({type(exc).__name__}); see configuration module logs.\n')


if __name__ == '__main__':
    main()
