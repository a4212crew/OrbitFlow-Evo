"""Session-owned bounded memoization of *computation*, never device freshness.

Always collect complete normalized interface/VLAN/configuration facts first.
Scoped reads cannot currently prove equivalent preservation/drift coverage.
Only an identical complete fresh input may reuse deterministic snapshot work.
Operational lookups are never cached across observation epochs.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json

from orbitflow.timing import stage

_current = ContextVar('execution_observation', default=None)
MAX_PROJECTION_BYTES = 8 * 1024 * 1024


class ObservationManager:
    def __init__(self, session, cli):
        self.session, self.cli = session, cli
        self.invalidate()

    def invalidate(self):
        self._key, self._value = None, None

    def project(self, session, context, cli, interfaces, vlans, factory):
        if session is not self.session or cli is not self.cli:
            raise ValueError('observation belongs to a different session')
        try:
            cli.require_session(session)
        except BaseException:
            self.invalidate()
            raise
        # Include every input except observation timestamps, which are replaced
        # from these fresh records. Never infer completeness from cached data.
        if vlans.configuration is None or context.collection_status != 'success':
            self.invalidate()
            return factory(context, interfaces, vlans)
        records = [asdict(i) for i in interfaces]
        for record in records:
            record.pop('collection_time')
        state = asdict(vlans)
        state.pop('collection_time')
        if state.get('aggregation') is not None:
            state['aggregation'].pop('collection_time')
        encoded = json.dumps([asdict(context), records, state], sort_keys=True,
                             default=lambda value: value.isoformat()).encode()
        key = hashlib.sha256(encoded).digest()
        cacheable = len(encoded) <= MAX_PROJECTION_BYTES
        if cacheable and key == self._key:
            with stage('snapshot_reuse'):
                result = deepcopy(self._value)
                result['observed_at'] = vlans.collection_time.isoformat()
                if result.get('aggregation') is not None and vlans.aggregation is not None:
                    result['aggregation']['collection_time'] = vlans.aggregation.collection_time
                for record, fresh in zip(result['interfaces'], interfaces):
                    record['collection_time'] = fresh.collection_time.isoformat()
                return result
        self.invalidate()
        result = factory(context, interfaces, vlans)
        # Bound both key input and retained projection; retain one generation.
        if cacheable and result.get('configuration_reliable') is True and len(json.dumps(result).encode()) <= MAX_PROJECTION_BYTES:
            self._key, self._value = key, deepcopy(result)
        return result


@contextmanager
def observation_scope(session, cli):
    manager = ObservationManager(session, cli)
    token = _current.set(manager)
    try:
        yield manager
    finally:
        manager.invalidate()
        _current.reset(token)


def invalidate():
    manager = _current.get()
    if manager is not None:
        manager.invalidate()


def project(session, context, cli, interfaces, vlans, factory):
    manager = _current.get()
    if manager is None:
        return factory(context, interfaces, vlans)
    return manager.project(session, context, cli, interfaces, vlans, factory)
