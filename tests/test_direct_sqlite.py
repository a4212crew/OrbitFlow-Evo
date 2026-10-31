"""Direct run storage: synthetic evidence only, no network or speed thresholds."""
from contextlib import closing
import json
import logging
import sqlite3
import tracemalloc
from concurrent.futures import ThreadPoolExecutor

import pytest
from orbitflow.execution import DeviceOutcome
from orbitflow.result_spool import ResultSpool


def collect(root, count=3, size=16):
    run = ResultSpool.create(root, 'synthetic', count)
    with run.collection():
        for position in range(count, 0, -1):
            run.append(DeviceOutcome(position, {'evidence': 'x' * size}), target='device')
    return run


def test_direct_order_batch_isolation_and_no_jsonl(tmp_path):
    first, second = collect(tmp_path), collect(tmp_path)
    assert first.path != second.path
    assert not list(tmp_path.rglob('*.jsonl'))
    with first.indexed() as index:
        assert len(index) == 3
        assert [position for position, _ in index.entries()] == [1, 2, 3]
        assert [r['input_position'] for r in index.records()] == [1, 2, 3]
        assert [r['input_position'] for r in index.records(positions=[3, 1])] == [1, 3]
        assert len(list(index.records(target='device'))) == 3
        assert not list(index.records(target='absent'))
        with pytest.raises(ValueError):
            list(index.records(positions=range(257)))
    assert not list(tmp_path.rglob('read-*'))


def test_interruption_and_offline_retry(tmp_path):
    run = ResultSpool.create(tmp_path, 'synthetic', 2)
    with pytest.raises(KeyboardInterrupt), run.collection():
        run.append(DeviceOutcome(1, {'safe': True}))
        raise KeyboardInterrupt
    loaded = ResultSpool(run.path)
    assert loaded.manifest['status'] == 'interrupted'
    assert loaded.manifest['completed_count'] == 1
    with pytest.raises(ValueError, match='Incomplete'):
        loaded.consume(lambda source: None)
    for _ in range(2):
        assert loaded.consume(lambda source: len(list(source.records())), cleanup=False, allow_partial=True) == 1


@pytest.mark.parametrize('fault', ['delete', 'identity', 'status', 'target_column', 'corrupt', 'missing'])
def test_direct_corruption_fails_closed(tmp_path, fault):
    run = collect(tmp_path, 1)
    path = run.path / 'r.db'
    if fault == 'corrupt':
        path.write_bytes(b'invalid database')
    elif fault == 'missing':
        path.unlink()
    else:
        with closing(sqlite3.connect(path)) as db, db:
            if fault == 'delete':
                db.execute('DELETE FROM results')
            elif fault == 'target_column':
                db.execute("UPDATE results SET target='wrong-device'")
            else:
                record = json.loads(db.execute('SELECT record FROM results').fetchone()[0])
                record['run_id' if fault == 'identity' else 'status'] = 'invalid'
                db.execute('UPDATE results SET record=?', (json.dumps(record),))
    with pytest.raises((sqlite3.DatabaseError, ValueError)):
        list(ResultSpool(run.path).records())


def test_single_owner_rejects_worker_writes_and_duplicates(tmp_path):
    run = ResultSpool.create(tmp_path, 'synthetic', 1)
    with run.collection():
        with ThreadPoolExecutor(4) as pool:
            futures = [pool.submit(run.append, DeviceOutcome(1)) for _ in range(4)]
            for future in futures:
                with pytest.raises(RuntimeError, match='owner'):
                    future.result()
        run.append(DeviceOutcome(1))
        with pytest.raises(ValueError, match='Duplicate'):
            run.append(DeviceOutcome(1))
    assert len(list(run.records())) == 1


def test_transaction_rollback_and_manifest_mirror(tmp_path):
    run = collect(tmp_path, 1)
    with closing(sqlite3.connect(run.path / 'r.db')) as db:
        db.execute('BEGIN')
        db.execute('DELETE FROM results')
        db.rollback()
    # A stale public checkpoint must not override committed authoritative metadata.
    mirror = json.loads((run.path / 'manifest.json').read_text())
    mirror['completed_count'] = 0
    (run.path / 'manifest.json').write_text(json.dumps(mirror))
    loaded = ResultSpool(run.path)
    assert loaded.manifest['completed_count'] == 1
    assert len(list(loaded.records())) == 1
    loaded.consume(lambda source: None)
    assert not loaded.path.exists()


