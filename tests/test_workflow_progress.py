"""Presentation regressions use synthetic results, clocks and terminal sizes."""
import io
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from orbitflow import terminal_progress as terminal
from orbitflow.execution import DeviceOutcome, execute_devices
from orbitflow.config import ExecutionConfig
from orbitflow.result_spool import ResultSpool


class Stream(io.StringIO):
    def isatty(self):
        return True


def test_concurrent_out_of_order_fixed_slots_and_last_ten():
    display = terminal.WorkflowProgress('Collection', total=30, write=lambda _: None)
    display.workers = 3
    display.worker(9, 'connect')
    display.worker(2, 'collect')
    display.worker(7, 'normalize')
    slots = display.slots.copy()
    display.returned(2)
    display.worker(4, 'connect')
    assert display.slots[9] == slots[9] and display.slots[7] == slots[7]
    assert display.slots[4] == slots[2]
    def complete(position):
        display.outcome(position, position % 2 == 0)
        display.outcome(position, False)  # Duplicate must never advance a count.
    with ThreadPoolExecutor(3) as pool:
        list(pool.map(complete, reversed(range(1, 31))))
    assert display.done == 30 and display.success == display.failure == 15
    assert len(display.recent) == 10
    assert all('input' in event for event in display.recent)


def test_redirected_output_is_rate_bounded_and_final_counts_are_truthful():
    now, lines = [0], []
    display = terminal.WorkflowProgress('Processing', total=100, write=lines.append, clock=lambda: now[0])
    display.start()
    for index in range(1, 101):
        display.worker(index, 'connect')
        display.returned(index)
        display.outcome(index)
    assert len(lines) == 1
    now[0] = 5
    display.tick()
    display.finish(True)
    assert len(lines) == 3
    assert 'success=0 failed=0 active=0 unknown=100' in lines[-1]
    assert '100/100' in lines[-1]
    assert '\x1b' not in ''.join(lines)


@pytest.mark.parametrize('columns,lines,platform,environment,full', [
    (120, 30, 'posix', {}, True),
    (120, 30, 'nt', {'WT_SESSION': 'test'}, True),
    (120, 30, 'nt', {}, False),
    (30, 8, 'posix', {}, False),
    (120, 30, 'posix', {'TERM': 'dumb'}, False),
])
def test_portable_frames_and_compact_fallback(monkeypatch, columns, lines, platform, environment, full):
    stream, now = Stream(), [0]
    monkeypatch.setattr(terminal.sys, 'stdout', stream)
    monkeypatch.setattr(terminal.shutil, 'get_terminal_size', lambda _: SimpleNamespace(columns=columns, lines=lines))
    monkeypatch.setattr(terminal, 'os', SimpleNamespace(name=platform, environ=environment))
    display = terminal.WorkflowProgress('Collection', total=4, clock=lambda: now[0])
    display.workers = 2
    display.start()
    display.worker(1, 'connect')
    display.worker(2, 'collect')
    now[0] = 1
    display.tick()
    assert ('Worker 2:' in stream.getvalue()) is full
    assert ('\x1b[' in stream.getvalue()) is full
    if full:
        assert 'Worker 1: input 1 | connect | active' in stream.getvalue()
        assert 'Worker 2: input 2 | collect | active' in stream.getvalue()
    display.finish(False)
    assert stream.getvalue().endswith('\n')
    assert 'unknown=4' in stream.getvalue().splitlines()[-1]


def test_spool_checkpoint_and_export_failure_are_distinct(tmp_path, capsys):
    spool = ResultSpool.create(tmp_path / 'runs', 'synthetic', 2)
    with terminal.workflow_progress('Test') as display:
        with spool.collection():
            spool.append(DeviceOutcome(2), payload={}, failed=True)
            spool.append(DeviceOutcome(1), payload={})
        assert display.done == 2 and display.success == display.failure == 1
        def fail(_):
            raise ValueError('PRIVATE EXCEPTION CONTENTS')
        with pytest.raises(ValueError):
            spool.consume(fail)
    output = capsys.readouterr().out
    assert 'records=2/2; errors=1; report/export pending' in output
    assert 'Export failed/interrupted' in output and str(spool.path) in output
    assert 'PRIVATE' not in output
    assert spool.manifest['status'] == 'output_failed'


