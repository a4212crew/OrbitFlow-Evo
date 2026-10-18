"""Deterministic rendering tests: no terminals, sleeps or devices required."""
import io
import pytest
from orbitflow.terminal_progress import TerminalProgress


def test_measured_wait_keeps_fraction_and_fallback_is_bounded():
    now, lines = [0], []
    display = TerminalProgress('Processing', write=lines.append, total=4, clock=lambda: now[0])
    display.start()
    for _ in range(100):
        display.update(2, 4)
    assert len(lines) == 1
    now[0] = 12
    display.tick()
    assert lines[-1] == 'Processing [##########----------] 50% (2/4) 12s elapsed'
    now[0] = 24
    display.tick()
    assert '50% (2/4) 24s elapsed' in lines[-1]
    display.finish(False)
    assert '50%' in lines[-1] and 'stopped' in lines[-1]
    display.tick()
    assert len(lines) == 4


@pytest.mark.parametrize('total', [None, 0, -1])
def test_unknown_total_moves_without_percentage(total):
    now, lines = [0], []
    display = TerminalProgress('Preparing execution', write=lines.append, total=total, clock=lambda: now[0])
    display.start()
    now[0] = 12
    display.tick()
    assert lines[0].split(']')[0] != lines[1].split(']')[0]
    assert all('%' not in line for line in lines)
    display.finish(True)
    assert '12s elapsed; phase finished.' in lines[-1]


@pytest.mark.parametrize('tty', [False, True])
def test_real_stream_flush_and_newline_cleanup(monkeypatch, tty):
    class Stream(io.StringIO):
        flushes = 0
        def isatty(self):
            return tty
        def flush(self):
            self.flushes += 1
    stream = Stream()
    monkeypatch.setattr('sys.stdout', stream)
    display = TerminalProgress('Processing', total=2)
    display.start()
    display.update(1, 2)
    display.finish(True)
    value = stream.getvalue()
    assert value.endswith('\n') and stream.flushes >= 2
    assert ('\r' in value) == tty
    assert '50% (1/2)' in value
    assert '100%' not in value  # A normal return cannot invent remaining outcomes.


def test_invalid_counts_and_broken_writer_are_non_authoritative():
    display = TerminalProgress('Processing', total=4, write=lambda _: (_ for _ in ()).throw(ValueError()))
    display.start()
    display.update(9, 4)
    display.update(1, None)
    assert display.done == 0
    display.finish(False)


def test_execution_stages_waits_status_and_payload_suppression():
    from orbitflow.terminal_progress import ExecutionProgress
    from orbitflow.configuration.v2.catalogue import BY_ID
    now, lines = [0], []
    display = ExecutionProgress('Processing', write=lines.append, total=2, clock=lambda: now[0])
    display.start()
    source = next(iter(BY_ID.values())).sheet + ' row 4'
    stages = ['preflight', 'row_preflight', 'backup', 'backup_complete', 'command_intent',
              'verification_intent', 'row_result', 'save_intent', 'save_result', 'device_failure', 'device_complete']
    for stage in stages:
        display.event(dict(stage=stage, management_ip='192.0.2.1', source=source,
                           status='Unknown', command='SECRET', hostname='SECRET', error_category='SECRET',
                           evidence='SECRET', command_index='1', command_total='2'))
    for seconds in (5, 40, 80):
        now[0] = seconds
        display.event(dict(stage='waiting', awaited_stage='row_preflight', management_ip='192.0.2.2',
                           source=source, waiting_seconds=seconds, command='SECRET'))
        display.tick()
    for status in ('Verified', 'Failed', 'Unknown'):
        display.event(dict(stage='row_result', status=status, management_ip='192.0.2.1'))
    display.event(dict(stage='SECRET', status='SECRET', source='SECRET', management_ip='SECRET'))
    display.event(dict(stage='row_result', status='SECRET', source='SECRET', management_ip='SECRET'))
    display.finish(False)
    output = '\n'.join(lines)
    assert 'SECRET' not in output
    assert all(label in output for label in ('Initial preflight', 'Row preflight', 'Backup recorded',
               'Command preparation', 'Verification started', 'Save result', 'Device failure', 'Device completion'))
    assert '80s waiting' in output and '0% (0/2) 80s elapsed' in output
    assert source in output and '192.0.2.2 | Waiting: Row preflight' in output
    for status in ('Verified', 'Failed', 'Unknown'):
        assert 'Row result | status=' + status in output
    assert 'stopped; completion not established' in output


def test_command_preparation_preserves_structured_intent_and_distinct_outcomes():
    from orbitflow.terminal_progress import ExecutionProgress
    from orbitflow.configuration.v2.catalogue import BY_ID
    lines = []
    display = ExecutionProgress('Processing', write=lines.append, clock=lambda: 0)
    source = next(iter(BY_ID.values())).sheet + ' row 4'
    event = dict(stage='command_intent', management_ip='192.0.2.1', source=source,
                 command_index=1, command_total=2)
    original = event.copy()
    display.event(event)
    assert event == original and event['stage'] == 'command_intent'
    assert lines == [f'192.0.2.1 | Command preparation | {source} | command 1/2']
    display.event(dict(stage='command_result', management_ip='192.0.2.1', status='Accepted'))
    display.event(dict(stage='verification_intent', management_ip='192.0.2.1'))
    display.event(dict(stage='row_result', management_ip='192.0.2.1', status='Verified'))
    assert lines[1:] == ['192.0.2.1 | Command result | status=Accepted',
                         '192.0.2.1 | Verification started',
                         '192.0.2.1 | Row result | status=Verified']


def test_execution_concurrent_events_are_complete_and_stop_after_cancellation():
    from concurrent.futures import ThreadPoolExecutor
    from orbitflow.terminal_progress import ExecutionProgress
    lines = []
    display = ExecutionProgress('Processing', write=lines.append, total=2)
    def worker(address):
        for stage in ('preflight', 'command_intent', 'verification_intent', 'row_result', 'device_complete'):
            display.event(dict(stage=stage, management_ip=address, status='Failed'))
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(worker, ['192.0.2.1', '192.0.2.2']))
    for address in ('192.0.2.1', '192.0.2.2'):
        events = [line for line in lines if line.startswith(address)]
        assert len(events) == 5
        assert 'Initial preflight' in events[0] and 'Device completion' in events[-1]
    display.finish(False)
    count = len(lines)
    display.event(dict(stage='preflight', management_ip='192.0.2.1'))
    display.tick()
    assert len(lines) == count


def test_execution_tty_events_flush_and_clear_partial_indicator(monkeypatch):
    from orbitflow.terminal_progress import ExecutionProgress
    class Stream(io.StringIO):
        flushes = 0
        def isatty(self):
            return True
        def flush(self):
            self.flushes += 1
    stream = Stream()
    monkeypatch.setattr('sys.stdout', stream)
    display = ExecutionProgress('Processing', total=2)
    display.start()
    display.event(dict(stage='preflight', management_ip='192.0.2.1'))
    display.finish(False)
    assert '\r192.0.2.1 | Initial preflight\x1b[K\n' in stream.getvalue()
    assert stream.getvalue().endswith('\n') and stream.flushes >= 3
