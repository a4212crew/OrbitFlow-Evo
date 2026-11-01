"""CLI log-root propagation and nested timing isolation."""
import json
import pytest
from orbitflow import run_timing as timing


@pytest.mark.parametrize('form', ['separate', 'equals', 'process'])
@pytest.mark.parametrize('fails', [False, True])
def test_cli_root_reaches_outer_and_nested_stages(tmp_path, monkeypatch, form, fails):
    root = tmp_path / 'selected'
    argv = ['--log-root', str(root)] if form != 'equals' else ['--log-root=' + str(root)]
    @timing.timed('projection')
    def child():
        if fails:
            raise RuntimeError('private-output')
    @timing.timed('total')
    def main(argv=None):
        child()
    monkeypatch.setattr('sys.argv', ['workflow'] + argv)
    if fails:
        with pytest.raises(RuntimeError):
            main(None if form == 'process' else argv)
    else:
        main(None if form == 'process' else argv)
    events = [json.loads(line) for path in root.rglob('*.log') for line in path.read_text().splitlines()]
    assert [e['stage'] for e in events] == ['total', 'projection', 'projection', 'total']
    assert len({e['run_id'] for e in events}) == 1
    assert all(e['status'] == ('failure' if fails else 'success') for e in events if e['message'] == 'stage_end')
    assert 'private-output' not in repr(events)
    assert timing.current_run.get() is None
    assert timing.current_log_root.get() is None


def test_positional_api_root_and_nested_override(tmp_path):
    @timing.timed('child')
    def child(log_root):
        pass
    @timing.timed('total')
    def parent(log_root):
        child(tmp_path / 'child')
    parent(tmp_path / 'parent')
    assert len(list((tmp_path / 'parent').rglob('*.log'))) == 1
    assert len(list((tmp_path / 'child').rglob('*.log'))) == 1


@pytest.mark.parametrize('script', ['device_interface_vlan_report', 'device_inventory_refresh', 'device_vlan_compliance', 'device_configuration_backup'])
def test_real_cli_input_failure_uses_selected_root(tmp_path, monkeypatch, script):
    import importlib
    module = importlib.import_module('scripts.' + script)
    root = tmp_path / 'logs'
    def fail(*args, **kwargs):
        raise RuntimeError('private-input')
    # Fail before networking, after the real parser has consumed --log-root.
    if hasattr(module, 'load_targets'):
        monkeypatch.setattr(module, 'load_targets', fail)
    else:
        monkeypatch.setattr(module, 'TransportConfig', fail)
    argv = ['missing.xlsx', '--proxy', 'synthetic', '--cluster', 'synthetic',
            '--bastion-host', 'synthetic', '--bastion-user', 'synthetic', '--log-root', str(root)]
    if script == 'device_vlan_compliance':
        argv.insert(0, 'run')
    with pytest.raises((SystemExit, RuntimeError)):
        module.main(argv)
    events = [json.loads(line) for path in root.rglob('*.log') for line in path.read_text().splitlines()]
    totals = [e for e in events if e.get('stage') == 'total']
    assert [e['message'] for e in totals] == ['stage_start', 'stage_end']
    assert totals[-1]['status'] == 'failure'
    assert 'private-input' not in repr(events)