def test_partial_export_and_no_file_result(tmp_path, capsys):
    spool = ResultSpool.create(tmp_path / 'runs', 'synthetic', 3)
    with terminal.workflow_progress('Test'):
        with pytest.raises(KeyboardInterrupt):
            with spool.collection():
                spool.append(DeviceOutcome(2), payload={})
                raise KeyboardInterrupt
        spool.consume(lambda _: None, allow_partial=True)
    text = capsys.readouterr().out
    assert 'unknown=2' in text
    assert 'partial_consumed: records=1/3' in text
    assert 'no saved file established' in text
    assert spool.path.exists()


def test_api_keeps_output_ownership_and_cli_retains_saved_path(tmp_path, capsys):
    execute_devices([object()], lambda _: None, config=ExecutionConfig(1))
    assert capsys.readouterr().out == ''
    destination = tmp_path / 'actual.xlsx'
    spool = ResultSpool.create(tmp_path / 'runs', 'synthetic', 0)
    with spool.collection():
        pass
    @terminal.cli_progress('Offline stages')
    def export(argv=None):
        def save(_):
            destination.write_bytes(b'synthetic')
            return destination
        return spool.consume(save)
    assert export([]) == destination
    output = capsys.readouterr().out
    assert str(destination) in output and 'removed after successful export' in output


def test_worker_stage_payload_and_exception_text_never_echo(capsys):
    with terminal.workflow_progress('Collection', total=1):
        def worker(_):
            terminal.worker_stage('SECRET command')
            terminal.worker_stage('collect')
            raise ValueError('SECRET exception')
        outcomes = execute_devices([{'password': 'SECRET'}], worker, config=ExecutionConfig(1))
    assert outcomes[0].error_category == 'ValueError'
    assert 'SECRET' not in capsys.readouterr().out


def test_execution_unknown_waits_for_checkpoint_and_counts_device_once(tmp_path, capsys):
    display = terminal.ExecutionProgress('Confirmed', total=1)
    display.start()
    spool = ResultSpool.create(tmp_path / 'runs', 'synthetic', 1)
    try:
        with spool.collection():
            for stage in ('preflight', 'command_unknown', 'row_result', 'device_complete'):
                display.event(dict(stage=stage, management_ip='192.0.2.1', status='Unknown',
                                   command='PRIVATE COMMAND', hostname='PRIVATE HOST'))
                assert display.dashboard.done == 0
            spool.append(DeviceOutcome(1), target='192.0.2.1', failed=True, payload={})
            assert display.dashboard.done == 1
            assert display.dashboard.success == display.dashboard.failure == 0
        display.event(dict(stage='device_complete', management_ip='192.0.2.1', status='Unknown'))
        assert display.dashboard.done == 1
    finally:
        display.finish(True)
    text = capsys.readouterr().out
    assert 'unknown=1' in text and 'PRIVATE' not in text


def test_broken_presentation_does_not_change_spool_results(tmp_path):
    spool = ResultSpool.create(tmp_path / 'runs', 'synthetic', 1)
    def broken(_):
        raise OSError('PRIVATE stream failure')
    display = terminal.WorkflowProgress('Collection', write=broken)
    token = terminal.current_display.set(display)
    try:
        with spool.collection():
            spool.append(DeviceOutcome(1), payload={})
        assert spool.manifest['collection_complete']
        assert len(list(spool.records())) == 1
    finally:
        terminal.current_display.reset(token)


def test_failed_optional_outcome_subscriber_cannot_poison_committed_append(tmp_path, monkeypatch):
    spool = ResultSpool.create(tmp_path / 'runs', 'synthetic', 1)
    display = terminal.WorkflowProgress('Collection', write=lambda _: None)
    monkeypatch.setattr(display, 'outcome', lambda *a: (_ for _ in ()).throw(ValueError('PRIVATE')))
    token = terminal.current_display.set(display)
    try:
        with spool.collection():
            spool.append(DeviceOutcome(1), payload={})
        assert spool.manifest['collection_complete']
        assert len(list(spool.records())) == 1
    finally:
        terminal.current_display.reset(token)


def test_output_stat_failure_does_not_change_successful_consumption(tmp_path, monkeypatch):
    from pathlib import Path
    spool = ResultSpool.create(tmp_path / 'runs', 'synthetic', 0)
    with spool.collection():
        pass
    destination = tmp_path / 'report.xlsx'
    destination.write_bytes(b'synthetic')
    def denied(_):
        raise PermissionError('PRIVATE')
    monkeypatch.setattr(Path, 'is_file', denied)
    assert spool.consume(lambda _: destination, cleanup=False) == destination
    assert spool.manifest['status'] == 'consumed'
