"""Disk handoff, bounded retention and recovery without live devices."""
from datetime import datetime, timedelta, timezone
import json
from threading import Barrier, Lock, get_ident
import weakref

import pytest

from orbitflow.config import ExecutionConfig
from orbitflow.execution import DeviceOutcome, execute_devices
from orbitflow.result_spool import ResultSpool, cleanup_stale_runs


def test_1500_targets_five_workers_exactly_once_bounded_results(tmp_path):
    barrier, lock = Barrier(5), Lock()
    live = weakref.WeakSet()
    peak = active = peak_active = 0
    caller = get_ident()
    class Payload(dict):
        __hash__ = object.__hash__
    def worker(index):
        nonlocal peak, active, peak_active
        with lock:
            active += 1
            peak_active = max(peak_active, active)
        try:
            if index < 5:
                barrier.wait(timeout=10)
            if index % 100 == 0:
                raise ValueError('never persist this secret')
            result = Payload(index=index, rows=['x' * 1000] * 10)
            with lock:
                live.add(result)
                peak = max(peak, len(live))
            return result
        finally:
            with lock:
                active -= 1
    spool = ResultSpool.create(tmp_path, 'synthetic', 1500)
    def persist(outcome):
        assert get_ident() == caller
        spool.append(outcome)
    with spool.collection():
        assert execute_devices(range(1500), worker, config=ExecutionConfig(5), on_outcome=persist) == []
    assert peak_active == 5
    assert peak <= 11  # bounded completed/pending futures, not 1,500 payloads
    assert len(live) == 0
    records = list(spool.records())
    assert [r['input_position'] for r in records] == list(range(1, 1501))
    assert spool.manifest['failed_count'] == 15
    assert spool.manifest['completed_count'] == 1500
    assert 'never persist' not in (spool.path / 'results.jsonl').read_text()


def test_retry_and_cleanup_do_not_recollect(tmp_path):
    spool = ResultSpool.create(tmp_path, 'synthetic', 2)
    with spool.collection():
        spool.append(DeviceOutcome(2, {'text': 'token=secret'}))
        spool.append(DeviceOutcome(1, {'text': 'safe'}))
    def fail(run):
        assert next(run.records())['input_position'] == 1
        raise OSError('private exception text')
    with pytest.raises(OSError):
        spool.consume(fail)
    reopened = ResultSpool(spool.path)
    assert reopened.manifest['status'] == 'output_failed'
    assert 'private exception text' not in (spool.path / 'manifest.json').read_text()
    assert 'secret' not in (spool.path / 'results.jsonl').read_text()
    assert reopened.consume(lambda run: sum(1 for _ in run.records())) == 2
    assert not spool.path.exists()


def test_interruption_partial_retry_and_stale_cleanup(tmp_path):
    spool = ResultSpool.create(tmp_path, 'synthetic', 2)
    with pytest.raises(KeyboardInterrupt):
        with spool.collection():
            spool.append(DeviceOutcome(1, 'safe'))
            raise KeyboardInterrupt()
    with (spool.path / 'results.jsonl').open('ab') as stream:
        stream.write(b'{"partial":')
    with pytest.raises(ValueError, match='Incomplete'):
        spool.consume(lambda run: None)
    assert spool.consume(lambda run: len(list(run.records())), allow_partial=True) == 1
    assert spool.path.exists()
    fresh = ResultSpool.create(tmp_path, 'synthetic', 0)
    cutoff = datetime.now(timezone.utc) + timedelta(days=1)
    with fresh.collection():
        assert cleanup_stale_runs(tmp_path, before=cutoff) == [spool.path]
        assert fresh.path.exists()  # even an old timestamp never overrides an active lease
    assert cleanup_stale_runs(tmp_path, before=datetime.now(timezone.utc) - timedelta(days=1)) == []
    assert cleanup_stale_runs(tmp_path, before=cutoff) == [fresh.path]


