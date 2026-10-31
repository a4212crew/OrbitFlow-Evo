"""Output-neutral, single-owner JSONL outcomes and recoverable run lifecycle.

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
from threading import get_ident
from time import sleep
from uuid import uuid4

from orbitflow.logging import sanitize_text


logger = logging.getLogger(__name__)

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


class ResultJournal:
    """Synchronized, fsynced incremental events, including pre-send intent.

    Workers submit JSON data to this owning writer. A process interruption leaves
    complete lines readable; an incomplete final line is ignored in recovery.
    """
    def __init__(self, path, *, clean=sanitize_text):
        from threading import Lock
        self.path = Path(path)
        self._lock = Lock()
        self._failed = False
        self._safe = ResultSpool.__new__(ResultSpool)
        self._safe.clean = clean

    def append(self, value):
        with self._lock:
            if self._failed:
                raise RuntimeError('Journal stopped after persistence failure')
            try:
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
        for name in ('manifest.json', 'results.jsonl', 'snapshot.jsonl', 'manifest.tmp', 'snapshot.tmp', '.lock'):
            if (self.path / name).is_symlink():
                raise ValueError('Spool files must not be links')
        self.clean = clean
        self.manifest = json.loads((self.path / 'manifest.json').read_text(encoding='utf-8'))
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
            run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ_') + uuid4().hex
            path = root / run_id
            path.mkdir()
        manifest = dict(schema_version=1, run_id=run_id, task=task,
                        target_count=target_count, completed_count=0, failed_count=0,
                        status='created', record_limit_bytes=MAX_RECORD_BYTES, collection_complete=False, created_at=_now(), updated_at=_now())
        (path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        (path / 'results.jsonl').touch()
        return cls(path, clean=clean)

    def _state(self, status):
        self.manifest.update(status=status, updated_at=_now())
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
            self.manifest = json.loads((self.path / 'manifest.json').read_text(encoding='utf-8'))
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
    def collection(self):
        from orbitflow.terminal_progress import workflow_progress, current_display
        with workflow_progress('Collection records', total=self.manifest['target_count'], durable=True, quiet=current_display.get() is None):
            try:
                with self._collection():
                    yield self
            finally:
                from orbitflow.terminal_progress import current_display
                display = current_display.get()
                display.finish(bool(self.manifest.get('collection_complete')))
                display._emit(self.clean(f"Collection {self.manifest['status']}: records={self.manifest['completed_count']}/{self.manifest['target_count']}; errors={self.manifest['failed_count']}; report/export pending; spool: {self.path}"), True)

    @contextmanager
    def _collection(self):
        with _lease(self.path):
            self.manifest = json.loads((self.path / 'manifest.json').read_text(encoding='utf-8'))
            if self.manifest['status'] != 'created':
                raise ValueError('Collection cannot be repeated')
            self._owner = get_ident()
            self._positions = set()  # Metadata only; never retains task payloads.
            self._append_failed = False
            try:
                self._state('collecting')
                with (self.path / 'results.jsonl').open('a', encoding='utf-8', newline='\n') as writer:
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
        """Stage sanitized JSON on disk, flush once, then checkpoint.

        Envelopes above 64 MiB or a spool above 64 GiB fail explicitly. Staging
        failures preserve preceding records; publication failures may leave an
        incomplete final line. Never retry an append failure.
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
                start = self._writer.tell()
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
                copyfileobj(staged, self._writer, length=64 * 1024)
            self._writer.flush()
            os.fsync(self._writer.fileno())
            self._positions.add(position)
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
        """Lease a reusable bounded SQLite view of authoritative JSONL.

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
                self.manifest = json.loads((self.path / 'manifest.json').read_text(encoding='utf-8'))
                if self.manifest.get('cleanup_started'):
                    raise ValueError('Output already consumed; retained run permits cleanup only')
                with self._indexed() as index:
                    yield index

    @property
    def _read_limit(self):
        return MAX_RECORD_BYTES if ('binding' in self.manifest or 'record_limit_bytes' in self.manifest) else LEGACY_MAX_RECORD_BYTES

    @contextmanager
    def _indexed(self):
        """Build one bounded-cache SQLite index for repeated/batch consumption.

        JSONL remains authoritative. Call under collection/consumption ownership
        when concurrent lifecycle operations are possible. No index is trusted
        across contexts or after an interrupted transaction.
        """
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
        temporary = self.path / 'snapshot.tmp'
        with temporary.open('w', encoding='utf-8') as writer:
            for row in rows:
                writer.write(json.dumps(self._safe(row), allow_nan=False) + '\n')
        temporary.replace(self.path / 'snapshot.jsonl')

    def snapshot_rows(self):
        with (self.path / 'snapshot.jsonl').open(encoding='utf-8') as source:
            for line in source:
                yield json.loads(line)

    def consume(self, consumer, *, cleanup=True, allow_partial=False):
        """Export separately from collection; report only actual saved outcomes."""
        from orbitflow.terminal_progress import workflow_progress, current_display
        with workflow_progress('Report/export stages', quiet=current_display.get() is None) as display:
            try:
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
            display._emit(self.clean(f"Export {self.manifest['status']}: records={self.manifest['completed_count']}/{self.manifest['target_count']}; collection/processing errors={self.manifest['failed_count']}; findings are separate; output: {output}; spool: {spool_location}"), True)
            return result

    def _consume(self, consumer, *, cleanup=True, allow_partial=False):
        with _lease(self.path):
            # Reload under the lease to prevent stale objects replaying lifecycle state.
            self.manifest = json.loads((self.path / 'manifest.json').read_text(encoding='utf-8'))
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
        allowed = {'manifest.json', 'manifest.tmp', 'results.jsonl', 'snapshot.jsonl', 'snapshot.tmp', '.lock'}
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
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return removed
