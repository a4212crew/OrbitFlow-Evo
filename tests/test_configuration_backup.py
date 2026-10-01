"""Synthetic configuration capture tests; no live devices or production secrets."""
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

from orbitflow import configuration_backup as backup
from orbitflow.capabilities.configuration import ConfigurationService, ConfigurationCaptureError
from orbitflow.config import ExecutionConfig
from orbitflow.vendors.common import DeviceCLI, InteractiveCLITimeout
from orbitflow.vendors.configuration import PROFILES
from test_capability_context import DEVICES
from test_shared_cli import device_session

CONFIG = 'banner motd ^\nUnrecognized command is banner text #\n^\n username synthetic secret fixture-only\n\nend\n'


@pytest.mark.parametrize('device', DEVICES, ids=[d[2] for d in DEVICES])
def test_commands_preservation_and_borrowed_lifecycle(device):
    session, client, channel = device_session(device)
    profile = PROFILES[device[1]]
    channel.outputs[profile.command] = CONFIG
    with session:
        with DeviceCLI(session) as cli:
            result = ConfigurationService().collect(session, SimpleNamespace(platform=device[1]), cli=cli)
            assert result == CONFIG
            assert channel.sent[-2:] == [profile.paging, profile.command]
            assert not channel.close_calls
    assert client.opens == client.closes == channel.close_calls == 1


@pytest.mark.parametrize('response', ['', '% Invalid input detected', '% Authorization failed'])
def test_rejected_and_empty_capture(response):
    session, client, channel = device_session(DEVICES[0])
    channel.outputs['show running-config'] = response
    with session, DeviceCLI(session) as cli:
        with pytest.raises(ConfigurationCaptureError):
            ConfigurationService().collect(session, SimpleNamespace(platform='cisco_ios'), cli=cli)
    assert channel.close_calls == client.closes == 1


def test_split_banner_is_not_a_prompt_and_whitespace_is_preserved():
    session, client, channel = device_session(DEVICES[0])
    channel.outputs['show running-config'] = CONFIG
    with session, DeviceCLI(session) as cli:
        original = channel.sendall
        def split(data):
            original(data)
            if data == b'show running-config\n':
                channel.pending = [b'sw#show running-config\r\n\r\nbanner motd ^\r\ntext #',
                                   b'\r\n^\r\n  trailing spaces  \r\n\r\nend\r\nsw#']
        channel.sendall = split
        assert cli.read_configuration('show running-config') == '\nbanner motd ^\ntext #\n^\n  trailing spaces  \n\nend'


def test_timeout_invalidates_cli_and_cleans_up():
    session, client, channel = device_session(DEVICES[0])
    channel.outputs['show running-config'] = socket.timeout('fixture-only secret')
    with pytest.raises(InteractiveCLITimeout):
        with session, DeviceCLI(session) as cli:
            cli.read_configuration('show running-config')
    assert client.closes == channel.close_calls == 1


def test_filename_collision_dates_and_ignore(tmp_path):
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    first, second = (backup.BackupWriter(tmp_path, now) for _ in range(2))
    assert first.path != second.path
    assert first.path.name.startswith('20261001T')
    paths = [first.write(name, 'cisco_ios', CONFIG) for name in ['A:/?*', 'a:/?*', 'A:/?*']]
    assert len({p.name.casefold() for p in paths}) == 3
    assert all(p.parent == first.path and p.read_text() == CONFIG for p in paths)
    assert first.write('CON', 'cisco_ios', CONFIG).name == '_CON-cisco_ios.txt'
    assert backup.filename_component('...') == 'unknown'
    assert len(backup.filename_component('a' * 300)) <= 90
    assert (first.path / '.gitignore').read_text() == '*\n'
    existing = first.path / 'existing-cisco_ios.txt'
    existing.write_text('original')
    assert first.write('existing', 'cisco_ios', CONFIG).name == 'existing-cisco_ios-2.txt'
    assert existing.read_text() == 'original'