def test_duplicate_missing_corrupt_and_unrelated_runs(tmp_path):
    spool = ResultSpool.create(tmp_path, 'synthetic', 2)
    with pytest.raises(ValueError, match='Duplicate'):
        with spool.collection():
            spool.append(DeviceOutcome(1, 'a'))
            spool.append(DeviceOutcome(1, 'b'))
    assert len(list(spool.records())) == 1
    with pytest.raises(ValueError, match='Only consumed'):
        spool.remove()
    other = tmp_path / 'unrelated'
    other.mkdir()
    (other / 'keep').write_text('unrelated')
    (spool.path / 'keep').write_text('unexpected')
    assert cleanup_stale_runs(tmp_path, before=datetime.now(timezone.utc) + timedelta(days=1)) == []
    assert (other / 'keep').exists()
    with pytest.raises(ValueError, match='Incomplete target'):
        with ResultSpool.create(tmp_path, 'synthetic', 1).collection():
            pass
    complete = ResultSpool.create(tmp_path, 'synthetic', 1)
    with complete.collection():
        complete.append(DeviceOutcome(1, 'value'))
    (complete.path / 'results.jsonl').write_text('')
    with pytest.raises(ValueError, match='Incomplete persisted'):
        complete.consume(lambda run: list(run.records()))
    assert complete.path.exists()


def test_unique_runs_and_recursive_sanitization(tmp_path):
    clean = lambda value: str(value).replace('runtime-password', '[REDACTED]')
    one = ResultSpool.create(tmp_path, 'synthetic', 1, clean=clean)
    two = ResultSpool.create(tmp_path, 'synthetic', 0)
    assert one.path != two.path
    with one.collection():
        one.append(DeviceOutcome(1, {'nested': [['runtime-password']]}), target='runtime-password')
    assert 'runtime-password' not in (one.path / 'results.jsonl').read_text()
    assert json.loads((one.path / 'manifest.json').read_text())['collection_complete']


def test_stale_handle_cannot_recollect_and_sink_failure_stops_refill(tmp_path):
    spool = ResultSpool.create(tmp_path, 'synthetic', 2)
    stale = ResultSpool(spool.path)
    seen = []
    def worker(target):
        seen.append(target)
        return target
    def fail(outcome):
        spool.append(outcome)
        raise OSError('sink failure')
    with pytest.raises(OSError):
        with spool.collection():
            execute_devices(range(2), worker, config=ExecutionConfig(1), on_outcome=fail)
    assert seen == [0]
    assert len(list(spool.records())) == 1
    with pytest.raises(ValueError, match='cannot be repeated'):
        with stale.collection():
            pass


def test_cleanup_skips_malformed_manifest_and_rejects_naive_cutoff(tmp_path):
    malformed = tmp_path / 'malformed'
    malformed.mkdir()
    (malformed / 'manifest.json').write_text('[]')
    assert cleanup_stale_runs(tmp_path, before=datetime.now(timezone.utc)) == []
    assert malformed.exists()
    with pytest.raises(ValueError, match='timezone-aware'):
        cleanup_stale_runs(tmp_path, before=datetime.now())


def test_retry_cleans_abandoned_reader_index(tmp_path, monkeypatch):
    spool = ResultSpool.create(tmp_path, 'synthetic', 1)
    with spool.collection():
        spool.append(DeviceOutcome(1, 'safe'))
    scratch = spool.path / 'read-abandoned'
    scratch.mkdir()
    (scratch / 'order.sqlite').write_bytes(b'partial index')
    monkeypatch.chdir(tmp_path)
    reopened = ResultSpool(spool.path.name)
    assert reopened.consume(lambda run: len(list(run.records()))) == 1
    assert not spool.path.exists()


