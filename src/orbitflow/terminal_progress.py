"""Console-only terminal rendering; no device or execution authority."""
import sys
from threading import RLock
from time import monotonic


class QuietOutput:
    """Discard service stage text while module logs retain diagnostics."""
    def write(self, text):
        return len(text)

    def flush(self):
        pass


class TerminalProgress:
    """Measured durable outcomes or indeterminate activity, with bounded output."""
    def __init__(self, label, *, write=print, total=None, clock=monotonic):
        self.label, self.write, self.total, self.clock = label, write, total, clock
        self.done = 0
        self.started = self.last = clock()
        self.frame = 0
        self.lock = RLock()
        self.tty = write is print and sys.stdout.isatty()
        self.closed = False

    def _emit(self, text, final=False):
        try:
            if self.tty:
                print('\r' + text + '\x1b[K', end='\n' if final else '', flush=True)
            elif self.write is print:
                print(text, flush=True)
            else:
                self.write(text)
        except Exception:
            pass  # Optional presentation must never alter durable work.

    def _line(self):
        elapsed = int(self.clock() - self.started)
        if type(self.total) is int and self.total > 0:
            cells = self.done * 20 // self.total
            return (f'{self.label} [{"#" * cells}{"-" * (20-cells)}] '
                    f'{self.done * 100 // self.total}% ({self.done}/{self.total}) {elapsed}s elapsed')
        start = self.frame % 18
        return f'{self.label} [{"." * start}###{"." * (17-start)}] {elapsed}s elapsed'

    def start(self):
        with self.lock:
            self._emit(self._line())

    def update(self, done, total):
        with self.lock:
            if self.closed or type(total) is not int or total <= 0 or type(done) is not int or not 0 <= done <= total:
                return
            self.done, self.total = done, total
            self.tick()

    def tick(self):
        with self.lock:
            if self.closed:
                return
            self.frame += 1
            now = self.clock()
            if self.tty or now - self.last >= 5:
                self._emit(self._line())
                self.last = now

    def finish(self, success):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            # Never fabricate completed counts, even when the service returns.
            self._emit(self._line() + ('; phase finished.' if success else '; stopped; completion not established.'), True)