def test_stage_success_and_exception_metadata(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger='orbitflow.result_spool')
    run = collect(tmp_path, 1)
    with pytest.raises(RuntimeError), run.timed_stage('evaluation'):
        raise RuntimeError('private response must never be logged')
    assert 'private response' not in caplog.text
    events = [r for r in caplog.records if r.message.startswith('stage_')]
    assert any(r.stage == 'sqlite_insert_commit' for r in events)
    assert [r.completed_count for r in events if r.stage == 'sqlite_insert_commit' and r.message == 'stage_end'] == [1]
    assert any(getattr(r, 'status', None) == 'failure' for r in events)
    assert all(r.run_id == run.manifest['run_id'] for r in events)
    ends = [r for r in events if r.message == 'stage_end']
    assert all(r.started_at <= r.ended_at and r.elapsed_seconds >= 0 for r in ends)



@pytest.mark.scale
@pytest.mark.parametrize('count,size', [(88,875000),(500,65536),(1500,65536)])
def test_direct_scale_has_bounded_python_memory(tmp_path, count, size):
    tracemalloc.start()
    try:
        run = collect(tmp_path, count, size)
        with run.indexed() as index:
            assert len(index) == count
            for position, record in enumerate(index.records(), 1):
                assert record['input_position'] == position
                assert len(record['payload']['evidence']) == size
        assert tracemalloc.get_traced_memory()[1] < 16 * 1024 * 1024
    finally:
        tracemalloc.stop()


def test_direct_journal_shares_run_store_and_concurrent_writer(tmp_path):
    from orbitflow.result_spool import ResultJournal
    run = ResultSpool.create(tmp_path, 'synthetic', 1)
    journal = ResultJournal(run.path / 'events.jsonl')
    with run.collection():
        with ThreadPoolExecutor(4) as pool:
            futures = [pool.submit(journal.append, {'row_id': str(i % 2), 'kind': 'intent', 'number': i}) for i in range(20)]
            run.append(DeviceOutcome(1, {'safe': True}))
            for future in futures:
                future.result()
    assert not (run.path / 'events.jsonl').exists()
    assert len(list(journal.records())) == 20
    with journal.indexed() as index:
        assert len(index) == 20
        assert len(list(index.entries(target='1'))) == 10
        index.set_reference(1, 55)
        assert index.reference(1) == 55
        assert index.reference(99) is None
    # Report-only references must never persist in evidence tables.
    with closing(sqlite3.connect(run.path / 'r.db')) as db:
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='references_map'").fetchall()


def test_timing_clock_and_exception_are_sanitized(tmp_path, monkeypatch):
    import orbitflow.run_timing as timing
    ticks = iter([10.0, 12.5])
    monkeypatch.setattr(timing, 'monotonic', lambda: next(ticks))
    @timing.timed('evaluation')
    def fail(*, log_root):
        raise RuntimeError('private-device-output')
    with pytest.raises(RuntimeError):
        fail(log_root=tmp_path)
    events = [json.loads(line) for path in tmp_path.rglob('*.log') for line in path.read_text().splitlines()]
    assert [r['message'] for r in events] == ['stage_start', 'stage_end']
    assert events[1]['elapsed_seconds'] == '2.5'
    assert events[1]['status'] == 'failure'
    assert events[0]['run_id'] == events[1]['run_id']
    assert 'private-device-output' not in repr(events)
    assert timing.current_run.get() is None


@pytest.mark.parametrize('category', ['disk full', 'permission denied'])
def test_direct_checkpoint_failure_retains_committed_insert(tmp_path, monkeypatch, category):
    run = ResultSpool.create(tmp_path, 'synthetic', 2)
    original = run._connect
    with pytest.raises(sqlite3.OperationalError), run.collection():
        run.append(DeviceOutcome(1, {'committed': True}))
        def failed():
            raise sqlite3.OperationalError(category)
        monkeypatch.setattr(run, '_connect', failed)
        run.append(DeviceOutcome(2, {'must_not_commit': True}))
    monkeypatch.setattr(run, '_connect', original)
    assert [r['input_position'] for r in run.records()] == [1, 2]
    assert ResultSpool(run.path).manifest['completed_count'] == 2
    assert not ResultSpool(run.path).manifest['collection_complete']
    assert run.path.exists()


