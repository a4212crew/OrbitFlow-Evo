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
