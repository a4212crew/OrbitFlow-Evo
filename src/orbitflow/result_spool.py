"""Output-neutral, single-owner SQLite outcomes (legacy JSONL readable) and recoverable run lifecycle.

Payloads must be normalized JSON data, never raw device output or credentials.
The supplied sanitizer is applied recursively before anything is persisted.
"""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sqlite3
from itertools import islice
from tempfile import TemporaryDirectory, TemporaryFile
from shutil import copyfileobj
from threading import get_ident, RLock
from weakref import WeakValueDictionary
from time import sleep, monotonic

from orbitflow.logging import sanitize_text


logger = logging.getLogger(__name__)
_writer_registry_lock = RLock()
_writer_registry = WeakValueDictionary()


def _run_writer(path):
    """One process-local write owner across result and journal handles per run."""
    with _writer_registry_lock:
        lock = _writer_registry.get(str(path))
        if lock is None:
            lock = RLock()
            _writer_registry[str(path)] = lock
        return lock


# Limits apply to individual envelopes, never the aggregate observation bundle.
# readline(size) enforces the bound before allocating an untrusted full line.
from orbitflow.indexed_json import MAX_VALUE_BYTES as MAX_RECORD_BYTES, MAX_TOTAL_BYTES as MAX_SPOOL_BYTES

# Historical writers predate record bounds and request binding. Preserve their
# demonstrated >64 MiB envelope case with a separate finite reader allowance;
# new writers and provenance-bound records retain the 64 MiB limit.
LEGACY_MAX_RECORD_BYTES = 256 * 1024 * 1024


class ResultIndex:
    """Lease-scoped disk index over authoritative JSONL, with bounded retrieval.

    Created by ResultSpool.indexed(); callers must not retain it beyond that
    context. SQLite stores offsets, not a second copy of device payloads.
    """
    def __init__(self, spool, db, source):
        self.spool, self.db, self.source = spool, db, source

    def _read(self, offset):
        self.source.seek(offset)
        return json.loads(self.source.readline(self.spool._read_limit + 1))

    def records(self, *, positions=None, target=None):
        """Yield input order; optional positions are bounded to 256 per query."""
        clauses, parameters = [], []
        if positions is not None:
            positions = tuple(islice(positions, 257))
            if len(positions) > 256 or any(type(p) is not int for p in positions):
                raise ValueError('Index batch must contain at most 256 integer positions')
            if not positions:
                return
            clauses.append('position IN (' + ','.join('?' for _ in positions) + ')')
            parameters.extend(positions)
        if target is not None:
            clauses.append('target = ?')
            parameters.append(target)
        for _, offset in self._offsets(clauses, parameters):
            yield self._read(offset)

    def _offsets(self, clauses, parameters):
        # Close each cursor before yielding to consumer code: a suspended
        # generator retained by an exception must not keep SQLite files open
        # beyond the lease (Windows cannot unlink an active statement).
        position = 0
        while True:
            query = ('SELECT position, offset FROM offsets WHERE ' +
                     ' AND '.join([*clauses, 'position > ?']) +
                     ' ORDER BY position LIMIT 256')
            with closing(self.db.execute(query, [*parameters, position])) as cursor:
                rows = cursor.fetchall()
            if not rows:
                return
            for position, offset in rows:
                yield position, offset

    def entries(self, *, target=None):
        """Yield (input position, record), optionally for one indexed key."""
        clauses, parameters = [], []
        if target is not None:
            clauses.append('target=?')
            parameters.append(target)
        for position, offset in self._offsets(clauses, parameters):
            yield position, self._read(offset)

    def set_reference(self, position, reference):
        """Attach a disk-backed consumer reference to an indexed journal event."""
        self.db.execute('INSERT OR REPLACE INTO references_map VALUES (?, ?)', (position, reference))

    def reference(self, position):
        row = self.db.execute('SELECT reference FROM references_map WHERE position=?', (position,)).fetchone()
        return row[0] if row else None

    def get(self, position):
        """Return one envelope or raise KeyError for a missing input position."""
        if type(position) is not int:
            raise ValueError('Index position must be an integer')
        row = self.db.execute('SELECT offset FROM offsets WHERE position=?', (position,)).fetchone()
        if row is None:
            raise KeyError(position)
        return self._read(row[0])

    def __len__(self):
        return self.db.execute('SELECT count(*) FROM offsets').fetchone()[0]