def test_direct_oversize_and_sanitization(tmp_path, monkeypatch):
    import orbitflow.result_spool as module
    monkeypatch.setattr(module, 'MAX_RECORD_BYTES', 1024)
    run = ResultSpool.create(tmp_path, 'synthetic', 2, clean=lambda value: value.replace('private-fixture', '[redacted]'))
    with pytest.raises(ValueError, match='size limit'), run.collection():
        run.append(DeviceOutcome(1, {'safe': 'private-fixture'}))
        run.append(DeviceOutcome(2, {'too_large': 'x' * 2000}))
    assert 'private-fixture' not in repr(list(run.records()))
    assert b'private-fixture' not in (run.path / 'r.db').read_bytes()
    assert len(list(run.records())) == 1


def test_process_crash_rolls_back_uncommitted_event(tmp_path):
    import subprocess
    import sys
    run = collect(tmp_path, 1)
    code = "import os,sqlite3,sys; db=sqlite3.connect(sys.argv[1]); db.execute('BEGIN IMMEDIATE'); db.execute(\"INSERT INTO events(target,record) VALUES ('crash','{}')\"); os._exit(7)"
    result = subprocess.run([sys.executable, '-c', code, str(run.path / 'r.db')], check=False)
    assert result.returncode == 7
    from orbitflow.result_spool import ResultJournal
    assert list(ResultJournal(run.path / 'events.jsonl').records()) == []
    assert len(list(run.records())) == 1


def test_insert_disk_full_rolls_back_and_preserves_prior_result(tmp_path):
    run = ResultSpool.create(tmp_path, 'synthetic', 2)
    class DiskFull:
        def __init__(self, db):
            self.db = db
        def __enter__(self):
            self.db.__enter__()
            return self
        def __exit__(self, *args):
            return self.db.__exit__(*args)
        def execute(self, *args):
            raise sqlite3.OperationalError('database or disk is full')
    with pytest.raises(sqlite3.OperationalError), run.collection():
        run.append(DeviceOutcome(1))
        run._writer = DiskFull(run._writer)
        run.append(DeviceOutcome(2))
    assert [r['input_position'] for r in run.records()] == [1]
    assert ResultSpool(run.path).manifest['status'] == 'interrupted'


def test_missing_direct_database_never_falls_back_to_empty_legacy_journal(tmp_path):
    from orbitflow.result_spool import ResultJournal
    run = collect(tmp_path, 1)
    (run.path / 'r.db').unlink()
    with pytest.raises(ValueError, match='Missing run database'):
        ResultJournal(run.path / 'events.jsonl')


@pytest.mark.parametrize('short_name', [False, True])
def test_total_and_store_share_one_run_identity(tmp_path, short_name):
    from orbitflow.run_timing import timed, current_run
    @timed('total')
    def workflow(*, log_root):
        run = ResultSpool.create(tmp_path / 'runs', 'synthetic', 0, short_name=short_name)
        if not short_name:
            assert run.manifest['run_id'] == current_run.get()
        run.operation_id = current_run.get()
        with run.collection():
            pass
        return run
    run = workflow(log_root=tmp_path / 'logs')
    logs = [json.loads(line) for p in (tmp_path / 'logs').rglob('*.log') for line in p.read_text().splitlines()]
    assert {entry['run_id'] for entry in logs} == {run.operation_id}
    assert {entry['evidence_run_id'] for entry in logs if 'evidence_run_id' in entry} == {run.manifest['run_id']}


def test_short_database_preserves_legacy_windows_path_budget(tmp_path):
    from orbitflow.run_timing import new_run_id
    root_length = 242 - len(new_run_id()) - 1
    root = tmp_path / 'long'
    while len(str(root)) + 33 < root_length:
        root = root / ('segment_' + 'x' * 24)
    remaining = root_length - len(str(root)) - 1
    if remaining > 0:
        root = root / ('z' * remaining)
    run = collect(root, 1)
    assert len(str(run.path)) <= 242
    assert len('r.db-journal') <= len('manifest.json')
    assert next(run.records())['input_position'] == 1
    run.consume(lambda source: None)
    assert not run.path.exists()