@pytest.mark.parametrize('limit', [1, 3])
def test_batch_failure_isolation_safe_outcomes_and_logs(tmp_path, monkeypatch, limit):
    sessions = [device_session(device) for device in DEVICES]
    for device, (_, _, channel) in zip(DEVICES, sessions):
        channel.outputs[PROFILES[device[1]].command] = CONFIG
    sessions[1][2].outputs['show running-config'] = socket.timeout(CONFIG)
    targets = [dict(management_ip=f'192.0.2.{i+1}', username='fixture-user', password='fixture-password') for i in range(len(sessions))]
    targets += [dict(management_ip='invalid', username='', password='')]
    def connect(ip, credentials, config):
        return sessions[int(ip.rsplit('.', 1)[1]) - 1][0]
    monkeypatch.setattr(backup, 'connect_device', connect)
    real_execute = backup.execute_devices
    outcomes = []
    def execute(*args, on_outcome, **kwargs):
        def record(outcome):
            outcomes.append(outcome)
            on_outcome(outcome)
        return real_execute(*args, on_outcome=record, **kwargs)
    monkeypatch.setattr(backup, 'execute_devices', execute)
    output = StringIO()
    folder = backup.run_backup(targets, object(), backups_dir=tmp_path/'backups',
        inventory_path=tmp_path/'inventory.json', log_root=tmp_path/'logs',
        output=output, execution_config=ExecutionConfig(max_concurrent_devices=limit))
    captures = list(folder.glob('*.txt'))
    assert len(captures) == len(sessions) - 1
    assert all(p.read_text() == CONFIG for p in captures)
    assert all(client.closes == channel.close_calls == 1 for _, client, channel in sessions)
    assert 'failed: 2' in output.getvalue()
    safe = output.getvalue() + repr(outcomes) + ''.join(p.read_text() for p in (tmp_path/'logs').rglob('*.log'))
    for secret in ['fixture-only', 'fixture-password', 'fixture-user', 'banner motd']:
        assert secret not in safe
    assert not list(tmp_path.rglob('results.jsonl'))
    assert all(p.stem.endswith(tuple(PROFILES)) for p in captures)


def test_partial_write_removed(tmp_path, monkeypatch):
    writer = backup.BackupWriter(tmp_path, datetime.now(timezone.utc))
    real_open = Path.open
    class FailingStream:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): self.stream.close()
        def write(self, text):
            self.stream.write(text[:10])
            raise OSError('fixture-only secret')
    def failing_open(path, *args, **kwargs):
        stream = real_open(path, *args, **kwargs)
        return FailingStream(stream) if path.suffix == '.txt' else stream
    monkeypatch.setattr(Path, 'open', failing_open)
    with pytest.raises(OSError): writer.write('sw', 'cisco_ios', CONFIG)
    assert not list(writer.path.glob('*.txt'))


@pytest.mark.parametrize('device', DEVICES, ids=[d[2] for d in DEVICES])
@pytest.mark.parametrize('stage', ['setup', 'capture'])
def test_all_platform_rejections(device, stage):
    session, client, channel = device_session(device)
    profile = PROFILES[device[1]]
    with session, DeviceCLI(session) as cli:
        channel.outputs[profile.paging if stage == 'setup' else profile.command] = (
            'Error: Unrecognized command' if device[1] == 'huawei_vrp' else '% Invalid input')
        from orbitflow.vendors.common import InteractiveCLIError
        with pytest.raises((ConfigurationCaptureError, InteractiveCLIError)):
            ConfigurationService().collect(session, SimpleNamespace(platform=device[1]), cli=cli)
    assert client.closes == channel.close_calls == 1


def test_unsupported_and_wrong_session():
    session, _, _ = device_session(DEVICES[0])
    with session, DeviceCLI(session) as cli:
        with pytest.raises(ConfigurationCaptureError):
            ConfigurationService().collect(session, SimpleNamespace(platform='unknown'), cli=cli)
        with pytest.raises(ValueError):
            ConfigurationService().collect(object(), SimpleNamespace(platform='cisco_ios'), cli=cli)


def test_entry_point_uses_shared_excel_loader(tmp_path, monkeypatch):
    from scripts import device_configuration_backup as script
    from openpyxl import Workbook
    path = tmp_path / 'targets.xlsx'
    workbook = Workbook()
    workbook.active.append(['management_ip', 'username', 'password'])
    workbook.active.append(['192.0.2.1', 'fixture-user', 'fixture-password'])
    workbook.active.append(['192.0.2.2', '', ''])
    workbook.save(path)
    captured = {}
    def run(targets, config, **kwargs):
        captured.update(targets=targets, config=config, **kwargs)
        return 'done'
    monkeypatch.setattr(script, 'run_backup', run)
    assert script.main([str(path), '--proxy', 'proxy', '--cluster', 'cluster',
                        '--bastion-host', 'host', '--bastion-user', 'user']) == 'done'
    assert len(captured['targets']) == 2
    assert captured['backups_dir'] == Path('backups')
    assert captured['timeout'] == 60