@pytest.mark.parametrize('entry,operation', [('results.jsonl', 'unlink'), ('.lock', 'unlink'), ('manifest.json', 'unlink'), ('run', 'rmdir')])
@pytest.mark.parametrize('denials', [2, 4])
def test_completed_cleanup_permission_retry_and_retention(tmp_path, monkeypatch, caplog, entry, operation, denials):
    from pathlib import Path
    import orbitflow.result_spool as module

    spool = ResultSpool.create(tmp_path, 'synthetic', 1)
    with spool.collection():
        spool.append(DeviceOutcome(1, {'value': 'safe'}))
    target = spool.path if entry == 'run' else spool.path / entry
    original = getattr(Path, operation)
    attempts = []
    sleeps = []

    def deny(path, *args, **kwargs):
        if path == target:
            attempts.append(path)
            if len(attempts) <= denials:
                raise PermissionError('secret-bearing filesystem exception')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, operation, deny)
    monkeypatch.setattr(module, 'sleep', sleeps.append)
    output = tmp_path / 'output.txt'
    calls = []

    def consumer(run):
        calls.append(1)
        output.write_text(next(run.records())['payload']['value'])
        return output

    assert spool.consume(consumer) == output
    assert output.read_text() == 'safe'
    assert calls == [1]
    assert len(attempts) == (3 if denials == 2 else 4)
    assert sleeps == ([0.1, 0.2] if denials == 2 else [0.1, 0.2, 0.4])
    assert 'secret-bearing' not in caplog.text
    if denials == 2:
        assert not spool.path.exists()
        assert 'cleanup deferred' not in caplog.text
    else:
        assert 'Successful output remains valid' in caplog.text
        reopened = ResultSpool(spool.path)
        assert reopened.manifest['status'] == 'consumed'
        assert reopened.manifest['cleanup_started'] is True
        with pytest.raises(ValueError, match='cleanup only'):
            reopened.consume(consumer)
        assert calls == [1]
        assert cleanup_stale_runs(tmp_path, before=datetime.now(timezone.utc) + timedelta(days=1)) == [spool.path]
        assert not spool.path.exists()
        assert output.read_text() == 'safe'


def test_cleanup_permission_retention_preserves_unknown_contents_checks(tmp_path, monkeypatch):
    from pathlib import Path
    import orbitflow.result_spool as module

    spool = ResultSpool.create(tmp_path, 'synthetic', 0)
    with spool.collection():
        pass
    original = Path.rmdir
    def deny(path):
        if path == spool.path:
            raise PermissionError('denied')
        return original(path)
    monkeypatch.setattr(Path, 'rmdir', deny)
    monkeypatch.setattr(module, 'sleep', lambda delay: None)
    assert spool.consume(lambda run: 'success') == 'success'
    (spool.path / 'keep').write_text('unrelated')
    with pytest.raises(ValueError, match='unexpected spool contents'):
        ResultSpool(spool.path).remove()
    assert (spool.path / 'keep').read_text() == 'unrelated'

@pytest.mark.parametrize('denials', [1, 3, 4])
def test_manifest_replace_retry_is_only_rename(tmp_path, monkeypatch, denials):
    from pathlib import Path
    import orbitflow.result_spool as module

    spool = ResultSpool.create(tmp_path, 'synthetic', 2)
    replace = Path.replace
    attempts, delays = [], []
    error = PermissionError('private path and password')
    def deny(path, destination):
        state = json.loads(path.read_text())
        if path.name == 'manifest.tmp' and state['completed_count'] == 1 and state['status'] == 'collecting':
            attempts.append(state)
            if len(attempts) <= denials:
                raise error
        return replace(path, destination)
    monkeypatch.setattr(Path, 'replace', deny)
    monkeypatch.setattr(module, 'sleep', delays.append)
    def collect():
        with spool.collection():
            spool.append(DeviceOutcome(1, error_category='InterfaceCapabilityError'))
            spool.append(DeviceOutcome(2, 'ok'))
    if denials == 4:
        with pytest.raises(PermissionError) as caught:
            collect()
        assert caught.value is error
    else:
        collect()
    reopened = ResultSpool(spool.path)
    records = list(reopened.records())
    assert [r['input_position'] for r in records] == ([1] if denials == 4 else [1, 2])
    assert reopened.manifest['completed_count'] == len(records)
    assert reopened.manifest['failed_count'] == 1
    assert reopened.manifest['status'] == ('interrupted' if denials == 4 else 'collected')
    assert len(attempts) == min(denials + 1, 4)
    assert delays == [0.1, 0.2, 0.4][:min(denials, 3)]