def test_prior_direct_database_basename_remains_readable(tmp_path):
    from orbitflow.result_spool import ResultJournal
    run = collect(tmp_path, 1)
    run.database_path.replace(run.path / 'results.sqlite')
    historical = ResultSpool(run.path)
    assert len(list(historical.records())) == 1
    assert list(ResultJournal(run.path / 'events.jsonl').records()) == []
    historical.consume(lambda source: None)
    assert not historical.path.exists()


def test_two_authoritative_database_names_fail_closed(tmp_path):
    import shutil
    run = collect(tmp_path, 1)
    shutil.copy2(run.database_path, run.path / 'results.sqlite')
    with pytest.raises(ValueError, match='Ambiguous'):
        ResultSpool(run.path)


def test_script_timing_identifies_entrypoint_without_private_parent(tmp_path):
    from orbitflow.run_timing import timed
    namespace = {'__name__': '__main__', '__file__': '/private-parent/synthetic_cli.py', '__spec__': None}
    exec('def main(*, log_root): return 1', namespace)
    assert timed('total')(namespace['main'])(log_root=tmp_path) == 1
    events = [json.loads(line) for p in tmp_path.rglob('*.log') for line in p.read_text().splitlines()]
    assert {event['workflow'] for event in events} == {'synthetic_cli'}
    assert 'private-parent' not in repr(events)


def test_shared_execution_api_correlates_all_workers(tmp_path):
    from orbitflow.execution import execute_devices
    from orbitflow.config import ExecutionConfig
    from orbitflow.logging import module_logger
    with module_logger('fixture', log_root=tmp_path) as _:
        outcomes = execute_devices([1, 2, 3], lambda target: target, config=ExecutionConfig(2, 0, 0))
    assert [outcome.value for outcome in outcomes] == [1, 2, 3]
    events = [json.loads(line) for p in tmp_path.rglob('*.log') for line in p.read_text().splitlines()]
    assert len({event['run_id'] for event in events}) == 1
    assert any(event['stage'] == 'device_execution_total' for event in events)
    assert sum(event['message'] == 'stage_end' and event['stage'] == 'device_processing_total' for event in events) == 3


def test_execution_preparation_api_times_early_gate_failure(tmp_path, monkeypatch):
    from test_configuration_execution import make_plan
    from orbitflow.configuration.execution import ExecutionService
    from orbitflow.configuration.plans import PlanError
    from orbitflow.logging import module_logger
    import orbitflow.configuration.execution as execution
    _, _, original = make_plan()
    monkeypatch.setattr(execution, 'connect_device', lambda *a, **k: pytest.fail('network forbidden'))
    with module_logger('fixture', log_root=tmp_path / 'logs') as _:
        with pytest.raises(PlanError):
            ExecutionService(tmp_path / 'authority').prepare(original, {}, expected_digest='0' * 64)
    events = [json.loads(line) for p in (tmp_path / 'logs').rglob('*.log') for line in p.read_text().splitlines()]
    assert any(event['stage'] == 'execution_prepare' and event['message'] == 'stage_end' and event['status'] == 'failure' for event in events)


def test_direct_journal_target_index_tamper_fails_closed(tmp_path):
    from orbitflow.result_spool import ResultJournal
    run = collect(tmp_path, 1)
    journal = ResultJournal(run.path / 'events.jsonl')
    journal.append({'row_id': 'original', 'kind': 'intent'})
    with closing(sqlite3.connect(run.database_path)) as db, db:
        db.execute("UPDATE events SET target='wrong-row'")
    with pytest.raises(ValueError, match='target identity'):
        list(journal.records())


def test_direct_cleanup_marker_reopens_after_database_removal(tmp_path, monkeypatch):
    import orbitflow.result_spool as module
    from pathlib import Path
    from orbitflow.logging import module_logger
    with module_logger('fixture', log_root=tmp_path / 'logs') as _:
        run = collect(tmp_path / 'runs', 1)
        rmdir = Path.rmdir
        def denied(path):
            if path == run.path:
                raise PermissionError('held synthetic directory')
            return rmdir(path)
        with monkeypatch.context() as patch:
            patch.setattr(Path, 'rmdir', denied)
            patch.setattr(module, 'sleep', lambda delay: None)
            run.consume(lambda source: None)
        assert run.path.exists()
        assert not (run.path / 'r.db').exists()
        reopened = ResultSpool(run.path)
        assert reopened.manifest['cleanup_started']
        with pytest.raises(ValueError, match='cleanup only'):
            list(reopened.records())
        assert reopened.remove()
        assert not run.path.exists()
