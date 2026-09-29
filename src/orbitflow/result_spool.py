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
from tempfile import TemporaryDirectory
from threading import get_ident
from time import sleep
from uuid import uuid4

from orbitflow.logging import sanitize_text


logger = logging.getLogger(__name__)


def _remove_with_retry(operation):
    """Allow a bounded handle-release delay without changing access controls."""
    for delay in (0.1, 0.2, 0.4, None):
        try:
            operation()
            return
        except PermissionError:
            if delay is None:
                raise
            sleep(delay)


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

    @classmethod
    def create(cls, root, task, target_count, *, clean=sanitize_text):
        if type(target_count) is not int or target_count < 0:
            raise ValueError('Target count must be a nonnegative integer')
        root = Path(root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ_') + uuid4().hex
        path = root / run_id
        path.mkdir()
        manifest = dict(schema_version=1, run_id=run_id, task=task,
                        target_count=target_count, completed_count=0, failed_count=0,
                        status='created', collection_complete=False, created_at=_now(), updated_at=_now())
        (path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        (path / 'results.jsonl').touch()
        return cls(path, clean=clean)

    def _state(self, status):
        self.manifest.update(status=status, updated_at=_now())
        temporary = self.path / 'manifest.tmp'
        temporary.write_text(json.dumps(self.manifest), encoding='utf-8')
        temporary.replace(self.path / 'manifest.json')

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
        with _lease(self.path):
            self.manifest = json.loads((self.path / 'manifest.json').read_text(encoding='utf-8'))
            if self.manifest['status'] != 'created':
                raise ValueError('Collection cannot be repeated')
            self._state('collecting')
            self._owner = get_ident()
            self._positions = set()  # Metadata only; never retains task payloads.
            try:
                with (self.path / 'results.jsonl').open('a', encoding='utf-8', newline='\n') as writer:
                    self._writer = writer
                    yield self
                if len(self._positions) != self.manifest['target_count']:
                    raise ValueError('Incomplete target outcomes')
                self.manifest['collection_complete'] = True
                self._state('collected')
            except BaseException:
                self._state('interrupted')
                raise
            finally:
                self._writer = None
                self._positions.clear()

    def append(self, outcome, *, payload=None, target='', failed=False):
        if self._writer is None or get_ident() != self._owner:
            raise RuntimeError('Only the collection owner may append')
        position = outcome.position
        if type(position) is not int or position in self._positions or not 1 <= position <= self.manifest['target_count']:
            raise ValueError('Duplicate or invalid input position')
        category = self.clean(outcome.error_category)
        record = dict(run_id=self.manifest['run_id'], input_position=position,
                      target=self.clean(target), status='failed' if failed or category else 'success',
                      completed_at=_now(), error_category=category,
                      payload=self._safe(outcome.value if payload is None else payload))
        self._writer.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + '\n')
        self._writer.flush()
        self._positions.add(position)
        self.manifest['completed_count'] += 1
        self.manifest['failed_count'] += record['status'] == 'failed'
        self._state('collecting')

    def records(self):
        """Input order via a bounded-cache disk index; JSONL remains authoritative."""
        with TemporaryDirectory(prefix='read-', dir=self.path) as temporary:
            with closing(sqlite3.connect(str(Path(temporary) / 'order.sqlite'))) as db:
                db.execute('PRAGMA cache_size = -512')
                db.execute('CREATE TABLE offsets (position INTEGER PRIMARY KEY, offset INTEGER)')
                with (self.path / 'results.jsonl').open('rb') as source:
                    while True:
                        offset = source.tell()
                        line = source.readline()
                        if not line:
                            break
                        if not line.endswith(b'\n'):
                            if self.manifest['collection_complete']:
                                raise ValueError('Truncated completed spool')
                            break  # A crash can leave an uncommitted final append.
                        record = json.loads(line)
                        if record['run_id'] != self.manifest['run_id']:
                            raise ValueError('Mismatched run identity')
                        db.execute('INSERT INTO offsets VALUES (?, ?)', (record['input_position'], offset))
                    db.commit()
                    count, minimum, maximum = db.execute('SELECT count(*), min(position), max(position) FROM offsets').fetchone()
                    if self.manifest['collection_complete'] and (count != self.manifest['target_count'] or (count and (minimum != 1 or maximum != count))):
                        raise ValueError('Incomplete persisted outcomes')
                    for (offset,) in db.execute('SELECT offset FROM offsets ORDER BY position'):
                        source.seek(offset)
                        yield json.loads(source.readline())

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
        with _lease(self.path):
            # Reload under the lease to prevent stale objects replaying lifecycle state.
            self.manifest = json.loads((self.path / 'manifest.json').read_text(encoding='utf-8'))
            if self.manifest.get('cleanup_started'):
                raise ValueError('Output already consumed; retained run permits cleanup only')
            complete = self.manifest['collection_complete']
            if not allow_partial and (not complete or self.manifest['status'] in {'created', 'collecting', 'interrupted'}):
                raise ValueError('Incomplete collection; explicitly request partial consumption')
            self._state('consuming')
            try:
                result = consumer(self)
            except BaseException:
                self._state('output_failed')
                raise
            self._state('consumed' if complete else 'partial_consumed')
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
