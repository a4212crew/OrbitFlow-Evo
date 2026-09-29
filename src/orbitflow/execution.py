"""Bounded per-device scheduling; workers own and clean up their device resources."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextvars import copy_context
from dataclasses import dataclass
from threading import Lock

from orbitflow.config import load_execution_config


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
        with self._lock:
            print(message, file=self.output, flush=True)


def execute_devices(targets, worker, *, config=None):
    """Return input-ordered outcomes with bounded submissions and dynamic refill.

    Exception objects/text and targets (which may contain credentials) are never
    retained in failure outcomes. Context variables, including the log root,
    are copied separately into each invocation. Limit 1 runs on the caller.
    """
    config = config if config is not None else load_execution_config()
    def invoke(position, target):
        try:
            return DeviceOutcome(position, worker(target))
        except Exception as exc:
            return DeviceOutcome(position, error_category=type(exc).__name__)

    indexed = iter(enumerate(targets, 1))
    if config.max_concurrent_devices == 1:
        return [copy_context().run(invoke, position, target) for position, target in indexed]
    outcomes = []
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
            outcomes.extend(future.result() for future in completed)
            refill()
    return sorted(outcomes, key=lambda outcome: outcome.position)