class SQLiteResultIndex:
    """Ordered bounded retrieval directly from authoritative run evidence."""
    table = 'results'

    def __init__(self, spool, db):
        self.spool, self.db = spool, db

    def records(self, *, positions=None, target=None):
        clauses, args = [], []
        if positions is not None:
            positions = tuple(islice(positions, 257))
            if len(positions) > 256 or any(type(p) is not int for p in positions):
                raise ValueError('Index batch must contain at most 256 integer positions')
            if not positions:
                return
            clauses.append('position IN (' + ','.join('?' for _ in positions) + ')')
            args.extend(positions)
        if target is not None:
            clauses.append('target=?')
            args.append(target)
        position = 0
        while True:
            # Fetch identifiers only; never batch 256 potentially large payloads.
            with closing(self.db.execute(f'SELECT position FROM {self.table} WHERE ' +
                    ' AND '.join([*clauses, 'position>?']) + ' ORDER BY position LIMIT 256',
                    [*args, position])) as cursor:
                identifiers = cursor.fetchall()
            if not identifiers:
                return
            for (position,) in identifiers:
                yield self.get(position)

    def entries(self, *, target=None):
        """Preserve the shared input-position/record iterator contract."""
        for record in self.records(target=target):
            yield record['input_position'], record

    def get(self, position):
        if type(position) is not int:
            raise ValueError('Index position must be an integer')
        with self.spool.timed_stage('sqlite_retrieval'):
            size = self.db.execute(f'SELECT length(record) FROM {self.table} WHERE position=?', (position,)).fetchone()
            if size is not None and size[0] > MAX_RECORD_BYTES:
                raise ValueError('Spool record size limit exceeded')
            with closing(self.db.execute(f'SELECT target, record FROM {self.table} WHERE position=?', (position,))) as cursor:
                row = cursor.fetchone()
        if row is None:
            raise KeyError(position)
        record = json.loads(row[1])
        if self.table == 'events':
            if not isinstance(record, dict) or str(record.get('row_id', '')) != row[0]:
                raise ValueError('Invalid journal target identity')
            return record
        if (not isinstance(record, dict) or record.get('run_id') != self.spool.manifest['run_id']
                or type(record.get('input_position')) is not int or record['input_position'] != position
                or not 1 <= position <= self.spool.manifest['target_count']
                or record.get('status') not in {'success', 'failed'}
                or not isinstance(record.get('target'), str) or record['target'] != row[0] or 'payload' not in record):
            raise ValueError('Invalid spool envelope or mismatched run identity')
        return record

    def __len__(self):
        return self.db.execute(f'SELECT count(*) FROM {self.table}').fetchone()[0]


class SQLiteJournalIndex(SQLiteResultIndex):
    """Direct event queries; temporary report references never change evidence."""
    table = 'events'

    def entries(self, *, target=None):
        position = 0
        while True:
            clause, args = (' AND target=?', [target]) if target is not None else ('', [])
            with closing(self.db.execute('SELECT position FROM events WHERE position>?' + clause + ' ORDER BY position LIMIT 256', [position, *args])) as cursor:
                rows = cursor.fetchall()
            if not rows:
                return
            for (position,) in rows:
                yield position, self.get(position)

    def set_reference(self, position, reference):
        self.db.execute('INSERT OR REPLACE INTO references_map VALUES (?, ?)', (position, reference))

    def reference(self, position):
        row = self.db.execute('SELECT reference FROM references_map WHERE position=?', (position,)).fetchone()
        return row[0] if row else None


