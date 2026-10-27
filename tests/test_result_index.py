"""Shared indexed retrieval, resource bounds and recovery; synthetic data only."""
import errno
import json
import sqlite3
import tracemalloc

import pytest

from orbitflow.execution import DeviceOutcome
from orbitflow.result_spool import ResultSpool


def collected(root, count=3):
    spool = ResultSpool.create(root, 'synthetic', count)
    with spool.collection():
        for position in range(count, 0, -1):
            spool.append(DeviceOutcome(position, {'value': position}), target=f'192.0.2.{position % 2 + 1}')
    return spool


def test_index_reuses_transaction_for_point_target_and_batch_access(tmp_path):
    spool = collected(tmp_path)
    with spool.indexed() as index:
        assert len(index) == 3
        assert index.get(2)['payload'] == {'value': 2}
        assert [r['input_position'] for r in index.records(target='192.0.2.2')] == [1, 3]
        assert [r['input_position'] for r in index.records(positions=[3, 1, 1])] == [1, 3]
        assert list(index.records(positions=[])) == []
        assert list(index.records(target='absent')) == []
        with pytest.raises(KeyError):
            index.get(4)
        with pytest.raises(ValueError, match='at most 256'):
            list(index.records(positions=range(257)))
        with pytest.raises(ValueError, match='integer'):
            list(index.records(positions=[True]))
        with pytest.raises(ValueError, match='integer'):
            index.get(True)
        # Reject an unbounded iterable without materializing it.
        from itertools import count
        with pytest.raises(ValueError, match='at most 256'):
            list(index.records(positions=count()))
        assert len(list(spool.path.glob('read-*'))) == 1
    assert not list(spool.path.glob('read-*'))
    with pytest.raises(sqlite3.ProgrammingError):
        index.get(1)


@pytest.mark.parametrize('change', ['duplicate', 'position', 'boolean_position', 'status', 'target', 'identity', 'payload', 'json', 'truncated'])
def test_invalid_authoritative_records_fail_closed_and_retain(tmp_path, change):
    spool = collected(tmp_path, 1)
    path = spool.path / 'results.jsonl'
    record = json.loads(path.read_text())
    if change == 'duplicate':
        path.write_text(path.read_text() * 2)
    elif change == 'json':
        path.write_text('invalid\n')
    elif change == 'truncated':
        path.write_text(path.read_text().rstrip('\n'))
    else:
        if change == 'position':
            record['input_position'] = 0
        elif change == 'boolean_position':
            record['input_position'] = True
        elif change == 'status':
            record['status'] = 'complete'
        elif change == 'target':
            record['target'] = []
        elif change == 'identity':
            record['run_id'] = 'other'
        elif change == 'payload':
            del record['payload']
        path.write_text(json.dumps(record) + '\n')
    with pytest.raises(ValueError):
        spool.consume(lambda run: list(run.records()))
    assert spool.path.exists()
    assert spool.manifest['status'] == 'output_failed'
    assert not list(spool.path.glob('read-*'))


@pytest.mark.parametrize('error', [PermissionError(errno.EACCES, 'private path'), OSError(errno.ENOSPC, 'private path')])
def test_index_allocation_failure_retains_canonical_data(tmp_path, monkeypatch, error):
    spool = collected(tmp_path)
    original = (spool.path / 'results.jsonl').read_bytes()
    import orbitflow.result_spool as module
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(module.sqlite3, 'connect', fail)
    with pytest.raises(type(error)):
        spool.consume(lambda run: list(run.records()))
    assert (spool.path / 'results.jsonl').read_bytes() == original
    assert not list(spool.path.glob('read-*'))
    assert spool.manifest['status'] == 'output_failed'


