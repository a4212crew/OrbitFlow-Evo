"""Bounded per-device scheduling; workers own and clean up their device resources."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextvars import copy_context
from dataclasses import dataclass
from threading import Lock

from orbitflow.config import load_execution_config
from orbitflow.transport.policy import (
    ConnectionStartPacer, connection_pacer, connection_retry_delay,
)


@dataclass(frozen=True)
class DeviceOutcome:
    position: int
    value: object = None
    error_category: str = ""


class Progress:
    """Serialize complete progress messages without serializing device work."""
    def __init__(self, output):
        self.output = output
        self._lock = Lock()

    def __call__(self, message):
        from orbitflow.terminal_progress import current_display, current_position, WorkflowProgress
        display, position = current_display.get(), current_position.get()
        if display is not None and display.enabled and not display.closed:
            # Never echo arbitrary caller text into a dashboard.
            import re
            import sys
            from orbitflow.terminal_progress import QuietOutput
            words = set(re.findall(r'[a-z]+', str(message).lower()))
            words.update({'connecting': 'connect', 'interfaces': 'interface', 'vlans': 'vlan', 'evaluated': 'evaluate'}[word]
                         for word in tuple(words) if word in {'connecting', 'interfaces', 'vlans', 'evaluated'})
            stage = next((stage for stage in WorkflowProgress.STAGES if stage in words), 'processing')
            if position is not None:
                display.worker(position, stage)
            else:
                with display.lock:
                    display.recent.append('Workflow | ' + stage)
                    display.tick()
            if self.output is sys.stdout or isinstance(self.output, QuietOutput):
                return
        with self._lock:
            print(message, file=self.output, flush=True)


def _execute_devices(targets, worker, *, config=None, on_outcome=None):
    """Return input-ordered outcomes with bounded submissions and dynamic refill.

    With on_outcome, deliver completions on the caller and return an empty list;
    only bounded in-flight results are retained. Sink failures abort scheduling.
    They propagate unchanged, without sink retry or conversion to DeviceOutcome.
    In-flight workers finish cleanup; undelivered results are not committed.

    Exception objects/text and targets (which may contain credentials) are never
    retained in failure outcomes. Context variables, including the log root,
    are copied separately into each invocation. Limit 1 runs on the caller.
    """
    config = config if config is not None else load_execution_config()
    pacer = ConnectionStartPacer(config.connection_start_interval)
    from orbitflow.terminal_progress import current_display, current_position
    display = current_display.get()
    display.workers = config.max_concurrent_devices
    if display.total is None and hasattr(targets, '__len__'):
        display.total = len(targets)
    def invoke(position, target):
        presentation_token = current_position.set(position)
        if not display.structured:
            display.assign(position, target)
            display.worker(position, 'processing')
        token = connection_pacer.set(pacer)
        retry_token = connection_retry_delay.set(config.connection_retry_delay)
        try:
            return DeviceOutcome(position, worker(target))
        except Exception as exc:
            return DeviceOutcome(position, error_category=type(exc).__name__)
        finally:
            if not display.structured:
                display.returned(position)
            current_position.reset(presentation_token)
            connection_retry_delay.reset(retry_token)
            connection_pacer.reset(token)

    outcomes = []
    def deliver(outcome):
        if on_outcome is None:
            outcomes.append(outcome)
        else:
            on_outcome(outcome)
        if not display.durable:
            display.outcome(outcome.position, True if outcome.error_category else None)

    indexed = iter(enumerate(targets, 1))
    if config.max_concurrent_devices == 1:
        for position, target in indexed:
            deliver(copy_context().run(invoke, position, target))
        return outcomes
    with ThreadPoolExecutor(max_workers=config.max_concurrent_devices,
                            thread_name_prefix="orbitflow-device") as executor:
        pending = set()
        def refill():
            while len(pending) < config.max_concurrent_devices:
                try:
                    position, target = next(indexed)
                except StopIteration:
                    break
                pending.add(executor.submit(copy_context().run, invoke, position, target))
        refill()
        while pending:
            completed, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                deliver(future.result())
            completed.clear()
            del future
            refill()
    return sorted(outcomes, key=lambda outcome: outcome.position)


def execute_devices(targets, worker, *, config=None, on_outcome=None):
    """Run bounded device work with best-effort, output-neutral presentation.

    Processing counts do not establish durable collection or export success.
    Existing callback, ordering, concurrency and failure contracts are unchanged.
    """
    from orbitflow.terminal_progress import workflow_progress, current_display
    total = len(targets) if hasattr(targets, '__len__') else None
    with workflow_progress('Device processing', total=total, quiet=current_display.get() is None):
        return _execute_devices(targets, worker, config=config, on_outcome=on_outcome)