class ExecutionProgress(TerminalProgress):
    """Confirmed-apply events: fixed vocabulary, canonical targets, no payload echo."""
    STAGES = {
        'confirmed_start': 'Execution started', 'connect': 'Connecting',
        'identify': 'Identifying device', 'preflight': 'Initial preflight',
        'row_preflight': 'Row preflight', 'backup': 'Backup started',
        'backup_complete': 'Backup recorded', 'command_intent': 'Command preparation',
        'command_result': 'Command result', 'command_unknown': 'Command outcome Unknown',
        'mode_intent': 'Mode transition intent', 'mode_result': 'Mode transition returned',
        'verification_intent': 'Verification started', 'verification_warning': 'Verification warning; see report',
        'row_result': 'Row result', 'save_intent': 'Save started', 'save_result': 'Save result',
        'save_confirmation_recognized': 'Save confirmation recognized',
        'save_answer_y_waiting_original_exec': 'Waiting for save completion',
        'cleanup_start': 'Cleanup started', 'cleanup': 'Cleanup result',
        'device_failure': 'Device failure; see retained evidence', 'device_complete': 'Device completion',
        'confirm': 'Confirmation claimed', 'recording': 'Recording result',
    }
    STATUSES = {'Verified', 'Failed', 'Unknown', 'Completed', 'Rejected', 'Skipped', 'Claimed',
                'Accepted', 'Returned', 'Not executed', 'Not attempted', 'Saved'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dashboard = WorkflowProgress(self.label, total=self.total, clock=self.clock) if self.write is print else None

    def start(self):
        if self.dashboard:
            self.dashboard.structured = True
            self.context_token = current_display.set(self.dashboard)
            self.dashboard.start()
        else:
            super().start()

    def tick(self):
        if self.dashboard:
            self.dashboard.tick()
        else:
            super().tick()

    def finish(self, success):
        if self.dashboard:
            self.dashboard.finish(success)
            for path in sorted(self.dashboard.resources):
                location('Log', path)
            if hasattr(self, 'context_token'):
                current_display.reset(self.context_token)
                del self.context_token
            self.closed = True
        else:
            super().finish(success)

    def event(self, event):
        from ipaddress import ip_address
        import re
        from orbitflow.configuration.v2.catalogue import BY_ID
        with self.lock:
            if self.closed:
                return
            stage = event.get('stage')
            waiting = stage == 'waiting'
            label = self.STAGES.get(event.get('awaited_stage') if waiting else stage)
            if label is None:
                return
            try:
                raw = event.get('management_ip', '')
                target = str(ip_address(raw)) if isinstance(raw, str) and '%' not in raw else 'target unavailable'
            except ValueError:
                target = 'target unavailable'
            parts = [target, ('Waiting: ' if waiting else '') + label]
            source = event.get('source')
            if isinstance(source, str):
                for template in BY_ID.values():
                    match = re.fullmatch(re.escape(template.sheet) + r' row ([0-9]{1,7})', source)
                    if match:
                        parts.append(f'{template.sheet} row {match[1]}')
                        break
            index, total = event.get('command_index'), event.get('command_total')
            if all(isinstance(x, (int, str)) and re.fullmatch(r'[0-9]{1,7}', str(x)) for x in (index, total)):
                parts.append(f'command {index}/{total}')
            status = event.get('status')
            if isinstance(status, str) and status in self.STATUSES:
                parts.append('status=' + status)
            if waiting:
                seconds = event.get('waiting_seconds')
                if type(seconds) in (int, float) and 0 <= seconds <= 10**9:
                    parts.append(f'{int(seconds)}s waiting')
            # Only allowlisted fields reach either dashboard or compact subscribers.
            # Hostnames, commands, evidence, errors and arbitrary identifiers never cross.
            if self.dashboard:
                total = event.get('devices_total')
                if type(total) is int and total >= 0:
                    self.dashboard.total = total
                if status == 'Unknown' or stage == 'command_unknown':
                    self.dashboard.unknown_targets.add(target)
                if stage == 'device_complete':
                    self.dashboard.returned(target)
                    if not self.dashboard.durable:
                        self.dashboard.outcome(target, True if status == 'Failed' else False if status in {'Completed', 'Verified'} else None)
                elif target != 'target unavailable':
                    self.dashboard.worker(target, ' | '.join(parts[1:]))
                return
            self._emit(' | '.join(parts), True)
            self.update(event.get('devices_completed', 0), event.get('devices_total'))

# Presentation context follows the shared runner's copy_context into each worker.
from collections import deque
from contextvars import ContextVar
from contextlib import contextmanager
import os
import shutil

current_display = ContextVar('terminal_display', default=None)
current_position = ContextVar('terminal_position', default=None)


class WorkflowProgress(TerminalProgress):
    """Bounded dashboard. Counts are supplied by the owner of the named phase.

    Worker returns mean processing finished, not successful collection or export.
    Only fixed stage labels, canonical addresses and input positions cross this boundary.
    """
    STAGES = ('input', 'connect', 'inventory', 'identify', 'interface', 'vlan',
              'collect', 'normalize', 'evaluate', 'backup', 'capture', 'write',
              'preflight', 'verification', 'save', 'cleanup', 'recording')

    def __init__(self, label, **kwargs):
        super().__init__(label, **kwargs)
        self.active = {}
        self.slots = {}
        self.identities = {}
        self.recent = deque(maxlen=10)
        self.workers = 1
        self.height = 0
        self.completed_positions = set()
        self.success = self.failure = 0
        self.enabled = True
        self.durable = False
        self.structured = False
        self.resources = set()
        self.unknown_targets = set()

    def _emit(self, text, final=False):
        # Full ANSI frames require enough space and a capable terminal. Windows
        # consoles without VT support use carriage-return-only compact output.
        from orbitflow.logging import sanitize_text
        import re
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', sanitize_text(text))
        size = shutil.get_terminal_size((80, 24))
        full = (self.tty and size.columns >= 70 and size.lines >= self.workers + 14
                and os.environ.get('TERM') != 'dumb'
                and (os.name != 'nt' or bool(os.environ.get('WT_SESSION') or os.environ.get('ANSICON'))))
        try:
            if final and self.tty:
                if self.height:
                    sys.stdout.write(f'\x1b[{self.height}A' + ('\r\x1b[K\n' * self.height) + f'\x1b[{self.height}A')
                    self.height = 0
                sys.stdout.write(text + '\n')
                sys.stdout.flush()
            elif full:
                rows = [text]
                slots = {self.slots[p]: (p, stage) for p, stage in self.active.items()}
                for slot in range(self.workers):
                    if slot in slots:
                        position, stage = slots[slot]
                        rows.append(f'Worker {slot+1}: {self.identity(position)} | {stage} | active')
                    else:
                        rows.append(f'Worker {slot+1}: idle')
                rows += ['Recent activity (last 10):'] + list(self.recent)
                rows += [''] * (self.workers + 12 - len(rows))
                prefix = f'\x1b[{self.height}A' if self.height else ''
                sys.stdout.write(prefix + ''.join('\r' + row[:size.columns-1] + '\x1b[K\n' for row in rows))
                sys.stdout.flush()
                self.height = 0 if final else len(rows)
            elif self.tty:
                if self.height:
                    sys.stdout.write(f'\x1b[{self.height}A' + ('\r\x1b[K\n' * self.height) + f'\x1b[{self.height}A')
                    self.height = 0
                compact = text[:max(1, size.columns-1)]
                sys.stdout.write('\r' + compact.ljust(max(1, size.columns-1)) + ('\n' if final else ''))
                sys.stdout.flush()
            else:
                super()._emit(text, final)
        except Exception:
            pass

    def tick(self):
        with self.lock:
            if self.closed:
                return
            now = self.clock()
            if now - self.last >= (0.1 if self.tty else 5):
                self.frame += 1
                self._emit(self._line())
                self.last = now

    def identity(self, position):
        return self.identities.get(position, f'input {position}')

    def assign(self, position, target):
        from ipaddress import ip_address
        if isinstance(target, tuple) and len(target) == 2:
            target = target[1]
        raw = target.get('management_ip') if isinstance(target, dict) else target
        try:
            address = str(ip_address(raw)) if isinstance(raw, str) and '%' not in raw else None
        except ValueError:
            address = None
        if address:
            with self.lock:
                self.identities[position] = f'input {position} ({address})'

    def worker(self, position, stage):
        with self.lock:
            if self.closed:
                return
            if position not in self.slots:
                used = {self.slots[p] for p in self.active}
                self.slots[position] = next((n for n in range(self.workers) if n not in used), 0)
            self.active[position] = stage
            self.recent.append(f'{self.identity(position)} | {stage}')
            self.tick()

    def returned(self, position):
        with self.lock:
            self.active.pop(position, None)
            self.slots.pop(position, None)
            self.recent.append(f'{self.identity(position)} | processing returned; outcome pending')
            self.tick()

    def outcome(self, position, failed=None):
        with self.lock:
            if position in self.completed_positions:
                return
            self.completed_positions.add(position)
            self.success += failed is False
            self.failure += failed is True
            self.done = len(self.completed_positions)
            self.recent.append(f'{self.identity(position)} | ' + ('failed' if failed else 'recorded' if failed is False else 'processed'))
            self.identities.pop(position, None)
            self.tick()

    def finish(self, success):
        with self.lock:
            if self.closed:
                return
            self.active.clear()
            self.slots.clear()
            super().finish(success)

    def _line(self):
        count = f'{self.done}/{self.total}' if type(self.total) is int else f'{self.done}/unknown'
        prefix = f'{self.label} [{count}]' if self.write is print else super()._line()
        unknown = max(0, (self.total if self.closed and type(self.total) is int else self.done)-self.success-self.failure)
        return (f'{prefix} | success={self.success} failed={self.failure} '
                f'active={len(self.active)} unknown={unknown} | {int(self.clock()-self.started)}s elapsed')


@contextmanager
def workflow_progress(label, *, total=None, durable=False, quiet=False):
    """Reuse an owning display; always close local presentation on interruption."""
    existing = current_display.get()
    if existing is not None and not existing.closed:
        if durable:
            existing.durable = True
            existing.total = total
            if not existing.structured:
                existing.label = label
        yield existing
        return
    display = WorkflowProgress(label, total=total, **({"write": lambda text: None} if quiet else {}))
    display.durable = durable
    display.enabled = not quiet
    token = current_display.set(display)
    display.start()
    from orbitflow.progress import Progress
    timer = None
    if not quiet:
        try:
            timer = Progress(lambda event: display.tick())
            timer.__enter__()
            timer.emit('', 'preflight')
        except Exception:
            timer = None
    try:
        yield display
    except BaseException:
        display.finish(False)
        raise
    else:
        display.finish(True)
    finally:
        if timer is not None:
            timer.__exit__(None, None, None)
        for path in sorted(display.resources):
            location('Log', path)
        current_display.reset(token)


def cli_progress(label):
    """Opt CLI entry points into presentation; library APIs keep output ownership."""
    from functools import wraps
    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            argv = kwargs.get('argv', args[0] if args else None)
            argv = sys.argv[1:] if argv is None else argv
            if '--help' in argv or '-h' in argv:
                return function(*args, **kwargs)
            with workflow_progress(label) as display:
                result = function(*args, **kwargs)
                from pathlib import Path
                try:
                    exists = isinstance(result, Path) and result.exists()
                except OSError:
                    exists = False
                if exists:
                    display.finish(True)
                    location('Saved output', result)
                return result
        return run
    return decorate


def location(label, path):
    """Print an existing application-owned path, without terminal control codes."""
    from orbitflow.logging import sanitize_text
    import re
    display = current_display.get()
    if display is not None:
        text = sanitize_text(str(path))
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        display._emit(label + ': ' + text, True)


def worker_stage(stage):
    """Fixed stage update from the current owning worker; no evidence payload."""
    display, position = current_display.get(), current_position.get()
    if display is not None and position is not None and stage in WorkflowProgress.STAGES:
        display.worker(position, stage)
