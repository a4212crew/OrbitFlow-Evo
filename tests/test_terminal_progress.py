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
