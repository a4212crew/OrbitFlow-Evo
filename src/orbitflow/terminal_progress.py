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
            self.closed = True
            # Never fabricate completed counts, even when the service returns.
            self._emit(self._line() + ('; phase finished.' if success else '; stopped; completion not established.'), True)


class ExecutionProgress(TerminalProgress):
    """Confirmed-apply events: fixed vocabulary, canonical targets, no payload echo."""
    STAGES = {
        'confirmed_start': 'Execution started', 'connect': 'Connecting',
        'identify': 'Identifying device', 'preflight': 'Initial preflight',
        'row_preflight': 'Row preflight', 'backup': 'Backup started',
        'backup_complete': 'Backup recorded', 'command_intent': 'Command intent (not success)',
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
            # Every event is a complete flushed line, serialized with timer updates.
            # Hostnames, commands, evidence, errors and arbitrary identifiers never cross.
            self._emit(' | '.join(parts), True)
            self.update(event.get('devices_completed', 0), event.get('devices_total'))