def test_reader_interruption_and_transaction_failure_are_disposable(tmp_path):
    spool = collected(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        with spool.indexed() as index:
            index.db.execute('BEGIN IMMEDIATE')
            index.db.execute('DELETE FROM offsets')
            raise KeyboardInterrupt
    assert not list(spool.path.glob('read-*'))
    for _ in range(2):
        with spool.indexed() as index:
            assert [r['input_position'] for r in index.records()] == [1, 2, 3]


def test_record_and_disk_limits_fail_before_publication(tmp_path, monkeypatch):
    import orbitflow.result_spool as module
    monkeypatch.setattr(module, 'MAX_RECORD_BYTES', 512)
    spool = ResultSpool.create(tmp_path, 'synthetic', 1)
    with pytest.raises(ValueError, match='record size'):
        with spool.collection():
            spool.append(DeviceOutcome(1, 'x' * 1024))
    assert (spool.path / 'results.jsonl').read_bytes() == b''
    assert spool.manifest['status'] == 'interrupted'
    monkeypatch.setattr(module, 'MAX_SPOOL_BYTES', 1)
    with pytest.raises(ValueError, match='Spool size'):
        with ResultSpool.create(tmp_path, 'synthetic', 1).collection() as another:
            another.append(DeviceOutcome(1, 'x'))
    existing = collected(tmp_path, 0)
    (existing.path / 'results.jsonl').write_text('x' * 1024)
    with pytest.raises(ValueError, match='record size'):
        list(existing.records())


def test_binding_precedes_collection_is_immutable_and_sanitized(tmp_path):
    spool = ResultSpool.create(tmp_path, 'synthetic', 0)
    binding = {'workbook_digest': 'a' * 64, 'request_digest': 'b' * 64}
    spool.bind(binding)
    assert ResultSpool(spool.path).manifest['binding'] == binding
    with pytest.raises(ValueError, match='cannot be replaced'):
        spool.bind(binding)
    with spool.collection():
        pass
    with pytest.raises(ValueError, match='precede collection'):
        spool.bind(binding)
    legacy = collected(tmp_path, 0)
    assert 'binding' not in ResultSpool(legacy.path).manifest
    unsafe = ResultSpool.create(tmp_path, 'synthetic', 0)
    with pytest.raises(ValueError, match='Unsafe'):
        unsafe.bind({'password': 'password=synthetic'})
    assert 'binding' not in ResultSpool(unsafe.path).manifest


@pytest.mark.parametrize('count, size', [(88, 875000), (500, 65536), (1500, 65536)])
def test_synthetic_scale_index_peak_memory(tmp_path, count, size, record_property):
    # 88 * 875,000 = 77 MB of sanitized observations, not a private capture.
    tracemalloc.start()
    try:
        spool = ResultSpool.create(tmp_path, 'synthetic', count)
        with spool.collection():
            for position in range(count, 0, -1):
                spool.append(DeviceOutcome(position, {'evidence': 'x' * size}), target=str(position))
        assert (spool.path / 'results.jsonl').stat().st_size >= count * size
        with spool.indexed() as index:
            assert len(index) == count
            for position, record in enumerate(index.records(), 1):
                assert record['input_position'] == position
                assert len(record['payload']['evidence']) == size
            assert len(index.get(count)['payload']['evidence']) == size
        _, peak = tracemalloc.get_traced_memory()
        record_property('peak_python_bytes', peak)
        record_property('targets', count)
        record_property('payload_bytes', count * size)
        assert peak < 16 * 1024 * 1024, (count, peak)
    finally:
        tracemalloc.stop()


def test_planning_binding_is_persisted_before_networking(tmp_path, monkeypatch):
    from orbitflow.configuration.v2 import observation
    from orbitflow.configuration.v2.catalogue import CATALOGUE
    from orbitflow.configuration.v2.planning import request
    from orbitflow.configuration.v2.workbook import WorkbookRequests
    from orbitflow.config import ExecutionConfig
    template = next(t for t in CATALOGUE if t.family == 'C3750X' and t.function == 'Interface Description')
    requests = WorkbookRequests(['Introduction', template.sheet])
    requests.source_digest = 'a' * 64
    requests.append(request(template.id, dict(management_ip='192.0.2.1', interface='GigabitEthernet1/0/1', description='test')))
    observed = []
    def network(*args, **kwargs):
        directories = list((tmp_path / 'runs').iterdir())
        assert len(directories) == 1
        manifest = ResultSpool(directories[0]).manifest
        observed.append(manifest)
        raise AssertionError('synthetic connection failure')
    monkeypatch.setattr(observation, 'connect_device', network)
    from orbitflow.transport import DeviceCredentials
    spool = observation.collect(requests, {'192.0.2.1': DeviceCredentials('engineer', 'synthetic')}, None,
        inventory_path=tmp_path / 'inventory.json', spool_root=tmp_path / 'runs', execution_config=ExecutionConfig(1))
    assert len(observed) == 1
    assert observed[0]['status'] == 'collecting'
    assert observed[0]['binding'] == dict(workbook_digest='a' * 64, request_digest=observation.request_digest(requests))
    assert spool.manifest['failed_count'] == 1
    assert next(spool.records())['payload'] == {'status': 'evidence_unavailable'}
    previous = observation.request_digest(requests)
    from orbitflow.configuration.plans import canonical
    import hashlib
    expected = dict(requests=sorted(requests, key=lambda r: (r['sheet_order'], r['row'])),
                    layout=requests.layout, errors=requests.errors)
    assert previous == hashlib.sha256(canonical(expected).encode()).hexdigest()
    requests.errors.append(dict(sheet=template.sheet, row=4, reason='INVALID_INPUT_ROW'))
    assert observation.request_digest(requests) != previous


def test_consumption_reuses_one_index_across_tables_and_clears_after_failure(tmp_path, monkeypatch):
    import orbitflow.result_spool as module
    spool = collected(tmp_path)
    connect = module.sqlite3.connect
    calls = []
    def counted(*args, **kwargs):
        calls.append(1)
        return connect(*args, **kwargs)
    monkeypatch.setattr(module.sqlite3, 'connect', counted)
    def consumer(run):
        for _ in range(5):
            assert [r['input_position'] for r in run.records()] == [1, 2, 3]
        # Interleaved point reads and iterators each seek their own offset.
        records = run.records()
        assert next(records)['input_position'] == 1
        assert run._reading_index.get(3)['input_position'] == 3
        assert next(records)['input_position'] == 2
        raise RuntimeError('synthetic export failure')
    with pytest.raises(RuntimeError):
        spool.consume(consumer)
    assert len(calls) == 1
    assert spool._reading_index is None
    assert spool.consume(lambda run: sum(1 for _ in run.records()), cleanup=False) == 3
    assert len(calls) == 2
