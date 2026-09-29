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