class ResultJournal:
    """Synchronized durable events, including pre-send intent.

    New run events commit to the shared SQLite store. Legacy standalone JSONL
    journals remain readable, including recovery of complete pre-crash lines.
    """
    def __init__(self, path, *, clean=sanitize_text):
        from threading import Lock
        self.path = Path(path)
        self._lock = Lock()
        self._failed = False
        self._safe = ResultSpool.__new__(ResultSpool)
        self._safe.clean = clean
        self._run = None
        manifest_path = self.path.parent / 'manifest.json'
        has_database = any((self.path.parent / name).exists() for name in ('r.db', 'results.sqlite'))
        if manifest_path.exists() and not has_database:
            if json.loads(manifest_path.read_text(encoding='utf-8')).get('storage') == 'sqlite':
                raise ValueError('Missing run database; legacy journal fallback forbidden')
        if has_database:
            # Explicit report copies retain their original run identity even when
            # the copied directory has a different name. No collection is opened.
            run = ResultSpool.__new__(ResultSpool)
            run.path = self.path.parent.absolute()
            if run.path.resolve() != run.path or run.database_path.is_symlink():
                raise ValueError('Journal path must not traverse links')
            run.clean, run._db_lock = clean, _run_writer(run.path)
            run.manifest = run._load_manifest()
            if run.manifest.get('schema_version') != 1 or not isinstance(run.manifest.get('run_id'), str):
                raise ValueError('Invalid journal run metadata')
            self._run = run

    def append(self, value):
        with self._lock:
            if self._failed:
                raise RuntimeError('Journal stopped after persistence failure')
            try:
                if self._run is not None:
                    value = self._safe._safe(value)
                    with TemporaryFile(mode='w+', encoding='ascii', dir=self.path.parent) as staged:
                        size = 0
                        for part in json.JSONEncoder(ensure_ascii=True, allow_nan=False).iterencode(value):
                            size += len(part)
                            if size > MAX_RECORD_BYTES:
                                raise ValueError('Journal record size limit exceeded')
                            staged.write(part)
                        staged.seek(0)
                        with self._run.timed_stage('sqlite_journal_commit'), self._run._db_lock, closing(self._run._connect()) as db, db:
                            if self._run.database_path.stat().st_size + size > MAX_SPOOL_BYTES:
                                raise ValueError('Journal size limit exceeded')
                            db.execute('INSERT INTO events(target,record) VALUES (?,?)', (value.get('row_id', ''), staged.read()))
                    return
                with TemporaryFile(mode='w+b') as staged:
                    size = 0
                    encoder = json.JSONEncoder(allow_nan=False)
                    for part in encoder.iterencode(self._safe._safe(value)):
                        encoded = part.encode('utf-8')
                        size += len(encoded)
                        if size + 1 > self._read_limit:
                            raise ValueError('Journal record size limit exceeded')
                        staged.write(encoded)
                    staged.write(b'\n')
                    staged.seek(0)
                    with self.path.open('ab') as stream:
                        if os.fstat(stream.fileno()).st_size + size + 1 > MAX_SPOOL_BYTES:
                            raise ValueError('Journal size limit exceeded')
                        copyfileobj(staged, stream, length=65536)
                        stream.flush()
                        os.fsync(stream.fileno())
            except BaseException:
                self._failed = True
                raise

    def records(self):
        if self._run is not None:
            with self.indexed() as index:
                yield from index.records()
            return
        if not self.path.exists():
            return
        with self.path.open('rb') as stream:
            while True:
                if stream.tell() > MAX_SPOOL_BYTES:
                    raise ValueError('Journal size limit exceeded')
                line = stream.readline(self._read_limit + 1)
                if stream.tell() > MAX_SPOOL_BYTES:
                    raise ValueError('Journal size limit exceeded')
                if len(line) > self._read_limit:
                    raise ValueError('Journal record size limit exceeded')
                if not line or not line.endswith(b'\n'):
                    break
                yield json.loads(line)

    _read_limit = LEGACY_MAX_RECORD_BYTES

    @contextmanager
    def indexed(self):
        """Bounded offset index for offline row/event consumption of a journal.

        One scan accepts complete lines only; an interrupted final line remains
        ignored. Payloads stay in authoritative JSONL, with row IDs indexed as
        target keys. Scratch references are discarded with the owning context.
        """
        if self._run is not None:
            with closing(self._run._connect()) as db:
                db.execute('CREATE TEMP TABLE references_map (position INTEGER PRIMARY KEY, reference INTEGER)')
                yield SQLiteJournalIndex(self._run, db)
            return
        with TemporaryDirectory(prefix='read-', dir=self.path.parent) as scratch:
            with closing(sqlite3.connect(str(Path(scratch) / 'order.sqlite'))) as db:
                db.execute('PRAGMA cache_size=-512')
                db.execute('PRAGMA temp_store=FILE')
                db.execute('CREATE TABLE offsets (position INTEGER PRIMARY KEY, offset INTEGER, target TEXT)')
                db.execute('CREATE INDEX targets ON offsets(target, position)')
                db.execute('CREATE TABLE references_map (position INTEGER PRIMARY KEY, reference INTEGER)')
                with (self.path.open('rb') if self.path.exists() else TemporaryFile(mode='w+b')) as source:
                    with db:
                        position = 0
                        while True:
                            offset = source.tell()
                            if offset > MAX_SPOOL_BYTES:
                                raise ValueError('Journal size limit exceeded')
                            line = source.readline(self._read_limit + 1)
                            if len(line) > self._read_limit:
                                raise ValueError('Journal record size limit exceeded')
                            if not line or not line.endswith(b'\n'):
                                break
                            record = json.loads(line)
                            position += 1
                            db.execute('INSERT INTO offsets VALUES (?, ?, ?)',
                                       (position, offset, record.get('row_id', '')))
                    yield ResultIndex(self, db, source)


def _permission_retry(operation):
    """Allow a bounded handle-release delay without changing access controls."""
    for delay in (0.1, 0.2, 0.4, None):
        try:
            operation()
            return
        except PermissionError:
            if delay is None:
                raise
            sleep(delay)


def _remove_with_retry(operation):
    return _permission_retry(operation)


def _now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _lease(path):
    """OS-released advisory lease: crashed owners do not block recovery forever."""
    lock_path = path / '.lock'
    if lock_path.is_symlink():
        raise ValueError('Spool lease must not be a link')
    handle = lock_path.open('a+b')
    try:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            if not handle.read(1):
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


