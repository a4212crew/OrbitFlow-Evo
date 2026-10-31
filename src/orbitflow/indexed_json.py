"""Shared bounded SQLite JSON working set and canonical streaming encoding.

Scratch databases are disposable; published JSON and run spools remain the durable
sources of truth. Values are bounded individually, never by aggregate run size.
"""
from collections.abc import Mapping
import hashlib
import json
import re
from pathlib import Path
import sqlite3
import weakref
from tempfile import TemporaryDirectory
from threading import RLock

MAX_VALUE_BYTES = 64 * 1024 * 1024
MAX_WORKING_VALUE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024 * 1024


def chunks(value):
    """Yield the existing ASCII canonical JSON representation without joining it."""
    if isinstance(value, Mapping):
        yield '{'
        for i, key in enumerate(sorted(value)):
            if i:
                yield ','
            yield json.dumps(key, ensure_ascii=True)
            yield ':'
            yield from chunks(value[key])
        yield '}'
    elif isinstance(value, (list, tuple, IndexedList)):
        yield '['
        for i, item in enumerate(value):
            if i:
                yield ','
            yield from chunks(item)
        yield ']'
    else:
        yield from json.JSONEncoder(ensure_ascii=True, allow_nan=False,
                                    separators=(',', ':')).iterencode(value)


def digest(value):
    result = hashlib.sha256()
    for piece in chunks(value):
        result.update(piece.encode('ascii'))
    return result.hexdigest()


