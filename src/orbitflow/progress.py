"""Optional output-neutral progress; timer never accesses sessions or channels."""
from contextvars import ContextVar
from contextlib import contextmanager
from threading import Event, RLock, Thread
from time import monotonic

# Save exchanges publish fixed labels through the owning worker's context.
exchange_progress = ContextVar('execution_exchange_progress', default=None)


def save_progress(stage):
    callback = exchange_progress.get()
    if callback:
        callback(stage)


class Progress:
    """Serialized best-effort subscriber with bounded periodic waiting events.

    Subscriber receives only scalar presentation fields, never raw device evidence.
    Subscriber exceptions disable that subscriber; durable audit is independent.
    """
    def __init__(self, subscriber=None, *, interval=5.0, clock=monotonic):
        self.subscriber = subscriber
        self.interval = interval
        self.clock = clock
        self.started = clock()
        self.lock = RLock()
        self.active = {}
        self.correlation = {}
        self.stop = Event()
        self.thread = None
        self.rows_completed = self.devices_completed = 0

    def __enter__(self):
        if self.subscriber:
            self.thread = Thread(target=self._wait, name='configuration-progress', daemon=True)
            self.thread.start()
        return self

    def emit(self, ip, stage, *, hostname='', timeout=None, **fields):
        with self.lock:
            if stage == 'row_result':
                self.rows_completed += 1
            if stage == 'device_complete':
                self.devices_completed += 1
            item = dict(management_ip=ip, hostname=hostname, stage=stage,
                        elapsed_seconds=round(self.clock()-self.started, 1),
                        rows_completed=self.rows_completed, devices_completed=self.devices_completed, **self.correlation, **fields)
            if stage == 'confirmed_start':
                self.correlation.update({k: item[k] for k in ('rows_total', 'devices_total') if k in item})
            if timeout is not None:
                item['timeout_seconds'] = timeout
            if stage not in {'connect', 'identify', 'preflight', 'row_preflight', 'backup', 'command_intent', 'verification_intent', 'mode_intent', 'save_intent', 'save_confirmation_recognized', 'save_answer_y_waiting_original_exec', 'report_generation', 'cleanup_start'}:
                self.active.pop(ip, None)
            else:
                self.active[ip] = (self.clock(), item)
            self._deliver(item)

    def _deliver(self, item):
        if self.subscriber:
            try:
                self.subscriber(dict(item))
            except Exception:
                self.subscriber = None

    def tick(self):
        """Publish elapsed wait snapshots; also usable with a deterministic clock."""
        with self.lock:
            for start, item in list(self.active.values()):
                waited = self.clock()-start
                if waited < self.interval:
                    continue
                waiting = dict(item, stage='waiting', awaited_stage=item['stage'],
                               waiting_seconds=round(waited, 1), elapsed_seconds=round(self.clock()-self.started, 1),
                               rows_completed=self.rows_completed, devices_completed=self.devices_completed)
                if item.get('timeout_seconds') is not None:
                    waiting['remaining_seconds'] = max(0, round(item['timeout_seconds']-waited, 1))
                self._deliver(waiting)

    def _wait(self):
        while not self.stop.wait(self.interval):
            self.tick()

    @contextmanager
    def save_scope(self, ip, hostname, timeout, *, audit=None):
        started = self.clock()
        def report(stage):
            if audit:
                audit(stage)
            self.emit(ip, stage, hostname=hostname, timeout=max(0, timeout-(self.clock()-started)))
        token = exchange_progress.set(report)
        try:
            yield
        finally:
            exchange_progress.reset(token)

    def __exit__(self, *exc):
        self.stop.set()
        if self.thread:
            self.thread.join()
        self.active.clear()


def console_progress(event):
    """Compact CLI stages; timing/commands remain in events, output is flushed.

    Progress serializes delivery across workers and the waiting timer.
    """
    parts = [f"{event['management_ip']} {event['hostname']} [{event['stage']}]"]
    if event.get('source'):
        parts.append(event['source'])
    if event.get('command_index'):
        parts.append(f"command {event['command_index']}/{event.get('command_total', '?')}")
    for key in ('status', 'error_category'):
        if event.get(key):
            parts.append(f"{key}={event[key]}")
    if event['stage'] == 'verification_warning':
        parts.append('warning: see configuration logs and report details')
    print(' | '.join(parts), flush=True)