class ResultSpool:
    """A unique run. Use collection() and consume() to hold exclusive ownership."""
    def __init__(self, path, *, clean=sanitize_text):
        self.path = Path(path).absolute()
        if self.path.is_symlink() or self.path.resolve() != self.path.absolute():
            raise ValueError('Spool path must not traverse links')
        for name in ('manifest.json', 'results.jsonl', 'snapshot.jsonl', 'manifest.tmp', 'snapshot.tmp', 'r.db', 'results.sqlite', '.lock'):
            if (self.path / name).is_symlink():
                raise ValueError('Spool files must not be links')
        self.clean = clean
        self._db_lock = _run_writer(self.path)
        self.manifest = self._load_manifest()
        if not isinstance(self.manifest, dict) or self.manifest.get('schema_version') != 1 or self.manifest.get('run_id') != self.path.name:
            raise ValueError('Invalid spool manifest')
        self._writer = None
        self._reading_index = None

    @classmethod
    def create(cls, root, task, target_count, *, clean=sanitize_text, short_name=False):
        """Allocate exclusively; opt-in short UTC names leave shared defaults intact."""
        if type(target_count) is not int or target_count < 0:
            raise ValueError('Target count must be a nonnegative integer')
        root = Path(root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        if short_name:
            stem = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            for sequence in range(100000):
                run_id = stem + (f'_{sequence:03d}' if sequence else '')
                path = root / run_id
                try:
                    path.mkdir()
                    break
                except FileExistsError:
                    continue
            else:
                raise ValueError('Run allocation exhausted')
        else:
            from orbitflow.run_timing import current_run, new_run_id
            run_id = current_run.get() or new_run_id()
            path = root / run_id
            path.mkdir()
        manifest = dict(schema_version=1, run_id=run_id, task=task,
                        target_count=target_count, completed_count=0, failed_count=0,
                        status='created', storage='sqlite', record_limit_bytes=MAX_RECORD_BYTES, collection_complete=False, created_at=_now(), updated_at=_now())
        (path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        with closing(sqlite3.connect(str(path / 'r.db'))) as db:
            db.execute('CREATE TABLE results (position INTEGER PRIMARY KEY, target TEXT NOT NULL, record TEXT NOT NULL)')
            db.execute('CREATE INDEX result_targets ON results(target, position)')
            db.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE snapshot (position INTEGER PRIMARY KEY, record TEXT NOT NULL)')
            db.execute('CREATE TABLE events (position INTEGER PRIMARY KEY, target TEXT NOT NULL, record TEXT NOT NULL)')
            db.execute('CREATE INDEX event_targets ON events(target, position)')
            db.execute('INSERT INTO metadata VALUES (?, ?)', ('manifest', json.dumps(manifest)))
            db.commit()
        return cls(path, clean=clean)

    def _load_manifest(self):
        manifest = json.loads((self.path / 'manifest.json').read_text(encoding='utf-8'))
        if not isinstance(manifest, dict):
            raise ValueError('Invalid spool manifest')
        if manifest.get('cleanup_started'):
            # Successful output may already have removed the database. This
            # durable marker authorizes cleanup only, never data consumption.
            return manifest
        if manifest.get('storage') == 'sqlite':
            with closing(self._connect()) as db:
                row = db.execute("SELECT value FROM metadata WHERE key='manifest' AND length(value)<=1048576").fetchone()
                if row is None:
                    raise ValueError('Missing or oversized run metadata')
                manifest = json.loads(row[0])
            if not isinstance(manifest, dict):
                raise ValueError('Invalid spool manifest')
        return manifest

    @property
    def database_path(self):
        """Short authoritative basename; retain earlier direct-store read compatibility."""
        short, previous = self.path / 'r.db', self.path / 'results.sqlite'
        if short.exists() and previous.exists():
            raise ValueError('Ambiguous run databases')
        return short if short.exists() else previous

    def _connect(self):
        db = sqlite3.connect(self.database_path.as_uri() + '?mode=rw', uri=True)
        db.execute('PRAGMA cache_size=-512')
        db.execute('PRAGMA temp_store=FILE')
        db.execute('PRAGMA synchronous=FULL')
        return db

    def _state(self, status):
        self.manifest.update(status=status, updated_at=_now())
        if self.manifest.get('storage') == 'sqlite':
            with self._db_lock, closing(self._connect()) as db, db:
                db.execute('UPDATE metadata SET value=? WHERE key=?', (json.dumps(self.manifest), 'manifest'))
        temporary = self.path / 'manifest.tmp'
        with temporary.open('w', encoding='utf-8') as stream:
            stream.write(json.dumps(self.manifest))
            stream.flush()
            os.fsync(stream.fileno())
        _permission_retry(lambda: temporary.replace(self.path / 'manifest.json'))

    def bind(self, metadata):
        """Persist sanitized request provenance once, before collection starts.

        Binding is caller-owned JSON metadata, not authentication. Legacy runs
        lack it; recovery must never infer a historical source association.
        """
        with _lease(self.path):
            self.manifest = self._load_manifest()
            if self.manifest['status'] != 'created' or 'binding' in self.manifest:
                raise ValueError('Run binding must precede collection and cannot be replaced')
            if not isinstance(metadata, dict):
                raise ValueError('Run binding must be a JSON object')
            value = self._safe(metadata)
            if value != metadata or len(json.dumps(value, allow_nan=False).encode()) > 65536:
                raise ValueError('Unsafe or oversized run binding')
            self.manifest['binding'] = value
            self._state('created')

    def _failed_state(self, status, original):
        """Keep the primary failure even when the diagnostic checkpoint fails."""
        try:
            self._state(status)
        except Exception as secondary:
            original.spool_state_error = secondary

    def _safe(self, value):
        if isinstance(value, dict):
            return {self.clean(k): self._safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._safe(v) for v in value]
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str):
            return self.clean(value)
        if value is None or isinstance(value, (bool, int, float)):
            return value
        raise TypeError('Spool payload must contain normalized JSON values')

    @contextmanager
    def timed_stage(self, name):
        """Monotonic stage boundaries, with payload-free structured file records."""
        from orbitflow.logging import module_logger
        started, wall = monotonic(), _now()
        status = 'success'
        from orbitflow.run_timing import run_scope, current_run
        operation_id = current_run.get() or self.manifest['run_id']
        metadata = dict(run_id=operation_id, evidence_run_id=self.manifest['run_id'],
                        workflow=self.manifest['task'], stage=name, started_at=wall)
        modules = {'configuration_observation_v2': 'observation', 'configuration_execution': 'execution',
                   'manual_configuration': 'manual', 'mac_table': 'mac_lookup',
                   'interface_vlan_report': 'reporting'}
        task = self.manifest['task']
        module = modules.get(task, task if task in {'inventory_refresh', 'vlan_compliance', 'configuration_backup'} else 'processing')
        with run_scope(operation_id), module_logger(module, 'run_stages') as (sink, _):
            sink.info('stage_start', extra=metadata)
            logger.info('stage_start', extra=metadata)
            try:
                yield
            except BaseException as exc:
                status = 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failure'
                raise
            finally:
                metadata.update(ended_at=_now(), elapsed_seconds=round(monotonic() - started, 3),
                                status=('partial' if status == 'success' and self.manifest['failed_count'] else status))
                # Journal-only handles do not own live device outcome counters.
                if hasattr(self, '_writer'):
                    metadata['completed_count'] = self.manifest['completed_count']
                sink.info('stage_end', extra=metadata)
                logger.info('stage_end', extra=metadata)

    @contextmanager
    def collection(self):
        from orbitflow.terminal_progress import workflow_progress, current_display
        collection_tick = monotonic()
        with workflow_progress('Collection records', total=self.manifest['target_count'], durable=True, quiet=current_display.get() is None):
            try:
                with self.timed_stage('collection'), self._collection():
                    yield self
            finally:
                from orbitflow.terminal_progress import current_display
                display = current_display.get()
                display.finish(bool(self.manifest.get('collection_complete')))
                display._emit(self.clean(f"Collection {self.manifest['status']}: records={self.manifest['completed_count']}/{self.manifest['target_count']}; errors={self.manifest['failed_count']}; report/export pending; collection_seconds={monotonic() - collection_tick:.3f}; spool: {self.path}"), True)

    @contextmanager
    def _collection(self):
        with _lease(self.path):
            self.manifest = self._load_manifest()
            if self.manifest['status'] != 'created':
                raise ValueError('Collection cannot be repeated')
            self._owner = get_ident()
            self._positions = set()  # Metadata only; never retains task payloads.
            self._append_failed = False
            try:
                self._state('collecting')
                with closing(self._connect()) if self.manifest.get('storage') == 'sqlite' else (self.path / 'results.jsonl').open('a', encoding='utf-8', newline='\n') as writer:
                    self._writer = writer
                    yield self
                if self._append_failed:
                    raise RuntimeError('Collection stopped after persistence failure')
                if len(self._positions) != self.manifest['target_count']:
                    raise ValueError('Incomplete target outcomes')
                self.manifest['collection_complete'] = True
                self._state('collected')
            except BaseException as exc:
                self.manifest['collection_complete'] = False
                self._failed_state('interrupted', exc)
                raise
            finally:
                self._writer = None
                self._positions.clear()

    def append(self, outcome, *, payload=None, target='', failed=False):
        """Stage sanitized JSON and transactionally commit its outcome/counts.

        Envelopes above 64 MiB or a store above 64 GiB fail explicitly. Legacy
        writers retain JSONL compatibility. Never retry a failed append: a later
        checkpoint failure can occur after a successful database commit.
        """
        if self._writer is None or get_ident() != self._owner:
            raise RuntimeError('Only the collection owner may append')
        if self._append_failed:
            raise RuntimeError('Collection stopped after persistence failure')
        position = outcome.position
        if type(position) is not int or position in self._positions or not 1 <= position <= self.manifest['target_count']:
            raise ValueError('Duplicate or invalid input position')
        category = self.clean(outcome.error_category)
        record = dict(run_id=self.manifest['run_id'], input_position=position,
                      target=self.clean(target), status='failed' if failed or category else 'success',
                      completed_at=_now(), error_category=category,
                      payload=self._safe(outcome.value if payload is None else payload))
        try:
            # Stage before touching authoritative JSONL: serialization, size or
            # scratch-disk failure must not publish a partial envelope. Avoid
            # joining all encoder chunks into an additional full-record string.
            with TemporaryFile(mode='w+', encoding='ascii', newline='\n', dir=self.path) as staged:
                size = 0
                direct = self.manifest.get('storage') == 'sqlite'
                start = self.database_path.stat().st_size if direct else self._writer.tell()
                encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False)
                for chunk in encoder.iterencode(record):
                    size += len(chunk)  # ensure_ascii makes characters == bytes
                    if size + 1 > MAX_RECORD_BYTES:
                        raise ValueError('Spool record size limit exceeded')
                    if start + size + 1 > MAX_SPOOL_BYTES:
                        raise ValueError('Spool size limit exceeded')
                    staged.write(chunk)
                staged.write('\n')
                staged.seek(0)
                if direct:
                    with self.timed_stage('sqlite_insert_commit'):
                        with self._db_lock, self._writer:
                            self._writer.execute('INSERT INTO results VALUES (?, ?, ?)', (position, record['target'], staged.read()))
                            checkpoint = dict(self.manifest, completed_count=self.manifest['completed_count'] + 1,
                                              failed_count=self.manifest['failed_count'] + (record['status'] == 'failed'))
                            self._writer.execute("UPDATE metadata SET value=? WHERE key='manifest'", (json.dumps(checkpoint),))
                        # Only advance after commit, before publishing stage-end counts.
                        self.manifest.update(checkpoint)
                else:
                    copyfileobj(staged, self._writer, length=64 * 1024)
            if not direct:
                self._writer.flush()
                os.fsync(self._writer.fileno())
            self._positions.add(position)
            if not direct:
                self.manifest['completed_count'] += 1
                self.manifest['failed_count'] += record['status'] == 'failed'
            self._state('collecting')
        except BaseException:
            self._append_failed = True
            raise
        # Optional subscribers must never turn a committed append into a sink
        # failure or invite retry of an already recorded device outcome.
        try:
            from orbitflow.terminal_progress import current_display
            display = current_display.get()
            if display is not None:
                display.outcome(position, None if target in display.unknown_targets else record['status'] == 'failed')
        except Exception:
            pass

    @contextmanager
    def indexed(self):
        """Lease bounded direct SQLite retrieval (legacy JSONL indexed on demand).

        Public readers cannot race collection, output consumption or cleanup.
        The owning collection/consumption thread reuses its existing lease.
        """
        if self._reading_index is not None:
            if get_ident() != self._reader_owner:
                raise RuntimeError('Only the consumption owner may read the shared index')
            yield self._reading_index
        elif self._writer is not None and get_ident() == self._owner:
            with self._indexed() as index:
                yield index
        else:
            with _lease(self.path):
                self.manifest = self._load_manifest()
                if self.manifest.get('cleanup_started'):
                    raise ValueError('Output already consumed; retained run permits cleanup only')
                with self._indexed() as index:
                    yield index

    @property
    def _read_limit(self):
        return MAX_RECORD_BYTES if ('binding' in self.manifest or 'record_limit_bytes' in self.manifest) else LEGACY_MAX_RECORD_BYTES

    @contextmanager
    def _indexed(self):
        """Validate direct run storage or index a retained legacy JSONL source.

        Call under collection/consumption ownership. New SQLite databases are
        authoritative; only legacy JSONL needs a disposable offset index.
        """
        if self.manifest.get('storage') == 'sqlite':
            with closing(self._connect()) as db:
                if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('Corrupt run database')
                if db.execute('SELECT 1 FROM results WHERE position<1 OR position>? LIMIT 1', (self.manifest['target_count'],)).fetchone():
                    raise ValueError('Invalid persisted input position')
                count = db.execute('SELECT count(*) FROM results').fetchone()[0]
                if self.manifest['collection_complete'] and count != self.manifest['target_count']:
                    raise ValueError('Incomplete persisted outcomes')
                index = SQLiteResultIndex(self, db)
                self._reading_index, self._reader_owner = index, get_ident()
                try:
                    yield index
                finally:
                    self._reading_index = None
            return
        with TemporaryDirectory(prefix='read-', dir=self.path) as temporary:
            with closing(sqlite3.connect(str(Path(temporary) / 'order.sqlite'))) as db:
                db.execute('PRAGMA cache_size = -512')
                db.execute('PRAGMA temp_store = FILE')
                db.execute('CREATE TABLE offsets (position INTEGER PRIMARY KEY, offset INTEGER, target TEXT)')
                db.execute('CREATE INDEX targets ON offsets(target, position)')
                with (self.path / 'results.jsonl').open('rb') as source:
                    with db:
                        while True:
                            offset = source.tell()
                            if offset > MAX_SPOOL_BYTES:
                                raise ValueError('Spool size limit exceeded')
                            line = source.readline(self._read_limit + 1)
                            if not line:
                                break
                            if len(line) > self._read_limit:
                                raise ValueError('Spool record size limit exceeded')
                            if not line.endswith(b'\n'):
                                if self.manifest['collection_complete']:
                                    raise ValueError('Truncated completed spool')
                                break
                            record = json.loads(line)
                            if not isinstance(record, dict) or record.get('run_id') != self.manifest['run_id']:
                                raise ValueError('Mismatched run identity')
                            position = record.get('input_position')
                            if (type(position) is not int or not 1 <= position <= self.manifest['target_count']
                                    or record.get('status') not in {'success', 'failed'}
                                    or not isinstance(record.get('target'), str) or 'payload' not in record):
                                raise ValueError('Invalid spool envelope')
                            try:
                                db.execute('INSERT INTO offsets VALUES (?, ?, ?)', (position, offset, record['target']))
                            except sqlite3.IntegrityError:
                                raise ValueError('Duplicate persisted input position') from None
                    count = db.execute('SELECT count(*) FROM offsets').fetchone()[0]
                    if self.manifest['collection_complete'] and count != self.manifest['target_count']:
                        raise ValueError('Incomplete persisted outcomes')
                    index = ResultIndex(self, db, source)
                    self._reading_index = index
                    self._reader_owner = get_ident()
                    try:
                        yield index
                    finally:
                        self._reading_index = None

    def records(self):
        """Input order through the shared bounded SQLite retrieval interface."""
        if self._reading_index is not None:
            if get_ident() != self._reader_owner:
                raise RuntimeError('Only the consumption owner may read the shared index')
            yield from self._reading_index.records()
        else:
            with self.indexed() as index:
                yield from index.records()

    def snapshot(self, rows):
        """Persist consumer-owned normalized snapshot data, not canonical state."""
        if self._writer is None or get_ident() != self._owner:
            raise RuntimeError('Snapshot requires collection ownership')
        if self.manifest.get('storage') == 'sqlite':
            with self._db_lock, self._writer:
                self._writer.execute('DELETE FROM snapshot')
                for position, row in enumerate(rows, 1):
                    value = json.dumps(self._safe(row), allow_nan=False)
                    if len(value.encode()) > MAX_RECORD_BYTES:
                        raise ValueError('Snapshot record size limit exceeded')
                    self._writer.execute('INSERT INTO snapshot VALUES (?, ?)', (position, value))
                self._writer.execute("INSERT OR REPLACE INTO metadata VALUES ('snapshot_complete', 'true')")
            return
        temporary = self.path / 'snapshot.tmp'
        with temporary.open('w', encoding='utf-8') as writer:
            for row in rows:
                writer.write(json.dumps(self._safe(row), allow_nan=False) + '\n')
        temporary.replace(self.path / 'snapshot.jsonl')

    def has_snapshot(self):
        """Whether this run has a complete historical export projection."""
        if self.manifest.get('storage') == 'sqlite':
            with closing(self._connect()) as db:
                return db.execute("SELECT 1 FROM metadata WHERE key='snapshot_complete'").fetchone() is not None
        return (self.path / 'snapshot.jsonl').exists()

    def snapshot_rows(self):
        if self.manifest.get('storage') == 'sqlite':
            with closing(self._connect()) as db:
                position = 0
                while True:
                    with closing(db.execute('SELECT position, record FROM snapshot WHERE position>? ORDER BY position LIMIT 1', (position,))) as cursor:
                        row = cursor.fetchone()
                    if row is None:
                        return
                    position, value = row
                    yield json.loads(value)
            return
        with (self.path / 'snapshot.jsonl').open(encoding='utf-8') as source:
            for line in source:
                yield json.loads(line)

    def consume(self, consumer, *, cleanup=True, allow_partial=False):
        """Export separately from collection; report only actual saved outcomes."""
        from orbitflow.terminal_progress import workflow_progress, current_display
        report_tick = monotonic()
        with workflow_progress('Report/export stages', quiet=current_display.get() is None) as display:
            try:
                with self.timed_stage('report_generation_publication'):
                    result = self._consume(consumer, cleanup=cleanup, allow_partial=allow_partial)
            except BaseException:
                display.finish(False)
                display._emit(self.clean(f'Export failed/interrupted; no completed output established; retained spool: {self.path}'), True)
                raise
            display.finish(True)
            try:
                saved = isinstance(result, (str, Path)) and Path(result).is_file()
                spool_location = str(self.path) if self.path.exists() else 'removed after successful export'
            except OSError:
                saved = False
                spool_location = 'retention unknown; run location: ' + str(self.path)
            output = str(result) if saved else 'no saved file established by consumer'
            display._emit(self.clean(f"Export {self.manifest['status']}: records={self.manifest['completed_count']}/{self.manifest['target_count']}; collection/processing errors={self.manifest['failed_count']}; report_seconds={monotonic() - report_tick:.3f}; findings are separate; output: {output}; spool: {spool_location}"), True)
            return result

    def _consume(self, consumer, *, cleanup=True, allow_partial=False):
        with _lease(self.path):
            # Reload under the lease to prevent stale objects replaying lifecycle state.
            self.manifest = self._load_manifest()
            if self.manifest.get('cleanup_started'):
                raise ValueError('Output already consumed; retained run permits cleanup only')
            complete = self.manifest['collection_complete']
            if not allow_partial and (not complete or self.manifest['status'] in {'created', 'collecting', 'interrupted'}):
                raise ValueError('Incomplete collection; explicitly request partial consumption')
            try:
                # Reuse one validated index across all report tables and passes.
                with self._indexed() as index:
                    self._reading_index = index
                    self._reader_owner = get_ident()
                    try:
                        completed = failed = 0
                        for record in self.records():
                            completed += 1
                            failed += record['status'] == 'failed'
                        self.manifest.update(completed_count=completed, failed_count=failed)
                        self._state('consuming')
                        result = consumer(self)
                        self._state('consumed' if complete else 'partial_consumed')
                    finally:
                        self._reading_index = None
            except BaseException as exc:
                self._failed_state('output_failed', exc)
                raise
        if cleanup and complete:
            self.remove()
        return result

    def remove(self, *, before=None):
        """Delete only recognized run files, never links or unknown subdirectories."""
        try:
            return self._remove(before=before)
        except PermissionError:
            # Do not expose exception text (which may contain sensitive paths).
            logger.warning('Spool cleanup deferred after bounded permission retries; '
                           'retained run requires later cleanup. Successful output remains valid.')
            return False

    def _remove(self, *, before=None):
        if self.path.is_symlink() or self.path.resolve() != self.path:
            raise ValueError('Spool path must not traverse links')
        allowed = {'manifest.json', 'manifest.tmp', 'results.jsonl', 'snapshot.jsonl', 'snapshot.tmp', 'r.db', 'r.db-journal', 'results.sqlite', 'results.sqlite-journal', '.lock'}
        with _lease(self.path):
            manifest = json.loads((self.path / 'manifest.json').read_text(encoding='utf-8'))
            if before is not None and datetime.fromisoformat(manifest['updated_at']) >= before:
                return False
            if before is None and manifest['status'] != 'consumed':
                raise ValueError('Only consumed runs permit normal cleanup')
            files, scratch = [], []
            for path in self.path.iterdir():
                if path.is_symlink() or path.resolve().parent != self.path:
                    raise ValueError('Refusing cleanup of linked spool contents')
                if path.is_dir() and path.name.startswith('read-'):
                    children = list(path.iterdir())
                    if any(child.name not in {'order.sqlite', 'order.sqlite-journal'}
                           or child.is_symlink() or not child.is_file()
                           or child.resolve().parent != path for child in children):
                        raise ValueError('Refusing cleanup of unexpected reader scratch')
                    scratch.append((path, children))
                elif path.name in allowed and path.is_file():
                    files.append(path)
                else:
                    raise ValueError('Refusing cleanup of unexpected spool contents')
            # Validate everything before deleting anything. No recursive deletion.
            self.manifest = manifest
            self.manifest['cleanup_started'] = True
            _remove_with_retry(lambda: (self.path / 'manifest.json').write_text(
                json.dumps(self.manifest), encoding='utf-8'))
            for directory, children in scratch:
                for child in children:
                    _remove_with_retry(child.unlink)
                _remove_with_retry(directory.rmdir)
            for path in files:
                if path.name not in {'.lock', 'manifest.json'}:
                    _remove_with_retry(path.unlink)
        _remove_with_retry((self.path / '.lock').unlink)
        # Keep the manifest until all other removals succeed. If the final
        # directory removal is denied, restore this small cleanup-only marker.
        manifest_path = self.path / 'manifest.json'
        _remove_with_retry(manifest_path.unlink)
        try:
            _remove_with_retry(self.path.rmdir)
        except PermissionError:
            _remove_with_retry(lambda: manifest_path.write_text(
                json.dumps(self.manifest), encoding='utf-8'))
            raise
        return True


def cleanup_stale_runs(root, *, before):
    """Explicit retention cutoff; skip leased, malformed and unrelated directories.

    Age alone never authorizes deleting an active run. OS leases also protect
    collection and consumption by other processes. Retained runs are otherwise
    removed only when an operator supplies this UTC cutoff.
    """
    if before.tzinfo is None:
        raise ValueError('Cleanup cutoff must be timezone-aware')
    removed = []
    root = Path(root).resolve()
    if not root.exists():
        return removed
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.is_symlink():
            continue
        try:
            spool = ResultSpool(path)
            if spool.remove(before=before):
                removed.append(path)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError):
            continue
    return removed
