"""Interactive operator adapter. Run with python -m orbitflow.menu."""
import argparse
from datetime import datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

from orbitflow.environment import PROFILE, PATHS, ROUTING, load_profile, save_profile, validate_session, validate_paths
from orbitflow.config import ExecutionConfig


class Cancelled(Exception):
    """Operator returned without starting a workflow."""


class Console:
    """Injectable terminal navigation over existing single-purpose services."""

    def __init__(self, profile=PROFILE, *, read=input, write=print, session_check=validate_session):
        self.profile = Path(profile)
        self.read, self.write, self.session_check = read, write, session_check

    def ask(self, prompt, default=None):
        value = self.read(prompt).strip()
        if value.casefold() in ('b', 'back', 'cancel'):
            raise Cancelled()
        return value or default or ''

    def concurrency(self):
        while True:
            value = self.ask('Concurrent devices [1-5, default 1]: ', '1')
            if value in ('1', '2', '3', '4', '5'):
                return int(value)
            self.write('Enter a whole integer from 1 to 5.')

    def setup(self):
        try:
            old = load_profile(self.profile)
        except (OSError, ValueError):
            from orbitflow.config import load_execution_config
            # Carry forward legacy pacing, never its stored concurrency.
            legacy = load_execution_config() if not self.profile.exists() else ExecutionConfig()
            old = {'teleport': {}, 'execution': dict(connection_start_interval=legacy.connection_start_interval,
                    connection_retry_delay=legacy.connection_retry_delay), 'paths': PATHS.copy()}
        self.write('Non-secret environment settings only; b cancels without saving.')
        routing = {key: self.ask(f'{key}: ', old['teleport'].get(key)) for key in ROUTING}
        for key in ('teleport_key_path', 'teleport_cert_path'):
            value = self.ask(f'{key} (optional file path): ', old['teleport'].get(key))
            if value:
                routing[key] = value
        execution = {key: float(self.ask(f'{key} [{default}]: ', str(old['execution'].get(key, default))))
                     for key, default in (('connection_start_interval', 1.0), ('connection_retry_delay', 5.0))}
        paths = {key: self.ask(f'{key} [{old["paths"][key]}]: ', old['paths'][key]) for key in PATHS}
        save_profile({'teleport': routing, 'execution': execution, 'paths': paths}, self.profile)
        self.write(f'Environment saved: {self.profile}')

    def settings(self):
        if not self.profile.exists():
            self.setup()
        return load_profile(self.profile)

    def choose_file(self, label, default):
        path = Path(self.ask(f'{label} [{default}] (b cancels): ', str(default)))
        if not path.is_file():
            raise ValueError('Missing input file')
        return path

    def network(self, settings, devices, label):
        from orbitflow.targets import load_targets
        targets = load_targets(devices, isolate_invalid=True)
        limit = self.concurrency()
        self.write(f'{label}; input={devices}; target rows={len(targets)}; concurrency={limit}; inventory={settings["paths"]["inventory"]}')
        if self.ask('Continue network operation? [y/N]: ').lower() != 'y':
            raise Cancelled()
        self.session_check(settings)
        validate_paths(settings)
        from orbitflow.transport import TransportConfig
        return targets, TransportConfig(**settings['teleport']), ExecutionConfig(limit, **settings['execution'])

    def template(self):
        from orbitflow.configuration.v2.workbook import create_input
        root = Path(self.settings()['paths']['templates'])
        root.mkdir(parents=True, exist_ok=True)
        day = datetime.now().strftime('%Y%m%d')
        sequence = 1
        while True:
            path = root / f'config_template_{day}_{sequence:03d}.xlsx'
            lock = path.with_suffix('.lock')
            try:
                with lock.open('xb'):
                    pass
            except FileExistsError:
                sequence += 1
                continue
            try:
                if path.exists():
                    sequence += 1
                    continue
                create_input(path)  # Existing service also opens exclusively.
                break
            finally:
                lock.unlink(missing_ok=True)
        self.write(str(path))

    def planning(self):
        from orbitflow.configuration.v2.workbook import read_input, export_plan
        from orbitflow.configuration.v2.catalogue import BY_ID
        from orbitflow.configuration.v2.planning import plan, save
        settings = self.settings()
        workbook = self.choose_file('Configuration workbook', settings['paths']['templates'])
        requests = read_input(workbook)
        ips = {r['inputs']['management_ip'] for r in requests if BY_ID[r['template_id']].family != 'All'}
        observations = {}
        if ips:
            devices = self.choose_file('Device workbook', settings['paths']['devices'])
            _, transport, execution = self.network(settings, devices, f'Read-only planning; selected targets={len(ips)}; output={settings["paths"]["plans"]}')
            from orbitflow.configuration.v2.observation import collect, bounded_observations
            from orbitflow.targets import load_device_credentials
            spool = collect(requests, load_device_credentials(devices, sorted(ips)), transport,
                            inventory_path=settings['paths']['inventory'], execution_config=execution)
            observations = bounded_observations(spool)
        result = plan(requests, observations, source='workbook-sha256:' + requests.source_digest)
        from orbitflow.configuration.v2.cli import _default_output
        output = _default_output(requests, root=Path(settings['paths']['plans']))
        save(result, output)
        export_plan(result, output.with_suffix('.xlsx'))
        self.write(f'Plan: {output}\nReview: {output.with_suffix(".xlsx")}\nDigest: {result.digest}')

    def execute(self):
        from orbitflow.configuration.execution import ApplySettings, ExecutionService, export_results, operator_summary, render_summary
        from orbitflow.configuration.v2.planning import load
        from orbitflow.targets import load_device_credentials, load_targets
        from orbitflow.transport import TransportConfig
        from orbitflow.progress import console_progress
        settings = self.settings()
        source = self.choose_file('Immutable plan JSON', settings['paths']['plans'])
        workbook = self.choose_file('Engineer-reviewed workbook', source.with_suffix('.xlsx'))
        digest = self.ask('Expected original plan digest: ')
        devices = self.choose_file('Device workbook', settings['paths']['devices'])
        load_targets(devices, isolate_invalid=True)
        self.write('Apply concurrency is separate from read-only execution settings.')
        limit = self.concurrency()
        service = ExecutionService('data/configuration/execution')
        prepared = service.prepare_workbook(load(source), workbook, expected_digest=digest,
                                           settings=ApplySettings(max_concurrent_devices=limit, **settings['execution']))
        self.write(render_summary(operator_summary(prepared)))
        if prepared['status'] != 'awaiting_confirmation':
            raise ValueError('Confirmation already consumed')
        if self.ask('Confirm execution? [y/N]: ').lower() != 'y':
            raise Cancelled()
        self.session_check(settings)
        validate_paths(settings)
        ips = sorted({row['request']['inputs']['management_ip'] for row in prepared['summary']['selected']})
        started = monotonic()
        spool = service.confirm(prepared['reference'], summary_digest=prepared['summary_digest'], apply=True,
                                credentials=load_device_credentials(devices, ips),
                                transport_config=TransportConfig(**settings['teleport']),
                                inventory_path=settings['paths']['inventory'], progress=console_progress)
        from orbitflow.configuration.execution_cli import outcome_summary
        self.write(outcome_summary(spool, monotonic() - started, skipped=len(prepared['summary'].get('skipped', []))))
        destination = self.output(settings['paths']['execution_reports'], 'execution')
        self.write(str(export_results(spool.path, destination)))

    @staticmethod
    def output(root, prefix):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        return root / f'{prefix}_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex}.xlsx'

    def run_workflow(self, kind, methodology=False):
        settings = self.settings()
        devices = self.choose_file('Device workbook', settings['paths']['devices'])
        destinations = {'inventory': 'outputs/reports/inventory', 'report': 'outputs/reports/interface_vlan',
                        'backup': 'outputs/backups/configuration', 'compliance': 'outputs/reports/vlan_compliance'}
        label = f'Read-only {kind}; output={destinations[kind]}'
        if kind == 'backup':
            label += '; sensitive configuration capture: restrict backup file access'
        if kind == 'compliance':
            from orbitflow.vlan_compliance import DEFAULT_POLICY
            label += f'; policy={DEFAULT_POLICY}; methodology={methodology}'
        targets, transport, execution = self.network(settings, devices, label)
        common = dict(inventory_path=settings['paths']['inventory'], execution_config=execution, log_root='outputs/logs')
        if kind == 'inventory':
            from orbitflow.inventory_refresh import refresh_inventory_from_excel
            result = refresh_inventory_from_excel(devices, transport, export_path=self.output('outputs/reports/inventory', 'inventory'),
                                                  spool_root='outputs/runs/inventory_refresh', **common)
        elif kind == 'report':
            from orbitflow.reporting import run_report
            result = run_report(targets, transport, spool_root='outputs/runs/interface_vlan_report', **common)
        elif kind == 'backup':
            from orbitflow.configuration_backup import run_backup
            result = run_backup(targets, transport, **common)
        else:
            from orbitflow.vlan_compliance import run_compliance, DEFAULT_POLICY
            from orbitflow.compliance import JsonPolicyProvider
            result = run_compliance(targets, transport, policy_provider=JsonPolicyProvider(DEFAULT_POLICY),
                                    spool_root='outputs/runs/vlan_compliance', cleanup=False,
                                    methodology_report=methodology, **common)
        # Some service returns contain sensitive records; never print arbitrary results.
        if isinstance(result, (str, Path)):
            self.write(f'Output: {result}')
        self.write('Run ended; review per-device outcomes and retained run logs.')

    def recover(self, kind):
        # Offline paths deliberately do not require a profile or a Teleport session.
        run = Path(self.ask('Retained run directory (b cancels): '))
        if kind == 'execution':
            from orbitflow.configuration.execution import export_results
            exporter = export_results
            root = 'outputs/reports/configuration_execution'
            if self.profile.exists():
                try:
                    root = load_profile(self.profile)['paths']['execution_reports']
                except (OSError, ValueError):
                    pass  # Broken environment must not prevent offline recovery.
            kwargs = {}
        else:
            root = f'outputs/reports/{kind}'
            if kind == 'vlan_compliance':
                from orbitflow.compliance_report import export_compliance_spool
                from orbitflow.methodology_report import export_methodology_spool
                exporter = export_methodology_spool if self.ask('Methodology report? [y/N]: ').lower() == 'y' else export_compliance_spool
            elif kind == 'inventory':
                from orbitflow.inventory_refresh import export_inventory_spool
                exporter = export_inventory_spool
            else:
                from orbitflow.reporting import export_report_spool
                exporter = export_report_spool
            kwargs = {'cleanup': False, 'allow_partial': self.ask('Export partial run? [y/N]: ').lower() == 'y'}
        self.write(str(exporter(run, self.output(root, kind), **kwargs)))

    def review(self):
        root = Path('outputs/reports/configuration_execution')
        if self.profile.exists():
            root = Path(load_profile(self.profile)['paths']['execution_reports'])
        self.write('Execution workbooks (open for complete/partial/Unknown outcomes; no commands are sent):')
        for path in sorted(root.glob('*.xlsx')):
            self.write(str(path))
            from openpyxl import load_workbook
            book = load_workbook(path, read_only=True, data_only=True)
            try:
                for row in book['Run Summary'].iter_rows(values_only=True):
                    if row[0] in ('Run', 'Selected / skipped rows', 'Rows by verification outcome', 'Devices by save outcome'):
                        self.write(f'{row[0]}: {row[1]}')
            finally:
                book.close()

    def submenu(self, title, actions):
        while True:
            self.write(title + '\n' + '\n'.join(f'{i}. {label}' for i, (label, _) in enumerate(actions, 1)) + f'\n{len(actions)+1}. Back')
            choice = self.ask('Selection: ')
            if choice == str(len(actions)+1):
                return
            if choice.isdigit() and 1 <= int(choice) <= len(actions):
                self.safe(actions[int(choice)-1][1])
            else:
                self.write('Invalid selection.')

    def safe(self, action):
        try:
            action()
        except Cancelled:
            self.write('Cancelled.')
        except SystemExit:
            self.write('Workflow ended; inspect its module logs.')
        except Exception:
            self.write('Operation failed. Check profile, input files, module logs and retained runs. For Teleport expiry, run tsh login outside the console.')

    def run(self):
        configuration = [('Generate Input Template', self.template), ('Generate Configuration Plan', self.planning),
                         ('Execute Approved Plan', self.execute), ('Review Executed Plan', self.review),
                         ('Regenerate Execution Report', lambda: self.recover('execution'))]
        compliance = [('Run VLAN Compliance', lambda: self.run_workflow('compliance')),
                      ('Run VLAN Compliance + Methodology Report', lambda: self.run_workflow('compliance', True)),
                      ('Regenerate Previous Report (offline)', lambda: self.recover('vlan_compliance'))]
        def workflow(kind):
            actions = [('Run', lambda: self.run_workflow(kind))]
            if kind != 'backup':
                actions.append(('Regenerate Previous Report (offline)', lambda: self.recover('inventory' if kind == 'inventory' else 'interface_vlan')))
            self.submenu(kind, actions)
        actions = [('Configuration Management', lambda: self.submenu('Configuration Management', configuration)),
                   ('Device Inventory', lambda: workflow('inventory')), ('Interface & VLAN Reporting', lambda: workflow('report')),
                   ('VLAN Compliance', lambda: self.submenu('VLAN Compliance', compliance)),
                   ('Configuration Backup', lambda: workflow('backup')), ('Environment Setting', self.setup)]
        try:
            while True:
                self.write('\n'.join(f'{i}. {label}' for i, (label, _) in enumerate(actions, 1)) + '\n7. Exit')
                choice = self.ask('Selection: ')
                if choice == '7':
                    return
                if choice.isdigit() and 1 <= int(choice) <= 6:
                    self.safe(actions[int(choice)-1][1])
                else:
                    self.write('Invalid selection.')
        except (EOFError, KeyboardInterrupt, Cancelled):
            self.write('Console exited; inspect retained execution runs after an interruption.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, default=PROFILE, help='Non-secret TOML environment profile')
    args = parser.parse_args(argv)
    Console(args.profile).run()


if __name__ == '__main__':
    main()