class IndexedJSON(Mapping):
    """Immutable key-addressable working set; at most one decoded value per read.

    Construction commits all values in one transaction. An unsuccessful build
    closes and removes scratch state. Call close() when no consumers remain.
    """
    def __init__(self, entries):
        self._scratch = TemporaryDirectory(prefix='orbitflow-json-')
        self._db = None
        self._finalizer = None
        self._lock = RLock()
        try:
            self._db = sqlite3.connect(str(Path(self._scratch.name) / 'values.sqlite'), check_same_thread=False)
            # Keep scratch alive until its connection is closed, including cyclic
            # GC. Independent TemporaryDirectory finalization can otherwise run
            # first and fail to unlink an open SQLite file on Windows.
            self._finalizer = weakref.finalize(self, self._release, self._db, self._scratch)
            self._db.execute('PRAGMA cache_size=-512')
            self._db.execute('PRAGMA temp_store=FILE')
            self._db.execute('CREATE TABLE entries (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            total = 0
            with self._db:
                for key, value in entries:
                    if type(key) is not str:
                        raise ValueError('JSON object key must be text')
                    # A device is the bounded processing unit. Serialization
                    # cannot exceed its record limit before allocating a join.
                    parts, size = [], 0
                    for part in chunks(value):
                        size += len(part)
                        if size > MAX_WORKING_VALUE_BYTES:
                            raise ValueError('Indexed JSON value size limit exceeded')
                        parts.append(part)
                    total += size
                    if total > MAX_TOTAL_BYTES:
                        raise ValueError('Indexed JSON disk limit exceeded')
                    self._db.execute('INSERT INTO entries VALUES (?, ?)', (key, ''.join(parts)))
        except BaseException:
            self.close()
            raise

    def __getitem__(self, key):
        with self._lock:
            row = self._db.execute('SELECT value FROM entries WHERE key=?', (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        return json.loads(row[0])

    def __iter__(self):
        for (key,) in self._db.execute('SELECT key FROM entries ORDER BY key'):
            yield key

    def __len__(self):
        with self._lock:
            return self._db.execute('SELECT count(*) FROM entries').fetchone()[0]

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None
        self._scratch.cleanup()
        if self._finalizer is not None:
            self._finalizer.detach()

    @staticmethod
    def _release(db, scratch):
        db.close()
        scratch.cleanup()


def read_json(stream, *, validate_observations=None, hash_results=False):
    """Read public JSON, indexing observation members as they are encountered.

    Reject duplicate keys, nonfinite numbers, excessive nesting, individual
    values and total input. No third-party parser or public format change.
    """
    decoder = json.JSONDecoder()
    owned = []
    buffer, position, consumed = '', 0, 0

    def fill():
        nonlocal buffer, position, consumed
        consumed += position
        buffer = buffer[position:] + stream.read(65536)
        position = 0
        if consumed + len(buffer) > MAX_TOTAL_BYTES:
            raise ValueError('JSON disk limit exceeded')

    def peek():
        nonlocal position
        while True:
            if position == len(buffer):
                fill()
                if not buffer:
                    return ''
            if buffer[position] not in ' \r\n\t':
                return buffer[position]
            position += 1

    def take(character):
        nonlocal position
        if peek() != character:
            raise ValueError('Invalid JSON structure')
        position += 1

    def scalar():
        nonlocal position
        first = peek()
        # Numeric raw_decode may accept a valid prefix such as 1 from a chunk
        # ending in 1.e or 1. Await the whole delimiter-terminated scalar token.
        if first != '"':
            while re.search(r'[ \r\n\t,\]}]', buffer[position:]) is None:
                old = len(buffer) - position
                if old >= MAX_WORKING_VALUE_BYTES:
                    raise ValueError('JSON scalar size limit exceeded')
                fill()
                if len(buffer) == old:
                    break
        while True:
            try:
                value, end = decoder.raw_decode(buffer, position)
                # A number may end at a chunk boundary. Wait for a delimiter.
                if end == len(buffer) and not isinstance(value, str):
                    old = len(buffer) - position
                    fill()
                    if len(buffer) > old:
                        continue
                    value, end = decoder.raw_decode(buffer, position)
                if not isinstance(value, (str, int, float, bool, type(None))):
                    raise ValueError('Invalid scalar')
                if isinstance(value, float) and not __import__('math').isfinite(value):
                    raise ValueError('Invalid JSON number')
                if end - position > MAX_WORKING_VALUE_BYTES:
                    raise ValueError('JSON scalar size limit exceeded')
                position = end
                return value
            except json.JSONDecodeError:
                if len(buffer) - position >= MAX_WORKING_VALUE_BYTES:
                    raise ValueError('JSON scalar size limit exceeded') from None
                old = len(buffer) - position
                fill()
                if len(buffer) == old:
                    raise ValueError('Invalid JSON scalar') from None

    def value(path=(), depth=0):
        nonlocal position
        if depth > 64:
            raise ValueError('JSON nesting limit exceeded')
        first = peek()
        container_start = consumed + position
        def bound():
            if (path and not (path[-1] in {'plan', 'observations'} and first == '{'
                             or path[-1] == 'results' and first == '[')
                    and consumed + position - container_start > MAX_WORKING_VALUE_BYTES):
                raise ValueError('JSON container size limit exceeded')
        if first == '{':
            take('{')
            def members():
                nonlocal position
                seen = set()
                if peek() == '}':
                    take('}')
                    return
                while True:
                    if peek() != '"':
                        raise ValueError('Invalid JSON key')
                    key = scalar()
                    if key in seen:
                        raise ValueError('Duplicate JSON field')
                    seen.add(key)
                    if len(seen) > 100000:
                        raise ValueError('JSON member limit exceeded')
                    take(':')
                    start = consumed + position
                    item = value(path + (key,), depth + 1)
                    if path and path[-1] == 'observations' and consumed + position - start > MAX_WORKING_VALUE_BYTES:
                        raise ValueError('JSON observation size limit exceeded')
                    bound()
                    yield key, item
                    if peek() == '}':
                        take('}')
                        return
                    take(',')
            if path in {('observations',), ('plan', 'observations')} and depth == len(path):
                indexed = IndexedJSON(validate_observations(members()) if validate_observations else members())
                owned.append(indexed)
                return indexed
            return dict(members())
        if first == '[':
            take('[')
            def elements():
                nonlocal position
                if peek() == ']':
                    take(']')
                    return
                count = 0
                while True:
                    if count >= 100000:
                        raise ValueError('JSON array limit exceeded')
                    item = value(path, depth + 1)
                    bound()
                    yield count, item
                    count += 1
                    if peek() == ']':
                        take(']')
                        return
                    take(',')
            if path in {('results',), ('plan', 'results')} and depth == len(path):
                indexed = HashedList(elements()) if hash_results else IndexedList(elements())
                owned.append(indexed)
                return indexed
            return [item for _, item in elements()]
        if first not in '"-0123456789tfn' or not first:
            raise ValueError('Invalid JSON value')
        return scalar()

    try:
        result = value()
        if peek():
            raise ValueError('Trailing JSON content')
        owned.clear()  # Transfer ownership; recursive parser closures retain no indexes.
        return result
    except BaseException:
        for resource in reversed(owned):
            close_json_resources(resource)
        raise


def close_json_resources(value):
    """Release owned indexed values without decoding their disk-backed contents."""
    if isinstance(value, IndexedJSON):
        value.close()
    elif isinstance(value, IndexedList):
        value.values.close()
    elif isinstance(value, HashedList):
        close_json_resources(value.hashes)
    elif isinstance(value, dict):
        for item in value.values():
            close_json_resources(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            close_json_resources(item)


class IndexedList:
    """Ordered JSON array backed by the same immutable SQLite working set."""
    def __init__(self, entries):
        self.values = IndexedJSON((f'{position:010d}', value) for position, value in entries)

    def __len__(self):
        return len(self.values)

    def __iter__(self):
        yield from self.values.values()

    def __getitem__(self, index):
        if index < 0:
            index += len(self)
        try:
            return self.values[f'{index:010d}']
        except KeyError:
            raise IndexError(index) from None

    def __eq__(self, other):
        if not hasattr(other, '__len__') or len(self) != len(other):
            return False
        return all(left == right for left, right in zip(self, other))


class HashedList:
    """Untrusted supplied results retained only as hashes until reevaluation.

    This prevents an altered artifact from persisting secret-bearing injected
    result strings to scratch SQLite before the immutable result check runs.
    """
    def __init__(self, entries):
        self.hashes = IndexedList((position, digest(value)) for position, value in entries)

    def matches(self, expected):
        return len(self.hashes) == len(expected) and all(
            supplied == digest(value) for supplied, value in zip(self.hashes, expected))


def read_bounded_text(path, *, max_bytes):
    """Read a small-contract JSON document with a byte bound before decoding.

    Binary bounded read also protects against a file growing after a stat check.
    Large observation artifacts instead use read_json and indexed working sets.
    """
    with Path(path).open('rb') as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError('JSON input size limit exceeded')
    return raw.decode('utf-8')