def test_five_workers_sink_failure_keeps_commit_and_primary_error(tmp_path, monkeypatch):
    from pathlib import Path
    import orbitflow.result_spool as module

    spool = ResultSpool.create(tmp_path, 'synthetic', 30)
    replace = Path.replace
    delays, states, started, delivered = [], [], [], []
    primary, secondary = PermissionError('primary secret'), PermissionError('secondary secret')
    def deny(path, destination):
        state = json.loads(path.read_text())
        if state['completed_count']:
            states.append(state['status'])
            raise secondary if state['status'] == 'interrupted' else primary
        return replace(path, destination)
    monkeypatch.setattr(Path, 'replace', deny)
    monkeypatch.setattr(module, 'sleep', delays.append)
    barrier, lock = Barrier(5), Lock()
    caller = get_ident()
    def worker(value):
        with lock:
            started.append(value)
        barrier.wait(timeout=10)
        raise ValueError('device secret')
    def persist(outcome):
        assert get_ident() == caller
        delivered.append(outcome.position)
        spool.append(outcome)
    with pytest.raises(PermissionError) as caught:
        with spool.collection():
            execute_devices(range(30), worker, config=ExecutionConfig(5, 0, 0), on_outcome=persist)
    assert caught.value is primary
    assert primary.spool_state_error is secondary
    assert sorted(started) == list(range(5))  # No refill after the failed checkpoint.
    assert len(delivered) == 1
    assert states == ['collecting'] * 4 + ['interrupted'] * 4
    assert delays == [0.1, 0.2, 0.4] * 2
    reopened = ResultSpool(spool.path)
    assert reopened.manifest['completed_count'] == 0  # Stale checkpoint is explicit.
    assert reopened.manifest['status'] == 'collecting'
    assert [r['input_position'] for r in reopened.records()] == delivered
    monkeypatch.setattr(Path, 'replace', replace)
    with pytest.raises(ValueError, match='partial'):
        reopened.consume(lambda run: None)
    assert reopened.consume(lambda run: len(list(run.records())), allow_partial=True) == 1
    assert reopened.manifest['completed_count'] == reopened.manifest['failed_count'] == 1
    assert reopened.manifest['status'] == 'partial_consumed'
    assert spool.path.exists()


@pytest.mark.parametrize('status', ['collecting', 'collected', 'consuming', 'consumed', 'output_failed'])
def test_manifest_lifecycle_denial_preserves_error(tmp_path, monkeypatch, status):
    from pathlib import Path
    import orbitflow.result_spool as module

    spool = ResultSpool.create(tmp_path, 'synthetic', 0)
    replace = Path.replace
    attempts = []
    error = PermissionError('sensitive filesystem path')
    original = RuntimeError('consumer secret')
    def deny(path, destination):
        if json.loads(path.read_text())['status'] == status:
            attempts.append(1)
            raise error
        return replace(path, destination)
    monkeypatch.setattr(Path, 'replace', deny)
    monkeypatch.setattr(module, 'sleep', lambda delay: None)
    def fail(run):
        raise original
    with pytest.raises((PermissionError, RuntimeError)) as caught:
        with spool.collection():
            pass
        spool.consume(fail if status == 'output_failed' else lambda run: None)
    assert caught.value is (original if status == 'output_failed' else error)
    assert len(attempts) == 4
    assert spool.path.exists()
    if status in {'collecting', 'collected'}:
        assert ResultSpool(spool.path).manifest['collection_complete'] is False
    if status == 'output_failed':
        assert original.spool_state_error is error


def test_append_cannot_be_retried_after_checkpoint_error(tmp_path, monkeypatch):
    spool = ResultSpool.create(tmp_path, 'synthetic', 1)
    state = spool._state
    with pytest.raises(RuntimeError, match='persistence failure'):
        with spool.collection():
            def fail(status):
                if status == 'collecting':
                    raise PermissionError('private')
                state(status)
            monkeypatch.setattr(spool, '_state', fail)
            with pytest.raises(PermissionError):
                spool.append(DeviceOutcome(1, 'value'))
            with pytest.raises(RuntimeError, match='persistence failure'):
                spool.append(DeviceOutcome(1, 'value'))
    assert len(list(spool.records())) == 1
